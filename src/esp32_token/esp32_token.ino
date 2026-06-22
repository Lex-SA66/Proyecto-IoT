#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <mbedtls/md.h>

// --- CONFIGURACIÓN DE RED ---
const char* ssid = "hotspot";
const char* password = "passwd";
const char* mqtt_server = "192.168.X.X";

const int MPU_ADDR = 0x68;
const int buttonPin = 4;

WiFiClient espClient;
PubSubClient client(espClient);

struct MensajeMQTT {
  char topic[20];
  char payload[50];
};
QueueHandle_t colaMensajes;

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

void despertarMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B); 
  Wire.write(0x00); 
  Wire.endTransmission(true);
}

void leerSensor(float &ax, float &ay, float &az) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B); 
  Wire.endTransmission(false);
  
  Wire.requestFrom(MPU_ADDR, 6, true); 
  
  int16_t rawX = Wire.read() << 8 | Wire.read();
  int16_t rawY = Wire.read() << 8 | Wire.read();
  int16_t rawZ = Wire.read() << 8 | Wire.read();

  ax = rawX / 16384.0;
  ay = rawY / 16384.0;
  az = rawZ / 16384.0;
}

void TareaSensores(void *parameter) {
  bool step1_done = false;
  unsigned long last_gesture_time = 0;
  MensajeMQTT msg;
  float ax, ay, az;

  for(;;) {
    leerSensor(ax, ay, az);

    // Calculamos el Roll (Izquierda/Derecha) y la Aceleración Total
    float roll = atan2(ay, az) * 180.0 / PI;
    float total_accel = sqrt(pow(ax, 2) + pow(ay, 2) + pow(az, 2));
    
    int buttonState = digitalRead(buttonPin);
    unsigned long current_time = millis();

    // MODO 1: LOGIN (Botón Presionado)
    if (buttonState == LOW) {
      if (roll > 50 && !step1_done) {
        step1_done = true; 
        vTaskDelay(300 / portTICK_PERIOD_MS); 
      }
      if (step1_done && roll < -50) {
        String token = generarTokenReal();
        strcpy(msg.topic, "boveda/acceso");
        strcpy(msg.payload, token.c_str());
        xQueueSend(colaMensajes, &msg, portMAX_DELAY);
        step1_done = false;
        vTaskDelay(1000 / portTICK_PERIOD_MS);
      }
    } 
    // MODO 2: LLAVES DE ARCHIVOS (Botón Suelto)
    else {
      step1_done = false;
      // Reducido a 1000ms (1 segundo) para que responda mucho más rápido
      if (current_time - last_gesture_time > 1000) {
        strcpy(msg.topic, "boveda/llaves");
        bool gesto_detectado = false;

        // 1. AGITAR: Detecta sacudida fuerte (Umbral bajado a 1.8g)
        if (total_accel > 1.8) { 
            strcpy(msg.payload, "GESTO_AGITAR"); 
            gesto_detectado = true; 
        } 
        // 2. VOLTEAR: Detecta si la gravedad tira hacia el techo (Eje Z negativo)
        else if (az < -0.6 && total_accel < 1.5) { 
            strcpy(msg.payload, "GESTO_VOLTEAR"); 
            gesto_detectado = true; 
        } 
        // 3. DERECHA: Roll positivo claro
        else if (roll > 55 && roll < 130) { 
            strcpy(msg.payload, "GESTO_DERECHA"); 
            gesto_detectado = true; 
        } 
        // 4. IZQUIERDA: Roll negativo claro
        else if (roll < -55 && roll > -130) { 
            strcpy(msg.payload, "GESTO_IZQUIERDA"); 
            gesto_detectado = true; 
        }

        if (gesto_detectado) {
          xQueueSend(colaMensajes, &msg, portMAX_DELAY);
          last_gesture_time = current_time;
          // Pausa extra para no inundar el servidor con el mismo gesto
          vTaskDelay(500 / portTICK_PERIOD_MS);
        }
      }
    }
    vTaskDelay(20 / portTICK_PERIOD_MS);
  }
}

void TareaRedMQTT(void *parameter) {
  WiFi.begin(ssid, password);
  
  // <--- CORRECCIÓN 1: Configurar el servidor MQTT antes de iniciar el ciclo
  client.setServer(mqtt_server, 1883); 

  MensajeMQTT msgRecibido;

  for(;;) {
    if (WiFi.status() != WL_CONNECTED) {
      vTaskDelay(1000 / portTICK_PERIOD_MS);
      continue;
    }
    if (!client.connected()) { 
      client.connect("ESP32_Token_KMS"); 
    }
    client.loop();

    if (xQueueReceive(colaMensajes, &msgRecibido, 0) == pdTRUE) {
      // <--- CORRECCIÓN 2: Validar que el mensaje realmente se envió al Broker
      if (client.publish(msgRecibido.topic, msgRecibido.payload)) {
        Serial.print("[EXITO] MQTT Enviado: ");
        Serial.println(msgRecibido.payload);
      } else {
        Serial.print("[ERROR] Fallo el envio MQTT de: ");
        Serial.println(msgRecibido.payload);
      }
    }
    vTaskDelay(50 / portTICK_PERIOD_MS);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(buttonPin, INPUT_PULLUP);
  
  Wire.begin(21, 22); 
  despertarMPU();

  colaMensajes = xQueueCreate(10, sizeof(MensajeMQTT));

  xTaskCreatePinnedToCore(TareaRedMQTT, "TareaRed", 8192, NULL, 1, NULL, 0); 
  xTaskCreatePinnedToCore(TareaSensores, "TareaSensores", 4096, NULL, 2, NULL, 1); 
}

void loop() {
  vTaskDelete(NULL); 
}
