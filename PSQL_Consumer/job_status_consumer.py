import json
import psycopg2
import paho.mqtt.client as mqtt
from datetime import datetime

# ====== CONFIG ======
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "AAU/Smartlab/PL1/Stations/Drilling_1/job_status"

PG_HOST = "localhost"
PG_PORT = 5432
PG_DB = "thesis_mes"
PG_USER = "postgres"
PG_PASSWORD = "password"

conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    database=PG_DB,
    user=PG_USER,
    password=PG_PASSWORD
)
cursor = conn.cursor()

# ====== HELPER ======
def insert_job(job):
    """Insert job_status into production_jobs table"""
    sql = """
    INSERT INTO production_jobs
    (station_id, order_id, job_id, result, ideal_cycle_time_ms, cycle_time_ms, quality, timestamp)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """
    cursor.execute(sql, (
        job.get("station_id"),
        job.get("order_id"),
        job.get("job_id"),
        job.get("result"),
        job.get("ideal_cycle_time_ms"),
        job.get("cycle_time_ms"),
        job.get("quality"),
        job.get("timestamp")
    ))
    conn.commit()
    print(f"[DB] Inserted job: {job.get('job_id')}")

# ====== MQTT CALLBACKS ======
def on_connect(client, userdata, flags, reasonCode, properties=None):
    if reasonCode == 0:
        print("[MQTT] Connected successfully")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"[MQTT] Failed to connect, code {reasonCode}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print("[MQTT RECEIVED]:", payload)

        if payload.get("result") == "COMPLETE":
            print("Inserting job into DB")
            insert_job(payload)

    except Exception as e:
        print("[ERROR]", type(e).__name__, e)

# ====== MQTT CLIENT ======
client = mqtt.Client(
    client_id="BackendConsumer",
    callback_api_version=mqtt.CallbackAPIVersion.VERSION1
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

client.loop_forever()