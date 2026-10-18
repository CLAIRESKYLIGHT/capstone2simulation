# ============================================================
# watcher.py - Central Control (types announcements, relays them, speaks them)
#   - Sends what you type to the Gateway (port 4000)
#   - Relays the gateway's authenticated packet to household1 (4001) and household2 (4002)
#   - Prepares the Filipino female voice WHILE the households beep, then plays it as soon
#     as both households report that their beep has finished
# ============================================================
import sys
import json
import hmac
import hashlib
import getpass
from datetime import datetime
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
 
# ---- Voice speed ----
VOICE_RATE = "-10%"      # online voice: "+0%" = normal, "-10%" a little slower, "-20%" slower still
OFFLINE_RATE = 140       # offline voice (words per minute); lower = slower
 
# ---- Beep / voice timing ----
# The households print "BEEP_DONE" when their beep has finished.
BEEP_WAIT_TIMEOUT = 6.0        # stop waiting after this many seconds and speak anyway
VOICE_DELAY_AFTER_BEEP = 0.4   # small gap after the beep (raise it if the beep still overlaps)
 
# Offline fallback: pick a FEMALE Windows voice (names checked in this order)
FEMALE_VOICE_HINTS = ["zira", "hazel", "susan", "heera", "catherine", "aria", "eva", "linda", "female"]
 
 
 
# ============================================================
# ACCESS CONTROL (Role-Based Access Control at the Central Control)
# Only logged-in barangay officials can send announcements. Passwords/PINs are never stored:
# each is kept as a salted PBKDF2-SHA256 hash in users.json. Every login and every
# announcement is written to audit_log.txt (who, when, what).
# ============================================================
USERS_FILE = "users.json"
AUDIT_FILE = "audit_log.txt"
MAX_LOGIN_ATTEMPTS = 3
PBKDF2_ROUNDS = 200_000
ROLES = {
    "admin":    "send announcements, add users, view the audit log",
    "official": "send announcements",
    "viewer":   "view the audit log only (cannot send)",
}
# ---- AUTH-START ----
 
 
def audit(user, event, detail=""):
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {user} | {event} | {detail}\n")
 
 
def hash_secret(secret, salt_hex=None):
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt.hex(), digest.hex()
 
 
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
 
 
def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
 
 
def add_user(users, name, secret, role):
    salt, digest = hash_secret(secret)
    users[name] = {"role": role, "salt": salt, "hash": digest}
    save_users(users)
 
 
def first_time_setup(users):
    print("No accounts exist yet. Create the first account (role: admin).")
    while True:
        name = input("Admin username: ").strip()
        secret = getpass.getpass("Admin password or PIN: ")
        again = getpass.getpass("Repeat it: ")
        if name and secret and secret == again:
            break
        print("Empty username/password, or the two entries differ. Try again.")
    add_user(users, name, secret, "admin")
    audit(name, "ACCOUNT_CREATED", "first admin account")
    print("Admin account created.\n")
 
 
def login():
    users = load_users()
    if not users:
        first_time_setup(users)
    print("=== Barangay Announcement System - Central Control login ===")
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        name = input("Username: ").strip()
        secret = getpass.getpass("Password or PIN: ")
        record = users.get(name)
        ok = False
        if record:
            _, digest = hash_secret(secret, record["salt"])
            ok = hmac.compare_digest(digest, record["hash"])
        if ok:
            audit(name, "LOGIN_OK", f"role={record['role']}")
            print(f"Welcome, {name} ({record['role']}).\n")
            return name, record["role"]
        audit(name or "(blank)", "LOGIN_FAIL", f"attempt {attempt}")
        print(f"Invalid username or password ({attempt}/{MAX_LOGIN_ATTEMPTS}).")
    audit("-", "LOCKED_OUT", f"{MAX_LOGIN_ATTEMPTS} failed attempts")
    print("Too many failed attempts. Exiting.")
    sys.exit(1)
# ---- AUTH-END ----
 
 
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
 
 
current_user, current_role = login()   # nothing connects or sends until a valid login
 
gateway = connect_with_retry("rfc2217://localhost:4000")
household1 = connect_with_retry("rfc2217://localhost:4001")
household2 = connect_with_retry("rfc2217://localhost:4002")
 
 
# ---------------- Voice ----------------
def pick_female_voice(engine):
    voices = engine.getProperty("voices")
    for hint in FEMALE_VOICE_HINTS:
        for v in voices:
            if hint in (v.name or "").lower():
                return v
    return None
 
 
def speak_offline_female(text):
    pythoncom.CoInitialize()
    try:
        engine = pyttsx3.init()
        voice = pick_female_voice(engine)
        if voice is not None:
            engine.setProperty("voice", voice.id)
            print(f"[TTS] Offline voice: {voice.name}")
        else:
            print("[TTS] WARNING: no female offline voice found; using the default voice.")
        engine.setProperty("rate", OFFLINE_RATE)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    finally:
        pythoncom.CoUninitialize()
 
 
def synthesize_tagalog(text):
    """Create the Filipino voice audio file (this is the slow, online step)."""
    async def _generate():
        communicate = edge_tts.Communicate(text, TAGALOG_VOICE, rate=VOICE_RATE)
        await communicate.save(TEMP_AUDIO_FILE)
    if os.path.exists(TEMP_AUDIO_FILE):
        try:
            os.remove(TEMP_AUDIO_FILE)
        except OSError:
            pass
    asyncio.run(_generate())
 
 
