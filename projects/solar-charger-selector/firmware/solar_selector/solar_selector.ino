// =====================================================================================
//  SOLAR CHARGER SELECTOR  -  final version (2026-11-28)
//  One PV array shared between three charge controllers: 12 V, 48 V, 72 V.
//  Arduino Uno + proto shield. Drawing: drawings/final_schematic.svg
// =====================================================================================
//
//  POWER SIDE
//    PV- of the array goes to every controller's PV- (common negative controllers only).
//    PV+ is switched by one relay per controller: K1 = 12 V, K3 = 48 V, K5 = 72 V.
//    Only one relay is ever closed. Every change: ALL relays open, wait 10 s, then close one.
//
//  PINS
//    D2 / D3 / D4  -> 100R -> IRLZ44N Q1 / Q2 / Q3 -> relay coil K1 / K3 / K5 (12 V)
//                     same pins: 330R -> LED green (12 V) / yellow (48 V) / blue (72 V)
//    D5  AUTO button      D6  NEXT button      A3  TIMER button     (button -> GND)
//    D9  white LED = AUTO mode      D8  red LED = TIMER mode      (both off = MANUAL)
//    A4  display SDA      D7  display SCL      (16x2 with PCF8574 I2C backpack, 0x27)
//    A5  panel voltage:  PV+ bus -> 0.5 A fuse -> 220k -> A5 -> 10k -> GND (+100 nF, 5.1 V zener)
//
//  BUTTONS
//    AUTO   : charge each battery until full, then the next one (12 -> 48 -> 72).
//    TIMER  : 12 V for 3 hours -> 48 V until full -> 72 V until full -> continue in AUTO.
//             TIMER always starts by itself at power-up and every morning.
//    NEXT   : short press = swap to the next battery (stays in the same mode).
//             hold 5 s   = MANUAL. Then each press: 12 -> 48 -> 72 -> OFF -> 12.
//             Leave MANUAL with AUTO or TIMER.
//
//  HOW "FULL" IS DETECTED (no battery wires needed)
//    During every 10 s all-off pause the Arduino reads the panel's open-circuit voltage (Voc).
//    A charging controller pulls the panel down to about 80 % of Voc. When its battery is
//    full the controller stops taking current and the panel rises back above 95 % of Voc.
//    95 % for 15 minutes = full. Voc is re-read every 30 minutes (short 10 s pause).
//    Safety limit: a battery step that never reads "full" ends after 4 hours.
//    Night: panel below 15 % of PANEL_VOC for 10 min -> all relays off ("NIGHT").
//    Morning: panel above 50 % of PANEL_VOC for 2 min -> TIMER sequence starts again.
//
//  SERIAL MONITOR (9600 baud, "Newline")
//    auto | timer | timer N (12 V minutes, e.g. timer 1 to test) | next | manual
//    0 / off / 12 / 48 / 72 (manual select) | ?  (status)
// =====================================================================================

// ------------------------------- settings you may change ------------------------------
#define PV_SENSE 1                 // 1 = panel divider fitted on A5, 0 = time only (no A5 wiring)
const float PANEL_VOC = 100.0;     // your array's open-circuit voltage: label Voc x panels in series
const float R_TOP_K = 220.0;       // divider top resistor (k): 220k up to ~110 V, 330k up to ~160 V
const float R_BOT_K = 10.0;        // divider bottom resistor (k)
float CAL_PV = 1.000;              // tune so "?" matches a multimeter on the PV+ bus

unsigned int timer12Min = 180;     // TIMER step 1: 12 V charging time (minutes)
const unsigned long MAX_STEP_MIN = 240;        // longest time on one battery when "full" never comes
const unsigned long DEAD_MS = 10000;           // all relays off between batteries
const float FULL_RATIO = 0.95;                 // panel >= 95 % of Voc ...
const unsigned long FULL_HOLD_MS = 15UL * 60000UL;   // ... for 15 minutes = full
const unsigned long VOC_REFRESH_MS = 30UL * 60000UL; // re-read Voc every 30 min (0 = never)
const float SUN_MIN = 0.70;                    // Voc must be >= 70 % of PANEL_VOC to judge "full"
const float NIGHT_LEVEL = 0.15, DAY_LEVEL = 0.50;
const unsigned long NIGHT_HOLD_MS = 10UL * 60000UL, DAY_HOLD_MS = 2UL * 60000UL;

