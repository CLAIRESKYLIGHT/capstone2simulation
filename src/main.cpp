#include <Arduino.h>
#define ROLE_PIN 4

void setup() {
  Serial.begin(115200);
  pinMode(ROLE_PIN, INPUT);
  delay(100);
  if (digitalRead(ROLE_PIN) == LOW) {
    Serial.println("I AM BOARD 1");
  } else {
    Serial.println("I AM BOARD 2");
  }
}

void loop() {
  Serial.println("heartbeat");
  delay(2000);
}