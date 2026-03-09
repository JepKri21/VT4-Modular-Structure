import paho.mqtt.client as mqtt
import random
import string
import time
import threading

# Konfiguration af MQTT broker
BROKER = "100.117.139.24"  # eller IP-adressen på din Raspberry Pi
PORT = 1883
TOPICS = ["aau/smartlab/PL1/stations/drilling_1/CMD", "aau/smartlab/PL1/stations/drilling_1/STATUS", "aau/smartlab/PL1/stations/drilling_1/ALARMS"]

# Funktion til at generere en besked med tilfældig størrelse
def generate_message(size):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=size))

# Funktion til at publicere beskeder på et topic med et interval
def publish_messages(client, topic, min_interval, max_interval, min_size, max_size):
    while True:
        size = random.randint(min_size, max_size)
        message = generate_message(size)
        client.publish(topic, message)
        print(f"Sent to {topic}: {message[:50]}... ({size} bytes)")
        interval = random.uniform(min_interval, max_interval)
        time.sleep(interval)

def main():
    client = mqtt.Client()
    client.connect(BROKER, PORT, 60)
    client.loop_start()

    # Start en tråd for hvert topic
    threads = []
    for topic in TOPICS:
        t = threading.Thread(target=publish_messages, args=(client, topic, 0.1, 0.1, 100, 500))
        t.daemon = True
        t.start()
        threads.append(t)

    # Hold programmet kørende
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping publisher...")
        client.loop_stop()

if __name__ == "__main__":
    main()