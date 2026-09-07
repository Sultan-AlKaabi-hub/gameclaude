"""
Cross-session room storage.

Streamlit runs every browser session as a separate thread inside one server
process. `st.cache_resource` returns the *same* object to every session rather
than a copy, and mutations to it are visible everywhere — which makes it the
supported way to share a game between two players without an external database.

Because those sessions are separate threads, every read-modify-write goes
through a lock. The Streamlit documentation is explicit about this: shared
mutable resources need coordinated access.

Limitations, stated rather than hidden:

* Rooms live in memory. A redeploy, or the free tier putting the app to sleep,
  destroys every game in progress. `find_room` returns None and the UI reports
  the room as expired instead of crashing.
* This assumes the app runs as a single process. If it were ever scaled to
  multiple replicas, two players could land on different ones and never see
  each other. Community Cloud does not do this today.
"""

from __future__ import annotations

import random
import string
import threading
import time
import uuid

import streamlit as st

from engine.duel import Duel

# Ambiguous glyphs removed: no 0/O, no 1/I, so codes can be read aloud.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 4
ROOM_TTL = 2 * 60 * 60      # hard expiry
IDLE_TTL = 20 * 60          # abandoned-room cleanup
MAX_ROOMS = 200


@st.cache_resource
def _store() -> dict:
    """One dict shared by every session in this server process."""
    return {"rooms": {}, "lock": threading.Lock()}


def _prune(rooms: dict) -> None:
    now = time.time()
    dead = [
        code
        for code, room in rooms.items()
        if now - room.created_at > ROOM_TTL or now - room.last_active > IDLE_TTL
    ]
    for code in dead:
        rooms.pop(code, None)
    # Hard cap, so a burst of abandoned rooms cannot grow without bound.
    if len(rooms) > MAX_ROOMS:
        for code in sorted(rooms, key=lambda c: rooms[c].last_active)[
            : len(rooms) - MAX_ROOMS
        ]:
            rooms.pop(code, None)


def new_token() -> str:
    return uuid.uuid4().hex[:12]


def create_room(name: str) -> tuple[str, str, int]:
    """Open a room and take the first seat. Returns (code, token, seat)."""
    store = _store()
    with store["lock"]:
        rooms = store["rooms"]
        _prune(rooms)
        for _ in range(50):
            code = "".join(random.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in rooms:
                break
        else:
            raise RuntimeError("could not allocate a room code")

        duel = Duel(code=code, seed=random.randint(1, 999_999))
        rooms[code] = duel
        token = new_token()
        seat = duel.claim_seat(name, token)
        return code, token, seat


def join_room(code: str, name: str) -> tuple[str | None, int | None, str]:
    """Take the second seat. Returns (token, seat, error_message)."""
    store = _store()
    code = (code or "").strip().upper()
    with store["lock"]:
        rooms = store["rooms"]
        _prune(rooms)
        duel = rooms.get(code)
        if duel is None:
            return None, None, "No room with that code. It may have expired."
        if duel.free_seat() is None:
            return None, None, "That room already has two commanders."
        token = new_token()
        seat = duel.claim_seat(name, token)
        return token, seat, ""


def find_room(code: str) -> Duel | None:
    store = _store()
    with store["lock"]:
        return store["rooms"].get((code or "").strip().upper())


def act(code: str, fn):
    """Run `fn(duel)` while holding the lock. Returns None if the room is gone."""
    store = _store()
    with store["lock"]:
        duel = store["rooms"].get((code or "").strip().upper())
        if duel is None:
            return None
        return fn(duel)


def room_count() -> int:
    store = _store()
    with store["lock"]:
        return len(store["rooms"])
