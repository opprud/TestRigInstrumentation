/*
  RP2040 (Arduino core) – HX711 + Tacho + ASCII Protocol
  v1.2.0 FULL (Backward compatible + Auto Scaling)

  ✔ Auto gain scaling (128 ↔ 64 ↔ 32)
  ✔ Separate calibration per gain
  ✔ EEPROM persistence (CRC v3)
  ✔ Keeps FULL protocol compatibility
*/

#include <Arduino.h>
#include "HX711.h"
#include <EEPROM.h>

#ifndef IRAM_ATTR
#define IRAM_ATTR
#endif

// ---------------- CONFIG ----------------
const int HX711_DOUT_PIN = 4;
const int HX711_SCK_PIN  = 2;
const int TACH_PIN = 0;
const bool TACH_USE_PULLUP = true;

volatile uint32_t PULSES_PER_REV = 1;

const unsigned long SERIAL_BAUD = 115200;
const unsigned long HX711_READ_TIMEOUT_MS = 200;

const char* FW_VENDOR  = "ForeverBearing";
const char* FW_DEVICE  = "RP2040";
const char* FW_VERSION = "1.2.0";

// ---------------- CALIBRATION ----------------
volatile float g128 = 0.0020f;
volatile float g64  = 0.0040f;
volatile float g32  = 0.0080f;

volatile long tare_offset = 0;
volatile uint8_t hx_gain = 64;

// ---------------- EEPROM ----------------
struct CalRecord {
  uint32_t magic;
  uint32_t version;

  float g128;
  float g64;
  float g32;

  int32_t tare;
  uint8_t gain;
  uint8_t pad[3];

  uint32_t crc;
};

static const uint32_t CAL_MAGIC = 0x43414C33;
static const uint32_t CAL_VERSION = 0x00030000;

// ---------------- GLOBAL ----------------
HX711 hx;

volatile uint32_t tach_pulses_total = 0;
volatile uint32_t last_edge_us = 0;
volatile uint32_t last_period_us = 0;
volatile uint64_t epoch_base_ms = 0;

int stable_counter = 0;
long last_raw = 0;

// ---------------- CRC ----------------
uint32_t crc32_update(uint32_t crc, uint8_t data) {
  crc ^= data;
  for (int i=0;i<8;i++)
    crc = (crc>>1) ^ (0xEDB88320 & -(crc&1));
  return crc;
}

uint32_t crc32_span(const uint8_t* data, size_t len) {
  uint32_t crc=0xFFFFFFFF;
  for(size_t i=0;i<len;i++)
    crc = crc32_update(crc,data[i]);
  return ~crc;
}

// ---------------- EEPROM ----------------
void saveCal() {
  CalRecord r;

  r.magic=CAL_MAGIC;
  r.version=CAL_VERSION;

  r.g128=g128;
  r.g64=g64;
  r.g32=g32;

  r.tare=tare_offset;
  r.gain=hx_gain;

  r.crc=crc32_span((uint8_t*)&r,sizeof(r)-4);

  EEPROM.put(0,r);
  EEPROM.commit();
}

bool loadCal() {
  CalRecord r;
  EEPROM.get(0,r);

  if(r.magic!=CAL_MAGIC || r.version!=CAL_VERSION)
    return false;

  if(crc32_span((uint8_t*)&r,sizeof(r)-4)!=r.crc)
    return false;

  g128=r.g128;
  g64=r.g64;
  g32=r.g32;

  tare_offset=r.tare;
  hx_gain=r.gain;

  return true;
}

void resetCal() {
  g128=0.0020f;
  g64=0.0040f;
  g32=0.0080f;
  tare_offset=0;
  hx_gain=64;
  saveCal();
}

// ---------------- TIME ----------------
uint64_t now_unix_ms() {
  return epoch_base_ms + millis();
}

// ---------------- TACH ----------------
void IRAM_ATTR tach_isr() {
  uint32_t now=micros();
  uint32_t prev=last_edge_us;
  last_edge_us=now;
  tach_pulses_total++;
  if(prev) last_period_us=now-prev;
}

float compute_rpm() {
  if(last_period_us==0) return 0;
  float s=last_period_us/1e6;
  return 60.0f/(s*PULSES_PER_REV);
}

// ---------------- HX ----------------
bool hx_read(long &raw) {
  unsigned long t0=millis();
  while(!hx.is_ready()) {
    if(millis()-t0>HX711_READ_TIMEOUT_MS) return false;
  }
  raw=hx.read();
  return true;
}

void apply_gain() {
  hx.set_gain(hx_gain);
  long dummy;
  hx_read(dummy);
}

float slope() {
  if(hx_gain==128) return g128;
  if(hx_gain==64)  return g64;
  return g32;
}

// ---------------- AUTO SCALE ----------------
void auto_scale(long raw) {
  if(abs(raw-last_raw)<50000) stable_counter++;
  else stable_counter=0;

  last_raw=raw;

  if(stable_counter<3) return;

  uint8_t newg=hx_gain;

  if(hx_gain==128 && abs(raw)>6500000) newg=64;
  else if(hx_gain==64 && abs(raw)>7500000) newg=32;
  else if(hx_gain==32 && abs(raw)<5000000) newg=64;
  else if(hx_gain==64 && abs(raw)<2500000) newg=128;

  if(newg!=hx_gain) {
    hx_gain=newg;
    apply_gain();
    stable_counter=0;

    Serial.print("OK AUTOGAIN gain=");
    Serial.print(newg);
    Serial.print("\r\n");
  }
}

