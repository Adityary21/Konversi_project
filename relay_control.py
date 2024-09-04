import network
import socket
from machine import Pin
import utime

# Mengonfigurasi Wi-Fi
ssid = 'wifi'
password = 'kucin123'

station = network.WLAN(network.STA_IF)
station.active(True)
station.connect(ssid, password)

while not station.isconnected():
    utime.sleep(1)
    print("Connecting to WiFi...")

print("Connected to WiFi")
print(station.ifconfig())

#pin relay
relay1 = Pin(2, Pin.OUT)
relay2 = Pin(3, Pin.OUT)
relay3 = Pin(4, Pin.OUT)
relay4 = Pin(5, Pin.OUT)

# Fungsi relay control
def toggle_relay(relay, state):
    relay.value(state)

# Membuat server socket
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.bind(addr)
s.listen(5)
print('Listening on', addr)

while True:
    cl, addr = s.accept()
    print('Client connected from', addr)
    request = cl.recv(1024).decode()
    print("Request:", request)

    if 'GET /1/on' in request:
        toggle_relay(relay1, 0)
    elif 'GET /1/off' in request:
        toggle_relay(relay1, 1)
    elif 'GET /2/on' in request:
        toggle_relay(relay2, 0)
    elif 'GET /2/off' in request:
        toggle_relay(relay2, 1)
    elif 'GET /3/on' in request:
        toggle_relay(relay3, 0)
    elif 'GET /3/off' in request:
        toggle_relay(relay3, 1)
    elif 'GET /4/on' in request:
        toggle_relay(relay4, 0)
    elif 'GET /4/off' in request:
        toggle_relay(relay4, 1)
    elif 'GET /off/all' in request:
        toggle_relay(relay1, 1)
        toggle_relay(relay2, 1)
        toggle_relay(relay3, 1)
        toggle_relay(relay4, 1)

    response = 'HTTP/1.1 200 OK\n\nRelay Command Executed'
    cl.send(response)
    cl.close()


