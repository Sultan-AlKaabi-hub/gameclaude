"""
Fleet, board, and shot resolution.

Two views of the same game exist and must never be confused:

* the **fleet** — the truth about where ships are, known only to their owner;
* the **shot grid** — what the attacker has learned, which is all the AI is
  allowed to reason from.

Keeping those apart is not tidiness, it is the fairness guarantee. The AI in
`ai/density.py` is handed a shot grid and a list of ship lengths still afloat,
and nothing else. There is no difficulty setting that quietly leaks the answer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

SIZE = 10

# Standard Milton Bradley fleet.
SHIP_TYPES = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]
TOTAL_SHIP_CELLS = sum(length for _, length in SHIP_TYPES)  # 17

# Shot grid states, from the attacker's point of view.
UNKNOWN, MISS, HIT, SUNK = 0, 1, 2, 3

COLUMN_LABELS = [chr(ord("A") + i) for i in range(SIZE)]


@dataclass
class Ship:
    name: str
    length: int
    cells: list = field(default_factory=list)
    hits: set = field(default_factory=set)

    @property
    def sunk(self) -> bool:
        return len(self.hits) >= self.length


class Fleet:
    """One player's ships and the damage taken."""

    def __init__(self) -> None:
        self.ships: list[Ship] = []
        self.owner_grid = [[-1] * SIZE for _ in range(SIZE)]  # ship index or -1

    # ------------------------------------------------------------ placement

    def place_random(self, rng: random.Random) -> None:
        """Lay out the fleet with no overlaps.

        Retries on collision rather than backtracking; with 17 cells on a
        100-cell board the failure rate is low enough that this converges
        immediately, and the whole layout is regenerated in the rare case it
        does not.
        """
        for _attempt in range(200):
            self.ships = []
            self.owner_grid = [[-1] * SIZE for _ in range(SIZE)]
            ok = True
            for name, length in SHIP_TYPES:
                if not self._place_one(name, length, rng):
                    ok = False
                    break
            if ok:
                return
        raise RuntimeError("could not place fleet")

    def _place_one(self, name: str, length: int, rng: random.Random) -> bool:
        for _ in range(400):
            horizontal = rng.random() < 0.5
            if horizontal:
                r = rng.randrange(SIZE)
                c = rng.randrange(SIZE - length + 1)
                cells = [(r, c + i) for i in range(length)]
            else:
                r = rng.randrange(SIZE - length + 1)
                c = rng.randrange(SIZE)
                cells = [(r + i, c) for i in range(length)]

            if any(self.owner_grid[rr][cc] != -1 for rr, cc in cells):
                continue

            index = len(self.ships)
            self.ships.append(Ship(name=name, length=length, cells=cells))
            for rr, cc in cells:
                self.owner_grid[rr][cc] = index
            return True
        return False

    # ----------------------------------------------- manual placement

    def clear(self) -> None:
        self.ships = []
        self.owner_grid = [[-1] * SIZE for _ in range(SIZE)]

    def can_place(self, length: int, r: int, c: int, horizontal: bool) -> bool:
        """Would a ship of `length` fit here, bow at (r, c)?"""
        for i in range(length):
            rr = r + (0 if horizontal else i)
            cc = c + (i if horizontal else 0)
            if not (0 <= rr < SIZE and 0 <= cc < SIZE):
                return False
            if self.owner_grid[rr][cc] != -1:
                return False
        return True

    def place(self, name: str, length: int, r: int, c: int, horizontal: bool) -> bool:
        if not self.can_place(length, r, c, horizontal):
            return False
        cells = [
            (r + (0 if horizontal else i), c + (i if horizontal else 0))
            for i in range(length)
        ]
        index = len(self.ships)
        self.ships.append(Ship(name=name, length=length, cells=cells))
        for rr, cc in cells:
            self.owner_grid[rr][cc] = index
        return True

    def remove_last(self) -> bool:
        """Undo the most recently placed ship."""
        if not self.ships:
            return False
        ship = self.ships.pop()
        for rr, cc in ship.cells:
            self.owner_grid[rr][cc] = -1
        return True

    def is_complete(self) -> bool:
        return len(self.ships) == len(SHIP_TYPES)

    def next_to_place(self) -> tuple | None:
        """(name, length) of the ship awaiting placement, or None when done."""
        if self.is_complete():
            return None
        return SHIP_TYPES[len(self.ships)]

    def valid_cells(self, length: int, horizontal: bool) -> set:
        return {
            (r, c)
            for r in range(SIZE)
            for c in range(SIZE)
            if self.can_place(length, r, c, horizontal)
        }

    # ----------------------------------------------------------- resolution

    def receive(self, r: int, c: int) -> tuple[str, Ship | None]:
        """Resolve an incoming shot. Returns (outcome, ship_if_sunk)."""
        index = self.owner_grid[r][c]
        if index == -1:
            return "miss", None
        ship = self.ships[index]
        ship.hits.add((r, c))
        if ship.sunk:
            return "sunk", ship
        return "hit", None

    def all_sunk(self) -> bool:
        return all(s.sunk for s in self.ships)

    def remaining_lengths(self) -> list[int]:
        return [s.length for s in self.ships if not s.sunk]

    def cells_remaining(self) -> int:
        return sum(s.length - len(s.hits) for s in self.ships)


class ShotGrid:
    """What one side has learned about the other's board."""

    def __init__(self) -> None:
        self.state = [[UNKNOWN] * SIZE for _ in range(SIZE)]
        self.shots = 0
        self.hits = 0
        self.sunk_names: list[str] = []

    def already_fired(self, r: int, c: int) -> bool:
        return self.state[r][c] != UNKNOWN

    def record(self, r: int, c: int, outcome: str, ship: Ship | None) -> None:
        self.shots += 1
        if outcome == "miss":
            self.state[r][c] = MISS
            return
        self.hits += 1
        self.state[r][c] = HIT
        if outcome == "sunk" and ship is not None:
            # Marking the whole hull as SUNK is what lets the density model
            # exclude those squares from further placement hypotheses.
            for rr, cc in ship.cells:
                self.state[rr][cc] = SUNK
            self.sunk_names.append(ship.name)

    def unresolved_hits(self) -> list[tuple[int, int]]:
        """Hits not yet accounted for by a sunk ship — the live scent."""
        return [
            (r, c)
            for r in range(SIZE)
            for c in range(SIZE)
            if self.state[r][c] == HIT
        ]

    @property
    def accuracy(self) -> float:
        return self.hits / self.shots if self.shots else 0.0


def label(r: int, c: int) -> str:
    return f"{COLUMN_LABELS[c]}{r + 1}"
