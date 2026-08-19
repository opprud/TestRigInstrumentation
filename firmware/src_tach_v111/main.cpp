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
    SETGAIN <64|128>                           (NEW – persists, reconfigures HX711)
    GAIN?                                      (NEW)
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
    OK SETGAIN
    OK GAIN gain=<int>
    ERR <code> <message>
*/
#include <Arduino.h>
#include "HX711.h"
#include <EEPROM.h>

#ifndef IRAM_ATTR
#define IRAM_ATTR
#endif

// ---------------------- USER CONFIG ----------------------
const int HX711_DOUT_PIN = 4;
const int HX711_SCK_PIN  = 2;
const int TACH_PIN = 0;
const bool TACH_USE_PULLUP = true;

volatile uint32_t PULSES_PER_REV = 1;

const unsigned long SERIAL_BAUD = 115200;
const unsigned long HX711_READ_TIMEOUT_MS = 200;

const char* FW_VENDOR  = "ForecverBearing";
const char* FW_DEVICE  = "RP2040";
const char* FW_VERSION = "1.1.1";   // v1.1.0 + robust tach (ticket 0007)

// ---------------------- CALIBRATION (RAM) ----------------------
// CHANGED: default slope doubled to match gain 64 (half gain → half counts → double slope)
// Re-run SETCAL after hardware calibration on your actual load cell.
volatile float g_per_count = 0.0040f;  // was 0.0020f at gain 128
volatile long  tare_offset = 0;
// CHANGED: default gain set to 64 for >30 kg range
volatile uint8_t hx_gain = 64;         // 64 or 128 (HX711 channel A)

// ---------------------- EEPROM PERSISTENCE ----------------------
struct CalRecord {
  uint32_t magic;
  uint32_t version;
  float    slope;
  int32_t  tare;
  uint8_t  gain;     // NEW field: stored HX711 gain (64 or 128)
  uint8_t  _pad[3];  // alignment padding
  uint32_t crc;
};

static const uint32_t CAL_MAGIC   = 0x43414C32; // 'CAL2' – bumped so old records are ignored
static const uint32_t CAL_VERSION = 0x00020000; // v2
static const size_t   EEPROM_SIZE = 64;

struct TachSnapshot {
  uint32_t pulses_total;
  uint32_t last_period_us;
  uint32_t glitch_total;
  uint32_t last_edge_us;
  uint32_t periods[5];       // TACH_MEDIAN_N; literal because the const is declared later
  int      period_count;
};

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

void saveCalibrationToEEPROM(float slope, long tare, uint8_t gain) {
  CalRecord rec;
  rec.magic   = CAL_MAGIC;
  rec.version = CAL_VERSION;
  rec.slope   = slope;
  rec.tare    = (int32_t)tare;
  rec.gain    = gain;
  rec._pad[0] = rec._pad[1] = rec._pad[2] = 0;
  rec.crc = crc32_span(reinterpret_cast<const uint8_t*>(&rec), sizeof(CalRecord) - sizeof(uint32_t));
  EEPROM.begin(EEPROM_SIZE);
  EEPROM.put(0, rec);
  EEPROM.commit();
}

bool loadCalibrationFromEEPROM(float &slope, long &tare, uint8_t &gain) {
  CalRecord rec;
  EEPROM.begin(EEPROM_SIZE);
  EEPROM.get(0, rec);
  if (rec.magic != CAL_MAGIC || rec.version != CAL_VERSION) return false;
  uint32_t calc_crc = crc32_span(reinterpret_cast<const uint8_t*>(&rec), sizeof(CalRecord) - sizeof(uint32_t));
  if (calc_crc != rec.crc) return false;
  slope = rec.slope;
  tare  = rec.tare;
  gain  = rec.gain;
  return true;
}

void resetCalibrationToDefaultsAndPersist() {
  float   defSlope = 0.0040f;  // matches gain 64 default
  long    defTare  = 0;
  uint8_t defGain  = 64;
  noInterrupts();
  g_per_count = defSlope;
  tare_offset = defTare;
  hx_gain     = defGain;
  interrupts();
  saveCalibrationToEEPROM(defSlope, defTare, defGain);
}

