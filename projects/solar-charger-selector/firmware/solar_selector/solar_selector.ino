// Solar selector: one PV array, three chargers (12 V / 48 V / 72 V)
// AUTO MODE: charge one battery until it is full, then move to the next one.
//
// D2 -> 100R -> Q1 (IRLZ44N) gate -> K1 + K2 coils -> 12 V charger
// D3 -> 100R -> Q2 (IRLZ44N) gate -> K3 + K4 coils -> 48 V charger
// D4 -> 100R -> Q3 (IRLZ44N) gate -> K5 + K6 coils -> 72 V charger
// Charging LEDs hang on the same pins (pin -> 330R -> LED -> GND), no code needed:
//   D2 green = 12 V charging, D3 yellow = 48 V charging, D4 blue = 72 V charging
// Mode LEDs (pin -> 330R -> LED -> GND):
//   D9 white = AUTO mode, D8 red = TIMER mode, both off = MANUAL mode
//   (with the parallel LCD option they move to A4 / A5, see MODE_LED_*)
// A0 <- 12 V bank  (33k / 10k divider)
// A1 <- 48 V bank  (150k / 10k divider)
// A2 <- 72 V bank  (220k / 10k divider)
// All bank negatives join the control GND (see sheet 3).
// 16x2 LCD (sheet 4): I2C backpack on A4 (SDA) / A5 (SCL), or parallel on D7-D12.
// LCD_SOFT_SCL 7 (default here): the display's SCL wire goes to D7 instead of A5.
//
// LCD line 1: mode and the battery being charged     e.g.  AUTO   CHG 48V
// LCD line 2: each battery in turn, every 2 seconds   e.g.  48V 55.2V CHG 7m
//             CHG = charging (7m = minutes left until counted full)
//             FULL / FLOAT / WAIT / LOW (needs charge)
//
// Rule: only one relay pair may ever be closed. Every change opens ALL pairs,
// waits DEAD_TIME_MS (10 s, so the relays fully de-energise), then closes exactly one pair.
//
// "Full" = the battery being charged stays at or above FULL_V for FULL_HOLD_MS.
// A full battery is skipped until its voltage falls below RESUME_V.
// When every battery is full, the last one stays connected (charger floats it).
//
// THREE BUTTONS (each button: pin -> button -> GND, no resistor, internal pull-up):
//   SW1 AUTO  (D5) : AUTO mode. Charge each battery until full, then move to the next.
//   SW3 TIMER (A3) : TIMER sequence (started automatically at power-up). 12 V for 3 hours, then 48 V until full,
//                    then 72 V until full, then carry on in AUTO.
//                    A battery that is already full is skipped. Press again to restart.
//   SW2 NEXT  (D6) : short press = SWAP to the next battery, in every mode:
//                      AUTO   -> next battery in order that is not full (stays in AUTO)
//                      TIMER  -> next step of the sequence
//                      MANUAL -> 12V -> 48V -> 72V -> OFF -> 12V ...
//                    hold 5 s = MANUAL mode (keeps the battery that is connected now).
//                    Leave MANUAL with AUTO or TIMER.
//
// Serial Monitor (9600 baud, "Newline"):
//   auto        AUTO mode
//   timer       start the TIMER sequence   (timer N = 12 V step of N minutes, e.g. timer 1 to test)
//   next        same as a short press of NEXT
//   manual      same as holding NEXT for 5 s
//   0|off|12|48|72   manual select
//   ?           status and battery voltages

// ---------- display ----------
#define LCD_I2C 1          // 1 = I2C backpack module, 0 = parallel wiring
#define LCD_SOFT_SCL 7     // I2C display: 0 = SCL on A5 (hardware I2C, needs the library)
                           //              7 = SCL wire on D7 (software I2C, no library), SDA stays on A4
