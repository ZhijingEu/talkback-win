# talkback-win

**Free, Windows-native TTS so your AI coding agent can talk back — no API key, one pip install.**

**OpenAI Codex users:** see https://github.com/ZhijingEu/talkback-win-openai-codex

![TalkBack-Win](https://miro.medium.com/v2/resize:fit:828/format:webp/1*t9Hb3BoXFCUM2RFm6rWkTw.jpeg "TalkBack-Win")

> **TL;DR** — When your agent finishes a response, `speak.py` reads it aloud using Microsoft's neural voices. Short conversational replies get spoken; long outputs, code blocks, and bullet lists are skipped automatically. Press Escape to interrupt mid-sentence. Works with Claude Code and Gemini CLI.

---

## Why this exists

In March 2026, Anthropic released `/voice` for Claude Code CLI — you can now *talk to* your agent by holding Space to dictate. But the agent still only replies in text. There's no voice reply.

Several community projects fill this gap, but each has a catch:

| Option | Cost | Works on Windows |
|--------|------|-----------------|
| ElevenLabs / OpenAI TTS | Paid API key | Yes |
| Kokoro (local neural model) | Free | Yes, but needs 82 MB model + `espeak-ng` system package |
| macOS `say` | Free | **No** |
| **talkback-win (this project)** | **Free** | **Yes — one pip install** |

`talkback-win` uses `edge-tts`, which streams from Microsoft's TTS servers — the same neural voices as Edge Read Aloud. No API key, no model download.

A nice bonus: Claude Code and Gemini CLI share the same hook mechanism, so `speak.py` works across both with minor config differences.

---

## Highlights

- **Neural voice quality** — Microsoft Aria, Jenny, Sonia, and 300+ others (edge engine), or instant offline SAPI voices (local engine)
- **Smart filtering** — only speaks short conversational replies; skips code, bullet lists, tool output, and long responses automatically
- **Escape to interrupt** — press Escape mid-sentence to stop playback (OS-level key detection)
- **One file** — `speak.py` is fully self-contained, no config file needed
- **Agent-agnostic** — Claude Code, Gemini CLI, or any agent that can pipe JSON to a subprocess

---

## Requirements

- **Windows 10 / 11**
- **Python 3.8+** (tested on 3.13)
- **Internet connection** for the `edge` engine only

---

## Quick start

**1. Install dependencies**

```bash
# edge engine (default) — neural voices, requires internet
pip install edge-tts

# local engine — offline SAPI voices (David, Zira), instant but robotic
pip install pyttsx3
```

**2. Copy `speak.py` into your project**

Place it in a gitignored folder so it stays local:

| Agent | Recommended path |
|-------|-----------------|
| Claude Code | `.claude/tts/speak.py` |
| Gemini CLI | `.gemini/tts/speak.py` |

> Codex CLI users: see the Codex-focused variant at https://github.com/ZhijingEu/talkback-win-openai-codex

**3. Verify it works**

```bash
python speak.py --test
# talkback-win self-check: engine=edge (Microsoft neural)
# OK
```

You should hear Aria say "talkback-win is working. Your agent can now talk back."

**4. Register the hook**

---

### Claude Code (Stop hook)

Add to `.claude/settings.local.json` in your project root:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "venv/Scripts/python.exe .claude/tts/speak.py"
          }
        ]
      }
    ]
  }
}
```

Restart Claude Code after editing — settings are loaded at startup.

---

### Codex CLI (not supported natively)

Codex CLI’s TUI does not expose a stable hook surface the same way Claude Code does, and JSON-based hook examples are ignored in current Codex configs. If you want Codex support, use the dedicated wrapper repo instead:

https://github.com/ZhijingEu/talkback-win-openai-codex

---

### Gemini CLI (AfterAgent hook, v0.26.0+)

Add to `.gemini/settings.json` in your project root:

```json
{
  "tools": { "enableHooks": true },
  "hooks": {
    "AfterAgent": [
      {
        "hooks": [
          {
            "name": "talkback-win",
            "type": "command",
            "command": "cmd /c set TTS_AGENT=gemini && venv/Scripts/python.exe .gemini/tts/speak.py",
            "timeout": 30000
          }
        ]
      }
    ]
  }
}
```

Note: as of v0.26.0 there is a known bug ([#15712](https://github.com/google-gemini/gemini-cli/issues/15712)) where `AfterAgent` does not fire for text-only responses. Check current status before relying on it.

---

### Other agents / manual call

`speak.py` reads from stdin and accepts JSON with the response text in any of these fields:

```json
{"last_assistant_message": "..."}
{"response": "..."}
{"message": "..."}
```

Call it from a shell:

```bash
echo '{"last_assistant_message": "Your response here."}' | python speak.py
```

Or from Python:

```python
import subprocess, json
subprocess.run(
    ["python", "speak.py"],
    input=json.dumps({"last_assistant_message": response_text}),
    text=True
)
```

---

## Choosing an engine

```bash
set TTS_ENGINE=edge    # neural voices, ~0.5–1.5s latency (default)
set TTS_ENGINE=local   # offline SAPI voices, instant but robotic
```

---

## Configuration

All settings are environment variables — no config file needed.

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_ENGINE` | `edge` | `edge` (neural) or `local` (SAPI offline) |
| `TTS_MUTE` | `0` | Set to `1` to silence TTS for the session |
| `TTS_MAX_CHARS` | `800` | Skip responses longer than this |
| `TTS_VOICE` | Aria / system default | Voice name override |
| `TTS_RATE` | `+0%` / `175` wpm | Speech rate override |

