from flask import Flask, request, jsonify
import threading
import os
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import signal
import time
import sys
import requests
import json
from datetime import datetime
import cv2

app = Flask(__name__)
laptop_ip = None
laptop_ip_received = threading.Event()
continue_reading = True
reader = SimpleMFRC522()

def gen():
    camera = cv2.VideoCapture(0)  # Change the index if you have multiple cameras

    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# Flask routes
@app.route('/set_ip', methods=['POST'])
def set_ip():
    global laptop_ip
    data = request.get_json()
    # Print sender details
    sender_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    print(f"Request received from IP: {sender_ip}")
    print(f"User-Agent: {user_agent}")
    if 'ip' in data:
        laptop_ip = data['ip']
        laptop_ip_received.set()  # Signal that the IP has been received
        return jsonify({"message": "IP address received", "ip_address": laptop_ip}), 200
    else:
        return jsonify({"error": "Invalid payload"}), 400

@app.route('/video_feed')
def video_feed():
    return Response(gen(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def start_flask():
    app.run(host='0.0.0.0', port=5001)  # Runs on port 5001

# RFID reading functions
def end_read(signal, frame):
    global continue_reading
    print("\nCtrl+C captured, ending read.")
    continue_reading = False
    GPIO.cleanup()
    sys.exit(0)  # Ensure the script exits

signal.signal(signal.SIGINT, end_read)

def send_rfid_data(id_hex, timestamp, server_ip):
    url = f"http://{server_ip}:5001/rfid"
    print(url)
    payload = {
        "id": id_hex,
        "timestamp": timestamp
    }
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx and 5xx)
        return response.status_code, response.json()
    except requests.exceptions.RequestException as e:
        return None, str(e)

def read_rfid():
    laptop_ip_received.wait()  # Wait until the laptop IP is received
    try:
        while continue_reading:
            print("Hold a tag near the reader")
            id, text = reader.read()
            id_hex = hex(id)
            timestamp = datetime.now().isoformat()
            print(f"ID: {id_hex}\nTimestamp: {timestamp}")

            status_code, response = send_rfid_data(id_hex, timestamp, laptop_ip)

            if status_code == 200:
                print(f"Server responded with status code 200: {response}")
            else:
                print(f"Failed to send data. Error: {response}")

            time.sleep(1)

    except Exception as e:
        print(f"An error occurred: {e}")
        GPIO.cleanup()
        sys.exit(1)

    finally:
        GPIO.cleanup()

# Main function to start both threads
if __name__ == '__main__':
    # Start Flask server thread
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.start()

    # Start RFID reading thread
    rfid_thread = threading.Thread(target=read_rfid)
    rfid_thread.start()

    # Wait for threads to complete
    flask_thread.join()
    rfid_thread.join()
