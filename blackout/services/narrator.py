"""
Mission narration, optionally powered by Gemini.

Design rule: the game must be completely playable with no API key. Narration
is flavour, never a dependency. Every function here returns a deterministic
template string when the key is missing, the quota is exhausted, the request
times out, or the response is malformed. There is no code path where a
failing third-party service can block a turn.

The API is also never called inside the turn loop. Gemini is touched exactly
twice per run, at briefing and debrief, so a request that takes two seconds
costs nothing during play. Google's free tier is Flash-only and rate-limited
to a small number of requests per minute, which this budget sits comfortably
inside.
"""

from __future__ import annotations

import os
import random

import requests

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = 6

# Model IDs churn. Try in order and use whichever the key can reach; the result
# is cached for the session so this costs one extra call at most.
MODEL_CANDIDATES = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-lite-latest",
]

_WORKING_MODEL: str | None = None


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


def _generate(prompt: str, max_tokens: int = 160) -> str | None:
    """One Gemini call. Returns None on any failure, which callers expect."""
    global _WORKING_MODEL
    api_key = _secret("GEMINI_API_KEY")
    if not api_key:
        return None

    configured = _secret("GEMINI_MODEL")
    models = (
        [configured] if configured
        else ([_WORKING_MODEL] if _WORKING_MODEL else MODEL_CANDIDATES)
    )

    for model in models:
        try:
            r = requests.post(
                ENDPOINT.format(model=model),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "maxOutputTokens": max_tokens,
                        "temperature": 1.0,
                    },
                },
                timeout=TIMEOUT,
            )
            if r.status_code >= 300:
                continue
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
            if text:
                _WORKING_MODEL = model
                return text
        except Exception:
            continue
    return None


# ------------------------------------------------------------------ briefing

_BRIEFING_TEMPLATES = [
    "Sensor net is live across the sector. {hunters} hunters deployed, "
    "sweeping on a staggered cadence. Secure {nodes} data nodes and reach "
    "extraction. They cannot see you — they can only infer you.",
    "Station is dark. {hunters} pursuit units are triangulating on noise. "
    "{nodes} nodes remain in the vault grid. Keep their estimate wide and "
    "you keep breathing.",
    "You are unlogged and unlit. {hunters} hunters hold the floor and their "
    "belief map is already updating. Retrieve {nodes} nodes, then run for "
    "the pad.",
]


def briefing(wave: int, difficulty: str, hunters: int, nodes: int) -> str:
    prompt = (
        "You are the mission controller in a tense stealth game called BLACKOUT. "
        "The player is an infiltrator on a dark space station. Enemy hunters cannot "
        "see the player; they track them using a probabilistic belief map. "
        f"Write a mission briefing for wave {wave} on {difficulty} difficulty, with "
        f"{hunters} hunters and {nodes} data nodes to collect. "
        "Two or three sentences. Cold, clipped, military-technical tone. "
        "No preamble, no markdown, no quotation marks. Output the briefing only."
    )
    text = _generate(prompt, max_tokens=150)
    if text:
        return text
    return random.choice(_BRIEFING_TEMPLATES).format(hunters=hunters, nodes=nodes)


# ------------------------------------------------------------------- debrief


def debrief(
    waves_cleared: int,
    nodes: int,
    turns: int,
    stealth: float,
    score: int,
    difficulty: str,
    outcome: str,
) -> str:
    stealth_pct = int(stealth * 100)
    prompt = (
        "You are the after-action analyst for a stealth game called BLACKOUT, where "
        "enemy hunters track the player with a particle filter and the player's "
        "'stealth rating' is the average entropy of the hunters' belief about their "
        "position (higher means the AI stayed more uncertain).\n"
        f"Run result: {outcome}. Difficulty {difficulty}. Waves cleared {waves_cleared}. "
        f"Data nodes secured {nodes}. Turns survived {turns}. "
        f"Stealth rating {stealth_pct}%. Final score {score}.\n"
        "Give a two-sentence tactical critique with one specific, actionable piece of "
        "advice for the next run. Cold and analytical. No markdown, no preamble."
    )
    text = _generate(prompt, max_tokens=180)
    if text:
        return text

    if stealth_pct < 35:
        tip = (
            "Their belief stayed concentrated on you for most of the run. Break line "
            "of sight earlier and use silent movement before they close, not after."
        )
    elif stealth_pct > 70:
        tip = (
            "You kept their estimate badly spread — excellent. The losses came from "
            "physical interception, so watch hunter positions two turns ahead."
        )
    else:
        tip = (
            "Serviceable evasion. Spend the EMP when a hunter is inside sensor range "
            "and closing; letting the belief decay is worth more than the retreat."
        )
    return (
        f"Run terminated after {turns} turns with {nodes} nodes secured and a "
        f"stealth rating of {stealth_pct}%. {tip}"
    )


def taunt(threat: float) -> str:
    """Cheap, offline-only. Called every turn, so it never touches the network."""
    if threat > 0.85:
        return "They have you. Move."
    if threat > 0.6:
        return "Belief is converging on your position."
    if threat > 0.35:
        return "Partial track. They are narrowing it down."
    return "Their estimate is scattered. You are a rumour."
