"""
Optional Gemini commentary.

Design rule, unchanged from the previous build: the game must be fully
playable with no API key. Every function returns a written fallback when the
key is missing, the quota is exhausted, or the request fails. Gemini is called
at most once per finished board and never during a move, so a slow response
can never stall play.
"""

from __future__ import annotations

import os
import random

import requests

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = 6
MODEL_CANDIDATES = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-lite-latest",
]
_WORKING_MODEL = None


def _secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


def available() -> bool:
    return bool(_secret("GEMINI_API_KEY"))


def _generate(prompt: str, max_tokens: int = 140):
    global _WORKING_MODEL
    api_key = _secret("GEMINI_API_KEY")
    if not api_key:
        return None
    configured = _secret("GEMINI_MODEL")
    models = ([configured] if configured
              else ([_WORKING_MODEL] if _WORKING_MODEL else MODEL_CANDIDATES))
    for model in models:
        try:
            r = requests.post(
                ENDPOINT.format(model=model),
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 1.0}},
                timeout=TIMEOUT,
            )
            if r.status_code >= 300:
                continue
            parts = r.json()["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
            if text:
                _WORKING_MODEL = model
                return text
        except Exception:
            continue
    return None


_WIN_FALLBACKS = [
    "Clean sweep. You walked every hull the moment you found it, and its search "
    "never got traction on your layout.",
    "Enemy fleet on the bottom. Hunting on the checkerboard and finishing each "
    "ship before moving on is exactly what wins these.",
]
_LOSS_FALLBACKS = [
    "It found your hulls faster than you found its. When you land a hit, walk "
    "the line along both axes before you go hunting elsewhere.",
    "Lost on efficiency. Every ship is at least two long, so shots off the "
    "checkerboard are wasted while you are still searching.",
]


def commentary(outcome: str, difficulty: str, shots: int, accuracy: int, reason: str) -> str:
    """One or two lines on the finished game."""
    prompt = (
        "You are a terse naval commentator for a game of Battleship where the "
        "opponent is an AI that fires at the square covered by the most fleet "
        "layouts still consistent with its shots. "
        f"Result: the human {outcome}. Difficulty {difficulty}. The human fired "
        f"{shots} shots at {accuracy}% accuracy; a perfect game is 17 shots. "
        f"The AI's last stated reasoning was: {reason}. "
        "Write two sentences: one on what happened, one specific piece of advice. "
        "Dry and analytical, never patronising. No markdown, no preamble."
    )
    text = _generate(prompt)
    if text:
        return text
    return random.choice(_WIN_FALLBACKS if outcome == "won" else _LOSS_FALLBACKS)
