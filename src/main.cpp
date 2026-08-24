// ============================================================
// SMART BARANGAY SYSTEM - Household Device (Phase 2)
// ESP32 + LCD + WiFi + NTP + BUZZER + RGB LED
// ============================================================

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ===== CONFIGURATION =====
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASSWORD ""
#define NTP_SERVER "pool.ntp.org"
#define UTC_OFFSET 0

// ===== PIN DEFINITIONS =====
#define BUZZER_PIN 12
#define LED_R 25
#define LED_G 26
#define LED_B 27

// ===== LCD SETUP =====
LiquidCrystal_I2C lcd(0x27, 16, 2);
char timeBuffer[20];
char dateBuffer[20];

// ===== LED STATE TRACKING =====
bool greenBlinkState = false;
unsigned long lastBlinkTime = 0;
const unsigned long BLINK_INTERVAL = 500;

// ===== FUNCTION: Set RGB LED Color =====
void setLED(bool r, bool g, bool b) {
  digitalWrite(LED_R, r ? HIGH : LOW);
  digitalWrite(LED_G, g ? HIGH : LOW);
  digitalWrite(LED_B, b ? HIGH : LOW);
}

void ledOff()     { setLED(false, false, false); }
void ledRed()     { setLED(true,  false, false); }
void ledGreen()   { setLED(false, true,  false); }
void ledBlue()    { setLED(false, false, true ); }
void ledYellow()  { setLED(true,  true,  false); }

// ===== FUNCTION: Update idle blinking green LED =====
void updateIdleLED() {
  if (millis() - lastBlinkTime >= BLINK_INTERVAL) {
    lastBlinkTime = millis();
    greenBlinkState = !greenBlinkState;
    if (greenBlinkState) {
      ledGreen();
    } else {
      ledOff();
    }
  }
}

// ===== FUNCTION: Play Alert Sounds =====
void playAlert(int type) {
  if (type == 1) {
    for (int i = 0; i < 5; i++) {
      tone(BUZZER_PIN, 1000, 200);
      delay(300);
    }
  } else if (type == 2) {
    for (int i = 0; i < 2; i++) {
      tone(BUZZER_PIN, 600, 300);
      delay(400);
    }
  } else if (type == 3) {
    tone(BUZZER_PIN, 400, 200);
    delay(200);
  } else if (type == 4) {
    tone(BUZZER_PIN, 523, 150);
    delay(200);
    tone(BUZZER_PIN, 659, 150);
    delay(200);
    tone(BUZZER_PIN, 784, 300);
  } else {
    tone(BUZZER_PIN, 300, 100);
    delay(100);
  }
}

// ===== FUNCTION: Connect to WiFi =====
void connectWiFi() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Connecting to");
  lcd.setCursor(0, 1);
  lcd.print("WiFi...");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    ledYellow();
    delay(250);
    ledOff();
    delay(250);
    attempts++;
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi Connected!");
    Serial.print("   IP: ");
    Serial.println(WiFi.localIP());

    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("✅ Connected!");
    lcd.setCursor(0, 1);
    lcd.print("IP: ");
    lcd.print(WiFi.localIP().toString().substring(0, 12));
    playAlert(4);
    delay(2000);
  } else {
    ledRed();
  }
}

// ===== FUNCTION: Get Time from NTP =====
void getTime() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Updating Time");
  lcd.setCursor(0, 1);
  lcd.print("Please wait...");

  configTime(UTC_OFFSET, 0, NTP_SERVER);

  struct tm timeinfo;
  int attempts = 0;
  while (!getLocalTime(&timeinfo) && attempts < 10) {
    delay(500);
    attempts++;
    Serial.print(".");
  }

  if (attempts < 10) {
    Serial.println("\n✅ Time Synced!");
    playAlert(4);
  }
}

// ===== FUNCTION: Display Time on LCD =====
void displayTime() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    lcd.setCursor(0, 1);
    lcd.print("Time Error");
    return;
  }

  strftime(timeBuffer, sizeof(timeBuffer), "%H:%M:%S", &timeinfo);
  strftime(dateBuffer, sizeof(dateBuffer), "%d/%m/%Y", &timeinfo);

  lcd.setCursor(0, 0);
  lcd.print(timeBuffer);

  lcd.setCursor(0, 1);
  lcd.print(dateBuffer);
  lcd.print("   ");
}

// ===== FUNCTION: Display Announcement with Sound =====
void displayAnnouncement(String message, int alertType) {
  if (alertType == 1) {
    for (int i = 0; i < 6; i++) {
      ledRed();
      delay(150);
      ledOff();
      delay(150);
    }
  } else {
    ledBlue();
  }

  playAlert(alertType);

  lcd.clear();
  lcd.setCursor(0, 0);

  if (alertType == 1) {
    lcd.print("🚨 EMERGENCY!");
  } else if (alertType == 2) {
    lcd.print("⚠️ WARNING!");
  } else {
    lcd.print("📢 ANNOUNCEMENT");
  }

  lcd.setCursor(0, 1);

  Serial.print("ANNOUNCE:");
  Serial.println(message);

  if (message.length() > 16) {
    lcd.print(message.substring(0, 16));
    delay(1500);
    lcd.setCursor(0, 1);
    lcd.print(message.substring(16, message.length()));
    delay(1500);
  } else {
    lcd.print(message);
    delay(3000);
  }

  lcd.clear();
}

// ===== FUNCTION: Receive announcement from gateway =====
void handleIncomingAnnouncement() {
  if (Serial.available()) {
    String message = Serial.readStringUntil('\n');
    message.trim();

    if (message.length() > 0) {
      displayAnnouncement(message, 3);
    }
  }
}

// ===== SETUP =====
void setup() {
  Serial.begin(115200);

  Serial.println("\n========================================");
  Serial.println("  SMART BARANGAY ANNOUNCEMENT SYSTEM");
  Serial.println("  Household Device - Phase 2 (with Buzzer + LED)");
  Serial.println("========================================\n");

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);
  ledOff();

  lcd.init();
  lcd.backlight();
  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Barangay Otavi");
  lcd.setCursor(0, 1);
  lcd.print("Smart Device");
  playAlert(4);
  delay(2000);

  connectWiFi();

  if (WiFi.status() == WL_CONNECTED) {
    getTime();
  }

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("✅ System Ready");
  lcd.setCursor(0, 1);
  lcd.print("Barangay Otavi");
  playAlert(3);
  delay(2000);

  Serial.println("✅ System Ready!");
  Serial.println("   Waiting for announcements...");
}

// ===== LOOP =====
void loop() {
  displayTime();
  updateIdleLED();
  handleIncomingAnnouncement();
  delay(100);
}