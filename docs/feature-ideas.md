# SPARK Feature Ideas

Features Obi and Adrian might want to build into SPARK. Roughly sorted by how hard they'd be to program — easiest first, so Obi can start contributing early.

---

## Beginner — Obi could help program these

### 🎵 Custom Sound Effects
Obi records a sound (a silly voice, a fart noise, a made-up word) and it gets saved as a new `tool-play-sound` option. SPARK plays it on request.
**Why:** Obi gets to literally put his voice into SPARK. Instant ownership.
**How:** Record via USB mic → save WAV → add to `sounds/` → SPARK learns the name.

### 🧠 Teach SPARK a Fact
Obi tells SPARK something he's learned. SPARK saves it to memory and can repeat it back later — or use it in conversation.
**Why:** Makes Obi the expert. Reverses the usual direction of information. Great for hyperfocus topics.
**How:** Extend `tool-remember` to tag notes as `[obi-fact]`. SPARK recalls them when relevant.

### 🦕 Science Fact of the Day
Every morning, SPARK has one new fact ready — something it "discovered overnight". Rotates through a curated list.
**Why:** Creates a daily ritual. Obi knows SPARK will have something for him.
**How:** `tool-fact-of-day` reads from a JSON list, tracks last index in session, speaks at first morning greeting.

### ⏱️ Custom Timers with Obi's Voice
Obi names a timer anything he wants ("Minecraft break", "snack time", "volcano experiment"). SPARK announces it back in a fun way when it fires.
**Why:** Obi-named timers feel like his idea. Reduces resistance to time limits.
**How:** Extend `tool-timer` with a `label` that gets read back verbatim.

---

## Intermediate — Adrian leads, Obi co-designs

### 📷 "What's This?" Mode
Obi holds something up to the camera. SPARK takes a photo and explains what it is, why it's interesting, and a surprising fact about it.
**Why:** Satisfies constant curiosity without needing to type a search. Works for rocks, bugs, LEGOs, anything.
**How:** Extend `tool-describe-scene` to accept a question context. Pass image + "Obi is showing me something — describe it with one surprising fact."

### 📖 Story Builder
Obi starts a story. SPARK adds the next sentence. They take turns. SPARK saves the whole story at the end.
**Why:** Narrative play is excellent for language, imagination, and emotional processing. Also just fun.
**How:** `tool-story` with `action: start|add|finish`. Maintains story buffer in session. Reads back finished story via `tool-voice`.

### 🌊 Dopamine Menu — Obi's Custom Activities
Obi adds his own activities to the dopamine menu. "Watching a volcano video" or "building with magnetic tiles" can go in the menu alongside the defaults.
**Why:** The menu only works if it actually reflects Obi's interests. He should own it.
**How:** Obi says "add this to my menu" → saved to `notes-spark.jsonl` tagged `[dopamine-item]` → `tool-dopamine-menu` pulls from notes + defaults.

### 👁️ Face Follow Mode
When SPARK detects a person nearby (via Vilib face detection), it slowly turns to face them and tracks them as they move around the room.
**Why:** Makes SPARK feel alive and attentive. Kids love being noticed.
**How:** Use existing `8.stare_at_you.py` from stock picar-x examples as the engine. Wrap in `tool-face-follow` with on/off toggle. Yields GPIO from px-alive.

### 🎙️ Obi's Custom Wake Word
Train a personal wake word on Obi's voice — "Hey Sparky" or anything Obi picks.
**Why:** It's *his* robot. His word. Vosk supports custom grammars; sherpa-onnx supports custom keyword models.
**How:** Vosk grammar is trivial to update. For a true voice-trained model, use `sherpa-onnx` keyword spotting training tools.

---

## Advanced — longer projects, great to learn from

### 🐍 Python Lesson Mode
SPARK teaches Obi one Python concept at a time, in SPARK's voice, with a live example on the Pi. Obi types, SPARK reads the output, they see it work together.
**Why:** Obi literally runs the code that makes SPARK smarter. Best possible motivation.
**How:** `tool-python-lesson` runs a lesson from a curriculum JSONL. Evaluates simple expressions via `subprocess` in a sandbox. Uses `tool-voice` to narrate each step.

### 🎨 Draw and Describe
SPARK describes a scene, animal, or weird fact. Obi draws it. Obi holds it up to the camera. SPARK takes a photo, describes what it sees, and compares it to what it said.
**Why:** Art + science + language. Obi gets to surprise SPARK with his interpretation.
**How:** `tool-draw-game` wraps describe-scene with a before/after prompt structure.

### 🎵 Music Mood Matching
SPARK detects ambient sound level (already has RMS tracking in `px-wake-listen`). When it hears music, it picks an emote and comment that matches the energy.
**Why:** Reactive robot feels more alive. Obi will deliberately play different music to see what SPARK does.
**How:** Extend ambient sound tracking with frequency analysis via FFT. Map energy bands to moods. Feed to px-mind expression layer.

### 🏎️ Obstacle Course Mode
Obi sets up obstacles on the floor. SPARK navigates through them using sonar, announcing what it detects. Obi can make it harder.
**Why:** Physical play. Obi is actively in control of SPARK's environment.
**How:** Extend `tool-wander` with a "course" mode that narrates sonar readings. Add `tool-navigate` with left/right/forward by sonar distance.

### 👥 Visitor Mode
When SPARK hears a new voice (or Obi says "there's someone here"), it introduces itself and asks the visitor a question about Obi — then tells Obi something nice the visitor said.
**Why:** Social bridging. SPARK can help Obi navigate having people over.
**How:** `tool-visitor` changes `tool-voice` persona briefly. Uses session flag to track visitor-mode active.

### 🌙 Sleep Mode / Nightlight
Bedtime mode: SPARK dims to a low glow (pan/tilt to face ceiling, emote "idle"), speaks one fact very quietly, then goes silent for the night. Can be woken by a whispered "hey spark".
**Why:** Bedtime routines are hard. Having SPARK as part of the ritual makes it feel safe and familiar.
**How:** `tool-sleep` sets session flag `spark_sleep_mode`. Lowers espeak amplitude. Adjusts `RMS_SILENCE` threshold for whisper wake detection.

---

## Obi's own ideas

*This section grows as Obi suggests things. SPARK records feature ideas automatically when Obi mentions something it can't do yet — look for `[feature idea]` tags in `state/notes-spark.jsonl`.*

---

## How to build something

If Obi wants to add a feature:

1. Tell SPARK what it should do — SPARK will remember it as a feature idea
2. Ask Adrian to open a GitHub issue for it (or SPARK can suggest one)
3. Adrian shows Obi the code for the simplest existing tool (start with `bin/tool-celebrate`)
4. Obi writes the new tool — Adrian reviews and helps debug
5. SPARK gets smarter

Every tool follows the same pattern:
```bash
#!/usr/bin/env bash
source "$SCRIPT_DIR/px-env"
python - "$@" <<'PY'
# Your code here
print('{"status": "ok", "spoken": "I did the thing!"}')
PY
```

That's it. If Obi can write that, he can add any feature he wants.