#define LCD_ADDR 0x27      // if the screen stays blank, try 0x3F
#if LCD_I2C && LCD_SOFT_SCL
  // Software I2C driver for a 16x2 LCD with PCF8574 backpack (RS=P0 RW=P1 E=P2 BL=P3 D4-D7=P4-P7)
  class SoftLcd : public Print {
   public:
    SoftLcd(uint8_t sda, uint8_t scl, uint8_t addr) : sda_(sda), scl_(scl), addr_(addr) {}
    void init() {
      rel(sda_); rel(scl_);
      delay(50);
      pcf(bl_);
      nib(0x3, 0); delay(5); nib(0x3, 0); delay(5); nib(0x3, 0); delayMicroseconds(200);
      nib(0x2, 0);
      cmd(0x28); cmd(0x0C); cmd(0x01); cmd(0x06);
    }
    void backlight() { bl_ = 0x08; pcf(bl_); }
    // Re-sync the 4-bit interface (no clear, no flicker). A glitch on the wires can leave the
    // display half a byte out of step, which shows as garbage; this puts it back in step.
    void resync() {
      nib(0x3, 0); delay(5); nib(0x3, 0); delayMicroseconds(150); nib(0x3, 0); nib(0x2, 0);
      cmd(0x28); cmd(0x0C); cmd(0x06);
    }
    void clear() { cmd(0x01); }
    void setCursor(uint8_t col, uint8_t row) { cmd(0x80 | (col + (row ? 0x40 : 0))); }
    size_t write(uint8_t c) override { send(c, 0x01); return 1; }
    using Print::write;
   private:
    uint8_t sda_, scl_, addr_, bl_ = 0x08;
    static void rel(uint8_t p) { pinMode(p, INPUT); }                       // released: pulled up by the backpack
    static void low(uint8_t p) { digitalWrite(p, LOW); pinMode(p, OUTPUT); }
    static void dly() { delayMicroseconds(10); }                          // slow and robust
    void start() { rel(sda_); rel(scl_); dly(); low(sda_); dly(); low(scl_); dly(); }
    void stop() { low(sda_); dly(); rel(scl_); dly(); rel(sda_); dly(); }
    void byteOut(uint8_t b) {
      for (int8_t i = 7; i >= 0; i--) {
        if (b & (1 << i)) rel(sda_); else low(sda_);
        dly(); rel(scl_); dly(); low(scl_);
      }
      rel(sda_); dly(); rel(scl_); dly(); low(scl_); dly();                  // ACK clock (not checked)
    }
    void pcf(uint8_t v) { start(); byteOut(addr_ << 1); byteOut(v); stop(); }
    void nib(uint8_t n, uint8_t rs) {
      uint8_t v = (n << 4) | rs | bl_;
      pcf(v | 0x04); pcf(v); delayMicroseconds(40);
    }
    void send(uint8_t b, uint8_t rs) { nib(b >> 4, rs); nib(b & 0x0F, rs); }
    void cmd(uint8_t c) { send(c, 0); if (c < 4) delay(2); }
  };
  SoftLcd lcd(A4, LCD_SOFT_SCL, LCD_ADDR);
#elif LCD_I2C
  // Library: "LiquidCrystal I2C" by Frank de Brabander (Library Manager)
  #include <Wire.h>
  #include <LiquidCrystal_I2C.h>
  LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);
#else
  #include <LiquidCrystal.h>              // built in
  LiquidCrystal lcd(7, 8, 9, 10, 11, 12); // RS, E, D4, D5, D6, D7
#endif
const unsigned long LCD_MS = 500;
const unsigned long LCD_PAGE_MS = 2000;

struct Bank {
  const char *name;
  uint8_t gatePin;
  uint8_t adcPin;
  float ratio;     // (Rtop + Rbottom) / Rbottom
  float fullV;     // set ~0.2 V per 12 V below your charger's absorption voltage
  float resumeV;   // battery counts as "needs charge" again below this
};

// Lead-acid / AGM defaults. LiFePO4: 12 V -> 14.0 / 13.2, 48 V (16s) -> 56.0 / 52.8
const Bank BANK[3] = {
  {"12V", 2, A0, (33.0 + 10.0) / 10.0, 14.2, 12.4},
  {"48V", 3, A1, (150.0 + 10.0) / 10.0, 56.8, 49.6},
  {"72V", 4, A2, (220.0 + 10.0) / 10.0, 85.2, 74.4},
};
float CAL[3] = {1.000, 1.000, 1.000};   // tune so readings match a multimeter

const unsigned long DEAD_TIME_MS = 10000;                 // all relays off for 10 s between batteries
const unsigned long FULL_HOLD_MS = 10UL * 60UL * 1000UL;   // 10 minutes
const unsigned long SAMPLE_MS = 1000;
const unsigned long REPORT_MS = 60UL * 1000UL;