**Voice examples:**

```bash
set TTS_VOICE=en-US-JennyNeural      # edge engine
set TTS_VOICE=en-GB-SoniaNeural      # edge engine, British
set TTS_VOICE=Zira                   # local engine
```

**Rate examples:**

```bash
set TTS_RATE=+20%    # faster (edge)
set TTS_RATE=-15%    # slower (edge)
set TTS_RATE=200     # words per minute (local)
```

List all available edge voices:

```bash
python -m edge_tts --list-voices
```

---

## Controls

| Action | Effect |
|--------|--------|
| Press **Escape** | Stops playback immediately |
| `set TTS_MUTE=1` | Silences TTS for the session |

---

## When TTS fires vs skips

TTS is **skipped** automatically when the response:

- Exceeds `TTS_MAX_CHARS` characters (default 800)
- Contains 3 or more bullet points
- Has more than 40% of content inside code fences
- Looks like tool output (file paths, JSON blobs, diffs, tables)
- Is under 10 characters after markdown stripping

---

## Troubleshooting

### Characters sound wrong — em dashes read as "a euros", symbols mispronounced

**Root cause:** Windows reads `sys.stdin` as cp1252 by default. The JSON from your agent is UTF-8, so multi-byte characters like `—` (em dash, `\xE2\x80\x94`) get decoded as three separate cp1252 characters (`Ã¢` + `â‚¬` + `"`) before the strip function ever sees them. Aria then says "a euros" instead of pausing.

**Fix:** `speak.py` reads stdin as `sys.stdin.buffer.read().decode("utf-8")` to force UTF-8 decoding. If you fork the script and see this problem return, check that line first.

**Quick diagnostic:** set `TTS_MUTE=1` temporarily and add this to `speak.py` to log what text is actually arriving:
```python
with open("tts_debug.txt", "w", encoding="utf-8") as f:
    f.write(repr(cleaned))
```
If you see `Ã¢â‚¬"` in the log instead of `—`, it's a cp1252 decoding issue.

---

### Hook causes a JSON validation error in Claude Code

**Symptom:** Claude Code shows `Stop hook error: JSON validation failed` in the status bar.

**Cause:** Claude Code's Stop hook validator rejects any stdout output from the hook script. The `{"decision": "allow"}` pattern needed by Gemini CLI's `AfterAgent` hook must not be printed when running under Claude Code.

**Fix:** Only enable the stdout decision via `set TTS_AGENT=gemini`. Do not set this for Claude Code.

---

### Local engine voices sound robotic / only David or Zira available

**Cause:** `pyttsx3` uses the legacy Windows SAPI5 registry path and cannot see the newer "Natural" neural voices installed via *Settings → Time & Language → Speech → Manage voices*.

**Fix:** Switch to the `edge` engine (`TTS_ENGINE=edge`) for neural voice quality. The `local` engine is intentionally limited to SAPI5 — it's the offline/instant option, not the quality option.

---

### Escape key doesn't stop playback

**Cause:** `msvcrt.kbhit()` does not detect keypresses when stdin is a pipe (which it always is when running as a hook).

**Fix:** `speak.py` uses `ctypes.WinDLL("user32").GetAsyncKeyState(0x1B)` instead, which polls keyboard state at the OS level regardless of stdin state. If Escape stops working, check that `user32` is accessible — it is present on all standard Windows installations.

---

### No audio plays but no error either

Things to check in order:
1. Is `TTS_MUTE=1` set in your shell environment?
2. Did the response exceed `TTS_MAX_CHARS` (default 800) or have 3+ bullet points?
3. Run the manual test: `python speak.py --test` — if silent, run `python -c "import edge_tts"` to confirm the package is installed.
4. Check Windows volume and default audio output device.

---

## Privacy notice (edge engine)

When using the `edge` engine, response text is transmitted to Microsoft's `speech.platform.bing.com` servers — the same backend as Edge Read Aloud. This is an **unofficial, reverse-engineered endpoint** with no published data-retention commitment from Microsoft (the no-persistent-storage guarantee applies to the paid Azure Speech SDK, not this endpoint).

**Practical guidance:**
- Fine for general development conversation
- **Avoid speaking sensitive text** — credentials, PII, confidential business data
- Use `TTS_ENGINE=local` for fully offline, zero-data-exposure operation
- For production/compliance use, replace `edge-tts` with the [official Azure Speech SDK](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/) under a signed service agreement

Note: commercial use via this unofficial endpoint likely violates Microsoft's Terms of Service.

---

## Disabling

Remove the hook entry from your agent's settings file and restart. The script can stay in place — nothing runs unless the hook is registered.

---

## Project structure

```
talkback-win/
├── speak.py           # The hook script — single file, no config needed
├── requirements.txt   # edge-tts (default) / pyttsx3 (local engine)
└── README.md          # This file
```

---

## Acknowledgements

- [Null-Phnix/claude-voice](https://github.com/Null-Phnix/claude-voice) — inspiration for the Stop hook pattern
- [rany2/edge-tts](https://github.com/rany2/edge-tts) — the library making free neural TTS possible
- Claude Code and Gemini CLI hook documentation
