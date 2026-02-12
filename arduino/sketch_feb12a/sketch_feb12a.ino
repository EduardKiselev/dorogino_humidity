#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>

// === НАСТРОЙКИ ===
const char* ssid = "ELTEX-46A0"; //"ELTEX-D660";
const char* password = "GP21424784"; //"GP21353620";
const int timeDelay = 10000;  // задержка в мс

#define DHTPIN 4        // GPIO пин для DHT11
#define DHTTYPE DHT11   // Тип датчика
#define SENSOR_ID 1     // Порядковый номер датчика

const char* server = "192.168.1.100";
const int serverPort = 5000;
const char* endpoint = "/data";

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);
  
  // Инициализация DHT
  dht.begin();
  delay(2000);
  
  // Подключение к Wi-Fi
  Serial.print("Подключение к Wi-Fi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("\n✓ Wi-Fi подключён");
  Serial.print("IP адрес ESP32: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // Считывание данных с датчика
  float temperature = dht.readTemperature(false);  // °C
  float humidity = dht.readHumidity();
  
  // Проверка ошибок чтения
  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("Ошибка чтения с датчика DHT11!");
    delay(timeDelay);
    return;
  }
  
  // Напряжение питания (3.3 В для питания от USB)
  // ESP.getVcc() НЕ СУЩЕСТВУЕТ на ESP32 — используем фиксированное значение
  float voltage = 3.3;
  
  // Формирование JSON
  String json = "{\"sensor_id\":" + String(SENSOR_ID) + 
                ",\"temperature\":" + String(temperature, 1) + 
                ",\"humidity\":" + String(humidity, 1) + 
                ",\"voltage\":" + String(voltage, 2) + "}";
  
  // Отправка POST-запроса
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(server, serverPort, endpoint);
    http.addHeader("Content-Type", "application/json");
    
    int httpResponseCode = http.POST(json);
    
    if (httpResponseCode > 0) {
      Serial.print("✓ Отправлено: ");
      Serial.print(json);
      Serial.print(" | Ответ сервера: ");
      Serial.println(httpResponseCode);
    } else {
      Serial.print("✗ Ошибка отправки: ");
      Serial.println(httpResponseCode);
    }
    
    http.end();
  } else {
    Serial.println("✗ Нет подключения к Wi-Fi");
  }
  
  delay(timeDelay);  // Задержка 10 секунд
}
