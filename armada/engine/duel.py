"""
Two-player duel state.

The server holds both fleets. Each connected player is only ever rendered their
own board plus what they have discovered about their opponent, so ship
positions are never sent to a browser that should not have them. This is
strictly safer than a peer-to-peer design, which would have to transmit the
opponent's board and trust the client not to look at it.

Seats are indexes 0 and 1. `shots[i]` is what player i has learned about
player (1-i)'s fleet. Nothing in this module imports Streamlit; `services/rooms.py`
owns the sharing and locking.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from engine.fleet import Fleet, ShotGrid, label

WAITING, PLACING, PLAYING, FINISHED, ABANDONED = (
    "waiting", "placing", "playing", "finished", "abandoned"
)

# How long a seat can go unseen before we tell the other player about it.
PRESENCE_TIMEOUT = 25.0


@dataclass
class Duel:
    """One two-player game."""

    code: str
    seed: int = 0
    status: str = WAITING
    turn: int = 0
    winner: int | None = None
    names: list = field(default_factory=lambda: [None, None])
    tokens: list = field(default_factory=lambda: [None, None])
    last_seen: list = field(default_factory=lambda: [0.0, 0.0])
    ready: list = field(default_factory=lambda: [False, False])
    log: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        rng = random.Random(self.seed)
        self.fleets = [Fleet(), Fleet()]
        for fleet in self.fleets:
            fleet.place_random(rng)
        self.shots = [ShotGrid(), ShotGrid()]
        self.log = ["Room created. Waiting for a second commander."]

    # ---------------------------------------------------------------- seats

    def seat_of(self, token: str | None) -> int | None:
        if token is None:
            return None
        for seat, held in enumerate(self.tokens):
            if held == token:
                return seat
        return None

    def free_seat(self) -> int | None:
        for seat, held in enumerate(self.tokens):
            if held is None:
                return seat
        return None

    def claim_seat(self, name: str, token: str) -> int | None:
        seat = self.free_seat()
        if seat is None:
            return None
        self.tokens[seat] = token
        self.names[seat] = (name or f"Player {seat + 1}").strip()[:18]
        self.touch(seat)
        if all(t is not None for t in self.tokens):
            self.status = PLACING
            self.log.append(f"{self.names[1]} joined. Both commanders deploy.")
        return seat

    def set_ready(self, seat: int) -> None:
        """Confirm this seat's fleet. The battle opens when both are ready."""
        self.ready[seat] = True
        self.touch(seat)
        if all(self.ready) and self.status == PLACING:
            self.status = PLAYING
            self.log.append(f"Fleets deployed. {self.names[0]} fires first.")

    def touch(self, seat: int) -> None:
        """Record that this seat is still connected."""
        now = time.time()
        self.last_seen[seat] = now
        self.last_active = now

    def opponent_present(self, seat: int) -> bool:
        other = 1 - seat
        if self.tokens[other] is None:
            return False
        return (time.time() - self.last_seen[other]) < PRESENCE_TIMEOUT

    # ----------------------------------------------------------------- play

    def can_fire(self, seat: int) -> bool:
        return self.status == PLAYING and self.turn == seat

    def fire(self, seat: int, r: int, c: int) -> bool:
        """Resolve a shot by `seat` against their opponent."""
        if not self.can_fire(seat):
            return False
        if self.shots[seat].already_fired(r, c):
            return False

        target = self.fleets[1 - seat]
        outcome, ship = target.receive(r, c)
        self.shots[seat].record(r, c, outcome, ship)

        who = self.names[seat] or f"Player {seat + 1}"
        if outcome == "sunk" and ship:
            self.log.append(f"{who} sank a {ship.name} at {label(r, c)}.")
        elif outcome == "hit":
            self.log.append(f"{who} hit at {label(r, c)}.")
        else:
            self.log.append(f"{who} missed at {label(r, c)}.")

        if target.all_sunk():
            self.status = FINISHED
            self.winner = seat
            self.log.append(f"{who} wins.")
        else:
            self.turn = 1 - seat

        self.log = self.log[-8:]
        self.touch(seat)
        return True

    def forfeit(self, seat: int) -> None:
        if self.status in (FINISHED, ABANDONED):
            return
        self.status = FINISHED
        self.winner = 1 - seat
        who = self.names[seat] or f"Player {seat + 1}"
        self.log.append(f"{who} withdrew.")

    # ------------------------------------------------------------- readouts

    def ships_left(self, seat: int) -> int:
        return sum(1 for s in self.fleets[seat].ships if not s.sunk)

    def status_line(self, seat: int) -> str:
        if self.status == WAITING:
            return "Waiting for an opponent to join."
        if self.status == PLACING:
            if not self.ready[seat]:
                return "Deploy your fleet."
            other = self.names[1 - seat] or "your opponent"
            return f"Fleet confirmed. Waiting for {other} to deploy."
        if self.status == FINISHED:
            if self.winner == seat:
                return "You won."
            return "You lost."
        if self.turn == seat:
            return "Your turn. Choose a target."
        other = self.names[1 - seat] or "Your opponent"
        return f"Waiting for {other} to fire."
