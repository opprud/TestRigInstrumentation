/*
  RP2040 (Arduino core) – HX711 + Tacho + Lightweight ASCII Protocol
  + EEPROM-backed calibration persistence (flash emulation)

  Commands (host → device; CRLF-terminated):
    PING
    INFO
    LOAD?
    TARE
    SPEED?
    SETTIME <unix_ms>
    SETCAL <slope_g_per_count> <tare_offset>   (persists)
    CAL?                                       (reads persisted/current cal)
    RESETCAL                                   (restore defaults, persist)
    SETPPR <pulses_per_rev>
    PPR?

  Responses (device → host; CRLF-terminated):
    OK PONG
    OK INFO vendor=... device=RP2040 fw=1.1.0
    OK LOAD mass_g=<float> raw=<int> ts=<unix_ms>
    OK TARE
    OK SPEED rpm=<float> period_ms=<float> pulses=<uint32> ts=<unix_ms>
    OK SETTIME
    OK SETCAL
    OK CAL slope=<float> tare=<int>
    OK RESETCAL
    OK SETPPR
    OK PPR ppr=<int>
    ERR <code> <message>
*/

#include <Arduino.h>
#include "HX711.h"
#include <EEPROM.h>

// If compiling on non-ESP, IRAM_ATTR may be undefined; make it a no-op.
#ifndef IRAM_ATTR
#define IRAM_ATTR
#endif

// ---------------------- USER CONFIG ----------------------

// HX711 wiring (adjust to your hardware)
const int HX711_DOUT_PIN = 4;    
const int HX711_SCK_PIN  = 2;    

// Tachometer input pin (adjust)
const int TACH_PIN = 0;
const bool TACH_USE_PULLUP = true;

// Tach pulses per one shaft revolution
volatile uint32_t PULSES_PER_REV = 1; // set via SETPPR <n>

// Serial
const unsigned long SERIAL_BAUD = 115200;

// HX711 behavior
const unsigned long HX711_READ_TIMEOUT_MS = 200;

// Firmware info
const char* FW_VENDOR  = "ForecverBearing";
const char* FW_DEVICE  = "RP2040";
const char* FW_VERSION = "1.0.1";  

// ---------------------- CALIBRATION (RAM) ----------------------
// Live calibration variables used during measurement
volatile float g_per_count = 0.0020f; // default slope (grams per count) – adjust for your sensor
volatile long  tare_offset = 0;       // default tare

// ---------------------- EEPROM PERSISTENCE ----------------------
// We store a small struct with magic, version, CRC, and fields.
// Layout: [magic][version][slope][tare][crc]
struct CalRecord {
  uint32_t magic;    // 'CAL1' = 0x43414C31
  uint32_t version;  // structure/layout version
  float    slope;    // grams per count
  int32_t  tare;     // raw tare offset
  uint32_t crc;      // CRC32 over (magic, version, slope, tare)
};

static const uint32_t CAL_MAGIC   = 0x43414C31; // 'CAL1'
static const uint32_t CAL_VERSION = 0x00010000; // v1
static const size_t   EEPROM_SIZE = 64;         // a single small page is enough

// Simple CRC32 (polynomial 0xEDB88320), byte-wise
uint32_t crc32_update(uint32_t crc, uint8_t data) {
  crc = crc ^ data;
  for (int i = 0; i < 8; ++i) {
    uint32_t mask = -(crc & 1u);
    crc = (crc >> 1) ^ (0xEDB88320u & mask);
  }
  return crc;
}

uint32_t crc32_span(const uint8_t* data, size_t len) {
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < len; ++i) {
    crc = crc32_update(crc, data[i]);
  }
  return ~crc;
}

void saveCalibrationToEEPROM(float slope, long tare) {
  CalRecord rec;
  rec.magic   = CAL_MAGIC;
  rec.version = CAL_VERSION;
  rec.slope   = slope;
  rec.tare    = (int32_t)tare;

  // compute CRC over first 16 bytes (magic, version, slope, tare)
  rec.crc = crc32_span(reinterpret_cast<const uint8_t*>(&rec), sizeof(CalRecord) - sizeof(uint32_t));

  EEPROM.begin(EEPROM_SIZE);
  EEPROM.put(0, rec);
  EEPROM.commit();   
}

bool loadCalibrationFromEEPROM(float &slope, long &tare) {
  CalRecord rec;
  EEPROM.begin(EEPROM_SIZE);
  EEPROM.get(0, rec);

  if (rec.magic != CAL_MAGIC || rec.version != CAL_VERSION) {
    return false;
  }
  uint32_t calc_crc = crc32_span(reinterpret_cast<const uint8_t*>(&rec), sizeof(CalRecord) - sizeof(uint32_t));
  if (calc_crc != rec.crc) {
    return false;
  }
  slope = rec.slope;
  tare  = rec.tare;
  return true;
}

void resetCalibrationToDefaultsAndPersist() {
  float defSlope = 0.0020f;
  long  defTare  = 0;
  noInterrupts();
  g_per_count = defSlope;
  tare_offset = defTare;
  interrupts();
  saveCalibrationToEEPROM(defSlope, defTare);
}

