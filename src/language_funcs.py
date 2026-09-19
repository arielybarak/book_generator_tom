"""
Hebrew and Braille language utilities.

Responsibilities:
- HEBREW_MAP / SPECIAL_REPLACEMENTS / DISPLAY_MAPPING: character-level constants
- hebrew_translator(): Hebrew → English via a local MarianMT model in a helper process
- convert_to_braille(): Hebrew string → Unicode Braille string
- apply_variations(): apply user-selected nikud (vowel marks) to a Hebrew string
- check_ambiguities(): find ambiguous characters in a string (feeds Gradio dropdowns)
- add_nikud(): interactive CLI version of nikud disambiguation (uses input())
"""
import json
import os
import re
import select
import subprocess
import sys
import threading
from functools import lru_cache

# ── Nikud / vowel-mark Unicode constants ──────────────────────────────────────
DAGESH   = 'ּ'
HIRIK    = 'ִ'
HOLAM    = 'ֹ'
SHURUK   = 'ֻ'
SHIN_DOT = 'ׂ'

# ── Hebrew → Braille character maps ───────────────────────────────────────────
HEBREW_MAP = {
    'א': '⠁', 'ב': '⠧', 'ג': '⠛', 'ד': '⠙', 'ה': '⠓',
    'ו': '⠺', 'ז': '⠵', 'ח': '⠭', 'ט': '⠞', 'י': '⠚',
    'כ': '⠡', 'ל': '⠇', 'מ': '⠍', 'נ': '⠝', 'ס': '⠎',
    'ע': '⠫', 'פ': '⠋', 'צ': '⠮', 'ק': '⠟', 'ר': '⠗',
    'ש': '⠩', 'ת': '⠹', 'ך': '⠡', 'ם': '⠍', 'ן': '⠝',
    'ף': '⠋', 'ץ': '⠮',
}

HEBREW_DAGESH_MAP = {
    'ב': '⠃',  # B with dagesh
    'כ': '⠅',  # K with dagesh
    'פ': '⠏',  # P with dagesh
}

VOWEL_TO_BRAILLE = {
    HOLAM:  '⠕',  # ו with holam
    SHURUK: '⠥',  # ו with shuruk
    HIRIK:  '⠊',  # י with hirik
}

# ── Disambiguation: characters that need user clarification ───────────────────
# Used by the Gradio UI to offer vowel-mark dropdowns.
SPECIAL_REPLACEMENTS = {
    'ו': {'default': 'ו', 'holam': 'ו' + HOLAM, 'shuruk': 'ו' + SHURUK},
    'ש': {'shin': 'ש' + SHIN_DOT, 'sin': 'שׂ'},
    'ב': {'default': 'ב', 'dagesh': 'ב' + DAGESH},
    'כ': {'default': 'כ', 'dagesh': 'כ' + DAGESH},
    'פ': {'default': 'פ', 'dagesh': 'פ' + DAGESH},
    'ך': {'default': 'ך', 'dagesh': 'ך' + DAGESH},
    'ף': {'default': 'ף', 'dagesh': 'ף' + DAGESH},
}

# Human-readable Hebrew labels for the Gradio dropdowns
DISPLAY_MAPPING = {
    'default': 'רגיל (ללא ניקוד)',
    'holam':   'חולם (וֹ)',
    'shuruk':  'שורוק (וּ)',
    'shin':    'שין ימנית (שׁ)',
    'sin':     'שין שמאלית (שׂ)',
    'dagesh':  'דגש (ּ)',
}


# ── Translation ────────────────────────────────────────────────────────────────
# Local model instead of Google Translate (Google IP-blocks the HF Space).
# The model runs in a separate helper process (this file, run as a script): loading
# torch/transformers in the ZeroGPU main process poisons its CUDA state, and every
# GPU worker forked from it then fails with "No CUDA GPUs are available".
TRANSLATION_MODEL = "Helsinki-NLP/opus-mt-tc-big-he-en"
HELPER_TIMEOUT_S = 180  # first reply includes model download + load
HEBREW_RE = re.compile(r"[֐-׿]")
NIKUD_RE = re.compile(r"[֑-ׇ]")  # model is trained on unpointed text

_helper = None
_helper_lock = threading.Lock()


@lru_cache(maxsize=256)
def _translate_he_en(text):
    """Send one text to the helper process and return its English translation."""
    global _helper
    with _helper_lock:
        if _helper is None or _helper.poll() is not None:
            _helper = subprocess.Popen(
                [sys.executable, "-u", __file__],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
            )
        _helper.stdin.write(json.dumps(text) + "\n")
        _helper.stdin.flush()
        ready, _, _ = select.select([_helper.stdout], [], [], HELPER_TIMEOUT_S)
        line = _helper.stdout.readline() if ready else ""
        if not line:
            _helper.kill()
            _helper = None
            raise RuntimeError("Translation helper died or timed out")
    reply = json.loads(line)
    if "error" in reply:
        raise RuntimeError(f"Translation failed: {reply['error']}")
    return reply["ok"]


def hebrew_translator(user_prompt):
    """Translate Hebrew → English; pass through if already English. Raises on failure."""
    if not user_prompt:
        return ""
    if not HEBREW_RE.search(user_prompt):
        return user_prompt
    translation = _translate_he_en(NIKUD_RE.sub("", user_prompt).strip())
    if not translation or HEBREW_RE.search(translation):
        raise RuntimeError(f"Could not translate picture description to English: {user_prompt!r}")
    return translation


