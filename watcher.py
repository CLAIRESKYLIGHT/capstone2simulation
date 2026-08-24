import serial
import threading
import time
import os
import asyncio
import pyttsx3
import pythoncom
import edge_tts
from playsound import playsound

SERIAL_URL = "rfc2217://localhost:4000"
BAUD = 115200

TAGALOG_VOICE = "fil-PH-BlessicaNeural"  # Filipino, female
TEMP_AUDIO_FILE = "temp_announcement.mp3"

def connect_with_retry(max_attempts=10, delay=1.5):
    for attempt in range(1, max_attempts + 1):
        try:
            s = serial.serial_for_url(SERIAL_URL, baudrate=BAUD, timeout=1)
            print("Connected to simulator.")
            return s
        except Exception as exc:
            print(f"Attempt {attempt}/{max_attempts} failed: {exc}")
            time.sleep(delay)
    raise RuntimeError("Could not connect after retries. Is the Wokwi simulation running?")

# ---- shared serial connection ----
ser = connect_with_retry()

# ---- background thread: listens for ANNOUNCE: lines and speaks them ----
def listen_loop():
    pythoncom.CoInitialize()

    async def _generate_tagalog(text, filename):
        communicate = edge_tts.Communicate(text, TAGALOG_VOICE)
        await communicate.save(filename)

    def speak_tagalog(text):
        """Try online Tagalog female voice first."""
        asyncio.run(_generate_tagalog(text, TEMP_AUDIO_FILE))
        playsound(TEMP_AUDIO_FILE)
        os.remove(TEMP_AUDIO_FILE)

    def speak_fallback(text):
        """Offline English fallback if no internet."""
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        del engine

    def speak(text):
        text = (text or "").strip()
        if not text:
            return
        print(f"Speaking: {text}")
        try:
            speak_tagalog(text)
        except Exception as exc:
            print(f"Tagalog TTS failed ({exc}), falling back to offline voice...")
            try:
                speak_fallback(text)
            except Exception as exc2:
                print(f"TTS error: {exc2}")

    buffer = ""
    try:
        while True:
            data = ser.read(1)
            if not data:
                time.sleep(0.02)
                continue
            buffer += data.decode(errors="ignore")
            if "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line.startswith("ANNOUNCE:"):
                    text = line.replace("ANNOUNCE:", "", 1).strip()
                    speak(text)
    except Exception as exc:
        print(f"Serial/listener error: {exc}")
    finally:
        pythoncom.CoUninitialize()

# ---- main thread: type announcements, send them ----
def send_loop():
    print("Gateway + Voice ready. Type an announcement and press Enter.")
    while True:
        text = input("Announcement: ").strip()
        if text.lower() in ("exit", "quit"):
            break
        ser.write((text + "\n").encode("utf-8"))
        print(f"Sent: {text}")

if __name__ == "__main__":
    listener = threading.Thread(target=listen_loop, daemon=True)
    listener.start()
    send_loop()
    ser.close()