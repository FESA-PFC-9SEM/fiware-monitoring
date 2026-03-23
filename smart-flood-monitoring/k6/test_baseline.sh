docker run -it --rm -e SCENARIO=flood -e MQTT_HOST=mosquitto --network fiware-backend -v $(pwd):/scripts k6-mqtt run /scripts/rain_monitoring_load_test.js