def _serve_translations():
    """Helper-process loop: one JSON string per stdin line → one JSON reply per stdout line."""
    out, sys.stdout = sys.stdout, sys.stderr  # library chatter must not reach the reply pipe
    from transformers import MarianMTModel, MarianTokenizer
    tokenizer = MarianTokenizer.from_pretrained(TRANSLATION_MODEL)
    model = MarianMTModel.from_pretrained(TRANSLATION_MODEL)
    for line in sys.stdin:
        try:
            ids = model.generate(**tokenizer([json.loads(line)], return_tensors="pt"), max_length=64)
            # "Little dog." → "Little dog" (spliced mid-sentence into the SD prompt)
            reply = {"ok": tokenizer.decode(ids[0], skip_special_tokens=True).strip().rstrip(".")}
        except Exception as e:
            reply = {"error": repr(e)}
        out.write(json.dumps(reply) + "\n")
        out.flush()


# ── Nikud (CLI only) ──────────────────────────────────────────────────────────

def add_nikud(text):
    """
    Interactively prompt for vowel marks via input().
    Only works in CLI / notebook contexts, not in Gradio.
    Use apply_variations() for programmatic/UI contexts.
    """
    result = ""
    for ch in text:
        if ch in ('ב', 'כ', 'פ'):
            ans = input(f"האם האות '{ch}' היא עם דגש? (כן/לא) ").strip().lower()
            result += ch
            if ans == 'כן':
                result += DAGESH
        elif ch == 'ו':
            ans = input("האם זו ו עם חולם vo / שורוק vu / רגיל v? (חו/ש/ר) ").strip().lower()
            result += ch
            if ans == 'חו':
                result += HOLAM
            elif ans == 'ש':
                result += SHURUK
        elif ch == 'י':
            ans = input("האם זו י עם חיריק yi ? (כן/לא) ").strip().lower()
            result += ch
            if ans == 'כן':
                result += HIRIK
        elif ch == 'ש':
            ans = input("האם זו שׂ (s)? (כן/לא) ").strip().lower()
            result += ch
            if ans == 'כן':
                result += SHIN_DOT
        else:
            result += ch
    return result


def apply_variations(raw_text, variations):
    """
    Apply user vowel-mark selections (from Gradio UI) to raw Hebrew text.
    `variations` is a dict of {str(char_index): variant_key}.
    This is the non-interactive equivalent of add_nikud().
    """
    if not variations:
        return raw_text
    result_chars = list(raw_text)
    for index_str, variant_name in variations.items():
        try:
            index = int(index_str)
            if 0 <= index < len(result_chars):
                char = result_chars[index]
                if char in SPECIAL_REPLACEMENTS and variant_name in SPECIAL_REPLACEMENTS[char]:
                    result_chars[index] = SPECIAL_REPLACEMENTS[char][variant_name]
        except (ValueError, IndexError):
            continue
    return "".join(result_chars)


def check_ambiguities(text):
    """
    Return a list of characters in `text` that need vowel-mark disambiguation.
    Each entry: {"index": int, "char": str, "options": [str, ...]}.
    Used by the Gradio UI to render per-character dropdowns.
    """
    ambiguities = []
    if not text:
        return ambiguities
    for i, char in enumerate(text):
        if char in SPECIAL_REPLACEMENTS:
            ambiguities.append({
                "index": i,
                "char": char,
                "options": list(SPECIAL_REPLACEMENTS[char].keys()),
            })
    return ambiguities


# ── Braille conversion ─────────────────────────────────────────────────────────

def letter_to_braille(base, marks):
    """Convert a single Hebrew base letter + its nikud marks to a Braille character."""
    if base == 'ש':
        return '⠱' if SHIN_DOT in marks else HEBREW_MAP['ש']
    if base in HEBREW_DAGESH_MAP and DAGESH in marks:
        return HEBREW_DAGESH_MAP[base]
    if base == 'ו':
        if HOLAM  in marks: return '⠕'
        if SHURUK in marks: return '⠥'
        return HEBREW_MAP['ו']
    if base == 'י':
        return '⠊' if HIRIK in marks else HEBREW_MAP['י']
    return HEBREW_MAP.get(base, base)


def convert_to_braille(text):
    """
    Convert Hebrew text (with optional nikud) to a Braille Unicode string.
    Output is left-to-right (Braille is always read LTR regardless of source language).
    """
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if 'א' <= ch <= 'ת':
            base = ch
            marks = []
            i += 1
            while i < len(text) and '֑' <= text[i] <= 'ׇ':
                marks.append(text[i])
                i += 1
            result.append(letter_to_braille(base, marks))
        else:
            result.append(ch)
            i += 1
    return "".join(result)


# ── English → Braille (Grade 1, uncontracted) ─────────────────────────────────
ENGLISH_BRAILLE_MAP = {
    'a': '⠁', 'b': '⠃', 'c': '⠉', 'd': '⠙', 'e': '⠑', 'f': '⠋', 'g': '⠛',
    'h': '⠓', 'i': '⠊', 'j': '⠚', 'k': '⠅', 'l': '⠇', 'm': '⠍', 'n': '⠝',
    'o': '⠕', 'p': '⠏', 'q': '⠟', 'r': '⠗', 's': '⠎', 't': '⠞', 'u': '⠥',
    'v': '⠧', 'w': '⠺', 'x': '⠭', 'y': '⠽', 'z': '⠵', ' ': ' ',
}


def english_to_braille(text):
    """English → Grade-1 (uncontracted) Unicode Braille, left-to-right. Unknown chars dropped."""
    return "".join(ENGLISH_BRAILLE_MAP.get(c, '') for c in text.lower())


def text_to_braille(text, language='hebrew'):
    """Language-aware Braille: Hebrew (RTL→reversed) or English (Grade-1, LTR)."""
    return english_to_braille(text) if language == 'english' else convert_to_braille(text)


if __name__ == "__main__":
    sys.path.pop(0)  # drop src/ so its modules (config.py, …) can't shadow library imports
    _serve_translations()
