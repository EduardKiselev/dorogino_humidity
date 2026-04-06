#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

const char* ssid = "ElSenorNegro";
const char* pass = "pomidorka38";
const int VALVE_PIN = 25;
const uint32_t CLOSE_DELAY = 30000; // 30 сек

Adafruit_SSD1306 display(128, 64, &Wire, -1);
WebServer server(80);

bool valveOpen = false;
uint32_t openedAt = 0;

void render() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(25, 15);
  display.setTextSize(2);
  display.println(valveOpen ? "OPEN" : "CLOSED");
  
  if (valveOpen) {
    display.setCursor(15, 45);
    display.setTextSize(1);
    uint32_t left = (CLOSE_DELAY - (millis() - openedAt)) / 1000;
    display.print("Close in: "); display.print(left); display.print("s");
  }
  display.display();
}

void handleOpen() {
  Serial.println("[HTTP] GET /valve/open");
  digitalWrite(VALVE_PIN, HIGH);
  valveOpen = true;
  openedAt = millis();
  Serial.println("[DEBUG] Valve OPENED");
  server.send(200, "text/plain", "OK: opened");
  render();
}

void handleClose() {
  Serial.println("[HTTP] GET /valve/close");
  digitalWrite(VALVE_PIN, LOW);
  valveOpen = false;
  Serial.println("[DEBUG] Valve CLOSED (manual)");
  server.send(200, "text/plain", "OK: closed");
  render();
}

void setup() {
  Serial.begin(115200);
  Serial.println("\n[INIT] ESP32 booting...");

  pinMode(VALVE_PIN, OUTPUT);
  digitalWrite(VALVE_PIN, LOW);

  Wire.begin(21, 22); // SDA, SCL
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("[WARN] SSD1306 not found!");
  } else {
    Serial.println("[INIT] Display ready");
  }
  render();

  Serial.printf("[WIFI] Connecting to '%s'...", ssid);
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\n[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());

  server.on("/valve/open", HTTP_GET, handleOpen);
  server.on("/valve/close", HTTP_GET, handleClose);
  
  // Опционально: корень для проверки
  server.on("/", HTTP_GET, []() {
    server.send(200, "text/plain", "ESP32 Valve Controller\nEndpoints: /valve/open, /valve/close");
  });

  server.begin();
  Serial.println("[HTTP] Server listening on port 80");
}

void loop() {
  server.handleClient();
  
  // Автозакрытие по таймеру (неблокирующее)
  if (valveOpen && millis() - openedAt >= CLOSE_DELAY) {
    digitalWrite(VALVE_PIN, LOW);
    valveOpen = false;
    Serial.println("[TIMER] Valve CLOSED (auto)");
    render();
  }
}