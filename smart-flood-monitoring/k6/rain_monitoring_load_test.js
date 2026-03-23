/**
 * FIWARE Smart Rain Monitoring — k6 MQTT Load Test
 * =================================================
 * Uses grafana/xk6-mqtt (import "k6/x/mqtt")
 *
 * Build the k6 binary with the MQTT extension:
 *   xk6 build --with github.com/grafana/xk6-mqtt
 *
 * Run:
 *   # Scenario 1 — Normal (baseline)
 *   SCENARIO=normal ./k6 run --vus 10 --duration 30s rain_monitoring_load_test.js
 *
 *   # Scenario 3 — Sudden storm burst
 *   SCENARIO=storm ./k6 run --vus 50 --duration 60s rain_monitoring_load_test.js
 *
 *   # Scenario 6 — Combined stress (default)
 *   SCENARIO=stress ./k6 run --vus 100 --duration 2m rain_monitoring_load_test.js
 *
 * Environment variables:
 *   MQTT_HOST      Mosquitto hostname/IP   (default: localhost)
 *   MQTT_PORT      Mosquitto port          (default: 1883)
 *   MQTT_USER      MQTT username           (optional)
 *   MQTT_PASS      MQTT password           (optional)
 *   API_KEY        FIWARE IoT Agent API key (default: RAIN)
 *   NUM_WATER      Number of WaterLevelSensor devices to simulate (default: 10)
 *   NUM_RAIN       Number of RainSensor devices to simulate       (default: 5)
 *   NUM_ZONES      Number of FloodZone IDs to reference           (default: 3)
 *   SCENARIO       Load scenario: normal | gradual | storm | flood | stress (default: stress)
 */

import { Client } from "k6/x/mqtt";
import { check, sleep } from "k6";
import { Counter, Trend, Rate } from "k6/metrics";
import exec from "k6/execution";

// ---------------------------------------------------------------------------
// Config from environment
// ---------------------------------------------------------------------------

const MQTT_HOST = __ENV.MQTT_HOST || "localhost";
const MQTT_PORT = __ENV.MQTT_PORT || "1883";
const MQTT_USER = __ENV.MQTT_USER || "";
const MQTT_PASS = __ENV.MQTT_PASS || "";
const API_KEY = __ENV.API_KEY || "TEF";
const NUM_WATER = parseInt(__ENV.NUM_WATER || "10");
const NUM_RAIN = parseInt(__ENV.NUM_RAIN || "5");
const NUM_ZONES = parseInt(__ENV.NUM_ZONES || "3");
const SCENARIO = __ENV.SCENARIO || "stress";

const BROKER_URL = `mqtt://${MQTT_HOST}:${MQTT_PORT}`;

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------

const mqttPublishOk = new Counter("mqtt_publish_ok");
const mqttPublishFail = new Counter("mqtt_publish_fail");
const mqttPublishDuration = new Trend("mqtt_publish_duration_ms", true);
const mqttConnectOk = new Counter("mqtt_connect_ok");
const mqttConnectFail = new Counter("mqtt_connect_fail");
const heavyRainRate = new Rate("heavy_rain_rate");     // intensity > 70
const highWaterRate = new Rate("high_water_rate");     // level > 2.0
const floodRiskRate = new Rate("flood_risk_rate");     // both exceeded

// ---------------------------------------------------------------------------
// Scenario options
// ---------------------------------------------------------------------------

// Each scenario shapes the k6 executor and the payload generator.
// VUs and duration can also be overridden at CLI level.
export const options = {
    scenarios: {
        rain_monitoring: {
            executor: "constant-vus",
            vus: scenarioVus(),
            duration: scenarioDuration(),
        },
    },
    thresholds: {
        mqtt_publish_ok: ["count>0"],
        mqtt_publish_fail: ["count<10"],          // fewer than 10 failures total
        mqtt_publish_duration_ms: ["p(95)<500"],         // 95th percentile under 500ms
        mqtt_connect_ok: ["count>0"],
    },
};

function scenarioVus() {
    const map = { normal: 5, gradual: 10, storm: 50, flood: 20, stress: 100 };
    return map[SCENARIO] || 50;
}