// ---------------- COMMANDS ----------------
void cmd_load() {
  long raw;
  if(!hx_read(raw)) {
    Serial.print("ERR 20 HX711_timeout\r\n");
    return;
  }

  if(abs(raw)>8000000) {
    Serial.print("ERR 21 ADC_saturation\r\n");
    return;
  }

  auto_scale(raw);

  float mass=(raw-tare_offset)*slope();

  Serial.print("OK LOAD ");
  Serial.print("mass_g="); Serial.print(mass,3);
  Serial.print(" raw="); Serial.print(raw);
  Serial.print(" ts="); Serial.print(now_unix_ms());
  Serial.print("\r\n");
}

void cmd_tare() {
  long raw;
  if(!hx_read(raw)) return;
  tare_offset=raw;
  saveCal();
  Serial.print("OK TARE\r\n");
}

void cmd_setcal(char* a) {
  float s=atof(strtok(a," "));
  long t=atol(strtok(NULL," "));

  if(hx_gain==128) g128=s;
  else if(hx_gain==64) g64=s;
  else g32=s;

  tare_offset=t;
  saveCal();

  Serial.print("OK SETCAL\r\n");
}

void cmd_speed() {
  Serial.print("OK SPEED rpm=");
  Serial.print(compute_rpm(),2);
  Serial.print(" period_ms=");
  Serial.print(last_period_us/1000.0,3);
  Serial.print(" pulses=");
  Serial.print(tach_pulses_total);
  Serial.print(" ts=");
  Serial.print(now_unix_ms());
  Serial.print("\r\n");
}

void cmd_settime(char* a) {
  uint64_t v=strtoull(a,NULL,10);
  epoch_base_ms=v-millis();
  Serial.print("OK SETTIME\r\n");
}

void cmd_setgain(char* a) {
  int g=atoi(a);
  if(g!=32 && g!=64 && g!=128) {
    Serial.print("ERR 35 invalid_gain\r\n");
    return;
  }
  hx_gain=g;
  apply_gain();
  saveCal();
  Serial.print("OK SETGAIN\r\n");
}

void cmd_cal() {
  Serial.print("OK CAL slope=");
  Serial.print(slope(),9);
  Serial.print(" tare=");
  Serial.print(tare_offset);
  Serial.print(" gain=");
  Serial.print(hx_gain);
  Serial.print("\r\n");
}

void cmd_ping(){ Serial.print("OK PONG\r\n"); }
void cmd_info(){
  Serial.print("OK INFO vendor=");
  Serial.print(FW_VENDOR);
  Serial.print(" device=");
  Serial.print(FW_DEVICE);
  Serial.print(" fw=");
  Serial.print(FW_VERSION);
  Serial.print("\r\n");
}

// ---------------- PARSER ----------------
void handle_line(char* line){
  char* cmd=strtok(line," ");
  char* args=strtok(NULL,"");

  if(!cmd) return;

  if(!strcmp(cmd,"PING")) cmd_ping();
  else if(!strcmp(cmd,"INFO")) cmd_info();
  else if(!strcmp(cmd,"LOAD?")) cmd_load();
  else if(!strcmp(cmd,"TARE")) cmd_tare();
  else if(!strcmp(cmd,"SETCAL")) cmd_setcal(args);
  else if(!strcmp(cmd,"CAL?")) cmd_cal();
  else if(!strcmp(cmd,"SETGAIN")) cmd_setgain(args);
  else if(!strcmp(cmd,"SPEED?")) cmd_speed();
  else if(!strcmp(cmd,"SETTIME")) cmd_settime(args);
  else if(!strcmp(cmd,"RESETCAL")) { resetCal(); Serial.print("OK RESETCAL\r\n"); }
  else Serial.print("ERR 10 unknown_command\r\n");
}

// ---------------- SETUP ----------------
void setup(){
  Serial.begin(SERIAL_BAUD);
  EEPROM.begin(128);

  if(!loadCal()) resetCal();

  hx.begin(HX711_DOUT_PIN,HX711_SCK_PIN);
  apply_gain();

  if(TACH_USE_PULLUP) pinMode(TACH_PIN,INPUT_PULLUP);
  else pinMode(TACH_PIN,INPUT);

  attachInterrupt(digitalPinToInterrupt(TACH_PIN),tach_isr,RISING);

  Serial.print("OK READY vendor=");
  Serial.print(FW_VENDOR);
  Serial.print(" device=");
  Serial.print(FW_DEVICE);
  Serial.print(" fw=");
  Serial.print(FW_VERSION);
  Serial.print("\r\n");
}

// ---------------- LOOP ----------------
void loop(){
  static char buf[128];
  static int i=0;

  while(Serial.available()){
    char c=Serial.read();
    if(c=='\n'){
      buf[i]=0;
      handle_line(buf);
      i=0;
    } else if(i<127){
      buf[i++]=c;
    }
  }
}