// ------------------------------- display ----------------------------------------------
#define LCD_SOFT_SCL 7             // 7 = SCL wire on D7 (software I2C, no library); 0 = SCL on A5
#define LCD_ADDR 0x27              // try 0x3F if the screen stays blank
#if LCD_SOFT_SCL
class SoftLcd : public Print {     // 16x2 LCD, PCF8574 backpack: RS=P0 RW=P1 E=P2 BL=P3 D4-D7=P4-P7
 public:
  SoftLcd(uint8_t sda, uint8_t scl, uint8_t addr) : sda_(sda), scl_(scl), addr_(addr) {}
  void init() {
    rel(sda_); rel(scl_); delay(50); pcf(bl_);
    nib(0x3, 0); delay(5); nib(0x3, 0); delay(5); nib(0x3, 0); delayMicroseconds(200); nib(0x2, 0);
    cmd(0x28); cmd(0x0C); cmd(0x01); cmd(0x06);
  }
  void backlight() { bl_ = 0x08; pcf(bl_); }
  void resync() {                  // puts the display back in step after a glitch (no flicker)
    nib(0x3, 0); delay(5); nib(0x3, 0); delayMicroseconds(150); nib(0x3, 0); nib(0x2, 0);
    cmd(0x28); cmd(0x0C); cmd(0x06);
  }
  void clear() { cmd(0x01); }
  void setCursor(uint8_t col, uint8_t row) { cmd(0x80 | (col + (row ? 0x40 : 0))); }
  size_t write(uint8_t c) override { send(c, 0x01); return 1; }
  using Print::write;
 private:
  uint8_t sda_, scl_, addr_, bl_ = 0x08;
  static void rel(uint8_t p) { pinMode(p, INPUT); }
  static void low(uint8_t p) { digitalWrite(p, LOW); pinMode(p, OUTPUT); }
  static void dly() { delayMicroseconds(10); }
  void start() { rel(sda_); rel(scl_); dly(); low(sda_); dly(); low(scl_); dly(); }
  void stop() { low(sda_); dly(); rel(scl_); dly(); rel(sda_); dly(); }
  void byteOut(uint8_t b) {
    for (int8_t i = 7; i >= 0; i--) { if (b & (1 << i)) rel(sda_); else low(sda_); dly(); rel(scl_); dly(); low(scl_); }
    rel(sda_); dly(); rel(scl_); dly(); low(scl_); dly();
  }
  void pcf(uint8_t v) { start(); byteOut(addr_ << 1); byteOut(v); stop(); }
  void nib(uint8_t n, uint8_t rs) { uint8_t v = (n << 4) | rs | bl_; pcf(v | 0x04); pcf(v); delayMicroseconds(40); }
  void send(uint8_t b, uint8_t rs) { nib(b >> 4, rs); nib(b & 0x0F, rs); }
  void cmd(uint8_t c) { send(c, 0); if (c < 4) delay(2); }
};
SoftLcd lcd(A4, LCD_SOFT_SCL, LCD_ADDR);
#else
#include <Wire.h>
#include <LiquidCrystal_I2C.h>     // "LiquidCrystal I2C" by Frank de Brabander
LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);
#endif

// ------------------------------- pins --------------------------------------------------
const uint8_t GATE[3] = {2, 3, 4};
const char *const NAME[3] = {"12V", "48V", "72V"};
const uint8_t BTN_PIN[3] = {5, 6, A3};          // AUTO, NEXT, TIMER
const uint8_t LED_WHITE = 9, LED_RED = 8;
const uint8_t PV_PIN = A5;

// ------------------------------- state -------------------------------------------------
enum Mode : uint8_t { MODE_AUTO, MODE_MANUAL, MODE_TIMER };
Mode mode = MODE_TIMER;
int8_t activeCh = -1, pendingCh = -1;
bool waiting = false, vocCheck = false, interlockFault = false;
unsigned long offAt = 0, stepStart = 0, lastVocCheck = 0;
float vpv = 0, voc = 0;
bool vocValid = false;
bool full[3] = {false, false, false};
bool highPv = false;
unsigned long highSince = 0;
bool night = false, dark = false, light = false;
unsigned long darkSince = 0, lightSince = 0;
uint8_t timerStage = 0;
unsigned long timerStart = 0;

