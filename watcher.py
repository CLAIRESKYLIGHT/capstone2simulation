import serial
import threading
import time
import os
import asyncio
import pythoncom
import edge_tts
import pyttsx3
from playsound import playsound
 
TAGALOG_VOICE = "fil-PH-BlessicaNeural"
TEMP_AUDIO_FILE = "temp_announcement.mp3"
 
# Seconds to wait after the households receive the packet, so their short beep finishes
# BEFORE the voice starts. Increase it if you still hear the beep over the voice.
VOICE_DELAY_AFTER_BEEP = 1.2
 
# Offline fallback: pick a FEMALE Windows voice (names checked in this order)
FEMALE_VOICE_HINTS = ["zira", "hazel", "susan", "heera", "catherine", "aria", "eva", "linda", "female"]
 
def connect_with_retry(url, max_attempts=10, delay=1.5):
    for attempt in range(1, max_attempts + 1):
        try:
            s = serial.serial_for_url(url, baudrate=115200, timeout=1)
            print(f"Connected to {url}")
            return s
        except Exception as exc:
            print(f"Attempt {attempt}/{max_attempts} failed for {url}: {exc}")
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to {url}. Is that simulation running?")
 
gateway = connect_with_retry("rfc2217://localhost:4000")
household1 = connect_with_retry("rfc2217://localhost:4001")
household2 = connect_with_retry("rfc2217://localhost:4002")
 
def pick_female_voice(engine):
    voices = engine.getProperty("voices")
    for hint in FEMALE_VOICE_HINTS:
        for v in voices:
            if hint in (v.name or "").lower():
                return v
    return None
 
 
def speak_offline_female(text):
    engine = pyttsx3.init()
    voice = pick_female_voice(engine)
    if voice is not None:
        engine.setProperty("voice", voice.id)
        print(f"[TTS] Offline voice: {voice.name}")
    else:
        print("[TTS] WARNING: no female offline voice found; using the default voice.")
    engine.setProperty("rate", 170)
    engine.say(text)
    engine.runAndWait()
    engine.stop()
 
 
def speak(text):
    """Filipino female voice (online). If that fails, a female offline voice."""
    print(f"[TTS] Attempting to speak: {text}")
    pythoncom.CoInitialize()
    try:
        asyncio.run(_speak_tagalog(text))
        print("[TTS] Tagalog voice succeeded.")
    except Exception as exc:
        print(f"[TTS] Tagalog voice failed: {exc}")
        print("[TTS] Using the offline female voice (it reads Tagalog with an English accent).")
        try:
            speak_offline_female(text)
        except Exception as exc2:
            print(f"[TTS] Offline voice also failed: {exc2}")
    finally:
        pythoncom.CoUninitialize()
 
async def _speak_tagalog(text):
    # rate="+20%" speaks noticeably faster, shortening total playback duration
    communicate = edge_tts.Communicate(text, TAGALOG_VOICE, rate="+20%")
    await communicate.save(TEMP_AUDIO_FILE)
    print(f"[TTS] Audio file saved: {TEMP_AUDIO_FILE}")
    playsound(TEMP_AUDIO_FILE)
    print("[TTS] playsound() finished.")
    os.remove(TEMP_AUDIO_FILE)
 
def relay_loop():
    buffer = ""
    while True:
        data = gateway.read(1)
        if not data:
            time.sleep(0.02)
            continue
        buffer += data.decode(errors="ignore")
        if "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line.startswith("ANNOUNCE:"):
                packet = line.replace("ANNOUNCE:", "", 1).strip()
                # packet format: sequence|hmac|message
                parts = packet.split("|", 2)
                if len(parts) == 3:
                    plain_message = parts[2]
                else:
                    plain_message = packet  # fallback if format is unexpected
 
                print(f"Relaying (authenticated) to households: {plain_message}")
                household1.write((packet + "\n").encode())
                household2.write((packet + "\n").encode())
                time.sleep(VOICE_DELAY_AFTER_BEEP)   # let the beep finish first
                speak(plain_message)
                
def type_loop():
    print("Type an announcement to send via Gateway.")
    while True:
        text = input("Announcement: ").strip()
        if text.lower() in ("exit", "quit"):
            break
        gateway.write((text + "\n").encode())
 
threading.Thread(target=relay_loop, daemon=True).start()
type_loop()