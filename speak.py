"""talkback-win: speaks the last AI assistant response via Windows TTS.

A Stop/AfterAgent hook for CLI coding agents (Claude Code, Codex CLI, Gemini CLI).
Drop speak.py into your project, register the hook, and your agent talks back.

Two engines supported, selected via TTS_ENGINE env var:
  edge   (default) -- Microsoft neural voices via edge-tts. Requires internet.
                      ~0.5-1.5s latency. Sounds natural (Aria, Jenny, etc.)
  local            -- Windows SAPI voices via pyttsx3. Instant, offline.
                      Robotic quality (David, Zira). No internet needed.

Env vars:
  TTS_MUTE=1          -- silences TTS for the session
  TTS_MAX_CHARS=N     -- override 800-char skip threshold (default 800)
  TTS_VOICE=<name>    -- override voice (edge: e.g. en-US-JennyNeural;
                         local: e.g. Microsoft Zira Desktop)
  TTS_RATE=<value>    -- override rate (edge: e.g. +10%; local: integer wpm)

Skip conditions (both engines):
  - Response exceeds TTS_MAX_CHARS characters
  - Response is >40% code fences
  - Response has 3+ bullet points
  - Response looks like tool output, paths, JSON, or diffs
  - TTS_MUTE=1 is set
"""
import json
import os
import re
import sys


# ── Config ────────────────────────────────────────────────────────────────────
MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "800"))
MUTE      = os.environ.get("TTS_MUTE", "0") == "1"
ENGINE    = os.environ.get("TTS_ENGINE", "edge").lower()  # "edge" or "local"
VOICE     = os.environ.get("TTS_VOICE", "")
RATE      = os.environ.get("TTS_RATE", "")

# Defaults per engine
_EDGE_VOICE_DEFAULT  = "en-US-AriaNeural"
_EDGE_RATE_DEFAULT   = "+0%"
_LOCAL_RATE_DEFAULT  = 175  # words per minute


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_mostly_code(text: str) -> bool:
    """Return True if >40% of the text is inside code fences."""
    code_chars = sum(len(m.group(0)) for m in re.finditer(r"```.*?```", text, re.DOTALL))
    return len(text) > 0 and (code_chars / len(text)) > 0.40


def _is_multi_bullet(text: str) -> bool:
    """Return True if the response has 3+ bullet points — better read than heard."""
    bullets = re.findall(r"^\s*[-*+]\s+|^\s*\d+\.\s+", text, re.MULTILINE)
    return len(bullets) >= 3


def _looks_like_tool_output(text: str) -> bool:
    """Return True for responses that are mostly paths, JSON, diffs, or tables."""
    lines = text.strip().splitlines()
    if not lines:
        return False
    noisy = sum(
        1 for l in lines
        if l.startswith(("/", "C:\\", "|", "+", "-", "{", "[", "  modified:", "  new file:"))
    )
    return len(lines) > 3 and (noisy / len(lines)) > 0.50


