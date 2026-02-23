#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>

// === НАСТРОЙКИ ===
const char* ssid = "ElSenorNegro";
const char* password = "pomidorka38";
const int timeDelay = 60000;

#define DHTPIN 25
#define DHTTYPE DHT22 
#define SENSOR_ID 1

const char* server = "192.168.10.100";
const int serverPort = 5000;
const char* endpoint = "/data";

DHT dht(DHTPIN, DHTTYPE);
WiFiClient wifiClient;

void setup() {
  Serial.begin(9600);
  delay(1000);
  dht.begin();
  
  WiFi.begin(ssid, password);
  unsigned long timeout = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - timeout < 30000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nWi-Fi Error");
    return;
  }
  Serial.println("\nWi-Fi Connected");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(5000);
    return;
  }

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  if (isnan(temperature) || isnan(humidity)) {
    delay(1000); // DHT22 медленнее DHT11
    temperature = dht.readTemperature();
    humidity = dht.readHumidity();
  }

  if (isnan(temperature) || isnan(humidity)) {
    delay(2000);
    return;
  }

  String json = "{\"sensor_id\":" + String(SENSOR_ID) +
                ",\"temperature\":" + String(temperature, 1) +
                ",\"humidity\":" + String(humidity, 1) + "}";

  HTTPClient http;
  String url = "http://" + String(server) + ":" + String(serverPort) + String(endpoint);
  
  if (http.begin(wifiClient, url)) {
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(json);
    Serial.print("HTTP Code: ");
    Serial.println(code);
    http.end();
  }

  delay(timeDelay);
}