"""
ARMADA — Streamlit host.

The game runs in the browser (web/index.html): boards, ship placement, the
probability-density AI, effects and sound all happen client-side, so every
tap is instant. Streamlit's job is to serve that page and to hold the state
that genuinely has to live on a server:

* online two-player rooms (both fleets stay server-side, each browser is only
  ever sent its own board plus what it has discovered), and
* the shared leaderboard and optional post-game commentary.

The page is registered as a bidirectional Streamlit component. It receives a
`state` dict on every render and reports player actions back as its value
({"n": nonce, "action": ..., ...}). The nonce is what stops a rerun from
replaying the last action, because a component's value persists across reruns.

Rooms live in `services/rooms.py`, shared across sessions through
`st.cache_resource`, exactly as before. While a session is in a room the
component is re-rendered every two seconds by `st.fragment` so a player sees
the opponent's move without touching anything.
"""

from __future__ import annotations

import pathlib

import streamlit as st
import streamlit.components.v1 as components

from engine.duel import FINISHED, PLACING, PLAYING, WAITING
from services import narrator, rooms
from services.leaderboard import get_store, make_entry, rank_of, top_entries

WEB = pathlib.Path(__file__).resolve().parent / "web"
game = components.declare_component("armada_game", path=str(WEB))

st.set_page_config(
    page_title="ARMADA", page_icon="⚓", layout="wide", initial_sidebar_state="collapsed"
)
st.markdown(
    """
    <style>
      #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
      [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none; }
      .stApp, [data-testid="stAppViewContainer"] { background: #0E141B; }
      [data-testid="stMainBlockContainer"], .block-container {
        padding: 0 !important; max-width: 100% !important; margin: 0 !important;
      }
      [data-testid="stVerticalBlock"] { gap: 0 !important; }
      [data-testid="stElementContainer"], [data-testid="element-container"] { margin: 0 !important; }
      .stApp iframe { display: block; width: 100% !important; min-height: 100vh; min-height: 100dvh; border: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

DEFAULTS = {
    "room_code": None, "seat": None, "seat_token": None,
    "last_n": None, "result": None, "error": "", "pending_code": "", "qp_checked": False,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


@st.cache_data(ttl=45, show_spinner=False)
def load_entries() -> list:
    return get_store().load()


def _leave() -> None:
    st.session_state.update(room_code=None, seat=None, seat_token=None)
    try:
        st.query_params.clear()
    except Exception:
        pass


def _enter(code: str, token: str, seat: int) -> None:
    st.session_state.update(room_code=code, seat_token=token, seat=seat, error="")
    st.query_params["game"] = code
    st.query_params["seat"] = token


def _bootstrap_from_url() -> None:
    """Reclaim a seat from ?game=CODE&seat=TOKEN after a refresh or reconnect."""
    if st.session_state["qp_checked"]:
        return
    st.session_state["qp_checked"] = True
    code = st.query_params.get("game")
    token = st.query_params.get("seat")
    if not code:
        return
    duel = rooms.find_room(code)
    if duel is None:
        st.session_state["error"] = (
            f"Room {str(code).upper()} no longer exists. Rooms are held in memory, "
            "so they are lost when the app restarts."
        )
        return
    seat = duel.seat_of(token) if token else None
    if seat is not None:
        st.session_state.update(room_code=duel.code, seat_token=token, seat=seat)
    else:
        st.session_state["pending_code"] = duel.code


_bootstrap_from_url()


# ----------------------------------------------------------------- the view


def _grid(shot_grid) -> list:
    return [list(row) for row in shot_grid.state]


def _ships(fleet, hits: bool = True) -> list:
    return [
        {"name": s.name, "length": s.length, "cells": [list(c) for c in s.cells],
         "hits": [list(h) for h in sorted(s.hits)] if hits else []}
        for s in fleet.ships
    ]


def _room_view(duel, seat: int) -> dict:
    duel.touch(seat)
    other = 1 - seat
    mode = {WAITING: "waiting", PLACING: "placing", PLAYING: "playing", FINISHED: "finished"}.get(
        duel.status, "finished"
    )
    return {
        "mode": mode, "code": duel.code, "seat": seat, "names": list(duel.names),
        "turn": duel.turn, "winner": duel.winner, "ready": list(duel.ready),
        "ownShips": _ships(duel.fleets[seat]),
        "incoming": _grid(duel.shots[other]), "shots": _grid(duel.shots[seat]),
        "myShots": duel.shots[seat].shots, "myHits": duel.shots[seat].hits,
        "theirShots": duel.shots[other].shots,
        "lastShot": list(duel.last[seat]) if duel.last[seat] else None,
        "theirLast": list(duel.last[other]) if duel.last[other] else None,
        "enemySunk": list(duel.shots[seat].sunk_names),
        "enemyShips": [[s.name, s.length] for s in duel.fleets[other].ships],
        # Only sunk enemy hulls are ever sent to this browser.
        "enemySunkShips": [
            {"name": s.name, "length": s.length, "cells": [list(c) for c in s.cells]}
            for s in duel.fleets[other].ships if s.sunk
        ],
        "log": duel.log[-6:], "opponentPresent": duel.opponent_present(seat),
    }


def _view() -> dict:
    v = {
        "mode": "idle", "lb": top_entries(load_entries(), 10),
        "durable": get_store().durable, "result": st.session_state["result"],
        "error": st.session_state["error"], "pendingCode": st.session_state["pending_code"],
    }
    st.session_state["error"] = ""
    code = st.session_state["room_code"]
    if code:
        duel = rooms.find_room(code)
        if duel is None:
            v["error"] = "The room disappeared. The app most likely restarted."
            _leave()
        else:
            v.update(_room_view(duel, st.session_state["seat"]))
    return v


# -------------------------------------------------------------- the actions


def _handle(val: dict) -> None:
    action = val.get("action")
    name = str(val.get("name") or "")[:18]
    code = st.session_state["room_code"]
    seat = st.session_state["seat"]

    if action == "create":
        new_code, token, new_seat = rooms.create_room(name)
        _enter(new_code, token, new_seat)

    elif action == "join":
        token, new_seat, err = rooms.join_room(str(val.get("code") or ""), name)
        if err:
            st.session_state["error"] = err
        else:
            _enter(str(val.get("code")).strip().upper(), token, new_seat)
            st.session_state["pending_code"] = ""

    elif action == "ready" and code is not None:
        ships = val.get("ships") or []

        def apply(d):
            if not d.set_fleet(seat, ships):
                return False
            d.set_ready(seat)
            return True

        if rooms.act(code, apply) is False:
            st.session_state["error"] = "That layout was not legal. Try again."

    elif action == "fire" and code is not None:
        rooms.act(code, lambda d: d.fire(seat, int(val["r"]), int(val["c"])))

    elif action == "leave":
        if code is not None:
            rooms.act(code, lambda d: d.forfeit(seat))
        _leave()

    elif action == "finish":
        entry = make_entry(
            name, int(val.get("score", 0)), int(val.get("sunk", 0)),
            str(val.get("difficulty", "")), int(val.get("hits", 0)),
            int(val.get("shots", 0)), float(val.get("acc", 0)) / 100.0,
        )
        ok = get_store().append(entry)
        load_entries.clear()
        rank = rank_of(load_entries(), entry["score"]) if ok else None
        text = narrator.commentary(
            "won" if val.get("won") else "lost", str(val.get("difficulty", "")),
            int(val.get("shots", 0)), int(val.get("acc", 0)), str(val.get("reason", "")),
        )
        st.session_state["result"] = {"n": val.get("n"), "rank": rank, "commentary": text}


def body() -> None:
    val = game(state=_view(), key="armada_game", default=None)
    if isinstance(val, dict) and val.get("n") != st.session_state["last_n"]:
        st.session_state["last_n"] = val.get("n")
        _handle(val)
        st.rerun()


if st.session_state["room_code"] and hasattr(st, "fragment"):
    st.fragment(run_every="2s")(body)()
else:
    body()
