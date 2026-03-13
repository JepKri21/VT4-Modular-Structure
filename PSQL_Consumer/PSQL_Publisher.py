import json
import psycopg2
import paho.mqtt.client as mqtt
from datetime import datetime

# ====== MQTT CONFIG ======
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
JOB_STATUS = "AAU/Smartlab/PL1/Stations/Drilling_1/job_status"
STATE = "AAU/Smartlab/PL1/Stations/Drilling_1/PackML_state"
ALARMS = "AAU/Smartlab/PL1/Stations/Drilling_1/active_alarms"

# ====== POSTGRESQL CONFIG ======
PG_HOST = "localhost"
PG_PORT = 5432
PG_DB = "thesis_mes"
PG_USER = "postgres"
PG_PASSWORD = "password"


# ====== RELEVANT PACKML STATES ======
RELEVANT_STATES = {
    """These states are the only relevant states to be logged in the database, due to them influencing the performance metrics of the station, such as availability, performance, and quality used in OEE calculations."""
    "PackMLState.EXECUTE",
    "PackMLState.IDLE",
    "PackMLState.HOLDING",
    "PackMLState.SUSPENDED",
    "PackMLState.ABORTED",
    "PackMLState.STOPPED"
}

last_state = None


# ====== DATABASE CONNECTION ======
conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    database=PG_DB,
    user=PG_USER,
    password=PG_PASSWORD
)
cursor = conn.cursor()

# ====== INSERT FUNCTIONS ======
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

def insert_state(state_data):
    """Insert state data into station_state_changes table"""
    sql = """
    INSERT INTO station_state_changes
    (station_id, state, timestamp)
    VALUES (%s,%s,%s)
    """
    timestamp = state_data.get("timestamp")

    if timestamp is None:
        timestamp = datetime.utcnow()
    cursor.execute(sql, (
        state_data.get("station_id"),
        state_data.get("state"),
        timestamp
    ))
    conn.commit()
    print(f"[DB] Inserted state: {state_data.get('state')}")

def insert_alarms(alarms_data):
    """Insert alarm data into station_alarms table"""
    alarms = alarms_data.get("active_alarms", [])
    for alarm_id in alarms:

        sql = """
        INSERT INTO station_alarms
        (station_id, alarm_id, timestamp)
        VALUES (%s,%s,%s)
        """
        timestamp = alarms_data.get("timestamp")
        if timestamp is None:
            timestamp = datetime.utcnow()
        cursor.execute(sql, (
            alarms_data.get("station_id"),
            alarm_id,
            timestamp
        ))

    conn.commit()
    print(f"[DB] Inserted {len(alarms)} alarms")


# ====== MQTT CALLBACKS ======
def on_connect(client, userdata, flags, reasonCode, properties=None):
    if reasonCode == 0:
        print("[MQTT] Connected successfully")
        client.subscribe(JOB_STATUS)
        client.subscribe(STATE)
        client.subscribe(ALARMS)
    else:
        print(f"[MQTT] Failed to connect, code {reasonCode}")

def on_message(client, userdata, msg):

    global last_state

    try:
        payload = json.loads(msg.payload.decode())
        print(f"[MQTT] Topic: {msg.topic}")
        print(payload)

        # ===== JOB STATUS =====
        if msg.topic == JOB_STATUS and payload.get("result") == "COMPLETE":
            insert_job(payload)

        # ===== STATE CHANGES =====
        elif msg.topic == STATE:
            state = payload.get("state")
            if state in RELEVANT_STATES and state != last_state:
                insert_state(payload)
                last_state = state
            else:
                print(f"[STATE] Ignored: {state}")

        # ===== ALARMS =====
        elif msg.topic == ALARMS:
            active_alarms = payload.get("active_alarms", [])
            if len(active_alarms) > 0:
                insert_alarms(payload)
            else:
                print("[ALARMS] No active alarms")

    except Exception as e:
        print("[ERROR]", type(e).__name__, e)

# ====== MQTT CLIENT ======

client = mqtt.Client(
    client_id="MES_Backend",
    callback_api_version=mqtt.CallbackAPIVersion.VERSION1
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

print("MES Consumer running...")

client.loop_forever()