bool btnStable[3] = {HIGH, HIGH, HIGH}, btnLast[3] = {HIGH, HIGH, HIGH};
unsigned long btnChanged[3] = {0, 0, 0};
const unsigned long DEBOUNCE_MS = 30, LONG_PRESS_MS = 5000;
unsigned long nextDownAt = 0;
bool nextLongDone = false;

unsigned long lastSample = 0, lastLcd = 0, lastPage = 0, lastReport = 0;
uint8_t lcdPage = 0;
char rxBuf[12];
uint8_t rxLen = 0;

// ------------------------------- measurement -------------------------------------------
long readVcc_mV() {                       // 5 V rail measured against the 1.1 V bandgap
  ADMUX = _BV(REFS0) | _BV(MUX3) | _BV(MUX2) | _BV(MUX1);
  delay(2);
  ADCSRA |= _BV(ADSC);
  while (bit_is_set(ADCSRA, ADSC));
  long r = ADCL;
  r |= (long)ADCH << 8;
  return r ? 1125300L / r : 5000;
}

float readPv() {
#if PV_SENSE
  long vcc = readVcc_mV();
  analogRead(PV_PIN);
  long sum = 0;
  for (uint8_t n = 0; n < 16; n++) sum += analogRead(PV_PIN);
  return (sum / 16.0) * (vcc / 1000.0) / 1023.0 * ((R_TOP_K + R_BOT_K) / R_BOT_K) * CAL_PV;
#else
  return 0;
#endif
}

// ------------------------------- switching ---------------------------------------------
void allOff() {
  for (uint8_t i = 0; i < 3; i++) digitalWrite(GATE[i], LOW);
  activeCh = -1;
}

bool allGatesLow() {
  for (uint8_t i = 0; i < 3; i++) if (digitalRead(GATE[i]) == HIGH) return false;
  return true;
}

void requestChannel(int8_t ch) {           // break-before-make with a 10 s pause
  if (ch == activeCh && !waiting) return;
  allOff();
  offAt = millis();
  highPv = false;
  vocCheck = false;
  if (ch < 0) { waiting = false; Serial.println(F("All relays off")); return; }
  pendingCh = ch;
  waiting = true;
  Serial.print(F("All relays off, waiting 10 s, then "));
  Serial.println(NAME[ch]);
}

void startVocCheck() {                     // open for 10 s to re-read Voc, then the same battery
  int8_t ch = activeCh;
  allOff();
  offAt = millis();
  pendingCh = ch;
  waiting = true;
  vocCheck = true;
  Serial.println(F("Voc check: relays open for 10 s"));
}

void finishPause(unsigned long now) {
  float v = readPv();                      // relays have been open 10 s: this is Voc
  if (PV_SENSE) { voc = v; vocValid = true; }
  lastVocCheck = now;
  if (allGatesLow()) {
    digitalWrite(GATE[pendingCh], HIGH);
    activeCh = pendingCh;
    interlockFault = false;
    if (!vocCheck) stepStart = now;
    highPv = false;
    Serial.print(NAME[activeCh]);
    Serial.print(F(" connected"));
    if (PV_SENSE) { Serial.print(F(", Voc ")); Serial.print(voc, 1); Serial.print(F(" V")); }
    Serial.println();
  } else {
    allOff();
    interlockFault = true;
    Serial.println(F("Interlock fault: a gate was still HIGH, all off"));
  }
  waiting = false;
  vocCheck = false;
}

// ------------------------------- modes -------------------------------------------------
int8_t pickNext() {                        // AUTO: stay until full, then the next one not full
  if (activeCh >= 0 && !full[activeCh]) return activeCh;
  int8_t start = activeCh < 0 ? 0 : activeCh + 1;
  for (uint8_t k = 0; k < 3; k++) { int8_t i = (start + k) % 3; if (!full[i]) return i; }
  return activeCh;                         // all full: keep the last one (its controller floats it)
}

void setAuto() { mode = MODE_AUTO; Serial.println(F("AUTO mode")); }

void setTimer() {
  mode = MODE_TIMER;
  timerStage = 0;
  timerStart = millis();
  Serial.print(F("TIMER: 12V for "));
  Serial.print(timer12Min);
  Serial.println(F(" min, then 48V until full, then 72V until full"));
  requestChannel(0);
}

