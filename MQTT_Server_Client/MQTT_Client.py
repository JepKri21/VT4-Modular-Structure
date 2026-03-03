import paho.mqtt.client as mqtt
import json
import time

class MQTT_Client_Resource():
    def __init__(self, broker, port, client_id, base_topic):
        self.BROKER = broker
        self.PORT = port
        self.CLIENT_ID = client_id
        self.BASE_TOPIC = base_topic

        self.CLIENT = mqtt.Client(client_id=self.CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
    
    def on_connect(self,client, userdata, flags, rc):

        if rc == 0:
            print(f"{self.CLIENT_ID} connected to MQTT Broker!")
            client.subscribe(f"{self.BASE_TOPIC}")
        else:
            print(f"Connection failed with code: {rc}")

    def on_message(self,client, userdata, msg):
        command = msg.payload.decode()
        print(f"Got this command: {command}")

    def publish_state(self, new_state):
        state_data = {"state": str(new_state)}
        self.CLIENT.publish(f"{self.BASE_TOPIC}/State", json.dumps(state_data))

    def start_mqtt_connection(self):
        self.CLIENT.on_connect = self.on_connect
        self.CLIENT.on_message = self.on_message

        self.CLIENT.connect(self.BROKER,self.PORT)
        self.CLIENT.loop_start()
        time.sleep(2)
    

        