function scenarioDuration() {
    const map = { normal: "30s", gradual: "90s", storm: "60s", flood: "30s", stress: "2m" };
    return map[SCENARIO] || "60s";
}

// ---------------------------------------------------------------------------
// Device ID pools
// (mirrors provision_rain_monitoring.py naming: wls0001 … rs0001 … fz0001 …)
// ---------------------------------------------------------------------------

function pad(n) { return String(n).padStart(4, "0"); }

const WATER_IDS = Array.from({ length: NUM_WATER }, (_, i) => `wls${pad(i + 1)}`);
const RAIN_IDS = Array.from({ length: NUM_RAIN }, (_, i) => `rs${pad(i + 1)}`);
const ZONE_IDS = Array.from({ length: NUM_ZONES }, (_, i) => `fz${pad(i + 1)}`);

function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

// ---------------------------------------------------------------------------
// FIWARE IoT Agent UltraLight topic builders
//
// Topic format:   /<API_KEY>/<device_id>/attrs
// Payload format: <object_id>=<value>|<object_id>=<value>
//
// WaterLevelSensor: object_ids → l (level), loc (location)
// RainSensor:       object_ids → i (intensity)
// ---------------------------------------------------------------------------

function topicFor(deviceId) {
    return `/${API_KEY}/${deviceId}/attrs`;
}

function waterPayload(level) {
    // lat/lon slightly randomised to simulate sensor drift
    const lat = (-22.9028 + (Math.random() - 0.5) * 0.01).toFixed(6);
    const lon = (-43.1729 + (Math.random() - 0.5) * 0.01).toFixed(6);
    return `l|${level.toFixed(2)}|loc|${lat},${lon}`;
}

function rainPayload(intensity) {
    return `i|${intensity.toFixed(1)}`;
}

// ---------------------------------------------------------------------------
// Value generators per scenario
// ---------------------------------------------------------------------------

function normalValues() {
    return {
        level: Math.random() * 0.6 + 0.2,           // 0.2 – 0.8 m
        intensity: Math.random() * 15 + 5,             // 5  – 20 mm
    };
}

function gradualValues() {
    // progress from 0 to 1 over the test duration — k6 doesn't expose elapsed time
    // easily, so we approximate with iteration count relative to VU
    const progress = (exec.scenario.iterationInTest % 80) / 80;
    return {
        level: 0.2 + progress * 2.2,                // 0.2 → 2.4
        intensity: 5 + progress * 85,                 // 5   → 90
    };
}

function stormValues() {
    return {
        level: Math.random() * 2.0 + 2.0,           // 2.0 – 4.0 m  (above threshold)
        intensity: Math.random() * 60 + 80,            // 80  – 140 mm (above threshold)
    };
}

function floodValues() {
    return {
        level: Math.random() * 1.5 + 2.5,           // always HIGH
        intensity: Math.random() * 40 + 90,            // always HIGH
    };
}

function stressValues() {
    // Mixed: ~60% normal, ~25% elevated, ~15% critical
    const r = Math.random();
    if (r < 0.60) return normalValues();
    if (r < 0.85) return { level: Math.random() * 1.5 + 1.0, intensity: Math.random() * 40 + 50 };
    return floodValues();
}

function valuesForScenario() {
    switch (SCENARIO) {
        case "normal": return normalValues();
        case "gradual": return gradualValues();
        case "storm": return stormValues();
        case "flood": return floodValues();
        case "stress": return stressValues();
        default: return stressValues();
    }
}

// ---------------------------------------------------------------------------
// Publish helper — wraps a single client.publish() with timing and metrics
// ---------------------------------------------------------------------------

function publishMeasured(client, topic, payload) {
    const t0 = Date.now();
    try {
        client.publish(topic, payload, { qos: 1, retain: false });
        mqttPublishOk.add(1);
        mqttPublishDuration.add(Date.now() - t0);
    } catch (e) {
        mqttPublishFail.add(1);
        console.error(`Publish failed on topic ${topic}: ${e}`);
    }
}

// ---------------------------------------------------------------------------
// Sleep between iterations — scenario-tuned
// ---------------------------------------------------------------------------