void timerAdvance(const __FlashStringHelper *why) {
  while (true) {
    timerStage++;
    if (timerStage > 2) { timerStage = 2; mode = MODE_AUTO; Serial.println(F("TIMER done, continuing in AUTO")); return; }
    if (!full[timerStage]) break;
    Serial.print(F("TIMER: ")); Serial.print(NAME[timerStage]); Serial.println(F(" already full, skipped"));
  }
  Serial.print(F("TIMER: ")); Serial.print(why); Serial.print(F(" -> ")); Serial.println(NAME[timerStage]);
  requestChannel(timerStage);
}

void timerFollow(unsigned long now) {
  if (timerStage == 0 && now - timerStart >= timer12Min * 60000UL) { timerAdvance(F("12V time is up")); return; }
  if (timerStage > 0 && full[timerStage]) { timerAdvance(F("battery full")); return; }
  if (activeCh != (int8_t)timerStage) requestChannel(timerStage);
}

void enterManual() {
  if (mode == MODE_MANUAL) return;
  mode = MODE_MANUAL;
  Serial.println(F("MANUAL (NEXT held 5 s): NEXT = next battery, AUTO or TIMER to leave"));
}

void manual(int8_t ch) {
  if (mode != MODE_MANUAL) Serial.println(F("MANUAL mode"));
  mode = MODE_MANUAL;
  requestChannel(ch);
}

void swapNext() {                          // NEXT short press
  if (night) { Serial.println(F("Night: no switching")); return; }
  int8_t cur = waiting ? pendingCh : activeCh;
  if (mode == MODE_MANUAL) {
    int8_t n = cur >= 2 ? -1 : cur + 1;
    Serial.print(F("MANUAL: NEXT -> ")); Serial.println(n < 0 ? "OFF" : NAME[n]);
    requestChannel(n);
  } else if (mode == MODE_TIMER) {
    timerAdvance(F("NEXT pressed"));
  } else {
    int8_t start = cur < 0 ? 0 : cur + 1, n = start % 3;
    for (uint8_t k = 0; k < 3; k++) { int8_t i = (start + k) % 3; if (!full[i]) { n = i; break; } }
    Serial.print(F("AUTO: NEXT -> ")); Serial.println(NAME[n]);
    requestChannel(n);
  }
}

// ------------------------------- every second ------------------------------------------
void sample(unsigned long now) {
  vpv = readPv();
#if PV_SENSE
  // night and morning
  if (vpv < NIGHT_LEVEL * PANEL_VOC) {
    light = false;
    if (!dark) { dark = true; darkSince = now; }
    if (!night && now - darkSince >= NIGHT_HOLD_MS) {
      night = true;
      requestChannel(-1);
      for (uint8_t i = 0; i < 3; i++) full[i] = false;
      Serial.println(F("NIGHT: no sun, all relays off"));
    }
  } else dark = false;
  if (night) {
    if (vpv > DAY_LEVEL * PANEL_VOC) {
      if (!light) { light = true; lightSince = now; }
      if (now - lightSince >= DAY_HOLD_MS) { night = false; Serial.println(F("MORNING: sun is back")); setTimer(); }
    } else light = false;
    return;
  }
#endif
  // full detection on the battery being charged
  if (activeCh >= 0 && !waiting) {
    uint8_t i = activeCh;
    if (PV_SENSE && vocValid && voc >= SUN_MIN * PANEL_VOC && vpv >= FULL_RATIO * voc) {
      if (!highPv) { highPv = true; highSince = now; }
      else if (!full[i] && now - highSince >= FULL_HOLD_MS) {
        full[i] = true;
        Serial.print(NAME[i]); Serial.println(F(" FULL (panel voltage back near Voc)"));
      }
    } else highPv = false;
    bool timedStep = mode == MODE_TIMER && timerStage == 0;
    if (mode != MODE_MANUAL && !timedStep && !full[i] && now - stepStart >= MAX_STEP_MIN * 60000UL) {
      full[i] = true;
      Serial.print(NAME[i]); Serial.println(F(": 4 h limit, counted as done"));
    }
  }
  if (waiting) return;
  if (PV_SENSE && VOC_REFRESH_MS && activeCh >= 0 && now - lastVocCheck >= VOC_REFRESH_MS) { startVocCheck(); return; }
  if (mode == MODE_AUTO) {
    int8_t n = pickNext();
    if (n != activeCh) { Serial.print(F("AUTO -> ")); Serial.println(NAME[n]); requestChannel(n); }
  } else if (mode == MODE_TIMER) timerFollow(now);
}