int8_t activeCh = -1;      // -1 = no charger connected
int8_t pendingCh = -1;
bool waiting = false;
unsigned long offAt = 0;

enum Mode : uint8_t { MODE_AUTO, MODE_MANUAL, MODE_TIMER };
Mode mode = MODE_TIMER;                   // power-up starts the TIMER sequence

// ---------- push buttons ----------
const uint8_t BTN_AUTO = 5, BTN_NEXT = 6, BTN_TIMER = A3;
const uint8_t BTN_PIN[3] = {BTN_AUTO, BTN_NEXT, BTN_TIMER};
const unsigned long DEBOUNCE_MS = 30;
bool btnStable[3] = {HIGH, HIGH, HIGH};
bool btnLast[3] = {HIGH, HIGH, HIGH};
unsigned long btnChanged[3] = {0, 0, 0};

// ---------- mode LEDs ----------
#if LCD_I2C
const uint8_t MODE_LED_WHITE = 9, MODE_LED_RED = 8;     // D7-D12 are free with the I2C display
#else
const uint8_t MODE_LED_WHITE = A4, MODE_LED_RED = A5;   // D7-D12 drive the parallel display
#endif

// ---------- timer sequence ----------
unsigned int timer12Min = 180;            // TIMER step 1: 12 V for 3 hours ("timer N" changes it)
uint8_t timerStage = 0;                   // 0 = 12 V timed, 1 = 48 V until full, 2 = 72 V until full
unsigned long timerStart = 0;
unsigned long timerMs() { return timer12Min * 60000UL; }

// ---------- NEXT long press ----------
const unsigned long LONG_PRESS_MS = 5000;
unsigned long nextDownAt = 0;
bool nextLongDone = false;

bool full[3] = {false, false, false};
bool above[3] = {false, false, false};
unsigned long aboveSince[3] = {0, 0, 0};
float volts[3] = {0, 0, 0};
unsigned long lastSample = 0, lastReport = 0;
unsigned long lastLcd = 0, lastPage = 0;
uint8_t lcdPage = 0;
bool interlockFault = false;

char rxBuf[12];
uint8_t rxLen = 0;

// ---------- measurement ----------
long readVcc_mV() {                       // measure 5 V rail against the 1.1 V bandgap
  ADMUX = _BV(REFS0) | _BV(MUX3) | _BV(MUX2) | _BV(MUX1);
  delay(2);
  ADCSRA |= _BV(ADSC);
  while (bit_is_set(ADCSRA, ADSC));
  long r = ADCL;
  r |= (long)ADCH << 8;
  return r ? 1125300L / r : 5000;
}

float readBank(uint8_t i, long vcc) {
  analogRead(BANK[i].adcPin);             // settle the mux
  long sum = 0;
  for (uint8_t n = 0; n < 16; n++) sum += analogRead(BANK[i].adcPin);
  float vPin = (sum / 16.0) * (vcc / 1000.0) / 1023.0;
  return vPin * BANK[i].ratio * CAL[i];
}

// ---------- switching ----------
void allOff() {
  for (uint8_t i = 0; i < 3; i++) digitalWrite(BANK[i].gatePin, LOW);
  activeCh = -1;
}

bool allGatesLow() {
  for (uint8_t i = 0; i < 3; i++)
    if (digitalRead(BANK[i].gatePin) == HIGH) return false;
  return true;
}

void requestChannel(int8_t ch) {
  if (ch == activeCh && !waiting) return;
  allOff();                               // break first
  offAt = millis();
  for (uint8_t i = 0; i < 3; i++) above[i] = false;
  if (ch < 0) {
    waiting = false;
    Serial.println(F("All chargers disconnected"));
    return;
  }
  pendingCh = ch;
  waiting = true;
  Serial.print(F("Opening all relays, waiting "));
  Serial.print(DEAD_TIME_MS / 1000);
  Serial.print(F(" s, then "));
  Serial.println(BANK[ch].name);
}

int8_t pickNext() {
  if (activeCh >= 0 && !full[activeCh]) return activeCh;
  int8_t start = activeCh < 0 ? 0 : activeCh + 1;
  for (uint8_t k = 0; k < 3; k++) {
    int8_t i = (start + k) % 3;
    if (!full[i]) return i;
  }
  return activeCh;                        // all full: keep floating the current one
}