// ---------------------- TIMING / TACH ----------------------
HX711 hx;

// --- tach robustness (ticket 0007), backported onto v1.1.0 ---
// Slowest real speed is 100 rpm = 600 ms/rev, so 1.5 s without an accepted edge means
// the signal is gone. The old code held last_period_us forever, so a lost signal froze
// rpm at its last value instead of reading zero.
const uint32_t TACH_TIMEOUT_US    = 1500000;
// 8 ms => >7500 rpm, impossible here (max real 3000 rpm = 20 ms). Replaces the old 100 us
// filter, which only caught contact bounce. Assumes PULSES_PER_REV = 1.
const uint32_t TACH_MIN_PERIOD_US = 8000;
const int      TACH_MEDIAN_N      = 5;
// TachSnapshot is declared above these constants and has to size its array with a literal.
// This keeps the two from drifting apart if TACH_MEDIAN_N is ever changed.
static_assert(TACH_MEDIAN_N == 5, "TachSnapshot::periods[5] must match TACH_MEDIAN_N");

volatile uint32_t tach_pulses_total = 0;   // every raw rising edge, including rejected
volatile uint32_t tach_glitch_total = 0;   // edges rejected as too close together
volatile uint32_t last_edge_us = 0;        // timestamp of the last ACCEPTED edge
volatile uint32_t last_period_us = 0;      // last accepted period
volatile uint32_t tach_periods[TACH_MEDIAN_N] = {0};
volatile int      tach_period_idx = 0;
volatile int      tach_period_count = 0;
volatile uint64_t epoch_base_ms = 0;

static inline uint64_t now_unix_ms() {
  noInterrupts();
  uint64_t base = epoch_base_ms;
  interrupts();
  return base + (uint64_t)millis();
}

static inline float us_to_ms(uint32_t us) { return (float)us / 1000.0f; }

static inline TachSnapshot tach_snapshot() {
  TachSnapshot s;
  noInterrupts();
  s.pulses_total   = tach_pulses_total;
  s.last_period_us = last_period_us;
  s.glitch_total   = tach_glitch_total;
  s.last_edge_us   = last_edge_us;
  s.period_count   = tach_period_count;
  for (int i = 0; i < TACH_MEDIAN_N; ++i) s.periods[i] = tach_periods[i];
  interrupts();
  return s;
}

// Median of the last N accepted periods, plus a timeout. The old version derived rpm from
// the single most recent interval and never expired it, so one odd edge moved the reading
// and a lost signal held the last value indefinitely.
static inline float compute_rpm(const TachSnapshot& s) {
  if (s.period_count == 0 || PULSES_PER_REV == 0) return 0.0f;
  if ((uint32_t)(micros() - s.last_edge_us) > TACH_TIMEOUT_US) return 0.0f;

  uint32_t p[TACH_MEDIAN_N];
  int n = s.period_count;
  for (int i = 0; i < n; ++i) p[i] = s.periods[i];
  for (int i = 1; i < n; ++i) {                      // insertion sort, n <= 5
    uint32_t k = p[i]; int j = i - 1;
    while (j >= 0 && p[j] > k) { p[j + 1] = p[j]; j--; }
    p[j + 1] = k;
  }
  uint32_t med = p[n / 2];
  if (med == 0) return 0.0f;
  float period_s = (float)med / 1e6f;
  if (period_s <= 0.0f) return 0.0f;
  return 60.0f * (1.0f / period_s) / (float)PULSES_PER_REV;
}

