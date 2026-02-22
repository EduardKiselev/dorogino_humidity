#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>

// === НАСТРОЙКИ ===
const char* ssid = "ElSenorNegro";
const char* password = "pomidorka38";
const int timeDelay = 60000;

#define SENSOR_ID 3
#define I2C_SDA 21
#define I2C_SCL 22

const char* server = "192.168.10.100";
const int serverPort = 5000;
const char* endpoint = "/data";

TwoWire I2C_BME = TwoWire(0);
Adafruit_BME280 bme;
WiFiClient wifiClient;
bool bmeReady = false;

// Функция инициализации сенсора
bool initBME() {
  I2C_BME.begin(I2C_SDA, I2C_SCL, 400000);
  if (bme.begin(0x76, &I2C_BME) || bme.begin(0x77, &I2C_BME)) {
    Serial.println("✓ BME280 найден");
    return true;
  }
  Serial.println("✗ BME280 не найден");
  return false;
}

void setup() {
  Serial.begin(9600);
  delay(1000);
  Serial.println("\n=== ESP32 BME280 Logger ===");

  // Попытки инициализации BME (до 5 раз)
  int attempts = 0;
  while (!bmeReady && attempts < 5) {
    Serial.print("Попытка инициализации BME... ");
    if (initBME()) bmeReady = true;
    else {
      attempts++;
      delay(1000);
    }
  }

  // Wi-Fi
  Serial.print("Подключение к Wi-Fi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  unsigned long timeout = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - timeout < 30000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? "\n✓ Wi-Fi OK" : "\n✗ Wi-Fi Error");
}

void loop() {
  // Переподключение Wi-Fi
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n⚠ Wi-Fi отключён — переподключение...");
    WiFi.reconnect();
    delay(5000);
    return;
  }

  // Проверка/Восстановление BME
  if (!bmeReady) {
    Serial.println("⚠ Попытка восстановления BME...");
    if (initBME()) bmeReady = true;
    else {
      delay(2000);
      return;
    }
  }

  // Чтение данных
  float temperature = bme.readTemperature();
  float humidity = bme.readHumidity();
  float pressure = bme.readPressure() / 100.0F;

  if (isnan(temperature) || isnan(humidity) || isnan(pressure)) {
    Serial.println("✗ Ошибка чтения BME280");
    bmeReady = false; // Сброс флага для повторной инициализации
    delay(2000);
    return;
  }

  // JSON
  String json = "{\"sensor_id\":" + String(SENSOR_ID) +
                ",\"temperature\":" + String(temperature, 1) +
                ",\"humidity\":" + String(humidity, 1) +
                ",\"pressure\":" + String(pressure, 1) + "}";

  Serial.println("\n→ Отправка: " + json);

  // HTTP POST
  HTTPClient http;
  String url = "http://" + String(server) + ":" + String(serverPort) + String(endpoint);
  
  if (http.begin(wifiClient, url)) {
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(json);
    Serial.print("→ Код: ");
    Serial.println(code);
    http.end();
  } else {
    Serial.println("✗ HTTP ошибка");
  }

  delay(timeDelay);
}