// ---------------------- TIMING / TACH ----------------------
HX711 hx;
volatile uint32_t tach_pulses_total = 0;
volatile uint32_t last_edge_us = 0;
volatile uint32_t last_period_us = 0;

// UNIX ms epoch base (set by SETTIME)
volatile uint64_t epoch_base_ms = 0; // 0 until set

static inline uint64_t now_unix_ms() {
  noInterrupts();
  uint64_t base = epoch_base_ms;
  interrupts();
  return base + (uint64_t)millis();
}

static inline float us_to_ms(uint32_t us) { return (float)us / 1000.0f; }

struct TachSnapshot {
  uint32_t pulses_total;
  uint32_t last_period_us;
};

static inline TachSnapshot tach_snapshot() {
  TachSnapshot s;
  noInterrupts();
  s.pulses_total = tach_pulses_total;
  s.last_period_us = last_period_us;
  interrupts();
  return s;
}

static inline float compute_rpm(const TachSnapshot& s) {
  if (s.last_period_us == 0 || PULSES_PER_REV == 0) return 0.0f;
  float period_s = (float)s.last_period_us / 1e6f;
  if (period_s <= 0.0f) return 0.0f;
  float rps = (1.0f / period_s) / (float)PULSES_PER_REV;
  return 60.0f * rps;
}

void IRAM_ATTR tach_isr() {
  uint32_t now = micros();
  uint32_t prev = last_edge_us;
  last_edge_us = now;
  tach_pulses_total++;
  if (prev != 0) {
    uint32_t dt = now - prev;
    if (dt > 100) {  // small glitch reject
      last_period_us = dt;
    }
  }
}

// ---------------------- HX711 helpers ----------------------
bool hx_read_blocking(long& raw) {
  unsigned long t0 = millis();
  while (!hx.is_ready()) {
    if (millis() - t0 > HX711_READ_TIMEOUT_MS) return false;
    delay(1);
  }
  raw = hx.read();
  return true;
}

// ---------------------- protocol helpers ----------------------
static inline void rstrip(char* s) {
  size_t n = strlen(s);
  while (n && (s[n-1] == '\r' || s[n-1] == '\n' || s[n-1] == ' ' || s[n-1] == '\t')) {
    s[--n] = '\0';
  }
}
static inline void lstrip(char* s) {
  size_t n = strlen(s);
  size_t i = 0;
  while (i < n && (s[i] == ' ' || s[i] == '\t')) i++;
  if (i) memmove(s, s + i, n - i + 1);
}
static inline bool streqi(const char* a, const char* b) {
  while (*a && *b) {
    char ca = (*a >= 'a' && *a <= 'z') ? (*a - 32) : *a;
    char cb = (*b >= 'a' && *b <= 'z') ? (*b - 32) : *b;
    if (ca != cb) return false;
    ++a; ++b;
  }
  return *a == '\0' && *b == '\0';
}

// ---------------------- commands ----------------------
void cmd_ping() { Serial.print("OK PONG\r\n"); }

void cmd_info() {
  Serial.print("OK INFO ");
  Serial.print("vendor="); Serial.print(FW_VENDOR);
  Serial.print(" device="); Serial.print(FW_DEVICE);
  Serial.print(" fw=");     Serial.print(FW_VERSION);
  Serial.print("\r\n");
}

void cmd_load() {
  long raw;
  if (!hx_read_blocking(raw)) { Serial.print("ERR 20 HX711_timeout\r\n"); return; }

  long tare; float slope;
  noInterrupts();
  tare  = tare_offset;
  slope = g_per_count;
  interrupts();

  float mass_g = (float)(raw - tare) * slope;
  uint64_t ts  = now_unix_ms();

  Serial.print("OK LOAD ");
  Serial.print("mass_g="); Serial.print(mass_g, 3);
  Serial.print(" raw=");    Serial.print(raw);
  Serial.print(" ts=");     Serial.print(ts);
  Serial.print("\r\n");
}

void cmd_tare() {
  long raw;
  if (!hx_read_blocking(raw)) { Serial.print("ERR 20 HX711_timeout\r\n"); return; }
  noInterrupts();
  tare_offset = raw;
  float slope = g_per_count;  // unchanged
  interrupts();
  // Persist new tare with current slope
  saveCalibrationToEEPROM(slope, raw);
  Serial.print("OK TARE\r\n");
}

void cmd_speed() {
  TachSnapshot s = tach_snapshot();
  float rpm = compute_rpm(s);
  float period_ms = (s.last_period_us == 0) ? 0.0f : us_to_ms(s.last_period_us);
  uint64_t ts = now_unix_ms();

  Serial.print("OK SPEED ");
  Serial.print("rpm=");       Serial.print(rpm, 2);
  Serial.print(" period_ms=");Serial.print(period_ms, 3);
  Serial.print(" pulses=");   Serial.print(s.pulses_total);
  Serial.print(" ts=");       Serial.print(ts);
  Serial.print("\r\n");
}