def play_announcement(text, tagalog_ready):
    if tagalog_ready:
        try:
            playsound(TEMP_AUDIO_FILE)
            print("[TTS] Tagalog voice played.")
            return
        except Exception as exc:
            print(f"[TTS] Could not play the Tagalog audio: {exc}")
        finally:
            try:
                os.remove(TEMP_AUDIO_FILE)
            except OSError:
                pass
    print("[TTS] Using the offline female voice (it reads Tagalog with an English accent).")
    try:
        speak_offline_female(text)
    except Exception as exc:
        print(f"[TTS] Offline voice also failed: {exc}")
 
 
# ---------------- Beep tracking ----------------
beep_done = {1: threading.Event(), 2: threading.Event()}
 
 
def household_reader(ser, number):
    """Listen to one household's serial output and note when its beep has finished."""
    buffer = ""
    while True:
        data = ser.read(1)
        if not data:
            time.sleep(0.02)
            continue
        buffer += data.decode(errors="ignore")
        if "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.strip() == "BEEP_DONE":
                beep_done[number].set()
 
 
# ---------------- Relay ----------------
def relay_loop():
    buffer = ""
    while True:
        data = gateway.read(1)
        if not data:
            time.sleep(0.02)
            continue
        buffer += data.decode(errors="ignore")
        if "\n" not in buffer:
            continue
        line, buffer = buffer.split("\n", 1)
        line = line.strip()
        if not line.startswith("ANNOUNCE:"):
            continue
 
        packet = line.replace("ANNOUNCE:", "", 1).strip()
        # packet format: sequence|hmac|message
        parts = packet.split("|", 2)
        plain_message = parts[2] if len(parts) == 3 else packet
 
        print(f"Relaying (authenticated) to households: {plain_message}")
        t_start = time.time()
        beep_done[1].clear()
        beep_done[2].clear()
 
        # 1. start preparing the voice NOW, while the households are beeping
        result = {"ready": False}
 
        def prepare():
            t0 = time.time()
            try:
                synthesize_tagalog(plain_message)
                result["ready"] = True
                print(f"[TTS] Tagalog voice ready after {time.time() - t0:.1f}s")
            except Exception as exc:
                print(f"[TTS] Tagalog voice failed: {exc}")
                print("[TTS] (try: pip install --upgrade edge-tts, and check the internet connection)")
 
        prep = threading.Thread(target=prepare)
        prep.start()
 
        # 2. send the packet to both households
        household1.write((packet + "\n").encode())
        household2.write((packet + "\n").encode())
 
        # 3. wait until both households have finished their beep
        deadline = time.time() + BEEP_WAIT_TIMEOUT
        for n in (1, 2):
            if not beep_done[n].wait(timeout=max(0.0, deadline - time.time())):
                print(f"[SYNC] household{n} did not report BEEP_DONE (does it have the newest main.cpp?)")
        print(f"[SYNC] beeps finished {time.time() - t_start:.1f}s after relaying")
 
        # 4. make sure the voice is ready, then speak
        prep.join()
        time.sleep(VOICE_DELAY_AFTER_BEEP)
        print(f"[TTS] Speaking {time.time() - t_start:.1f}s after relaying: {plain_message}")
        play_announcement(plain_message, result["ready"])
 
 
def show_log():
    if not os.path.exists(AUDIT_FILE):
        print("(audit log is empty)")
        return
    with open(AUDIT_FILE, "r", encoding="utf-8") as f:
        for line in f.readlines()[-15:]:
            print("  " + line.rstrip())
 
 
def add_user_command():
    users = load_users()
    name = input("New username: ").strip()
    role = input(f"Role ({'/'.join(ROLES)}): ").strip().lower()
    if not name or role not in ROLES or name in users:
        print("Cancelled: empty name, unknown role, or the user already exists.")
        return
    secret = getpass.getpass("Password or PIN: ")
    again = getpass.getpass("Repeat it: ")
    if not secret or secret != again:
        print("Cancelled: empty secret or the entries differ.")
        return
    add_user(users, name, secret, role)
    audit(current_user, "ACCOUNT_CREATED", f"{name} ({role})")
    print(f"Account '{name}' created.")
 
 
def type_loop():
    print(f"Logged in as {current_user} ({current_role}): {ROLES[current_role]}.")
    print("Type an announcement and press Enter.  Commands: /log  /adduser  exit")
    while True:
        text = input("Announcement: ").strip()
        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            audit(current_user, "LOGOUT")
            break
        if text == "/log":
            if current_role in ("admin", "viewer"):
                show_log()
            else:
                print("Access denied for your role.")
                audit(current_user, "DENIED", "/log")
        elif text == "/adduser":
            if current_role == "admin":
                add_user_command()
            else:
                print("Access denied: only an admin can add users.")
                audit(current_user, "DENIED", "/adduser")
        elif text.startswith("/"):
            print("Unknown command.")
        elif current_role == "viewer":
            print("Access denied: your role cannot send announcements.")
            audit(current_user, "DENIED", f"send attempt: {text}")
        else:
            gateway.write((text + "\n").encode())
            audit(current_user, "SEND", text)
            print("Sent to Gateway.")
 
 
threading.Thread(target=household_reader, args=(household1, 1), daemon=True).start()
threading.Thread(target=household_reader, args=(household2, 2), daemon=True).start()
threading.Thread(target=relay_loop, daemon=True).start()
type_loop()