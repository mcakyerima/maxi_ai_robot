#include <WiFi.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <EEPROM.h>
#include <esp_task_wdt.h>

// WiFi Configuration
const char* ssid = "😡";
const char* password = "o(Nlog(n))";

// WebSocket Server
WebSocketsServer webSocket = WebSocketsServer(81);

// PCA9685 Configuration
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// Servo Configuration for MG996R
#define SERVO_FREQ 50
#define SERVO_MIN 102   // Min pulse length for MG996R (0.5ms)
#define SERVO_MAX 512   // Max pulse length for MG996R (2.5ms)
#define NUM_SERVOS 12


// Servo Mapping
enum ServoIndex {
  RIGHT_THUMB = 0,
  RIGHT_INDEX = 1,
  RIGHT_MIDDLE = 2,
  RIGHT_RING = 3,
  RIGHT_PINKY = 4,
  RIGHT_WRIST = 5,
  LEFT_WRIST = 6,
  LEFT_THUMB = 7,
  LEFT_INDEX = 8,
  LEFT_MIDDLE = 9,
  LEFT_RING = 10,
  LEFT_PINKY = 11
};

// Advanced Servo State Management
struct ServoState {
  int currentAngle;
  int targetAngle;
  int homePosition;
  unsigned long lastUpdate;
  bool isMoving;
  bool isEnabled;
  float speed;  // Custom speed per servo
  int minAngle;
  int maxAngle;
};

ServoState servos[NUM_SERVOS];

// Performance optimization variables
unsigned long lastHeartbeat = 0;
unsigned long lastStatusUpdate = 0;
bool isConnected = false;
int connectedClients = 0;

// Movement parameters
const int DEFAULT_MOVEMENT_SPEED = 3;
const int UPDATE_INTERVAL = 15;
const int HEARTBEAT_INTERVAL = 5000;
const int STATUS_UPDATE_INTERVAL = 1000;

// Task handles for multi-core processing
TaskHandle_t ServoUpdateTask;
TaskHandle_t WebSocketTask;

// Mutex for thread safety
SemaphoreHandle_t servoMutex;

void setup() {
  Serial.begin(115200);
  
  // Initialize watchdog timer
  esp_task_wdt_config_t wdt_config = {
  .timeout_ms = 10000,         // 10 seconds in milliseconds
  .idle_core_mask = 1,         // Watch Core 0 only
  .trigger_panic = true        // Trigger panic on timeout
  };

  esp_task_wdt_init(&wdt_config);
  esp_task_wdt_add(NULL);  // Register current task (NULL = current)

  
  // Initialize EEPROM for servo calibration data
  EEPROM.begin(512);
  
  Serial.println("ESP32 Advanced Servo Controller Starting...");
  
  // Initialize mutex
  servoMutex = xSemaphoreCreateMutex();
  
  // Initialize PCA9685
  Wire.begin();
  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(SERVO_FREQ);
  
  Serial.println("PCA9685 initialized");
  
  // Initialize servo states with calibration data
  initializeServoStates();
  
  // Connect to WiFi
  connectToWiFi();
  
  // Initialize WebSocket server
  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
  
  Serial.println("WebSocket server started on port 81");
  Serial.print("ESP32 IP Address: ");
  Serial.println(WiFi.localIP());
  
  // Create tasks for multi-core processing
  xTaskCreatePinnedToCore(
    servoUpdateTaskFunction,
    "ServoUpdate",
    4096,
    NULL,
    2,
    &ServoUpdateTask,
    0  // Core 0
  );
  
  xTaskCreatePinnedToCore(
    webSocketTaskFunction,
    "WebSocket",
    8192,
    NULL,
    1,
    &WebSocketTask,
    1  // Core 1
  );
  
  Serial.println("Multi-core tasks created");
  Serial.println("System ready!");
  
  // Send ready signal
  broadcastMessage("{\"status\":\"ready\",\"message\":\"ESP32 servo controller initialized\",\"ip\":\"" + WiFi.localIP().toString() + "\"}");
}

void loop() {
  // Main loop handles watchdog and emergency checks
  esp_task_wdt_reset();
  
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected, attempting reconnection...");
    connectToWiFi();
  }
  
  delay(100);
}