function iterationSleep() {
    const map = { normal: 1.0, gradual: 0.8, storm: 0.1, flood: 0.5, stress: 0.05 };
    const base = map[SCENARIO] || 0.2;
    // jitter ±30%
    sleep(base * (0.7 + Math.random() * 0.6));
}

// ---------------------------------------------------------------------------
// Main VU function
// ---------------------------------------------------------------------------

export default function () {
    const vuId = exec.vu.idInTest;
    const clientId = `k6-vu-${vuId}-${Date.now()}`;

    const client = new Client();
    let connected = false;

    client.on("connect", () => {
        connected = true;
        mqttConnectOk.add(1);

        const { level, intensity } = valuesForScenario();

        // Track threshold breaches for custom metrics
        heavyRainRate.add(intensity > 70 ? 1 : 0);
        highWaterRate.add(level > 2.0 ? 1 : 0);
        floodRiskRate.add(intensity > 70 && level > 2.0 ? 1 : 0);

        // --- Publish water level sensor reading
        const waterDeviceId = pick(WATER_IDS);
        publishMeasured(client, topicFor(waterDeviceId), waterPayload(level));

        // --- Publish rain sensor reading
        const rainDeviceId = pick(RAIN_IDS);
        publishMeasured(client, topicFor(rainDeviceId), rainPayload(intensity));

        // --- Storm / stress: burst-publish to multiple sensors simultaneously
        if (SCENARIO === "storm" || SCENARIO === "stress") {
            const extraCount = SCENARIO === "stress" ? 3 : 2;
            for (let i = 0; i < extraCount; i++) {
                const { level: l2, intensity: i2 } = valuesForScenario();
                publishMeasured(client, topicFor(pick(WATER_IDS)), waterPayload(l2));
                publishMeasured(client, topicFor(pick(RAIN_IDS)), rainPayload(i2));
            }
        }

        check(connected, { "mqtt connected": (v) => v === true });

        client.end();
    });

    client.on("error", (err) => {
        mqttConnectFail.add(1);
        console.error(`MQTT error on VU ${vuId}: ${err}`);
    });

    client.connect(BROKER_URL, {
        clientId: clientId,
        username: MQTT_USER,
        password: MQTT_PASS,
        keepAlive: 30,
        clean: true,
    });

    iterationSleep();
}

// ---------------------------------------------------------------------------
// Setup — print test plan summary
// ---------------------------------------------------------------------------

export function setup() {
    console.log("=================================================");
    console.log(" FIWARE Smart Rain Monitoring — k6 MQTT Load Test");
    console.log("=================================================");
    console.log(` Broker:    ${BROKER_URL}`);
    console.log(` API Key:   ${API_KEY}`);
    console.log(` Scenario:  ${SCENARIO}`);
    console.log(` Fleet:     ${NUM_WATER} WaterLevelSensor | ${NUM_RAIN} RainSensor | ${NUM_ZONES} FloodZone`);
    console.log(` VUs:       ${scenarioVus()}`);
    console.log(` Duration:  ${scenarioDuration()}`);
    console.log("-------------------------------------------------");
    console.log(" Topics (FIWARE UltraLight format):");
    console.log(`   /${API_KEY}/<device_id>/attrs`);
    console.log("   WaterLevelSensor payload: l|<level>|loc|<lat>,<lon>");
    console.log("   RainSensor payload:       i|<intensity>");
    console.log("=================================================");
}

// ---------------------------------------------------------------------------
// Teardown — final summary
// ---------------------------------------------------------------------------

export function teardown() {
    console.log("=================================================");
    console.log(" Test complete. Key metrics to check:");
    console.log("   mqtt_publish_ok           — total successful publishes");
    console.log("   mqtt_publish_fail         — should be near 0");
    console.log("   mqtt_publish_duration_ms  — p95 target < 500ms");
    console.log("   heavy_rain_rate           — % of msgs with intensity > 70");
    console.log("   high_water_rate           — % of msgs with level > 2.0");
    console.log("   flood_risk_rate           — % of msgs triggering full flood alert");
    console.log("=================================================");
}