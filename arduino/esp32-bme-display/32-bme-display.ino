#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "esp_system.h"  // esp_random()

// === НАСТРОЙКИ ===
const char* ssid = "ElSenorNegro";
const char* password = "pomidorka38";
const int timeDelay = 60000;

#define SENSOR_ID 3
#define I2C_SDA 21
#define I2C_SCL 22

// Сервера (массив для совместимости)
const char* servers[] = {"192.168.10.100", "192.168.10.101"};
const int SERVER_COUNT = 2;
const int serverPort = 5000;
const char* endpoint = "/data";

// OLED
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDRESS 0x3C

// Глобальные переменные
TwoWire I2C_BME = TwoWire(0);
Adafruit_BME280 bme;
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &I2C_BME, OLED_RESET);
WiFiClient wifiClient;
bool bmeReady = false;
String sessionPUID;

// === Генерация сессионного PUID (32 бита) ===
String generateSessionPUID() {
  char buf[16];
  snprintf(buf, sizeof(buf), "%08X", esp_random());
  return String(buf);
}

// === Инициализация BME280 ===
bool initBME() {
  I2C_BME.begin(I2C_SDA, I2C_SCL, 400000);
  if (bme.begin(0x76, &I2C_BME) || bme.begin(0x77, &I2C_BME)) {
    Serial.println("✓ BME280 найден");
    return true;
  }
  Serial.println("✗ BME280 не найден");
  return false;
}

// === Отправка на один сервер ===
bool sendToServer(const char* host, const String& json) {
  HTTPClient http;
  String url = "http://" + String(host) + ":" + String(serverPort) + String(endpoint);
  
  Serial.print("  → ");
  Serial.print(host);
  
  if (http.begin(wifiClient, url)) {
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(json);
    Serial.print(" [");
    Serial.print(code);
    Serial.println("]");
    http.end();
    return (code == 200 || code == 201);
  } else {
    Serial.println(" [HTTP ERROR]");
    return false;
  }
}

// === Обновление OLED ===
void updateDisplay(float h, float t, float p) {
  display.clearDisplay();
  display.setTextSize(4);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.print(h, 1);
  display.println("%");
  
  display.setTextSize(1);
  display.setCursor(0, 48);
  display.print("T:");
  display.print(t, 1);
  display.print("C  P:");
  display.print(p, 0);
  display.println(" hPa");
  display.display();
}

void setup() {
  Serial.begin(9600);
  delay(1000);
  Serial.println("\n=== ESP32 BME280 + OLED ===");

  // OLED
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
    Serial.println("✗ OLED ошибка");
    for (;;);
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Загрузка...");
  display.display();

  // PUID сессии
  sessionPUID = generateSessionPUID();
  Serial.print("Session PUID: ");
  Serial.println(sessionPUID);

  // BME
  int attempts = 0;
  while (!bmeReady && attempts < 5) {
    if (initBME()) bmeReady = true;
    else { attempts++; delay(1000); }
  }

  // Wi-Fi
  Serial.print("Wi-Fi: ");
  WiFi.begin(ssid, password);
  unsigned long timeout = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - timeout < 30000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? "OK" : "ERROR");
  
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println(WiFi.status() == WL_CONNECTED ? "Wi-Fi OK" : "Wi-Fi Error");
  display.display();
  delay(1000);
}

void loop() {
  // Переподключение Wi-Fi
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n⚠ Wi-Fi reconnect...");
    WiFi.reconnect();
    delay(5000);
    return;
  }

  // Восстановление BME
  if (!bmeReady) {
    if (initBME()) bmeReady = true;
    else { delay(2000); return; }
  }

  // Чтение данных
  float t = bme.readTemperature();
  float h = bme.readHumidity();
  float p = bme.readPressure() / 100.0F;

  if (isnan(t) || isnan(h) || isnan(p)) {
    Serial.println("✗ BME read error");
    bmeReady = false;
    delay(2000);
    return;
  }

  // OLED
  updateDisplay(h, t, p);

  // JSON: puid+ts в одном поле, без лишней запятой
  String json = "{"
                "\"puid\":\"" + sessionPUID + "-" + String(millis()) + "\","
                "\"sensor_id\":" + String(SENSOR_ID) + ","
                "\"temperature\":" + String(t, 1) + ","
                "\"humidity\":" + String(h, 1) + ","
                "\"pressure\":" + String(p, 1) +
                "}";

  Serial.println("\n→ Payload: " + json);

  // Отправка на все сервера
  for (int i = 0; i < SERVER_COUNT; i++) {
    sendToServer(servers[i], json);
    delay(100);
  }

  delay(timeDelay);
}