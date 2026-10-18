# replay_test.py - proves the household rejects replayed, old, tampered and forged packets.
# Usage (watcher.py must be STOPPED, the household simulation must be running):
#     python replay_test.py            -> tests household1 (port 4001)
#     python replay_test.py 4002       -> tests household2
# After the test, RESTART that household simulation (its "last accepted sequence" is now 1001).
import sys
import time
import hmac
import hashlib
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "4001"
SECRET = b"BarangayOtaviSecretKey2026"        # must match SHARED_SECRET in main.cpp
WRONG_SECRET = b"SomeAttackerGuessedKey"


def sign(seq, msg, key=SECRET):
    return hmac.new(key, f"{seq}|{msg}".encode(), hashlib.sha256).hexdigest()[:16]


def packet(seq, msg, hop=0, key=SECRET):
    return f"{seq}|{hop}|{sign(seq, msg, key)}|{msg}"


TESTS = [
    ("1. Normal new message",                          packet(1000, "Replay test one"),
     "ACCEPTED, then FORWARD and RECEIVED"),
    ("2. SAME packet sent again (replay of a copy)",   packet(1000, "Replay test one"),
     "DUPLICATE ... not shown, not forwarded"),
    ("3. OLD message with a VALID signature",          packet(999, "Old message"),
     "REJECTED: replay detected (seq 999 < last accepted 1000)"),
    ("4. Next new message",                            packet(1001, "Replay test two"),
     "ACCEPTED, then FORWARD and RECEIVED"),
    ("5. Message 1000 replayed AFTER 1001 was shown",  packet(1000, "Replay test one"),
     "REJECTED: replay detected (seq 1000 < last accepted 1001)"),
    ("6. TAMPERED text (signature of a different text)",
     f"1002|0|{sign(1002, 'Real text')}|Changed text",
     "REJECTED: message integrity check failed (HMAC mismatch)"),
    ("7. FORGED packet (signed with a wrong key)",     packet(1003, "Forged announcement", key=WRONG_SECRET),
     "REJECTED: message integrity check failed (HMAC mismatch)"),
]

ser = serial.serial_for_url(f"rfc2217://localhost:{PORT}", baudrate=115200, timeout=0.5)
time.sleep(1)
ser.reset_input_buffer()

for title, pkt, expected in TESTS:
    print(f"\n=== {title}")
    print(f"    sending : {pkt}")
    print(f"    expected: {expected}")
    ser.write((pkt + "\n").encode())
    end = time.time() + 5
    while time.time() < end:
        line = ser.readline().decode(errors="replace").rstrip()
        if line:
            print("    device  :", line)

ser.close()
print("\nDone. Restart this household simulation before using the normal system again.")