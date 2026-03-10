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

        self.station_seq_no = 1
        self.controller_seq_no = 1
        self.seq_no_error = "NO_ERROR"
        #Potentially add a list for sequence numbers, you update the list every time you send a message with it's seq_no, 
        #that way you can ensure that if you send two messages before an acknowledgement has been sent from the controller
        #That you still check for the correct seq_no's.
        #The same could be done for the line controller, creating a list of all the messages that it is expecting 
        # an acknowledge from. And maybe it is actually smart to save the entire message in that list
        # that way it is easier to retransmit it, incase you don't recieve an acknowledge

        self.CLIENT = mqtt.Client(client_id=self.CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
    
    def on_connect(self,client, userdata, flags, rc):

        if rc == 0:
            print(f"{self.CLIENT_ID} connected to MQTT Broker!")
            client.subscribe(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/CMD")
            client.subscribe(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/info_request")
            client.subscribe(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/controller_ack")
        
        else:
            print(f"Connection failed with code: {rc}")

    def on_message(self,client, userdata, msg):
        try:
            
            topic = msg.topic
            print(f"Received message on topic: {topic}")

            if topic == f"{self.BASE_TOPIC}/{self.CLIENT_ID}/CMD":
                #Create a check for the topic, also read the sequence nubmer from the payload
                
                payload_str = msg.payload.decode()
                payload = json.loads(payload_str) 
                self.MACHINE.current_job = payload
                new_controller_seq_no = payload["seq_no"]

                #After having received the command, we send an ack
                self.publish_acknowledgement(new_controller_seq_no)

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
                
            elif topic == f"{self.BASE_TOPIC}/{self.CLIENT_ID}/info_request":
                payload_str = msg.payload.decode()
                payload = json.loads(payload_str)
                print("Received info request:", payload)
                requested_info = payload.get("info_request")
                self.publish_requested_info(requested_info)
                

            elif topic == f"{self.BASE_TOPIC}/{self.CLIENT_ID}/controller_ack":
                payload_str = msg.payload.decode()
                payload = json.loads(payload_str) 

                #This one should check if the seq number is correct, if it isn't do nothing and wait for a new one
                #Maybe start a timer so that if it times out we retransmit the message
                if payload["seq_no"] == 0:
                    self.controller_seq_no = 1


                if payload["error_code"] == "SEQ_TOO_LOW" or payload["error_code"] == "SEQ_TOO_HIGH":
                    #Sending reset to controller:
                    print(f"Resetting ack given the payload: {payload}")
                    self.publish_reset_acknowledgement()

                #When publishing a new message, send a sequence number with it and add it to a list
                #Here we can check that list to make sure we get an answer for all of them

        except Exception as e:
            print("MQTT parse error:", e)



    def publish_state(self, new_state):
        state_data = {
            "seq_no" : self.station_seq_no,
            "station_id": self.CLIENT_ID, 
            "state": str(new_state)
        }
        self.CLIENT.publish(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/PackML_state", json.dumps(state_data))
        self.station_seq_no += 1
    
    def publish_alarms(self, alarm_ids):
        alarm_data = {
            "station_id": self.CLIENT_ID,
            "seq_no" : self.station_seq_no,
            "active_alarms": alarm_ids,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        self.CLIENT.publish(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/active_alarms", json.dumps(alarm_data))
        self.station_seq_no += 1


    def publish_job_status(self, result, order_id, job_id, ideal_cycle_time_ms, cycle_time_ms, quality):
        job_data = {
            "station_id": self.CLIENT_ID,
            "seq_no": self.station_seq_no,
            "result": result,
            "order_id": order_id,
            "job_id": job_id,
            "ideal_cycle_time_ms": ideal_cycle_time_ms,
            "cycle_time_ms": cycle_time_ms,
            "quality": quality,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")        }
        self.CLIENT.publish(
            
            f"{self.BASE_TOPIC}/{self.CLIENT_ID}/job_status",
            json.dumps(job_data)
        )
        self.station_seq_no += 1

    def publish_acknowledgement(self, recieved_seq_no):
        #When we recieve a command or other message, we have to acknowledge it
        #We must check if the receieved seq number is correct

        if self.controller_seq_no == recieved_seq_no:
            error_code = "NO_ERROR"
        elif self.controller_seq_no > recieved_seq_no:
            error_code = "SEQ_TOO_LOW"
        elif self.controller_seq_no < recieved_seq_no:
            error_code = "SEQ_TOO_HIGH"
        
    
        ack_data = {
            "seq_no" : self.controller_seq_no,
            "error_code" : error_code,
            "timestamp" : time.strftime("%Y-%m-%dT%H:%M:%S") 
        }
        self.CLIENT.publish(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/station_ack", json.dumps(ack_data))

        #We update it so that the next expected seq_no is one more than what it previously was
        self.controller_seq_no += 1
    
    def publish_reset_acknowledgement(self):
        self.station_seq_no = 1
        ack_data = {
            "seq_no" : 0,
            "error_code" : "NO_ERROR",
            "timestamp" : time.strftime("%Y-%m-%dT%H:%M:%S") 
        }
        self.CLIENT.publish(f"{self.BASE_TOPIC}/{self.CLIENT_ID}/station_ack", json.dumps(ack_data))

    def publish_requested_info(self, requested_info):
        if requested_info == "system_state":
            self.publish_state(self.MACHINE.state)
        if requested_info == "active_alarms":
            self.publish_alarms(self.MACHINE.active_alarms)
            # self.publish_alarms(self.MACHINE.alarm_ids)


    def start_mqtt_connection(self):
        self.CLIENT.on_connect = self.on_connect
        self.CLIENT.on_message = self.on_message

        self.CLIENT.connect(self.BROKER,self.PORT)
        self.CLIENT.loop_start()
        time.sleep(2)
    

        