const __FlashStringHelper *modeName() {
  if (mode == MODE_AUTO) return F("AUTO");
  if (mode == MODE_TIMER) return F("TIMER");
  return F("MANUAL");
}

// ---------- reporting ----------
void printVolts() {
  for (uint8_t i = 0; i < 3; i++) {
    Serial.print(BANK[i].name);
    Serial.print(F(": "));
    Serial.print(volts[i], 2);
    Serial.print(F(" V"));
    if (full[i]) Serial.print(F(" FULL"));
    if (i == activeCh) Serial.print(F(" <charging>"));
    Serial.print(i < 2 ? F("  |  ") : F("\n"));
  }
}

void printStatus() {
  Serial.print('[');
  Serial.print(modeName());
  if (mode == MODE_TIMER) {
    Serial.print(F(" step "));
    Serial.print(timerStage + 1);
    if (timerStage == 0) {
      unsigned long el = millis() - timerStart;
      Serial.print(F(", 12V min left "));
      Serial.print(el >= timerMs() ? 0 : (timerMs() - el) / 60000UL + 1);
    } else Serial.print(F(", until full"));
  }
  Serial.print(F("] "));
  if (waiting) {
    Serial.print(F("dead time, next = "));
    Serial.println(BANK[pendingCh].name);
  } else if (activeCh < 0) {
    Serial.println(F("all chargers disconnected"));
  } else {
    Serial.print(BANK[activeCh].name);
    Serial.println(F(" charger connected"));
  }
  printVolts();
}

// ---------- LCD ----------
void lcdBegin() {
#if LCD_I2C
  lcd.init();
  lcd.backlight();
#else
  lcd.begin(16, 2);
#endif
  lcd.clear();
  lcd.print(F("Solar selector"));
  lcd.setCursor(0, 1);
  lcd.print(F("starting..."));
}

void lcdRow(uint8_t row, char *s) {
  uint8_t n = strlen(s);
  while (n < 16) s[n++] = ' ';           // pad so old characters are overwritten
  s[16] = '\0';
  lcd.setCursor(0, row);
  lcd.print(s);
}

void updateLcd(unsigned long now) {
  char l1[17], l2[17], v[8], st[8], m[8];
  if (mode == MODE_AUTO) strcpy(m, "AUTO  ");
  else if (mode == MODE_MANUAL) strcpy(m, "MANUAL");
  else strcpy(m, "TIMER ");

  bool holding = btnStable[1] == LOW && !nextLongDone && now - nextDownAt >= 1000;
  if (interlockFault) snprintf(l1, sizeof l1, "INTERLOCK FAULT");
  else if (holding && mode != MODE_MANUAL) {
    unsigned long left = (LONG_PRESS_MS - (now - nextDownAt) + 999) / 1000;
    snprintf(l1, sizeof l1, "HOLD %lus->MANUAL", left);
  }
  else if (waiting) {
    unsigned long el = now - offAt;
    unsigned long left = el >= DEAD_TIME_MS ? 0 : (DEAD_TIME_MS - el + 999) / 1000;
    snprintf(l1, sizeof l1, "%s >>%s %2lus", m, BANK[pendingCh].name, left);
  }
  else if (activeCh < 0) snprintf(l1, sizeof l1, "%s ALL OFF", m);
  else snprintf(l1, sizeof l1, "%s CHG %s", m, BANK[activeCh].name);

  uint8_t p = lcdPage;
  dtostrf(volts[p], 4, 1, v);            // e.g. "13.6", "55.2"
  if (p == activeCh && !waiting) {
    if (full[p]) strcpy(st, "FLOAT");
    else if (mode == MODE_TIMER && timerStage == 0) {   // time left on the 12 V step, e.g. T2h59
      unsigned long el = now - timerStart;
      unsigned long left = el >= timerMs() ? 0 : (timerMs() - el) / 60000UL + 1;
      snprintf(st, sizeof st, "T%luh%02lu", left / 60, left % 60);
    } else if (above[p] && now - aboveSince[p] < FULL_HOLD_MS) {
      unsigned long left = (FULL_HOLD_MS - (now - aboveSince[p])) / 60000UL + 1;
      snprintf(st, sizeof st, "CHG%2lum", left);
    } else strcpy(st, "CHG");
  } else if (full[p]) strcpy(st, "FULL");
  else if (volts[p] < BANK[p].resumeV) strcpy(st, "LOW");
  else strcpy(st, "WAIT");
  snprintf(l2, sizeof l2, "%s %sV %s", BANK[p].name, v, st);

#if LCD_I2C && LCD_SOFT_SCL
  lcd.resync();
#endif
  lcdRow(0, l1);
  lcdRow(1, l2);
}