void cmd_settime(char* args) {
  char* tok = strtok(args, " \t");
  if (!tok) { Serial.print("ERR 30 missing_unix_ms\r\n"); return; }
  uint64_t v = strtoull(tok, nullptr, 10);
  noInterrupts();
  epoch_base_ms = v - (uint64_t)millis();
  interrupts();
  Serial.print("OK SETTIME\r\n");
}

void cmd_setcal(char* args) {
  // SETCAL <slope_g_per_count> <tare_offset>
  char* a = strtok(args, " \t");
  char* b = strtok(nullptr, " \t");
  if (!a || !b) { Serial.print("ERR 31 missing_args\r\n"); return; }
  float slope = atof(a);
  long  tare  = atol(b);
  noInterrupts();
  g_per_count = slope;
  tare_offset = tare;
  interrupts();
  // persist immediately
  saveCalibrationToEEPROM(slope, tare);
  Serial.print("OK SETCAL\r\n");
}

void cmd_calq() {
  float slope; long tare;
  noInterrupts();
  slope = g_per_count;
  tare  = tare_offset;
  interrupts();
  Serial.print("OK CAL ");
  Serial.print("slope="); Serial.print(slope, 9);
  Serial.print(" tare=");  Serial.print(tare);
  Serial.print("\r\n");
}

void cmd_resetcal() {
  resetCalibrationToDefaultsAndPersist();
  Serial.print("OK RESETCAL\r\n");
}

void cmd_setppr(char* args) {
  char* a = strtok(args, " \t");
  if (!a) { Serial.print("ERR 32 missing_ppr\r\n"); return; }
  uint32_t ppr = strtoul(a, nullptr, 10);
  if (ppr == 0) { Serial.print("ERR 33 invalid_ppr\r\n"); return; }
  noInterrupts();
  PULSES_PER_REV = ppr;
  interrupts();
  Serial.print("OK SETPPR\r\n");
}

void cmd_pprq() {
  uint32_t ppr;
  noInterrupts();
  ppr = PULSES_PER_REV;
  interrupts();
  Serial.print("OK PPR ");
  Serial.print("ppr="); Serial.print(ppr);
  Serial.print("\r\n");
}

// ---------------------- parser ----------------------
void handle_line(char* line) {
  // trim
  size_t n = strlen(line);
  while (n && (line[n-1] == '\r' || line[n-1] == '\n')) line[--n] = '\0';
  while (*line == ' ' || *line == '\t') ++line;
  if (*line == '\0') return;

  char* cmd  = strtok(line, " \t");
  char* args = strtok(nullptr, ""); // may be null

  if (streqi(cmd, "PING"))          { cmd_ping(); }
  else if (streqi(cmd, "INFO"))     { cmd_info(); }
  else if (streqi(cmd, "LOAD?"))    { cmd_load(); }
  else if (streqi(cmd, "TARE"))     { cmd_tare(); }
  else if (streqi(cmd, "SPEED?"))   { cmd_speed(); }
  else if (streqi(cmd, "SETTIME"))  { cmd_settime(args ? args : (char*)""); }
  else if (streqi(cmd, "SETCAL"))   { cmd_setcal(args ? args : (char*)""); }
  else if (streqi(cmd, "CAL?"))     { cmd_calq(); }
  else if (streqi(cmd, "RESETCAL")) { cmd_resetcal(); }
  else if (streqi(cmd, "SETPPR"))   { cmd_setppr(args ? args : (char*)""); }
  else if (streqi(cmd, "PPR?"))     { cmd_pprq(); }
  else { Serial.print("ERR 10 unknown_command\r\n"); }
}

// ---------------------- setup/loop ----------------------
void setup() {
  Serial.begin(SERIAL_BAUD);
  while (!Serial) { delay(10); }

  // Load calibration from EEPROM (or defaults if invalid)
  float s; long t;
  if (loadCalibrationFromEEPROM(s, t)) {
    noInterrupts();
    g_per_count = s;
    tare_offset = t;
    interrupts();
  } else {
    // persist defaults so CAL? always returns something valid
    resetCalibrationToDefaultsAndPersist();
  }

  // HX711
  hx.begin(HX711_DOUT_PIN, HX711_SCK_PIN);
  // hx.set_gain(128); // default

  // Tach
  if (TACH_USE_PULLUP) pinMode(TACH_PIN, INPUT_PULLUP);
  else                 pinMode(TACH_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(TACH_PIN), tach_isr, RISING);

  // Banner
  Serial.print("OK READY vendor="); Serial.print(FW_VENDOR);
  Serial.print(" device=");        Serial.print(FW_DEVICE);
  Serial.print(" fw=");            Serial.print(FW_VERSION);
  Serial.print("\r\n");
}

void loop() {
  static char linebuf[128];
  static size_t idx = 0;

  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      linebuf[idx] = '\0';
      handle_line(linebuf);
      idx = 0;
    } else {
      if (idx < sizeof(linebuf) - 1) {
        linebuf[idx++] = c;
      } else {
        idx = 0;
        Serial.print("ERR 11 line_too_long\r\n");
      }
    }
  }
}