// ------------------------------- display -----------------------------------------------
void lcdRow(uint8_t row, char *s) {
  uint8_t n = strlen(s);
  while (n < 16) s[n++] = ' ';
  s[16] = '\0';
  lcd.setCursor(0, row);
  lcd.print(s);
}

void hm(char *out, unsigned long ms) {     // "2h05"
  unsigned long m = ms / 60000UL;
  snprintf(out, 8, "%luh%02lu", m / 60, m % 60);
}

void updateLcd(unsigned long now) {
  char l1[17], l2[17], m[8], a[8], b[8];
  strcpy(m, mode == MODE_AUTO ? "AUTO  " : mode == MODE_MANUAL ? "MANUAL" : "TIMER ");
  bool holding = btnStable[1] == LOW && !nextLongDone && now - nextDownAt >= 1000;
  if (interlockFault) strcpy(l1, "INTERLOCK FAULT");
  else if (holding && mode != MODE_MANUAL)
    snprintf(l1, sizeof l1, "HOLD %lus->MANUAL", (LONG_PRESS_MS - (now - nextDownAt) + 999) / 1000);
  else if (night) strcpy(l1, "NIGHT   all off");
  else if (waiting) {
    unsigned long el = now - offAt, left = el >= DEAD_MS ? 0 : (DEAD_MS - el + 999) / 1000;
    if (vocCheck) snprintf(l1, sizeof l1, "%sVocChk %2lus", m, left);
    else snprintf(l1, sizeof l1, "%s >>%s %2lus", m, NAME[pendingCh], left);
  } else if (activeCh < 0) snprintf(l1, sizeof l1, "%s ALL OFF", m);
  else snprintf(l1, sizeof l1, "%s CHG %s", m, NAME[activeCh]);

  if (lcdPage == 0) {                      // panel voltage and Voc
    if (!PV_SENSE) strcpy(l2, "PV sense off");
    else { dtostrf(vpv, 5, 1, a); dtostrf(voc, 3, 0, b); snprintf(l2, sizeof l2, "PV%sV Voc%s", a, b); }
  } else if (lcdPage == 1) {               // time on this battery
    if (activeCh < 0 || waiting) strcpy(l2, "--");
    else if (mode == MODE_TIMER && timerStage == 0) {
      unsigned long el = now - timerStart, t = timer12Min * 60000UL;
      hm(a, el >= t ? 0 : t - el); snprintf(l2, sizeof l2, "12V left %s", a);
    } else {
      hm(a, now - stepStart);
      if (highPv) snprintf(l2, sizeof l2, "%s on %s F%2lum", NAME[activeCh], a, (FULL_HOLD_MS - (now - highSince)) / 60000UL + 1);
      else snprintf(l2, sizeof l2, "%s on %s", NAME[activeCh], a);
    }
  } else snprintf(l2, sizeof l2, "Full12/48/72:%c%c%c", full[0] ? 'Y' : '-', full[1] ? 'Y' : '-', full[2] ? 'Y' : '-');

#if LCD_SOFT_SCL
  lcd.resync();
#endif
  lcdRow(0, l1);
  lcdRow(1, l2);
}

// ------------------------------- buttons / serial --------------------------------------
void updateModeLeds() {
  digitalWrite(LED_WHITE, mode == MODE_AUTO ? HIGH : LOW);
  digitalWrite(LED_RED, mode == MODE_TIMER ? HIGH : LOW);
}

void readButtons(unsigned long now) {
  for (uint8_t b = 0; b < 3; b++) {
    bool r = digitalRead(BTN_PIN[b]);
    if (r != btnLast[b]) { btnLast[b] = r; btnChanged[b] = now; }
    if (now - btnChanged[b] >= DEBOUNCE_MS && r != btnStable[b]) {
      btnStable[b] = r;
      if (b == 1) {                        // NEXT: short = swap, hold 5 s = MANUAL
        if (r == LOW) { nextDownAt = now; nextLongDone = false; }
        else if (!nextLongDone) swapNext();
      } else if (r == LOW) {
        if (b == 0) setAuto(); else setTimer();
      }
      lastLcd = 0;
    }
  }
  if (btnStable[1] == LOW && !nextLongDone && now - nextDownAt >= LONG_PRESS_MS) {
    nextLongDone = true;
    enterManual();
    lastLcd = 0;
  }
}