// ---------- timer sequence ----------
void timerAdvance(const __FlashStringHelper *why) {
  while (true) {
    timerStage++;
    if (timerStage > 2) {
      timerStage = 2;
      mode = MODE_AUTO;
      Serial.println(F("TIMER: sequence done, continuing in AUTO"));
      return;
    }
    if (!full[timerStage]) break;
    Serial.print(F("TIMER: "));
    Serial.print(BANK[timerStage].name);
    Serial.println(F(" already full, skipped"));
  }
  Serial.print(F("TIMER: "));
  Serial.print(why);
  Serial.print(F(", step "));
  Serial.print(timerStage + 1);
  Serial.print(F(" = "));
  Serial.print(BANK[timerStage].name);
  Serial.println(F(" until full"));
  requestChannel(timerStage);
}

void timerFollow(unsigned long now) {
  if (timerStage == 0 && now - timerStart >= timerMs()) { timerAdvance(F("12V time is up")); return; }
  if (timerStage > 0 && full[timerStage]) { timerAdvance(F("battery full")); return; }
  if (activeCh != (int8_t)timerStage) requestChannel(timerStage);   // keep this step's battery connected
}

// ---------- auto logic ----------
void autoStep() {
  unsigned long now = millis();
  long vcc = readVcc_mV();
  for (uint8_t i = 0; i < 3; i++) volts[i] = readBank(i, vcc);

  // full detection on the battery being charged
  if (activeCh >= 0 && !waiting) {
    uint8_t i = activeCh;
    if (volts[i] >= BANK[i].fullV) {
      if (!above[i]) { above[i] = true; aboveSince[i] = now; }
      else if (!full[i] && now - aboveSince[i] >= FULL_HOLD_MS) {
        full[i] = true;
        Serial.print(BANK[i].name);
        Serial.println(F(" battery FULL"));
      }
    } else {
      above[i] = false;
    }
  }
  // a full battery that has been used again needs charging
  for (uint8_t i = 0; i < 3; i++) {
    if (full[i] && volts[i] < BANK[i].resumeV) {
      full[i] = false;
      Serial.print(BANK[i].name);
      Serial.println(F(" battery needs charge again"));
    }
  }
  if (waiting) return;
  if (mode == MODE_AUTO) {
    int8_t next = pickNext();
    if (next != activeCh) {
      Serial.print(F("AUTO: switching to "));
      Serial.println(next >= 0 ? BANK[next].name : "none");
      requestChannel(next);
    }
  } else if (mode == MODE_TIMER) {
    timerFollow(now);
  }
}

// ---------- modes ----------
void setAuto() {
  mode = MODE_AUTO;
  Serial.println(F("AUTO mode"));
}

void setTimer() {                         // start (or restart) the sequence at step 1
  mode = MODE_TIMER;
  timerStage = 0;
  timerStart = millis();
  Serial.print(F("TIMER: step 1 = 12V for "));
  Serial.print(timer12Min);
  Serial.println(F(" min, then 48V until full, then 72V until full"));
  requestChannel(0);
}

void manual(int8_t ch) {
  if (mode != MODE_MANUAL) Serial.println(F("MANUAL mode (press AUTO or TIMER to leave)"));
  mode = MODE_MANUAL;
  requestChannel(ch);
}

void enterManual() {                      // NEXT held 5 s: keep the battery that is connected now
  if (mode == MODE_MANUAL) return;
  mode = MODE_MANUAL;
  Serial.println(F("MANUAL mode (NEXT held 5 s). NEXT = next battery, AUTO or TIMER to leave"));
}