def _strip_for_speech(text: str) -> str:
    """Remove markdown and noise that would sound bad when spoken."""
    # Remove code fences entirely
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    # Remove markdown headers, bold, italic, strikethrough
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    # Remove markdown links, keep link text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove bare URLs
    text = re.sub(r"https?://\S+", "", text)
    # Remove table rows (lines of | ... |)
    text = re.sub(r"^\|.*\|$", "", text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)
    # Remove bullet/numbered list markers (keep the text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Dashes -> natural pause (comma); use Unicode escapes to avoid encoding issues
    text = re.sub(u"\u2014", ", ", text)    # em dash —
    text = re.sub(u"\u2013", ", ", text)    # en dash -
    text = re.sub(u"\u2012", ", ", text)    # figure dash
    text = re.sub(u"\u2212", ", ", text)    # minus sign
    text = re.sub(r"\s+-\s+", ", ", text)   # spaced hyphen used as dash
    # Currency / symbols -> spoken words
    text = text.replace(u"\u20ac", " euros ")   # €
    text = text.replace(u"\u00a3", " pounds ")  # £
    text = text.replace("$", " dollars ")
    text = text.replace("%", " percent ")
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    # Common abbreviation pronunciations
    replacements = {
        r"\bWACC\b":  "wack",
        r"\bJSON\b":  "jason",
        r"\bf2f\b":   "face to face",
        r"\bLLM\b":   "L L M",
        r"\bMCP\b":   "M C P",
        r"\bAPI\b":   "A P I",
        r"\bTTS\b":   "T T S",
        r"\bDCF\b":   "D C F",
        r"\bROIC\b":  "R O I C",
        r"\bCAGR\b":  "C A G R",
        r"\bHTML\b":  "H T M L",
        r"\bURL\b":   "U R L",
        r"\bPR\b":    "P R",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    return text.strip()


# ── Playback helpers ───────────────────────────────────────────────────────────

def _play_with_interrupt(tmp_path: str) -> None:
    """Play an MP3 file via Windows MCI; Escape key stops playback early."""
    import ctypes
    import time
    user32 = ctypes.WinDLL("user32")
    winmm  = ctypes.WinDLL("winmm")
    VK_ESCAPE = 0x1B
    alias = "claude_tts"
    buf = ctypes.create_unicode_buffer(128)
    winmm.mciSendStringW(f'open "{tmp_path}" type mpegvideo alias {alias}', None, 0, None)
    winmm.mciSendStringW(f"play {alias}", None, 0, None)
    while True:
        winmm.mciSendStringW(f"status {alias} mode", buf, 127, None)
        if buf.value != "playing":
            break
        if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
            break
        time.sleep(0.05)
    winmm.mciSendStringW(f"close {alias}", None, 0, None)


def _speak_edge(text: str) -> None:
    """Speak using edge-tts (Microsoft neural voices). Requires internet."""
    import asyncio
    import tempfile
    import edge_tts

    voice = VOICE or _EDGE_VOICE_DEFAULT
    rate  = RATE  or _EDGE_RATE_DEFAULT

    async def _save(path: str) -> None:
        await edge_tts.Communicate(text, voice=voice, rate=rate).save(path)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name

    asyncio.run(_save(tmp_path))
    try:
        _play_with_interrupt(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _speak_local(text: str) -> None:
    """Speak using pyttsx3 + Windows SAPI (offline, instant, robotic)."""
    import pyttsx3
    engine = pyttsx3.init()

    # Voice selection: env override, or first voice whose name matches VOICE hint
    if VOICE:
        for v in engine.getProperty("voices"):
            if VOICE.lower() in v.name.lower():
                engine.setProperty("voice", v.id)
                break

    rate = int(RATE) if RATE.lstrip("+-").isdigit() else _LOCAL_RATE_DEFAULT
    engine.setProperty("rate", rate)
    engine.say(text)
    engine.runAndWait()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Self-check mode: python speak.py --test
    if "--test" in sys.argv:
        engine_label = "edge (Microsoft neural)" if ENGINE != "local" else "local (Windows SAPI)"
        print(f"talkback-win self-check: engine={engine_label}")
        phrase = "talkback-win is working. Your agent can now talk back."
        try:
            if ENGINE == "local":
                _speak_local(phrase)
            else:
                _speak_edge(phrase)
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")
        return

    if MUTE:
        return

    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        data = json.loads(raw)
        # Support multiple agent payload formats:
        #   Claude Code / Codex CLI Stop hook: "last_assistant_message"
        #   Gemini CLI AfterAgent hook:        "response" or "message"
        #   Manual / other agents:             any of the above
        message = (
            data.get("last_assistant_message")
            or data.get("response")
            or data.get("message")
            or ""
        )
    except Exception:
        return

    if not message:
        return

    # Skip conditions
    if len(message) > MAX_CHARS:
        return
    if _is_mostly_code(message):
        return
    if _looks_like_tool_output(message):
        return
    if _is_multi_bullet(message):
        return

    cleaned = _strip_for_speech(message)
    if not cleaned or len(cleaned) < 10:
        return

    try:
        if ENGINE == "local":
            _speak_local(cleaned)
        else:
            _speak_edge(cleaned)
    except Exception:
        pass  # TTS failure -- never block the AI agent

    # Gemini CLI AfterAgent hooks require a JSON decision on stdout.
    # Set TTS_AGENT=gemini to enable. Do NOT enable for Claude Code or Codex
    # (their Stop hooks fail JSON validation if stdout is non-empty).
    if os.environ.get("TTS_AGENT", "").lower() == "gemini":
        print('{"decision": "allow"}')


if __name__ == "__main__":
    main()
