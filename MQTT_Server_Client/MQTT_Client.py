import paho.mqtt.client as mqtt
import json
import time
import asyncio

class MQTT_Client_Resource():
    def __init__(self, broker, port, client_id, base_topic, machine):
        self.BROKER = broker
        self.PORT = port
        self.CLIENT_ID = client_id
        self.BASE_TOPIC = base_topic
        self.MACHINE = machine

        self.CLIENT = mqtt.Client(client_id=self.CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
    
    def on_connect(self,client, userdata, flags, rc):

        if rc == 0:
            print(f"{self.CLIENT_ID} connected to MQTT Broker!")
            client.subscribe(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/CMD")
            client.subscribe(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/info_request")
        
        else:
            print(f"Connection failed with code: {rc}")

    def on_message(self,client, userdata, msg):
        try:
            payload_str = msg.payload.decode()
            payload = json.loads(payload_str) 
            self.MACHINE.current_job = payload
            print("Received:", payload)
            if payload["command"] == "start":
                asyncio.run_coroutine_threadsafe(
                    self.MACHINE.state_command_callback("start"),
                    self.MACHINE.loop
                )
            elif payload["command"] == "stop":
                asyncio.run_coroutine_threadsafe(
                    self.MACHINE.state_command_callback("stop"),
                    self.MACHINE.loop
                )
            elif payload["command"] == "abort":
                asyncio.run_coroutine_threadsafe(
                    self.MACHINE.state_command_callback("abort"),
                    self.MACHINE.loop
                )
            elif payload["command"] == "reset":
                asyncio.run_coroutine_threadsafe(
                    self.MACHINE.state_command_callback("reset"),
                    self.MACHINE.loop
                )
            elif payload["command"] == "hold":
                asyncio.run_coroutine_threadsafe(
                    self.MACHINE.state_command_callback("hold"),
                    self.MACHINE.loop
                )
            elif payload["command"] == "unhold":
                asyncio.run_coroutine_threadsafe(
                    self.MACHINE.state_command_callback("unhold"),
                    self.MACHINE.loop
                )
            elif payload["command"] == "suspend":
                asyncio.run_coroutine_threadsafe(
                    self.MACHINE.state_command_callback("suspend"),
                    self.MACHINE.loop
                )
            elif payload["command"] == "clear":
                asyncio.run_coroutine_threadsafe(
                    self.MACHINE.state_command_callback("clear"),
                    self.MACHINE.loop
                )
        except Exception as e:
            print("MQTT parse error:", e)



    def publish_state(self, new_state):
        state_data = {
            "station_id": self.CLIENT_ID, 
            "state": str(new_state)
        }
        self.CLIENT.publish(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/State", json.dumps(state_data))

    def publish_job_status(self, result, order_id, job_id, ideal_cycle_time_ms, cycle_time_ms, quality):
        job_data = {
            "station_id": self.CLIENT_ID,
            "result": result,
            "order_id": order_id,
            "job_id": job_id,
            "ideal_cycle_time_ms": ideal_cycle_time_ms,
            "cycle_time_ms": cycle_time_ms,
            "quality": quality,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")        }
        self.CLIENT.publish(
            
            f"{self.BASE_TOPIC}/{self.CLIENT_ID}/JobStatus",
            json.dumps(job_data)
        )

    def start_mqtt_connection(self):
        self.CLIENT.on_connect = self.on_connect
        self.CLIENT.on_message = self.on_message

        self.CLIENT.connect(self.BROKER,self.PORT)
        self.CLIENT.loop_start()
        time.sleep(2)
    

        