void connectToWiFi() {
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("WiFi connected successfully");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("WiFi connection failed");
  }
}

void initializeServoStates() {
  // Default servo configurations with individual calibration
  struct ServoConfig {
    int home;
    int minAngle;
    int maxAngle;
    float speed;
  };
  
  ServoConfig defaultConfigs[NUM_SERVOS] = {
    {90, 0, 180, 2.0},   // RIGHT_THUMB
    {90, 0, 180, 2.5},   // RIGHT_INDEX
    {90, 0, 180, 2.5},   // RIGHT_MIDDLE
    {90, 0, 180, 2.5},   // RIGHT_RING
    {90, 0, 180, 2.0},   // RIGHT_PINKY
    {90, 30, 150, 1.5},  // RIGHT_WRIST
    {90, 30, 150, 1.5},  // LEFT_WRIST
    {90, 0, 180, 2.0},   // LEFT_THUMB
    {90, 0, 180, 2.5},   // LEFT_INDEX
    {90, 0, 180, 2.5},   // LEFT_MIDDLE
    {90, 0, 180, 2.5},   // LEFT_RING
    {90, 0, 180, 2.0}    // LEFT_PINKY
  };
  
  for (int i = 0; i < NUM_SERVOS; i++) {
    servos[i].homePosition = defaultConfigs[i].home;
    servos[i].currentAngle = defaultConfigs[i].home;
    servos[i].targetAngle = defaultConfigs[i].home;
    servos[i].minAngle = defaultConfigs[i].minAngle;
    servos[i].maxAngle = defaultConfigs[i].maxAngle;
    servos[i].speed = defaultConfigs[i].speed;
    servos[i].lastUpdate = 0;
    servos[i].isMoving = false;
    servos[i].isEnabled = true;
    
    // Load calibration from EEPROM if available
    loadServoCalibration(i);
    
    // Set initial position
    setServoAngle(i, servos[i].homePosition, true);
  }
  
  delay(1000); // Allow servos to reach position
  Serial.println("Servo states initialized");
}

void loadServoCalibration(int servoIndex) {
  int address = servoIndex * 16; // 16 bytes per servo
  
  // Check if calibration data exists (magic number)
  if (EEPROM.read(address) == 0xAA && EEPROM.read(address + 1) == 0x55) {
    servos[servoIndex].minAngle = EEPROM.read(address + 2);
    servos[servoIndex].maxAngle = EEPROM.read(address + 3);
    servos[servoIndex].homePosition = EEPROM.read(address + 4);
    
    float speedBytes[4];
    for (int i = 0; i < 4; i++) {
      speedBytes[i] = EEPROM.read(address + 5 + i);
    }
    memcpy(&servos[servoIndex].speed, speedBytes, sizeof(float));
  }
}

void saveServoCalibration(int servoIndex) {
  int address = servoIndex * 16;
  
  // Magic number for validation
  EEPROM.write(address, 0xAA);
  EEPROM.write(address + 1, 0x55);
  EEPROM.write(address + 2, servos[servoIndex].minAngle);
  EEPROM.write(address + 3, servos[servoIndex].maxAngle);
  EEPROM.write(address + 4, servos[servoIndex].homePosition);
  
  // Save speed as bytes
  byte speedBytes[4];
  memcpy(speedBytes, &servos[servoIndex].speed, sizeof(float));
  for (int i = 0; i < 4; i++) {
    EEPROM.write(address + 5 + i, speedBytes[i]);
  }
  
  EEPROM.commit();
}

// Multi-core task for servo updates (Core 0)
void servoUpdateTaskFunction(void *parameter) {
  for (;;) {
    updateServoMovements();
    vTaskDelay(pdMS_TO_TICKS(UPDATE_INTERVAL));
  }
}

