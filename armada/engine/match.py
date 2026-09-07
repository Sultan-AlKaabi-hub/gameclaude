"""
Match state and scoring.

The player and the AI each own a `Fleet` (the truth) and a `ShotGrid` (what
they have learned about the other). A turn is: the player fires, and if the
game is still running the AI fires back.

Nothing here imports Streamlit.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ai.density import DIFFICULTIES, TargetingAI
from engine.fleet import SIZE, TOTAL_SHIP_CELLS, Fleet, ShotGrid, label

WIN_POINTS = 1500
PERFECT_SHOTS = TOTAL_SHIP_CELLS  # 17, the theoretical minimum to win
EFFICIENCY_POINTS = 25
SURVIVAL_POINTS = 60


@dataclass
class Match:
    """One complete game of Battleship."""

    difficulty: str
    seed: int = 0
    status: str = "playing"  # playing | won | lost
    log: list = field(default_factory=list)
    last_ai_shot: tuple | None = None

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.player_fleet = Fleet()
        self.ai_fleet = Fleet()
        self.player_fleet.place_random(self.rng)
        self.ai_fleet.place_random(self.rng)
        self.player_shots = ShotGrid()  # what the player knows about the AI
        self.ai_shots = ShotGrid()      # what the AI knows about the player
        self.ai = TargetingAI(self.difficulty, self.rng)
        self.log = ["Fleets deployed. Open fire."]

    # ------------------------------------------------------------ placement

    def reshuffle_player_fleet(self) -> None:
        """Re-lay the player's own ships before the first shot."""
        if self.player_shots.shots or self.ai_shots.shots:
            return
        self.player_fleet.place_random(self.rng)

    # ----------------------------------------------------------------- turn

    def fire(self, r: int, c: int) -> bool:
        """Player fires, then the AI replies. Returns False on an illegal shot."""
        if self.status != "playing" or self.player_shots.already_fired(r, c):
            return False

        outcome, ship = self.ai_fleet.receive(r, c)
        self.player_shots.record(r, c, outcome, ship)
        if outcome == "sunk" and ship:
            self.log.append(f"You sank their {ship.name} at {label(r, c)}.")
        elif outcome == "hit":
            self.log.append(f"Hit at {label(r, c)}.")
        else:
            self.log.append(f"Miss at {label(r, c)}.")

        if self.ai_fleet.all_sunk():
            self.status = "won"
            self.log.append("Enemy fleet destroyed.")
            return True

        self._ai_turn()
        return True

    def _ai_turn(self) -> None:
        r, c = self.ai.choose(self.ai_shots, self.player_fleet.remaining_lengths())
        outcome, ship = self.player_fleet.receive(r, c)
        self.ai_shots.record(r, c, outcome, ship)
        self.last_ai_shot = (r, c)

        if outcome == "sunk" and ship:
            self.log.append(f"They sank your {ship.name} at {label(r, c)}.")
        elif outcome == "hit":
            self.log.append(f"They hit your fleet at {label(r, c)}.")
        else:
            self.log.append(f"They missed at {label(r, c)}.")

        if self.player_fleet.all_sunk():
            self.status = "lost"
            self.log.append("Your fleet is gone.")

        self.log = self.log[-6:]

    # -------------------------------------------------------------- scoring

    def score(self) -> int:
        mult = DIFFICULTIES.get(self.difficulty, DIFFICULTIES["ADMIRAL"])["multiplier"]
        if self.status == "won":
            # 17 shots is a perfect game; every wasted shot costs.
            wasted = max(0, self.player_shots.shots - PERFECT_SHOTS)
            efficiency = max(0, (100 - PERFECT_SHOTS - wasted)) * EFFICIENCY_POINTS
            survivors = self.player_fleet.cells_remaining() * SURVIVAL_POINTS
            return int((WIN_POINTS + efficiency + survivors) * mult)
        # A loss still pays for damage done.
        sunk = len(self.player_shots.sunk_names)
        return int((sunk * 150 + self.player_shots.hits * 25) * mult)

    def breakdown(self) -> list[tuple[str, str]]:
        mult = DIFFICULTIES.get(self.difficulty, DIFFICULTIES["ADMIRAL"])["multiplier"]
        rows = []
        if self.status == "won":
            wasted = max(0, self.player_shots.shots - PERFECT_SHOTS)
            rows.append(("Victory", f"{WIN_POINTS:,}"))
            rows.append((
                f"Efficiency ({self.player_shots.shots} shots, {wasted} wasted)",
                f"{max(0, 100 - PERFECT_SHOTS - wasted) * EFFICIENCY_POINTS:,}",
            ))
            rows.append((
                f"Fleet surviving ({self.player_fleet.cells_remaining()} cells)",
                f"{self.player_fleet.cells_remaining() * SURVIVAL_POINTS:,}",
            ))
        else:
            rows.append((
                f"Ships sunk ({len(self.player_shots.sunk_names)})",
                f"{len(self.player_shots.sunk_names) * 150:,}",
            ))
            rows.append((f"Hits landed ({self.player_shots.hits})",
                         f"{self.player_shots.hits * 25:,}"))
        rows.append((f"{self.difficulty} difficulty", f"×{mult}"))
        return rows

    # ------------------------------------------------------------- readouts

    def player_accuracy(self) -> float:
        return self.player_shots.accuracy

    def ai_accuracy(self) -> float:
        return self.ai_shots.accuracy

    def enemy_ships_left(self) -> int:
        return sum(1 for s in self.ai_fleet.ships if not s.sunk)

    def own_ships_left(self) -> int:
        return sum(1 for s in self.player_fleet.ships if not s.sunk)