void swapNext() {                         // NEXT short press
  int8_t cur = waiting ? pendingCh : activeCh;
  if (mode == MODE_MANUAL) {              // 12 -> 48 -> 72 -> OFF -> 12
    int8_t n = cur >= 2 ? -1 : cur + 1;
    Serial.print(F("MANUAL: NEXT -> "));
    Serial.println(n < 0 ? "OFF" : BANK[n].name);
    requestChannel(n);
  } else if (mode == MODE_TIMER) {
    timerAdvance(F("NEXT pressed"));
  } else {                                // AUTO: next battery in order that is not full
    int8_t start = cur < 0 ? 0 : cur + 1;
    int8_t n = start % 3;
    for (uint8_t k = 0; k < 3; k++) {
      int8_t i = (start + k) % 3;
      if (!full[i]) { n = i; break; }
    }
    Serial.print(F("AUTO: NEXT -> "));
    Serial.println(BANK[n].name);
    requestChannel(n);
  }
}

void updateModeLeds() {
  digitalWrite(MODE_LED_WHITE, mode == MODE_AUTO ? HIGH : LOW);
  digitalWrite(MODE_LED_RED, mode == MODE_TIMER ? HIGH : LOW);
}

void readButtons(unsigned long now) {
  for (uint8_t b = 0; b < 3; b++) {
    bool r = digitalRead(BTN_PIN[b]);
    if (r != btnLast[b]) { btnLast[b] = r; btnChanged[b] = now; }
    if (now - btnChanged[b] >= DEBOUNCE_MS && r != btnStable[b]) {
      btnStable[b] = r;
      if (b == 1) {                       // NEXT: short press = swap, hold 5 s = MANUAL
        if (r == LOW) { nextDownAt = now; nextLongDone = false; }
        else if (!nextLongDone) swapNext();
      } else if (r == LOW) {
        if (b == 0) setAuto();
        else setTimer();
      }
      lastLcd = 0;                        // refresh the display now
    }
  }
  if (btnStable[1] == LOW && !nextLongDone && now - nextDownAt >= LONG_PRESS_MS) {
    nextLongDone = true;
    enterManual();
    lastLcd = 0;
  }
}

// ---------- serial ----------
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
  else if (!strcmp(cmd, "?")) printStatus();
  else Serial.println(F("Commands: auto, timer, timer N, next, manual, 0/off, 12, 48, 72, ?"));
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      rxBuf[rxLen] = '\0';
      if (rxLen) handleCommand(rxBuf);
      rxLen = 0;
    } else if (rxLen < sizeof(rxBuf) - 1) {
      rxBuf[rxLen++] = c;
    }
  }
}

void setup() {
  for (uint8_t i = 0; i < 3; i++) {
    digitalWrite(BANK[i].gatePin, LOW);   // latch LOW before the pin becomes an output
    pinMode(BANK[i].gatePin, OUTPUT);
  }
  for (uint8_t b = 0; b < 3; b++) pinMode(BTN_PIN[b], INPUT_PULLUP);
  pinMode(MODE_LED_WHITE, OUTPUT);
  pinMode(MODE_LED_RED, OUTPUT);
  updateModeLeds();
  Serial.begin(9600);
  lcdBegin();
  Serial.println(F("Solar selector ready (TIMER). AUTO D5, TIMER A3, NEXT D6 (hold 5 s = MANUAL). 10 s relay pause"));
  Serial.println(F("Commands: auto, timer, timer N, next, manual, 0/off, 12, 48, 72, ?"));
  setTimer();                             // always start with the TIMER sequence (12V first)
}

void loop() {
  unsigned long now = millis();

  if (waiting && now - offAt >= DEAD_TIME_MS) {
    if (allGatesLow()) {                  // interlock check before making
      digitalWrite(BANK[pendingCh].gatePin, HIGH);
      activeCh = pendingCh;
      interlockFault = false;
      Serial.print(BANK[activeCh].name);
      Serial.println(F(" charger connected"));
    } else {
      allOff();
      interlockFault = true;
      Serial.println(F("Interlock fault: gate still HIGH, all off"));
    }
    waiting = false;
  }

  readButtons(now);
  updateModeLeds();

  if (now - lastPage >= LCD_PAGE_MS) {
    lastPage = now;
    lcdPage = (lcdPage + 1) % 3;
  }
  if (now - lastLcd >= LCD_MS && now >= SAMPLE_MS) {
    lastLcd = now;
    updateLcd(now);
  }

  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    autoStep();
  }
  if (now - lastReport >= REPORT_MS) {
    lastReport = now;
    printVolts();
  }
  readSerial();
}