void IRAM_ATTR tach_isr() {
  uint32_t now  = micros();
  uint32_t prev = last_edge_us;
  tach_pulses_total++;
  if (prev != 0) {
    uint32_t dt = now - prev;                 // unsigned: rollover-safe
    if (dt < TACH_MIN_PERIOD_US) {            // glitch / double-edge
      tach_glitch_total++;
      return;                                 // keep last_edge_us at the last REAL edge
    }
    last_period_us = dt;
    tach_periods[tach_period_idx] = dt;
    tach_period_idx = (tach_period_idx + 1) % TACH_MEDIAN_N;
    if (tach_period_count < TACH_MEDIAN_N) tach_period_count++;
  }
  last_edge_us = now;
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

// Apply current hx_gain to the HX711 chip.
// Must be called from setup() or whenever gain changes.
// NOTE: hx.set_gain() takes 128, 64, or 32.
void apply_hx_gain() {
  uint8_t g;
  noInterrupts();
  g = hx_gain;
  interrupts();
  hx.set_gain(g);
  // The gain change only takes effect after the next read cycle;
  // perform one dummy read to flush it through.
  long dummy;
  hx_read_blocking(dummy);
}

// ---------------------- protocol helpers ----------------------
static inline void streq_prep(char* s) {
  size_t n = strlen(s);
  while (n && (s[n-1] == '\r' || s[n-1] == '\n' || s[n-1] == ' ' || s[n-1] == '\t')) s[--n] = '\0';
  size_t i = 0;
  while (i < strlen(s) && (s[i] == ' ' || s[i] == '\t')) i++;
  if (i) memmove(s, s + i, strlen(s) - i + 1);
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
void cmd_ping()  { Serial.print("OK PONG\r\n"); }

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
  Serial.print(" raw=");   Serial.print(raw);
  Serial.print(" ts=");    Serial.print(ts);
  Serial.print("\r\n");
}

void cmd_tare() {
  long raw;
  if (!hx_read_blocking(raw)) { Serial.print("ERR 20 HX711_timeout\r\n"); return; }
  float slope; uint8_t gain;
  noInterrupts();
  tare_offset = raw;
  slope = g_per_count;
  gain  = hx_gain;
  interrupts();
  saveCalibrationToEEPROM(slope, raw, gain);
  Serial.print("OK TARE\r\n");
}

void cmd_speed() {
  TachSnapshot s = tach_snapshot();
  float rpm       = compute_rpm(s);
  float period_ms = (s.last_period_us == 0) ? 0.0f : us_to_ms(s.last_period_us);
  uint64_t ts     = now_unix_ms();
  Serial.print("OK SPEED ");
  Serial.print("rpm=");        Serial.print(rpm, 2);
  Serial.print(" period_ms="); Serial.print(period_ms, 3);
  Serial.print(" pulses=");    Serial.print(s.pulses_total);
  Serial.print(" ts=");        Serial.print(ts);
  Serial.print("\r\n");
}

// Raw edge statistics, so the spurious pulse source can be measured at the rig without a
// scope: with the shaft stationary the accepted count still rises, at the spurious rate.
// That is the ticket 0003 EMI-vs-optics discriminator.
void cmd_tachdiag() {
  TachSnapshot s = tach_snapshot();
  Serial.print("OK TACHDIAG ");
  Serial.print("pulses=");         Serial.print(s.pulses_total);
  Serial.print(" glitches=");      Serial.print(s.glitch_total);
  Serial.print(" accepted=");      Serial.print(s.pulses_total - s.glitch_total);
  Serial.print(" last_period_ms="); Serial.print(us_to_ms(s.last_period_us), 3);
  Serial.print(" ts=");            Serial.print(now_unix_ms());
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
  char* a = strtok(args, " \t");
  char* b = strtok(nullptr, " \t");
  if (!a || !b) { Serial.print("ERR 31 missing_args\r\n"); return; }
  float   slope = atof(a);
  long    tare  = atol(b);
  uint8_t gain;
  noInterrupts();
  g_per_count = slope;
  tare_offset = tare;
  gain = hx_gain;
  interrupts();
  saveCalibrationToEEPROM(slope, tare, gain);
  Serial.print("OK SETCAL\r\n");
}

void cmd_calq() {
  float slope; long tare; uint8_t gain;
  noInterrupts();
  slope = g_per_count;
  tare  = tare_offset;
  gain  = hx_gain;
  interrupts();
  Serial.print("OK CAL ");
  Serial.print("slope="); Serial.print(slope, 9);
  Serial.print(" tare=");  Serial.print(tare);
  Serial.print(" gain=");  Serial.print(gain);
  Serial.print("\r\n");
}

void cmd_resetcal() {
  resetCalibrationToDefaultsAndPersist();
  apply_hx_gain();
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
  Serial.print("OK PPR ppr="); Serial.print(ppr); Serial.print("\r\n");
}

// NEW: SETGAIN <64|128>
// Changing gain alters the ADC full-scale range.
// After SETGAIN you MUST re-run SETCAL with a new slope value, or run TARE at minimum.
void cmd_setgain(char* args) {
  char* a = strtok(args, " \t");
  if (!a) { Serial.print("ERR 34 missing_gain\r\n"); return; }
  uint8_t g = (uint8_t)strtoul(a, nullptr, 10);
  if (g != 64 && g != 128) { Serial.print("ERR 35 invalid_gain_use_64_or_128\r\n"); return; }
  float slope; long tare;
  noInterrupts();
  hx_gain = g;
  slope   = g_per_count;
  tare    = tare_offset;
  interrupts();
  saveCalibrationToEEPROM(slope, tare, g);
  apply_hx_gain();  // reconfigure HX711 chip immediately
  Serial.print("OK SETGAIN\r\n");
}

// NEW: GAIN?
void cmd_gainq() {
  uint8_t g;
  noInterrupts();
  g = hx_gain;
  interrupts();
  Serial.print("OK GAIN gain="); Serial.print(g); Serial.print("\r\n");
}

// ---------------------- parser ----------------------
void handle_line(char* line) {
  size_t n = strlen(line);
  while (n && (line[n-1] == '\r' || line[n-1] == '\n')) line[--n] = '\0';
  while (*line == ' ' || *line == '\t') ++line;
  if (*line == '\0') return;
  char* cmd  = strtok(line, " \t");
  char* args = strtok(nullptr, "");

  if      (streqi(cmd, "PING"))     cmd_ping();
  else if (streqi(cmd, "INFO"))     cmd_info();
  else if (streqi(cmd, "LOAD?"))    cmd_load();
  else if (streqi(cmd, "TARE"))     cmd_tare();
  else if (streqi(cmd, "SPEED?"))   cmd_speed();
  else if (streqi(cmd, "TACHDIAG?")) cmd_tachdiag();
  else if (streqi(cmd, "SETTIME"))  cmd_settime(args ? args : (char*)"");
  else if (streqi(cmd, "SETCAL"))   cmd_setcal(args ? args : (char*)"");
  else if (streqi(cmd, "CAL?"))     cmd_calq();
  else if (streqi(cmd, "RESETCAL")) cmd_resetcal();
  else if (streqi(cmd, "SETPPR"))   cmd_setppr(args ? args : (char*)"");
  else if (streqi(cmd, "PPR?"))     cmd_pprq();
  else if (streqi(cmd, "SETGAIN"))  cmd_setgain(args ? args : (char*)"");  // NEW
  else if (streqi(cmd, "GAIN?"))    cmd_gainq();                            // NEW
  else Serial.print("ERR 10 unknown_command\r\n");
}

// ---------------------- setup/loop ----------------------
void setup() {
  Serial.begin(SERIAL_BAUD);
  EEPROM.begin(256);
  // Load calibration (including gain) from EEPROM, or fall back to defaults
  float s; long t; uint8_t g;
  if (loadCalibrationFromEEPROM(s, t, g)) {
    noInterrupts();
    g_per_count = s;
    tare_offset = t;
    hx_gain     = g;
    interrupts();
  } else {
    resetCalibrationToDefaultsAndPersist();
  }

  // HX711 – begin() then set gain BEFORE first measurement
  hx.begin(HX711_DOUT_PIN, HX711_SCK_PIN);
  apply_hx_gain();   // CHANGED: was hx.set_gain(128); now uses stored/default gain (64)

  // Tach
  if (TACH_USE_PULLUP) pinMode(TACH_PIN, INPUT_PULLUP);
  else                 pinMode(TACH_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(TACH_PIN), tach_isr, RISING);

  // Banner
  Serial.print("OK READY vendor="); Serial.print(FW_VENDOR);
  Serial.print(" device=");         Serial.print(FW_DEVICE);
  Serial.print(" fw=");             Serial.print(FW_VERSION);
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