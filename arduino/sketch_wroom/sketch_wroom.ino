#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClient.h>
#include <DHT.h>

// === НАСТРОЙКИ ===
const char* ssid = "ElSenorNegro";
const char* password = "pomidorka38";
const int timeDelay = 10000;  // задержка в мс

#define DHTPIN 26
#define DHTTYPE DHT11
#define SENSOR_ID 2

const char* server = "192.168.10.100";
const int serverPort = 5000;
const char* endpoint = "/data";

DHT dht(DHTPIN, DHTTYPE);
WiFiClient wifiClient;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== ESP32 DHT11 Logger ===");

  // Инициализация DHT
  dht.begin();
  delay(2000);

  // Подключение к Wi-Fi с таймаутом 30 сек
  Serial.print("Подключение к Wi-Fi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  unsigned long timeout = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - timeout < 30000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n✗ Ошибка: не удалось подключиться к Wi-Fi за 30 сек");
    Serial.println("Проверьте SSID/пароль и доступность сети");
    return;
  }

  Serial.println("\n✓ Wi-Fi подключён");
  Serial.print("IP адрес ESP32: ");
  Serial.println(WiFi.localIP());
  Serial.print("Шлюз: ");
  Serial.println(WiFi.gatewayIP());
  Serial.print("Маска: ");
  Serial.println(WiFi.subnetMask());
  Serial.println();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n⚠ Wi-Fi отключён — попытка переподключения...");
    WiFi.reconnect();
    delay(5000);
    return;
  }

  // Считывание данных с датчика
  float temperature = dht.readTemperature(false);
  float humidity = dht.readHumidity();

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("\n✗ Ошибка чтения DHT11 — повтор через 2 сек");
    delay(2000);
    return;
  }

  float voltage = 3.3;

  // Формирование JSON
  String json = "{\"sensor_id\":" + String(SENSOR_ID) +
                ",\"temperature\":" + String(temperature, 1) +
                ",\"humidity\":" + String(humidity, 1) +
                ",\"voltage\":" + String(voltage, 2) + "}";

  Serial.println("\n→ Отправка данных:");
  Serial.println(json);

  // Отправка POST-запроса
  HTTPClient http;
  String url = "http://" + String(server) + ":" + String(serverPort) + String(endpoint);
  
  if (http.begin(wifiClient, url)) {
    http.addHeader("Content-Type", "application/json");
    int httpResponseCode = http.POST(json);

    Serial.print("→ Код ответа: ");
    Serial.println(httpResponseCode);

    if (httpResponseCode > 0) {
      String response = http.getString();
      if (response.length() > 0) {
        Serial.print("→ Тело ответа: ");
        Serial.println(response);
      } else {
        Serial.println("→ Тело ответа пустое (это нормально для некоторых серверов)");
      }
    } else {
      Serial.print("✗ Ошибка HTTP: ");
      Serial.println(httpResponseCode);
      Serial.println("  Возможные причины:");
      Serial.println("  • Сервер не запущен или недоступен");
      Serial.println("  • Изоляция клиентов в роутере (AP Isolation)");
      Serial.println("  • Брандмауэр блокирует порт 5000");
      Serial.println("  • Неправильный эндпоинт или метод запроса");
    }

    http.end();
  } else {
    Serial.println("✗ Ошибка инициализации HTTP-клиента");
  }

  Serial.println("---");
  delay(timeDelay);
}