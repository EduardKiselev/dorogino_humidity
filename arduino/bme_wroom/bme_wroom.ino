#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(5000);  // ← Было 100, стало 500 мс — критично для стабильности!
  Serial.println("\n=== Сканер I2C ===");
  
  Wire.begin(21, 22);
  
  byte error, address;
  int nDevices = 0;
  
  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();
    if (error == 0) {
      Serial.print("Найден датчик по адресу 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
      nDevices++;
    }
    delay(1);  // ← Добавьте эту задержку в цикл сканирования
  }
  
  if (nDevices == 0) {
    Serial.println("✗ Ничего не найдено");
  } else {
    Serial.println("✓ Датчик обнаружен!");
  }
}

void loop() {}