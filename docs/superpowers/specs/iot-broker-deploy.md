# IoT MQTT Broker — EMQX Deploy Notes

The Watchful IoT system uses EMQX 5 as its MQTT broker. The `react-crm-api` service connects as a *subscriber* (the bridge) — devices connect as *publishers* using mTLS.

## Production: deploy as a Railway service

1. In the Mac-CRM-React project, create a new service: **New Service → Docker Image → `emqx/emqx:5.4`**.
2. Set service name: `mqtt-broker`.
3. Add a public TCP domain (Railway → Settings → Networking → Custom TCP):
   - Public TCP port → 8883 (mTLS port)
   - Required for direct device-to-broker connections.
4. Mount a persistent volume for `/opt/emqx/data` (cluster/session state).
5. Environment variables:
   ```
   EMQX_LISTENERS__SSL__DEFAULT__BIND=0.0.0.0:8883
   EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__CACERTFILE=/opt/emqx/etc/certs/ca.pem
   EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__CERTFILE=/opt/emqx/etc/certs/server.pem
   EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__KEYFILE=/opt/emqx/etc/certs/server.key
   EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__VERIFY=verify_peer
   EMQX_LISTENERS__SSL__DEFAULT__SSL_OPTIONS__FAIL_IF_NO_PEER_CERT=true
   EMQX_LOG__CONSOLE__LEVEL=info
   ```
6. Mount certs (CA + server cert/key) via Railway secrets / volume.
7. ACL config (`/opt/emqx/etc/acl.conf` mounted via volume):
   ```
   {allow, {clientid, {re, "^device-.+$"}}, publish, ["devices/${clientid}/+"]}.
   {allow, {clientid, {re, "^device-.+$"}}, subscribe, ["devices/${clientid}/cmd"]}.
   {allow, {clientid, "react-crm-bridge"}, subscribe, ["devices/+/+"]}.
   {allow, {clientid, "react-crm-bridge"}, publish, ["devices/+/cmd"]}.
   {deny, all}.
   ```

## Bridge configuration on `react-crm-api`

Set these env vars on the existing `react-crm-api` Railway service:
```
IOT_MQTT_ENABLED=true
IOT_MQTT_BROKER_HOST=mqtt-broker.railway.internal     # private DNS
IOT_MQTT_BROKER_PORT=8883
IOT_MQTT_BROKER_TLS=true
IOT_MQTT_CLIENT_CERT=/etc/secrets/iot-bridge.pem
IOT_MQTT_CLIENT_KEY=/etc/secrets/iot-bridge.key
IOT_MQTT_CA_CERT=/etc/secrets/iot-ca.pem
IOT_MQTT_CLIENT_ID=react-crm-bridge
```

## Local dev

Add to `docker-compose.yml`:
```yaml
emqx:
  image: emqx/emqx:5.4
  ports:
    - "1883:1883"   # plain TCP for local
    - "8883:8883"   # TLS
    - "18083:18083" # dashboard
  environment:
    - EMQX_NAME=emqx-dev
    - EMQX_HOST=127.0.0.1
  volumes:
    - emqx-data:/opt/emqx/data

volumes:
  emqx-data:
```

For local dev, set `IOT_MQTT_BROKER_PORT=1883`, `IOT_MQTT_BROKER_TLS=false`, omit cert paths.

## Cert generation (Phase 7 will fully script this)

Generate a CA, server cert, bridge client cert, and per-device client certs offline:
```bash
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.pem -subj "/CN=mac-septic-iot-ca"

openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -subj "/CN=mqtt-broker.railway.internal"
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out server.pem -days 825 -sha256

# Bridge cert
openssl genrsa -out bridge.key 2048
openssl req -new -key bridge.key -out bridge.csr -subj "/CN=react-crm-bridge"
openssl x509 -req -in bridge.csr -CA ca.pem -CAkey ca.key -out bridge.pem -days 825 -sha256

# Per-device cert (during manufacturing)
openssl genrsa -out device-${UUID}.key 2048
openssl req -new -key device-${UUID}.key -out device-${UUID}.csr -subj "/CN=device-${UUID}"
openssl x509 -req -in device-${UUID}.csr -CA ca.pem -CAkey ca.key -out device-${UUID}.pem -days 3650 -sha256
```

The device-side private key gets burned into nRF9160 secure storage at provisioning; the public cert (PEM) gets uploaded to the CRM via `POST /api/v2/iot/devices` along with the device serial.
