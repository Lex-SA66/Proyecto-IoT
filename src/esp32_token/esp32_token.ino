#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>
#include <mbedtls/md.h>

// --- CONFIGURACIÓN DE RED ---
const char* ssid = "TU_WIFI_HOTSPOT";
const char* password = "TU_PASSWORD";
const char* mqtt_server = "192.168.X.X"; // IP de la Arduino UNO Q

WiFiClient espClient;
PubSubClient client(espClient);
Adafruit_MPU6050 mpu;

const int buttonPin = 4;

// --- FREERTOS: Buzón de Mensajes ---
struct MensajeMQTT {
  char topic[20];
  char payload[50];
};
QueueHandle_t colaMensajes;

// --- FUNCIÓN DE HASHING (TOKEN OTP) ---
String generarTokenReal() {
  byte shaResult[32];
  String payload = String(millis()) + "SemillaSecretaESCOM2026"; 
  
  mbedtls_md_context_t ctx;
  mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 0);
  mbedtls_md_starts(&ctx);
  mbedtls_md_update(&ctx, (const unsigned char *)payload.c_str(), payload.length());
  mbedtls_md_finish(&ctx, shaResult);
  mbedtls_md_free(&ctx);

  String hashStr = "";
  for (int i = 0; i < 12; i++) { 
    if (shaResult[i] < 16) hashStr += "0";
    hashStr += String(shaResult[i], HEX);
  }
  return hashStr;
}

void setup() {
  Serial.begin(115200);
  pinMode(buttonPin, INPUT_PULLUP);
  
  if (!mpu.begin()) {
    Serial.println("Error: No se encontró el MPU6050");
    while (1) { delay(10); }
  }

  colaMensajes = xQueueCreate(10, sizeof(MensajeMQTT));

  // Tareas Dual-Core
  xTaskCreatePinnedToCore(TareaRedMQTT, "TareaRed", 8192, NULL, 1, NULL, 0); 
  xTaskCreatePinnedToCore(TareaSensores, "TareaSensores", 4096, NULL, 2, NULL, 1); 
}

void loop() {
  vTaskDelete(NULL); 
}

void TareaSensores(void *parameter) {
  bool step1_done = false;
  unsigned long last_gesture_time = 0;
  MensajeMQTT msg;

  for(;;) {
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);

    float roll = atan2(a.acceleration.y, a.acceleration.z) * 180.0 / PI;
    float pitch = atan2(-a.acceleration.x, sqrt(a.acceleration.y * a.acceleration.y + a.acceleration.z * a.acceleration.z)) * 180.0 / PI;
    float total_accel = sqrt(pow(a.acceleration.x, 2) + pow(a.acceleration.y, 2) + pow(a.acceleration.z, 2)) / 9.81;
    
    int buttonState = digitalRead(buttonPin);
    unsigned long current_time = millis();

    // MODO 1: LOGIN ZERO TRUST
    if (buttonState == LOW) {
      if (roll > 60 && !step1_done) {
        step1_done = true; 
        vTaskDelay(500 / portTICK_PERIOD_MS); 
      }
      if (step1_done && roll < -60) {
        String token = generarTokenReal();
        strcpy(msg.topic, "boveda/acceso");
        strcpy(msg.payload, token.c_str());
        xQueueSend(colaMensajes, &msg, portMAX_DELAY);
        step1_done = false;
        vTaskDelay(2000 / portTICK_PERIOD_MS);
      }
    } 
    // MODO 2: LLAVES DE ARCHIVOS
    else {
      step1_done = false;
      if (current_time - last_gesture_time > 2000) {
        strcpy(msg.topic, "boveda/llaves");
        bool gesto_detectado = false;

        if (total_accel > 2.5) { strcpy(msg.payload, "GESTO_AGITAR"); gesto_detectado = true; } 
        else if (pitch > 150) { strcpy(msg.payload, "GESTO_VOLTEAR"); gesto_detectado = true; } 
        else if (roll > 60) { strcpy(msg.payload, "GESTO_DERECHA"); gesto_detectado = true; } 
        else if (roll < -60) { strcpy(msg.payload, "GESTO_IZQUIERDA"); gesto_detectado = true; }

        if (gesto_detectado) {
          xQueueSend(colaMensajes, &msg, portMAX_DELAY);
          last_gesture_time = current_time;
        }
      }
    }
    vTaskDelay(20 / portTICK_PERIOD_MS);
  }
}

void TareaRedMQTT(void *parameter) {
  WiFi.begin(ssid, password);
  MensajeMQTT msgRecibido;

  for(;;) {
    if (WiFi.status() != WL_CONNECTED) {
      vTaskDelay(1000 / portTICK_PERIOD_MS);
      continue;
    }
    if (!client.connected()) { client.connect("ESP32_Token_KMS"); }
    client.loop();

    if (xQueueReceive(colaMensajes, &msgRecibido, 0) == pdTRUE) {
      client.publish(msgRecibido.topic, msgRecibido.payload);
      Serial.println("Paquete criptográfico enviado.");
    }
    vTaskDelay(50 / portTICK_PERIOD_MS);
  }
}