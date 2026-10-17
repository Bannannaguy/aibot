#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

void setup() {
  Serial.begin(9600);
  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(60);
  delay(10);
}

void loop() {
  // --- SECTION 1: Servos on Pin 2 and Pin 5 ---
  Serial.println("Pins 2 & 5: Moving to 90 degrees");
  pwm.setPWM(2, 0, 245);
  pwm.setPWM(5, 0, 455);
  delay(1000);

  // --- SECTION 2: Servos on Pin 0 and Pin 3 ---
  Serial.println("Pins 0 & 3: Moving to 0 degrees"); // Fixed print message
  pwm.setPWM(0, 0, 90);
  pwm.setPWM(3, 0, 90);
  delay(1000);

  Serial.println("Pins 0 & 3: Moving to ~45 degrees"); // Fixed print message
  pwm.setPWM(0, 0, 130);
  pwm.setPWM(3, 0, 130);
  delay(1000);

  // --- SECTION 3: Servos on Pin 1 and Pin 4 ---
  Serial.println("Pins 1 & 4: Moving to 0 degrees"); // Fixed print message
  pwm.setPWM(1, 0, 90);
  pwm.setPWM(4, 0, 90);
  delay(1000);

  // --- SECTION 4: Servos on Pin 1 and Pin 3 ---
  Serial.println("Pins 1 & 3: Moving to ~45 degrees"); // Fixed print message
  pwm.setPWM(1, 0, 130);
  pwm.setPWM(3, 0, 130);
  delay(1000);

  // --- SECTION 5: Servos on Pin 2 and Pin 5 ---
  Serial.println("Pins 2 & 5: Moving to 180 degrees");
  pwm.setPWM(2, 0, 405);
  pwm.setPWM(5, 0, 205);
  delay(1000);
}
