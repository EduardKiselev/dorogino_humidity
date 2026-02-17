#define DEBUG  // Удалите эту строку, чтобы отключить логи

#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <esp_sleep.h>

// === НАСТРОЙКИ ===
const char* ssid = "ElSenorNegro";
const char* password = "pomidorka38";
const uint64_t sleepTime = 60 * 1000000ULL; 

#define DHTPIN 26
#define DHTPWR 5
#define VBAT_PIN 34
#define SENSOR_ID 1

const char* server = "192.168.10.100";
const int serverPort = 5000;
const char* endpoint = "/data";

DHT dht(DHTPIN, DHT11);

void setup() {
  Serial.begin(115200);
  #ifdef DEBUG
    Serial.println("\n[START] Wake up");
  #endif

  pinMode(DHTPWR, OUTPUT);
  digitalWrite(DHTPWR, HIGH);
  delay(1000); 
  dht.begin();

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db); 

  int raw = analogRead(VBAT_PIN);
  float voltage = (raw / 4095.0) * 3.3 * 2.38; 
  
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();

  #ifdef DEBUG
    Serial.printf("Sensor: T=%.1f, H=%.1f, V=%.2f\n", temp, hum, voltage);
  #endif

  WiFi.begin(ssid, password);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    #ifdef DEBUG
      Serial.println("WiFi Connected");
    #endif
    delay(1000);

    HTTPClient http;
    http.setTimeout(2000);
    String url = "http://" + String(server) + ":" + serverPort + endpoint;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    
    String json = "{\"sensor_id\":" + String(SENSOR_ID) + 
                ",\"temperature\":" + String(temp, 1) + 
                ",\"humidity\":" + String(hum, 1) + 
                ",\"voltage\":" + String(voltage, 2) + "}";
    
    #ifdef DEBUG
      Serial.println("POST: " + json);
    #endif

    int code = http.POST(json);
    
    #ifdef DEBUG
      Serial.printf("HTTP Code: %d\n", code);
    #endif

    http.end();
    WiFi.disconnect(true);
  } else {
    #ifdef DEBUG
      Serial.println("WiFi Failed");
    #endif
  }

  digitalWrite(DHTPWR, LOW);
  
  #ifdef DEBUG
    Serial.println("Going to sleep...");
    Serial.flush();
  #endif

  esp_sleep_enable_timer_wakeup(sleepTime);
  esp_deep_sleep_start();
}

void loop() {}