// Multi-core task for WebSocket handling (Core 1)
void webSocketTaskFunction(void *parameter) {
  for (;;) {
    webSocket.loop();
    
    // Send periodic heartbeat and status
    unsigned long currentTime = millis();
    
    if (currentTime - lastHeartbeat >= HEARTBEAT_INTERVAL) {
      sendHeartbeat();
      lastHeartbeat = currentTime;
    }
    
    if (currentTime - lastStatusUpdate >= STATUS_UPDATE_INTERVAL && connectedClients > 0) {
      sendStatusUpdate();
      lastStatusUpdate = currentTime;
    }
    
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

void webSocketEvent(uint8_t num, WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.printf("Client %u disconnected\n", num);
      connectedClients--;
      isConnected = (connectedClients > 0);
      break;
      
    case WStype_CONNECTED:
      {
        IPAddress ip = webSocket.remoteIP(num);
        Serial.printf("Client %u connected from %d.%d.%d.%d\n", num, ip[0], ip[1], ip[2], ip[3]);
        connectedClients++;
        isConnected = true;
        
        // Send welcome message
        String welcome = "{\"status\":\"connected\",\"message\":\"ESP32 servo controller connected\",\"servos\":" + String(NUM_SERVOS) + "}";
        webSocket.sendTXT(num, welcome);
      }
      break;
      
    case WStype_TEXT:
      Serial.printf("Received from client %u: %s\n", num, payload);
      processWebSocketCommand((char*)payload, num);
      break;
      
    default:
      break;
  }
}

void processWebSocketCommand(String command, uint8_t clientNum) {
  DynamicJsonDocument doc(2048);
  DeserializationError error = deserializeJson(doc, command);
  
  if (error) {
    sendError(clientNum, "Invalid JSON format", "parse_error");
    return;
  }
  
  String action = doc["action"];
  //String responseId = doc.containsKey("id") ? doc["id"] : "";
  String responseId = doc.containsKey("id") ? String(doc["id"].as<const char*>()) : "";

  
  if (action == "set_servo") {
    handleSetServo(doc, clientNum, responseId);
  }
  else if (action == "gesture") {
    handleGesture(doc, clientNum, responseId);
  }
  else if (action == "show_number") {
    handleShowNumber(doc, clientNum, responseId);
  }
  else if (action == "sequence") {
    handleSequence(doc, clientNum, responseId);
  }
  else if (action == "calibrate") {
    handleCalibration(doc, clientNum, responseId);
  }
  else if (action == "reset_all") {
    handleResetAll(clientNum, responseId);
  }
  else if (action == "emergency_stop") {
    handleEmergencyStop(clientNum, responseId);
  }
  else if (action == "get_status") {
    handleGetStatus(clientNum, responseId);
  }
  else if (action == "configure_servo") {
    handleConfigureServo(doc, clientNum, responseId);
  }
  else {
    sendError(clientNum, "Unknown command: " + action, responseId);
  }
}

void handleSetServo(DynamicJsonDocument& doc, uint8_t clientNum, String responseId) {
  int channel = doc["channel"];
  int angle = doc["angle"];
  bool immediate = doc.containsKey("immediate") ? doc["immediate"] : false;
  float speed = doc.containsKey("speed") ? doc["speed"] : servos[channel].speed;
  
  if (channel >= 0 && channel < NUM_SERVOS && angle >= 0 && angle <= 180) {
    if (xSemaphoreTake(servoMutex, pdMS_TO_TICKS(100))) {
      servos[channel].speed = speed;
      setServoAngle(channel, angle, immediate);
      xSemaphoreGive(servoMutex);
      
      sendSuccess(clientNum, "Servo " + String(channel) + " set to " + String(angle) + " degrees", responseId);
    } else {
      sendError(clientNum, "Servo busy", responseId);
    }
  } else {
    sendError(clientNum, "Invalid servo channel or angle", responseId);
  }
}

void handleGesture(DynamicJsonDocument& doc, uint8_t clientNum, String responseId) {
  String gestureName = doc["gesture"];
  float speed = doc.containsKey("speed") ? doc["speed"] : 2.0;
  
  executeGesture(gestureName, speed);
  sendSuccess(clientNum, "Gesture '" + gestureName + "' executed", responseId);
}

void handleShowNumber(DynamicJsonDocument& doc, uint8_t clientNum, String responseId) {
  int number = doc["number"];
  float speed = doc.containsKey("speed") ? doc["speed"] : 2.0;
  
  if (showNumber(number, speed)) {
    sendSuccess(clientNum, "Showing number " + String(number), responseId);
  } else {
    sendError(clientNum, "Invalid number (0-10 only)", responseId);
  }
}

void handleSequence(DynamicJsonDocument& doc, uint8_t clientNum, String responseId) {
  JsonArray sequence = doc["sequence"];
  executeSequence(sequence);
  sendSuccess(clientNum, "Sequence executed", responseId);
}

void handleCalibration(DynamicJsonDocument& doc, uint8_t clientNum, String responseId) {
  int channel = doc["channel"];
  
  if (channel >= 0 && channel < NUM_SERVOS) {
    if (doc.containsKey("min_angle")) servos[channel].minAngle = doc["min_angle"];
    if (doc.containsKey("max_angle")) servos[channel].maxAngle = doc["max_angle"];
    if (doc.containsKey("home")) servos[channel].homePosition = doc["home"];
    if (doc.containsKey("speed")) servos[channel].speed = doc["speed"];
    
    saveServoCalibration(channel);
    sendSuccess(clientNum, "Servo " + String(channel) + " calibrated", responseId);
  } else {
    sendError(clientNum, "Invalid servo channel", responseId);
  }
}

void handleResetAll(uint8_t clientNum, String responseId) {
  resetAllServos();
  sendSuccess(clientNum, "All servos reset to home position", responseId);
}

void handleEmergencyStop(uint8_t clientNum, String responseId) {
  emergencyStop();
  sendSuccess(clientNum, "Emergency stop activated", responseId);
}

void handleGetStatus(uint8_t clientNum, String responseId) {
  sendFullStatus(clientNum, responseId);
}

void handleConfigureServo(DynamicJsonDocument& doc, uint8_t clientNum, String responseId) {
  int channel = doc["channel"];
  
  if (channel >= 0 && channel < NUM_SERVOS) {
    if (doc.containsKey("enabled")) servos[channel].isEnabled = doc["enabled"];
    if (doc.containsKey("speed")) servos[channel].speed = doc["speed"];
    
    sendSuccess(clientNum, "Servo " + String(channel) + " configured", responseId);
  } else {
    sendError(clientNum, "Invalid servo channel", responseId);
  }
}

void setServoAngle(int channel, int angle, bool immediate) {
  if (channel < 0 || channel >= NUM_SERVOS || !servos[channel].isEnabled) return;
  
  // Constrain to servo limits
  angle = constrain(angle, servos[channel].minAngle, servos[channel].maxAngle);
  
  if (immediate) {
    servos[channel].currentAngle = angle;
    servos[channel].targetAngle = angle;
    servos[channel].isMoving = false;
    
    int pwmValue = map(angle, 0, 180, SERVO_MIN, SERVO_MAX);
    pwm.setPWM(channel, 0, pwmValue);
  } else {
    servos[channel].targetAngle = angle;
    servos[channel].isMoving = (servos[channel].currentAngle != angle);
  }
}

void updateServoMovements() {
  if (xSemaphoreTake(servoMutex, pdMS_TO_TICKS(10))) {
    unsigned long currentTime = millis();
    
    for (int i = 0; i < NUM_SERVOS; i++) {
      if (servos[i].isMoving && servos[i].isEnabled && 
          (currentTime - servos[i].lastUpdate >= UPDATE_INTERVAL)) {
        
        int current = servos[i].currentAngle;
        int target = servos[i].targetAngle;
        float speed = servos[i].speed;
        
        if (current != target) {
          int step = max(1, (int)speed);
          
          if (current < target) {
            current = min(current + step, target);
          } else {
            current = max(current - step, target);
          }
          
          servos[i].currentAngle = current;
          servos[i].lastUpdate = currentTime;
          
          int pwmValue = map(current, 0, 180, SERVO_MIN, SERVO_MAX);
          pwm.setPWM(i, 0, pwmValue);
          
          if (current == target) {
            servos[i].isMoving = false;
          }
        }
      }
    }
    
    xSemaphoreGive(servoMutex);
  }
}

void executeGesture(String gesture, float speed) {
  gesture.toLowerCase();
  
  // Temporarily adjust speed for all servos
  float originalSpeeds[NUM_SERVOS];
  for (int i = 0; i < NUM_SERVOS; i++) {
    originalSpeeds[i] = servos[i].speed;
    servos[i].speed = speed;
  }
  
  if (gesture == "wave") {
    // Enhanced wave with multiple movements
    setServoAngle(RIGHT_WRIST, 45, false);
    delay(300);
    setServoAngle(RIGHT_WRIST, 135, false);
    delay(300);
    setServoAngle(RIGHT_WRIST, 45, false);
    delay(300);
    setServoAngle(RIGHT_WRIST, 135, false);
    delay(300);
    setServoAngle(RIGHT_WRIST, servos[RIGHT_WRIST].homePosition, false);
  }
  else if (gesture == "point") {
    setServoAngle(RIGHT_INDEX, 180, false);
    setServoAngle(RIGHT_THUMB, 45, false);
    setServoAngle(RIGHT_MIDDLE, 45, false);
    setServoAngle(RIGHT_RING, 45, false);
    setServoAngle(RIGHT_PINKY, 45, false);
  }
  else if (gesture == "fist") {
    for (int i = RIGHT_THUMB; i <= RIGHT_PINKY; i++) {
      setServoAngle(i, 45, false);
    }
  }
  else if (gesture == "open_hand") {
    for (int i = RIGHT_THUMB; i <= RIGHT_PINKY; i++) {
      setServoAngle(i, 180, false);
    }
  }
  else if (gesture == "peace") {
    setServoAngle(RIGHT_INDEX, 180, false);
    setServoAngle(RIGHT_MIDDLE, 180, false);
    setServoAngle(RIGHT_THUMB, 45, false);
    setServoAngle(RIGHT_RING, 45, false);
    setServoAngle(RIGHT_PINKY, 45, false);
  }
  else if (gesture == "thumbs_up") {
    setServoAngle(RIGHT_THUMB, 180, false);
    for (int i = RIGHT_INDEX; i <= RIGHT_PINKY; i++) {
      setServoAngle(i, 45, false);
    }
  }
  
  // Restore original speeds
  for (int i = 0; i < NUM_SERVOS; i++) {
    servos[i].speed = originalSpeeds[i];
  }
}

bool showNumber(int number, float speed) {
  if (number < 0 || number > 10) return false;
  
  // Temporarily adjust speed
  float originalSpeeds[NUM_SERVOS];
  for (int i = 0; i < NUM_SERVOS; i++) {
    originalSpeeds[i] = servos[i].speed;
    servos[i].speed = speed;
  }
  
  // Reset all fingers first
  for (int i = RIGHT_THUMB; i <= LEFT_PINKY; i++) {
    setServoAngle(i, 45, false);
  }
  
  delay(500);
  
  // Show number logic (enhanced)
  switch (number) {
    case 0: break; // All closed
    case 1: setServoAngle(RIGHT_INDEX, 180, false); break;
    case 2: 
      setServoAngle(RIGHT_INDEX, 180, false);
      setServoAngle(RIGHT_MIDDLE, 180, false);
      break;
    case 3:
      setServoAngle(RIGHT_INDEX, 180, false);
      setServoAngle(RIGHT_MIDDLE, 180, false);
      setServoAngle(RIGHT_RING, 180, false);
      break;
    case 4:
      for (int i = RIGHT_INDEX; i <= RIGHT_PINKY; i++) {
        setServoAngle(i, 180, false);
      }
      break;
    case 5:
      for (int i = RIGHT_THUMB; i <= RIGHT_PINKY; i++) {
        setServoAngle(i, 180, false);
      }
      break;
    default: // 6-10
      // Right hand (5)
      for (int i = RIGHT_THUMB; i <= RIGHT_PINKY; i++) {
        setServoAngle(i, 180, false);
      }
      // Left hand (remaining)
      int remaining = number - 5;
      for (int i = LEFT_THUMB; i < LEFT_THUMB + remaining; i++) {
        setServoAngle(i, 180, false);
      }
      break;
  }
  
  // Restore speeds
  for (int i = 0; i < NUM_SERVOS; i++) {
    servos[i].speed = originalSpeeds[i];
  }
  
  return true;
}

void executeSequence(JsonArray& sequence) {
  for (JsonVariant step : sequence) {
    if (step.containsKey("servo") && step.containsKey("angle")) {
      int servo = step["servo"];
      int angle = step["angle"];
      int delayMs = step.containsKey("delay") ? step["delay"] : 0;
      bool immediate = step.containsKey("immediate") ? step["immediate"] : false;
      
      setServoAngle(servo, angle, immediate);
      
      if (delayMs > 0) {
        delay(delayMs);
      }
    }
  }
}

void resetAllServos() {
  if (xSemaphoreTake(servoMutex, pdMS_TO_TICKS(1000))) {
    for (int i = 0; i < NUM_SERVOS; i++) {
      setServoAngle(i, servos[i].homePosition, false);
    }
    xSemaphoreGive(servoMutex);
  }
}

void emergencyStop() {
  if (xSemaphoreTake(servoMutex, pdMS_TO_TICKS(100))) {
    for (int i = 0; i < NUM_SERVOS; i++) {
      servos[i].isMoving = false;
      servos[i].targetAngle = servos[i].currentAngle;
    }
    xSemaphoreGive(servoMutex);
  }
}

void sendSuccess(uint8_t clientNum, String message, String responseId) {
  DynamicJsonDocument doc(512);
  doc["status"] = "success";
  doc["message"] = message;
  doc["timestamp"] = millis();
  if (responseId != "") doc["id"] = responseId;
  
  String response;
  serializeJson(doc, response);
  webSocket.sendTXT(clientNum, response);
}

void sendError(uint8_t clientNum, String message, String responseId) {
  DynamicJsonDocument doc(512);
  doc["status"] = "error";
  doc["message"] = message;
  doc["timestamp"] = millis();
  if (responseId != "") doc["id"] = responseId;
  
  String response;
  serializeJson(doc, response);
  webSocket.sendTXT(clientNum, response);
}

void sendHeartbeat() {
  if (connectedClients > 0) {
    DynamicJsonDocument doc(256);
    doc["type"] = "heartbeat";
    doc["timestamp"] = millis();
    doc["free_heap"] = ESP.getFreeHeap();
    doc["wifi_rssi"] = WiFi.RSSI();
    
    String response;
    serializeJson(doc, response);
    webSocket.broadcastTXT(response);
  }
}

void sendStatusUpdate() {
  DynamicJsonDocument doc(1024);
  doc["type"] = "status_update";
  doc["timestamp"] = millis();
  
  JsonArray positions = doc.createNestedArray("servos");
  for (int i = 0; i < NUM_SERVOS; i++) {
    JsonObject servo = positions.createNestedObject();
    servo["id"] = i;
    servo["current"] = servos[i].currentAngle;
    servo["target"] = servos[i].targetAngle;
    servo["moving"] = servos[i].isMoving;
    servo["enabled"] = servos[i].isEnabled;
  }
  
  String response;
  serializeJson(doc, response);
  webSocket.broadcastTXT(response);
}

void sendFullStatus(uint8_t clientNum, String responseId) {
  DynamicJsonDocument doc(2048);
  doc["status"] = "success";
  doc["type"] = "full_status";
  doc["timestamp"] = millis();
  doc["free_heap"] = ESP.getFreeHeap();
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["connected_clients"] = connectedClients;
  if (responseId != "") doc["id"] = responseId;
  
  JsonArray servosArray = doc.createNestedArray("servos");
  for (int i = 0; i < NUM_SERVOS; i++) {
    JsonObject servo = servosArray.createNestedObject();
    servo["id"] = i;
    servo["current"] = servos[i].currentAngle;
    servo["target"] = servos[i].targetAngle;
    servo["home"] = servos[i].homePosition;
    servo["min"] = servos[i].minAngle;
    servo["max"] = servos[i].maxAngle;
    servo["speed"] = servos[i].speed;
    servo["moving"] = servos[i].isMoving;
    servo["enabled"] = servos[i].isEnabled;
  }
  
  String response;
  serializeJson(doc, response);
  webSocket.sendTXT(clientNum, response);
}

void broadcastMessage(String message) {
  webSocket.broadcastTXT(message);
}