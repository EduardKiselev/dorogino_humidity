#define DEBUG
#include <WiFi.h>
#include <HTTPClient.h>

// === НАСТРОЙКИ ===
const char* ssid = "ElSenorNegro";
const char* password = "pomidorka38";
const uint32_t interval = 60000; // 60 секунд

#define VBAT_PIN 34
#define SENSOR_ID 10

const char* server = "192.168.10.100";
const int serverPort = 5000;
const char* endpoint = "/data";

void setup() {
  Serial.begin(115200);
  #ifdef DEBUG
    Serial.println("\n[START] System Ready (Mock Data)");
  #endif

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db); 

  WiFi.begin(ssid, password);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    attempts++;
  }
  
  #ifdef DEBUG
    if (WiFi.status() == WL_CONNECTED) Serial.println("WiFi Connected");
    else Serial.println("WiFi Failed");
  #endif
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    #ifdef DEBUG
      Serial.println("Reconnecting WiFi...");
    #endif
    WiFi.disconnect();
    WiFi.begin(ssid, password);
    delay(5000);
    if (WiFi.status() != WL_CONNECTED) {
      delay(interval);
      return;
    }
  }

  // Замеры напряжения
  int raw = analogRead(VBAT_PIN);
  float voltage = (raw / 4095.0) * 3.3 * 2.38; 
  
  // Фиксированные данные для теста
  float temp = 50.0;
  float hum = 50.0;

  #ifdef DEBUG
    Serial.printf("Mock: T=%.1f, H=%.1f, V=%.2f\n", temp, hum, voltage);
  #endif

  // Отправка
  HTTPClient http;
  http.setTimeout(2000);
  String url = "http://" + String(server) + ":" + serverPort + endpoint;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  
  String json = "{\"sensor_id\":" + String(SENSOR_ID) + 
              ",\"temperature\":" + String(temp, 1) + 
              ",\"humidity\":" + String(hum, 1) + 
              ",\"voltage\":" + String(voltage, 2) + "}";
  
  int code = http.POST(json);
  #ifdef DEBUG
    Serial.printf("HTTP Code: %d\n", code);
  #endif
  http.end();

  delay(interval);
}