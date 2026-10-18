# send_test.py - sends test packets to the household device and prints its replies.
# Run it while the Wokwi simulation is running. Stop watcher.py first (it uses the same port).
import time
import serial
 
PORT = "rfc2217://localhost:4000"
LINES = [
    "1|0|3a0ade314b8bef15|Test one",
    "1|0|3a0ade314b8bef15|Test one",
    "2|30|65009374dc629882|Hop limit",
    "3|5|2f6e29bed8273174|Mid hop",
    "4|bdf343040b28d3ed|Old gateway",
]

 
ser = serial.serial_for_url(PORT, baudrate=115200, timeout=0.5)
time.sleep(1)
ser.reset_input_buffer()
 
for line in LINES:
    print("\n>>> SENDING:", line)
    ser.write((line + "\n").encode())
    end = time.time() + 4          # the device shows and beeps for about 2-3 s
    while time.time() < end:
        data = ser.readline().decode(errors="replace").rstrip()
        if data:
            print("   ", data)
 
ser.close()
print("\nDone.")