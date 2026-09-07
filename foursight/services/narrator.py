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
    "You found the line before it did. It searched deeper than you and still "
    "came second, which means your plan was better than its arithmetic.",
    "Clean win. You built a double threat it could not answer from one move.",
]
_LOSS_FALLBACKS = [
    "It saw the fork coming several moves before you played into it. Watch for "
    "positions where you have two separate threats — that is what it builds.",
    "Lost to a forced sequence. Next time, check what your move lets it play, "
    "not only what it gives you.",
]
_DRAW_FALLBACKS = [
    "A draw against a full search is a genuine result. Neither side left a gap.",
]


def commentary(outcome: str, difficulty: str, moves: int, streak: int, verdict: str) -> str:
    """One or two lines on the finished board."""
    prompt = (
        "You are a terse chess-style commentator for a Connect Four game where the "
        "opponent is a minimax engine with alpha-beta pruning.\n"
        f"Result: the human {outcome}. Difficulty {difficulty}. The board lasted "
        f"{moves} moves. The human's current win streak is {streak}. "
        f"The engine's own read on the final position was: {verdict}\n"
        "Write two sentences: one on what happened, one specific piece of advice. "
        "Dry and analytical, never patronising. No markdown, no preamble."
    )
    text = _generate(prompt)
    if text:
        return text
    if outcome == "won":
        return random.choice(_WIN_FALLBACKS)
    if outcome == "drew":
        return random.choice(_DRAW_FALLBACKS)
    return random.choice(_LOSS_FALLBACKS)