void printStatus(unsigned long now) {
  Serial.print('[');
  Serial.print(mode == MODE_AUTO ? F("AUTO") : mode == MODE_MANUAL ? F("MANUAL") : F("TIMER"));
  if (mode == MODE_TIMER) { Serial.print(F(" step ")); Serial.print(timerStage + 1); }
  if (night) Serial.print(F(" NIGHT"));
  Serial.print(F("] "));
  if (waiting) { Serial.print(F("pause, next ")); Serial.print(NAME[pendingCh]); }
  else if (activeCh < 0) Serial.print(F("all off"));
  else { Serial.print(NAME[activeCh]); Serial.print(F(" for ")); Serial.print((now - stepStart) / 60000UL); Serial.print(F(" min")); }
  Serial.print(F(" | PV ")); Serial.print(vpv, 1);
  Serial.print(F(" V, Voc ")); Serial.print(voc, 1);
  Serial.print(F(" V | full 12/48/72: "));
  for (uint8_t i = 0; i < 3; i++) Serial.print(full[i] ? 'Y' : '-');
  Serial.println();
}

void handleCommand(const char *cmd) {
  if (!strcmp(cmd, "0") || !strcasecmp(cmd, "off")) manual(-1);
  else if (!strcmp(cmd, "12")) manual(0);
  else if (!strcmp(cmd, "48")) manual(1);
  else if (!strcmp(cmd, "72")) manual(2);
  else if (!strcasecmp(cmd, "auto")) setAuto();
  else if (!strcasecmp(cmd, "timer")) setTimer();
  else if (!strncasecmp(cmd, "timer ", 6)) {
    int t = atoi(cmd + 6);
    if (t < 1 || t > 1440) Serial.println(F("timer N: 12V minutes, 1 to 1440"));
    else { timer12Min = t; setTimer(); }
  }
  else if (!strcasecmp(cmd, "next")) swapNext();
  else if (!strcasecmp(cmd, "manual")) enterManual();
  else if (!strcmp(cmd, "?")) printStatus(millis());
  else Serial.println(F("Commands: auto, timer, timer N, next, manual, 0/off, 12, 48, 72, ?"));
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') { rxBuf[rxLen] = '\0'; if (rxLen) handleCommand(rxBuf); rxLen = 0; }
    else if (rxLen < sizeof(rxBuf) - 1) rxBuf[rxLen++] = c;
  }
}

// ------------------------------- setup / loop ------------------------------------------
void setup() {
  for (uint8_t i = 0; i < 3; i++) { digitalWrite(GATE[i], LOW); pinMode(GATE[i], OUTPUT); }
  for (uint8_t b = 0; b < 3; b++) pinMode(BTN_PIN[b], INPUT_PULLUP);
  pinMode(LED_WHITE, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(PV_PIN, INPUT);
  Serial.begin(9600);
#if LCD_SOFT_SCL
  lcd.init();
#else
  lcd.init();
  lcd.backlight();
#endif
  lcd.clear();
  lcd.print(F("Solar selector"));
  lcd.setCursor(0, 1);
  lcd.print(F("starting..."));
  Serial.println(F("Solar selector ready. AUTO D5, TIMER A3, NEXT D6 (hold 5 s = MANUAL)"));
  Serial.println(F("Commands: auto, timer, timer N, next, manual, 0/off, 12, 48, 72, ?"));
  setTimer();                              // always start with the TIMER sequence
}

void loop() {
  unsigned long now = millis();
  if (waiting && now - offAt >= DEAD_MS) finishPause(now);
  readButtons(now);
  updateModeLeds();
  if (now - lastSample >= 1000) { lastSample = now; sample(now); }
  if (now - lastPage >= 2500) { lastPage = now; lcdPage = (lcdPage + 1) % 3; }
  if (now - lastLcd >= 500 && now >= 1000) { lastLcd = now; updateLcd(now); }
  if (now - lastReport >= 60000UL) { lastReport = now; printStatus(now); }
  readSerial();
}
