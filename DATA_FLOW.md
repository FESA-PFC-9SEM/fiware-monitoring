# FIWARE Data Flow

## Overview

### Steps

1. **Arduino collects data**
   *(no payload yet — internal sensor reading)*

---

2. **Publishes via MQTT (raw data)**

```json
topic: /1234/device01/attrs
payload: t=25&h=60
```

---

3. **MQTT Broker receives and distributes**
*(payload unchanged — just routing)*

---

4. **IoT Agent consumes the topic**
*(same payload received)*

```json
t=25&h=60
```

---

5. **IoT Agent transforms → NGSI (structured context)**

```json
{
  "id": "device01",
  "type": "Sensor",
  "temperature": {
    "value": 25,
    "type": "Number"
  },
  "humidity": {
    "value": 60,
    "type": "Number"
  }
}
```

---

6. **Sends to Orion (HTTP NGSI request)**

```http
POST /v2/entities/device01/attrs
Content-Type: application/json

{
  "temperature": { "value": 25, "type": "Number" },
  "humidity": { "value": 60, "type": "Number" }
}
```

---

7. Orion updates entity (current state)

```json
{
  "id": "device01",
  "type": "Sensor",
  "temperature": { "value": 25 },
  "humidity": { "value": 60 }
}
```

8. Orion stores in MongoDB (current state)

```json
{
  "_id": "device01",
  "temperature": 25,
  "humidity": 60,
  "lastUpdate": "2026-03-22T23:00:00Z"
}
```

9. Orion notifies STH-Comet

```json
{
  "data": [
    {
      "id": "device01",
      "temperature": { "value": 25 },
      "humidity": { "value": 60 }
    }
  ]
}
```

10. STH-Comet stores history (MongoDB)

```json
{
  "entityId": "device01",
  "attrName": "temperature",
  "value": 25,
  "recvTime": "2026-03-22T23:00:00Z"
}
```

### Flow Chart

```mermaid
flowchart TD
    A["🔌 Arduino\n(Sensor Reading)"]
    B["📡 MQTT Broker\ntopic: /1234/device01/attrs\npayload: t=25&h=60"]
    C["🔄 IoT Agent\nConsumes MQTT topic"]
    D["📦 IoT Agent\nTransforms → NGSI\n{id, type, temperature, humidity}"]
    E["🌐 Orion Context Broker\nPOST /v2/entities/device01/attrs"]
    F["🗄️ MongoDB\nCurrent State\n{device01, temp: 25, hum: 60}"]
    G["📈 STH-Comet\nReceives Notification"]
    H["🗄️ MongoDB\nTime Series History\n{entityId, value, recvTime}"]

    A -->|"Publishes MQTT\nt=25&h=60"| B
    B -->|"Routes raw payload\n(unchanged)"| C
    C -->|"Parses UL format"| D
    D -->|"HTTP NGSI request"| E
    E -->|"Stores current state"| F
    E -->|"Sends notification"| G
    G -->|"Stores historical data"| H

    style A fill:#4CAF50,color:#fff
    style B fill:#2196F3,color:#fff
    style C fill:#FF9800,color:#fff
    style D fill:#FF5722,color:#fff
    style E fill:#9C27B0,color:#fff
    style F fill:#607D8B,color:#fff
    style G fill:#00BCD4,color:#fff
    style H fill:#607D8B,color:#fff
```

### Sequence Diagram

```mermaid
sequenceDiagram
    participant Arduino
    participant MQTT Broker
    participant IoT Agent
    participant Orion
    participant MongoDB
    participant STH-Comet
    participant MongoDB History

    Arduino->>MQTT Broker: Publish t=25&h=60<br/>topic: /1234/device01/attrs
    MQTT Broker->>IoT Agent: Route raw payload (t=25&h=60)
    IoT Agent->>IoT Agent: Parse UL format → NGSI
    IoT Agent->>Orion: POST /v2/entities/device01/attrs<br/>{temperature: 25, humidity: 60}
    Orion->>MongoDB: Store current state<br/>{device01, temp: 25, hum: 60}
    Orion->>STH-Comet: Notify change<br/>{id: device01, temperature: 25, humidity: 60}
    STH-Comet->>MongoDB History: Store time series<br/>{entityId, value, recvTime}
```

### Quick summary

Before IoT Agent: raw data (t=25)
After IoT Agent: structured context (NGSI)
Orion: current state
STH-Comet: historical time series

## Scenario: 🌧️ Smart Flood Monitoring & Emergency Response

## Objective

Monitor flood risks in the city using:

- water level sensors
- rain intensity sensors
- geographic zones

Trigger alerts and support real-time decision-making.

---

## Entities

### WaterLevelSensor

- `level` (meters)
- `location` (geo:point)

### RainSensor

- `intensity` (mm or index)

### FloodZone

- `riskLevel` (LOW, MEDIUM, HIGH)

---

## Example Payloads

### Water sensor

topic: /city/water01/attrs
payload: level=2.3

### Rain sensor

topic: /city/rain01/attrs
payload: rain=80

---

## Core Rules

- **Heavy rain** → `rain > 70`
- **High water level** → `level > 2.0`
- **Flood risk** → rain + water high
- **Geo alert** → sensors near critical areas exceed threshold

---

## Possible Occurrences (Scenarios)

### 1. Normal Conditions

- Low rain and water levels
- Stable system
- No alerts

---

### 2. Gradual Rain Increase

- Rain rises slowly
- Water level follows
- Early warning triggered

---

### 3. Sudden Storm (Burst Event)

- All sensors update simultaneously
- High-frequency updates
- CPU spike due to:
  - multiple writes
  - rule evaluations
  - notifications

---

### 4. Flood Risk Detection

- Rain + water exceed thresholds
- FloodZone updated to `HIGH`
- Alerts triggered

---

### 5. Geo-Query Pressure

- Dashboard querying nearby sensors frequently
- Expensive spatial queries
- CPU and DB load increase

---

### 6. Combined Stress Scenario (Worst Case)

- Burst updates
- - geo queries
- - active subscriptions

Results:

- Orion CPU spikes
- MongoDB query slowdown
- Notification backlog

---

## What to Observe

- Orion CPU usage and latency
- MongoDB query performance (geo queries)
- Event processing delay
- Notification throughput

---

## Key Insight

This scenario stresses:

- **data ingestion (writes)**
- **real-time queries (reads)**
- **spatial processing (geo)**
