#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include "esp_system.h"  // esp_random()

// === НАСТРОЙКИ ===
const char* ssid = "ElSenorNegro";
const char* password = "pomidorka38";
const int timeDelay = 60000;

#define DHTPIN 25
#define DHTTYPE DHT22
#define SENSOR_ID 1

// Сервера (массив для совместимости с BME версией)
const char* servers[] = {"192.168.10.100", "192.168.10.101"};
const int SERVER_COUNT = 2;
const int serverPort = 5000;
const char* endpoint = "/data";

// Глобальные переменные
DHT dht(DHTPIN, DHTTYPE);
WiFiClient wifiClient;
String sessionPUID;

// === Генерация сессионного PUID (32 бита) ===
String generateSessionPUID() {
  char buf[16];
  snprintf(buf, sizeof(buf), "%08X", esp_random());
  return String(buf);
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

void setup() {
  Serial.begin(9600);
  delay(2000);
  Serial.flush();
  
  Serial.println("\n=== ESP32 DHT22 Logger ===");

  // PUID сессии
  sessionPUID = generateSessionPUID();
  Serial.print("Session PUID: ");
  Serial.println(sessionPUID);

  // DHT
  dht.begin();
  Serial.println("✓ DHT22 инициализирован");

  // Wi-Fi
  Serial.print("Wi-Fi: ");
  WiFi.begin(ssid, password);
  unsigned long timeout = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - timeout < 30000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? "OK" : "ERROR");
}

void loop() {
  // Переподключение Wi-Fi
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n⚠ Wi-Fi reconnect...");
    WiFi.reconnect();
    delay(5000);
    return;
  }

  // Чтение данных
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  // Если ошибка — пробуем ещё раз (DHT22 медленный)
  if (isnan(temperature) || isnan(humidity)) {
    delay(2000);
    temperature = dht.readTemperature();
    humidity = dht.readHumidity();
    
    if (isnan(temperature) || isnan(humidity)) {
      Serial.println("✗ DHT read error");
      delay(2000);
      return;
    }
  }

  // JSON: puid+ts в одном поле, без лишней запятой
  String json = "{"
                "\"puid\":\"" + sessionPUID + "-" + String(millis()) + "\","
                "\"sensor_id\":" + String(SENSOR_ID) + ","
                "\"temperature\":" + String(temperature, 1) + ","
                "\"humidity\":" + String(humidity, 1) +
                "}";

  Serial.println("\n→ Payload: " + json);

  // Отправка на все сервера
  for (int i = 0; i < SERVER_COUNT; i++) {
    sendToServer(servers[i], json);
    delay(100);  // пауза между запросами
  }

  delay(timeDelay);
}