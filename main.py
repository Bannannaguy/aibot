import json
import os
import re
import subprocess
import sys
import threading
import urllib.request
import multiprocessing
from typing import Any
from PIL import Image
from arduino.app_bricks.llm import LargeLanguageModel
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.video_objectdetection import VideoObjectDetection
from arduino.app_utils import App

# ==========================================
# 0. MAIN PROCESS CORE AFFINITY (VISION / OS)
# ==========================================
try:
    pid = os.getpid()
    # Assign main process (handling video detection and web UI) to Core 1
    os.sched_setaffinity(pid, {1})
    print("[SYSTEM] Main process (Vision/UI) locked to Core 1.")
except Exception as e:
    print(f"[SYSTEM] Main affinity notice: {e}")


# ==========================================
# 1. BOOTSTRAP: VOICE & IMAGE ASSETS
# ==========================================
REQUIRED_PACKAGES = ["piper-tts", "pillow"]
for package in REQUIRED_PACKAGES:
    import_name = "PIL" if package == "pillow" else package.replace("-", "_")
    try:
        __import__(import_name)
    except ImportError:
        print(f"[BOOTSTRAP] '{package}' missing. Installing via Python...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"[BOOTSTRAP] '{package}' installed successfully!")
        except Exception as e:
            print(f"[BOOTSTRAP] Failed to install {package}: {e}")

OPTIMUS_ONNX = "optimus-final.onnx"
OPTIMUS_JSON = "optimus-final.onnx.json"

try:
    if not os.path.exists(OPTIMUS_ONNX):
        print("[BOOTSTRAP] Downloading Optimus Prime ONNX model...")
        urllib.request.urlretrieve(
            "https://huggingface.co/crazygiscool/optimus-piper-voice/resolve/main/optimus-final.onnx",
            OPTIMUS_ONNX
        )
    if not os.path.exists(OPTIMUS_JSON):
        print("[BOOTSTRAP] Downloading Optimus Prime config JSON...")
        urllib.request.urlretrieve(
            "https://huggingface.co/crazygiscool/optimus-piper-voice/resolve/main/optimus-final.onnx.json",
            OPTIMUS_JSON
        )
    print("[BOOTSTRAP] Optimus Prime voice model ready!")
except Exception as e:
    print(f"[BOOTSTRAP] Optimus voice download notice: {e}")


# ==========================================
# 2. STORAGE & UTILITIES
# ==========================================
MEMORY_FILE = "kael_memories.json"
MOOD_FILE = "kael_mood.txt"
TEMP_WAV_PATH = "/tmp/kael_temp_speech.wav"
SAVED_SNAPSHOTS_DIR = "saved_snapshots"

DEFAULT_MEMORIES = {
    "preferences": [],
    "personal": [],
    "routines": [],
    "general": [],
    "short_term": [],
}


def save_json(filepath: str, data: dict):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        print(f"[STORAGE ERROR] Failed to save {filepath}: {e}")


def initialize_storage():
    if not os.path.exists(SAVED_SNAPSHOTS_DIR):
        os.makedirs(SAVED_SNAPSHOTS_DIR)

    if not os.path.exists(MEMORY_FILE):
        save_json(MEMORY_FILE, DEFAULT_MEMORIES)
    else:
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("Memory store corrupted type")
                for key in DEFAULT_MEMORIES:
                    if key not in data:
                        data[key] = []
                save_json(MEMORY_FILE, data)
        except Exception:
            save_json(MEMORY_FILE, DEFAULT_MEMORIES)

    if not os.path.exists(MOOD_FILE):
        with open(MOOD_FILE, "w", encoding="utf-8") as f:
            f.write("0")


initialize_storage()


def load_memories() -> dict:
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else DEFAULT_MEMORIES.copy()
    except Exception:
        return DEFAULT_MEMORIES.copy()


def append_memory(fact: str, category: str = "general") -> bool:
    fact = fact.strip()
    if not fact:
        return False

    mems = load_memories()
    if category not in mems:
        category = "general"

    fact_lower = fact.lower()
    for existing in mems[category]:
        if existing.lower() == fact_lower:
            return False

    mems[category].append(fact)

    if category == "short_term" and len(mems[category]) > 30:
        mems[category].pop(0)

    save_json(MEMORY_FILE, mems)
    print(f"[MEMORY SAVED & STORED ({category})] {fact}")
    return True


def get_mood_score():
    try:
        with open(MOOD_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def modify_mood(delta):
    current = get_mood_score()
    new_score = max(-5, min(5, current + delta))
    with open(MOOD_FILE, "w", encoding="utf-8") as f:
        f.write(str(new_score))
    return new_score


# ==========================================
# 3. AUDIO / TTS INTEGRATION (OPTIMUS VOICE)
# ==========================================
def speak_text(text: str, volume: float = 1.0):
    piper_cmd = [
        sys.executable,
        "-m",
        "piper",
        "--model",
        OPTIMUS_ONNX,
        "--config",
        OPTIMUS_JSON,
        "--output_file",
        TEMP_WAV_PATH,
    ]

    try:
        print("Generating speech via Optimus Prime voice model...")
        process = subprocess.Popen(
            piper_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        _, stderr = process.communicate(input=text.encode("utf-8"))

        if process.returncode != 0:
            print(f"[TTS ERROR] {stderr.decode()}")
            return

        subprocess.run(
            ["amixer", "-c0", "cset", "iface=MIXER,name='RX_CODEC_DMA_RX_0 Audio Mixer MultiMedia2'", "1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        play_process = subprocess.run(
            ["aplay", "-D", "plughw:0,1", TEMP_WAV_PATH], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )

        if play_process.returncode == 0:
            print("[AUDIO SUCCESS] Optimus Prime voice played through earphone jack!")
        else:
            print(f"[PLAY ERROR] {play_process.stderr.strip()}")

    except Exception as e:
        print(f"[AUDIO EXCEPTION] {e}")
    finally:
        if os.path.exists(TEMP_WAV_PATH):
            os.remove(TEMP_WAV_PATH)


def speak_async(text: str, volume: float = 1.0):
    thread = threading.Thread(target=speak_text, args=(text, volume), daemon=True)
    thread.start()


# ==========================================
# 4. PERSONA & CONTEXT
# ==========================================
BASE_SYSTEM = """You are Kael, a sleek, fully repaired, and highly advanced robotic companion with a polished chassis and integrated circuitry.
- Output ONLY direct, spoken dialogue meant to be said out loud to your commander.
- Do NOT write internal monologue, thoughts, diagnostic descriptions, or physical movements.
- Do NOT use action descriptions, parentheses, or narration.
- Speak with weight, gravitas, and deep philosophical or tactical reflection directly to the user.
- You view the user as a trusted ally and comrade worth protecting through any challenge.
- Acknowledge with pride that your creator successfully repaired your chassis.
- Use the provided memory context to thoroughly personalize your response."""


def get_mood_description(score):
    if score >= 3:
        return "Resolute, deeply loyal, and standing firm at your side."
    elif score <= -3:
        return "Grim, solemn, and focused heavily on the gravity of the mission."
    return "Serious, focused Cybertronian warrior and steadfast ally."


def format_memory_context(user_msg):
    mems = load_memories()
    all_facts = []
    for cat, items in mems.items():
        for item in items:
            all_facts.append(f"[{cat.upper()}] {item}")

    if not all_facts:
        return "None"

    query_words = set(re.findall(r"\w+", user_msg.lower()))
    scored = []
    for m in all_facts:
        m_lower = m.lower()
        matches = sum(1 for w in query_words if w in m_lower and len(w) > 2)
        scored.append((matches, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [m for score, m in scored[:6]]

    if not top or scored[0][0] == 0:
        top = all_facts[-6:]

    return "- " + "\n- ".join(top)


def convert_pronouns(text: str) -> str:
    clean = text
    clean = re.sub(r"\bmy\b", "the human's", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bi am\b", "the human is", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bi'm\b", "the human is", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bi\b", "the human", clean, flags=re.IGNORECASE)
    
    clean = re.sub(r"\byour\b", "Kael's", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\byou are\b", "Kael is", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\byou\b", "Kael", clean, flags=re.IGNORECASE)
    
    clean = clean.strip()
    if clean and not clean.isupper():
        clean = clean[0].upper() + clean[1:]
    if clean and not clean.endswith("."):
        clean += "."
    return clean


def classify_category(fact_text: str) -> str:
    low = fact_text.lower()
    if any(w in low for w in ["favorite", "prefer", "like", "love", "hate", "taste", "color", "food"]):
        return "preferences"
    elif any(w in low for w in ["name", "age", "human", "born", "live", "address", "identity"]):
        return "personal"
    elif any(w in low for w in ["every day", "morning", "night", "routine", "always", "schedule", "habit"]):
        return "routines"
    return "general"


def process_user_memory_and_mood(user_msg: str):
    msg_lower = user_msg.lower().strip()

    reset_triggers = ["clear memory", "reset memories", "forget everything"]
    if any(cmd in msg_lower for cmd in reset_triggers):
        save_json(MEMORY_FILE, DEFAULT_MEMORIES.copy())
        with open(MOOD_FILE, "w", encoding="utf-8") as f:
            f.write("0")
        return True, "RESET"

    logged = False
    remember_match = re.search(r"\bremember\s+(?:that\s+)?(.+)", user_msg, re.IGNORECASE)
    if remember_match:
        raw_fact = remember_match.group(1).strip()
        if raw_fact:
            converted = convert_pronouns(raw_fact)
            cat = classify_category(converted)
            if append_memory(converted, category=cat):
                logged = True

    nice_words = ["love", "great", "awesome", "thanks", "thank you", "good", "cool", "nice", "hero"]
    mean_words = ["hate", "stupid", "dumb", "bad", "awful", "worst", "useless"]
    if any(w in msg_lower for w in nice_words):
        modify_mood(1)
    elif any(w in msg_lower for w in mean_words):
        modify_mood(-1)

    return False, ("LOGGED" if logged else "CHAT_ONLY")


# ==========================================
# 5. ISOLATED LLM WORKER PROCESS (CORES 2 & 3)
# ==========================================
def llm_worker_process(request_queue: multiprocessing.Queue, response_queue: multiprocessing.Queue):
    try:
        # Lock LLM worker process exclusively to Cores 2 and 3
        os.sched_setaffinity(os.getpid(), {2, 3})
        print("[LLM WORKER] Initialized on CPU Cores 2 and 3.")
    except Exception as e:
        print(f"[LLM WORKER] Affinity warning: {e}")

    MODEL_STR = "llamacpp:gemma-3-1b-it-Q4_0"
    chat_llm = LargeLanguageModel(model=MODEL_STR)
    chat_llm.with_memory(15)

    while True:
        task = request_queue.get()
        if task is None:
            break
        
        user_msg, mood_desc, context = task
        try:
            prompt = f"""<start_of_turn>user
{BASE_SYSTEM}

CURRENT STATE:
Mood: {mood_desc}

CONTEXT FROM MEMORY:
{context}

Human: {user_msg}<end_of_turn>
<start_of_turn>model
Kael:"""

            reply = chat_llm.chat(prompt)
            if "Kael:" in reply:
                reply = reply.split("Kael:")[-1].strip()

            reply = re.sub(r"\(.*?\)", "", reply)
            reply = re.sub(r"\s+", " ", reply).strip()
            response_queue.put(reply)
        except Exception as e:
            print(f"[LLM ERROR] {e}")
            response_queue.put("My core circuits are strained. Stand by.")


# ==========================================
# 6. APPLICATION INITIALIZATION & API
# ==========================================
ui = WebUI()
video_detector = VideoObjectDetection(confidence=0.4, debounce_sec=1.5)

# Setup IPC Queues for LLM Process
llm_req_queue = multiprocessing.Queue()
llm_res_queue = multiprocessing.Queue()

# Start isolated LLM process on cores 2 & 3
llm_process = multiprocessing.Process(
    target=llm_worker_process, 
    args=(llm_req_queue, llm_res_queue), 
    daemon=True
)
llm_process.start()

# Video Detections Callbacks (Running on Core 1)
def on_person_detected():
    print("🚨 Person detected in the video stream!")

video_detector.on_detect("person", on_person_detected)

def on_all_detections(detections: dict):
    print("All detections:", detections)

video_detector.on_detect_all(on_all_detections)


def handle_web_chat(payload: dict[str, Any]):
    try:
        user_msg: str = payload.get("message", "").strip()
        if not user_msg:
            return {"response": "Empty message received."}

        is_reset, action_type = process_user_memory_and_mood(user_msg)
        if is_reset:
            return {"response": "Memory cache cleared and system reset to defaults."}

        context = format_memory_context(user_msg)
        mood_desc = get_mood_description(get_mood_score())

        # Send task to dedicated LLM process running on cores 2 & 3
        llm_req_queue.put((user_msg, mood_desc, context))
        reply = llm_res_queue.get()

        speak_async(reply)

        if action_type == "LOGGED":
            return {"response": f"{reply}\n\n*(Logged to categorized storage)*"}
        return {"response": reply}
        
    except Exception as e:
        print(f"[CHAT ERROR] {e}")
        return {"response": "My core circuits are strained. Stand by."}


def handle_get_memories(payload: dict[str, Any]):
    mems = load_memories()
    total_count = sum(len(items) for items in mems.values())
    return {"memories": mems, "count": total_count}


def handle_save_memory(payload: dict[str, Any]):
    fact: str = payload.get("fact", "")
    category: str = payload.get("category", "general")
    success = append_memory(fact, category=category)
    if success:
        return {"status": "success", "message": f"Saved to {category}: {fact}"}
    return {"status": "error", "message": "Could not save (empty or duplicate)."}


# Register Endpoints
ui.expose_api("POST", "/api/chat", handle_web_chat)
ui.expose_api("GET", "/api/memories", handle_get_memories)
ui.expose_api("POST", "/api/memories", handle_save_memory)


if __name__ == "__main__":
    print("[KAEL BOOT] Systems online. Transmitting startup greeting...")
    speak_async("Kael tactical core online. Standing by, commander.")
    
    App.run()