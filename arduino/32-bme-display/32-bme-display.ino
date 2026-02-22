#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

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

// OLED
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1

TwoWire I2C_BME = TwoWire(0);
Adafruit_BME280 bme;
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &I2C_BME, OLED_RESET);

WiFiClient wifiClient;
bool bmeReady = false;

bool initBME() {
  I2C_BME.begin(I2C_SDA, I2C_SCL, 400000);
  if (bme.begin(0x76, &I2C_BME) || bme.begin(0x77, &I2C_BME)) {
    return true;
  }
  return false;
}

void setup() {
  Serial.begin(9600);
  delay(1000);
  Serial.println("\n=== ESP32 BME280 + OLED ===");

  // OLED
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("✗ OLED ошибка");
    for (;;);
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Загрузка...");
  display.display();

  // BME
  int attempts = 0;
  while (!bmeReady && attempts < 5) {
    if (initBME()) bmeReady = true;
    else { attempts++; delay(1000); }
  }

  // Wi-Fi
  WiFi.begin(ssid, password);
  unsigned long timeout = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - timeout < 30000) {
    delay(500);
  }
  
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println(WiFi.status() == WL_CONNECTED ? "Wi-Fi OK" : "Wi-Fi Error");
  display.display();
  delay(1000);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(5000);
    return;
  }

  if (!bmeReady) {
    if (initBME()) bmeReady = true;
    else { delay(2000); return; }
  }

  float t = bme.readTemperature();
  float h = bme.readHumidity();
  float p = bme.readPressure() / 100.0F;

  if (isnan(t) || isnan(h) || isnan(p)) {
    bmeReady = false;
    delay(2000);
    return;
  }

  // OLED Display
  display.clearDisplay();
  display.setTextSize(3);
  display.setCursor(0, 0);
  display.print(t, 1); display.println(" C");
  display.print(h, 1); display.println(" %");
  display.setTextSize(1);
  display.print("P: "); display.println(p, 0);
  display.display();

  // HTTP
  String json = "{\"sensor_id\":" + String(SENSOR_ID) +
                ",\"temperature\":" + String(t, 1) +
                ",\"humidity\":" + String(h, 1) +
                ",\"pressure\":" + String(p, 1) + "}";

  HTTPClient http;
  String url = "http://" + String(server) + ":" + String(serverPort) + String(endpoint);
  
  if (http.begin(wifiClient, url)) {
    http.addHeader("Content-Type", "application/json");
    http.POST(json);
    http.end();
  }

  delay(timeDelay);
}