"""
Game state and turn resolution.

One `GameState` object holds an entire run. Streamlit re-executes the script
on every interaction, so the object is parked in `st.session_state` and
mutated by `step()`; nothing in here imports Streamlit, which keeps the rules
testable headlessly and independent of the presentation layer.

Ordering inside a turn matters and is fixed:

    1. the player acts
    2. objectives resolve
    3. the filter predicts (belief diffuses)
    4. sensors fire and the filter updates
    5. hunters bid, plan, and move
    6. capture is checked

The player always acts on stale hunter positions and the hunters always react
to a fresh observation. Reversing 3 and 4 would let the filter update on the
player's previous cell and the AI would feel a turn behind.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

from ai.auction import allocate, select_targets
from ai.hunter import Hunter
from ai.particle_filter import ParticleFilter
from engine.grid import DIRECTIONS, Grid, manhattan
from engine.scoring import (
    DEFAULT_DIFFICULTY,
    GRID_HEIGHT,
    GRID_WIDTH,
    WALL_DENSITY,
    WaveConfig,
    compute_score,
    wave_config,
)

MAX_STAMINA = 100.0
SILENT_MOVE_COST = 10.0
STAMINA_REGEN_MOVE = 5.0
STAMINA_REGEN_WAIT = 16.0
SILENT_RADIUS_PENALTY = 4
DECOY_DURATION = 4
EMP_DURATION = 3
DECOY_RANGE = 5
HUNTER_GLYPHS = ["A", "B", "C", "D", "E"]


@dataclass
class GameState:
    """Everything about a run in progress."""

    seed: int
    daily: bool = False
    difficulty: str = DEFAULT_DIFFICULTY

    wave: int = 1
    turn: int = 0
    status: str = "active"  # active | caught | extracted

    grid: Grid = field(init=False)
    config: WaveConfig = field(init=False)
    player: tuple[int, int] = field(init=False)
    hunters: list[Hunter] = field(init=False)
    pf: ParticleFilter = field(init=False)
    nodes: set = field(default_factory=set)
    extraction: tuple[int, int] = field(init=False)

    stamina: float = MAX_STAMINA
    decoys: int = 2
    emps: int = 1
    decoy_cell: tuple[int, int] | None = None
    decoy_turns: int = 0
    emp_turns: int = 0

    nodes_extracted: int = 0
    turns_survived: int = 0
    waves_cleared: int = 0
    entropy_total: float = 0.0
    entropy_samples: int = 0

    log: list = field(default_factory=list)
    last_seen: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        self._build_wave(self.wave)

    # --------------------------------------------------------------- setup

    def _build_wave(self, wave: int) -> None:
        """Lay out a fresh arena. Seeded per wave so runs stay reproducible."""
        self.config = wave_config(wave, self.difficulty)
        wave_seed = self.seed * 7919 + wave * 104729
        py_rng = random.Random(wave_seed)
        self.rng = np.random.default_rng(wave_seed)

        self.grid = Grid(GRID_HEIGHT, GRID_WIDTH, wave_seed, WALL_DENSITY)

        # Player starts in a corner region, objectives spread across the map,
        # hunters as far from the player as the sampler can manage. A hunter
        # spawning next to the player would end the wave before the filter has
        # taken a single reading.
        cells = self.grid.random_free_cells(1, py_rng)
        self.player = cells[0]

        picks = self.grid.random_free_cells(
            self.config.nodes + 1,
            py_rng,
            exclude={self.player},
            min_separation=4,
        )
        self.nodes = set(picks[: self.config.nodes])
        self.extraction = picks[self.config.nodes]

        far = sorted(
            (c for c in self.grid.free_cells if c != self.player),
            key=lambda c: -manhattan(c, self.player),
        )[: max(6, self.config.hunters * 3)]
        py_rng.shuffle(far)
        self.hunters = [
            Hunter(
                pos=far[i % len(far)],
                radius=self.config.sensor_radius,
                sigma=self.config.sensor_sigma,
                vision=self.config.vision,
                glyph=HUNTER_GLYPHS[i % len(HUNTER_GLYPHS)],
                index=i,
            )
            for i in range(self.config.hunters)
        ]

        self.pf = ParticleFilter(self.grid, self.config.particles, self.rng)
        self.decoy_cell = None
        self.decoy_turns = 0
        self.emp_turns = 0
        self.stamina = MAX_STAMINA
        self.decoys = 2
        self.emps = 1
        self.last_seen = None
        self.log = [f"Wave {wave} inserted. {len(self.nodes)} data nodes to secure."]

    # ---------------------------------------------------------------- turn

    def step(self, action: str, argument=None) -> None:
        """Resolve one full turn. `action` is a move, wait, decoy, or emp."""
        if self.status != "active":
            return

        stealth = 0

        # 1. Player action -------------------------------------------------
        if action in ("N", "S", "W", "E", "silent_N", "silent_S", "silent_W", "silent_E"):
            silent = action.startswith("silent_")
            key = action.split("_")[-1]
            delta = {"N": (-1, 0), "S": (1, 0), "W": (0, -1), "E": (0, 1)}[key]
            target = (self.player[0] + delta[0], self.player[1] + delta[1])

            if not self.grid.walkable(target):
                self.log.append("Blocked by structure.")
                return

            if silent:
                if self.stamina < SILENT_MOVE_COST:
                    self.log.append("Insufficient stamina for silent movement.")
                    return
                self.stamina -= SILENT_MOVE_COST
                stealth = SILENT_RADIUS_PENALTY
            else:
                self.stamina = min(MAX_STAMINA, self.stamina + STAMINA_REGEN_MOVE)

            self.player = target

        elif action == "wait":
            self.stamina = min(MAX_STAMINA, self.stamina + STAMINA_REGEN_WAIT)
            stealth = 1  # standing still is quieter than walking

        elif action == "decoy":
            if self.decoys <= 0:
                self.log.append("No decoy emitters remaining.")
                return
            self.decoys -= 1
            candidates = [
                c
                for c in self.grid.free_cells
                if 2 <= manhattan(c, self.player) <= DECOY_RANGE
            ]
            if candidates:
                self.decoy_cell = candidates[self.rng.integers(0, len(candidates))]
                self.decoy_turns = DECOY_DURATION
                self.log.append("Decoy emitter deployed. Sensors are chasing a ghost.")
            self.stamina = min(MAX_STAMINA, self.stamina + STAMINA_REGEN_MOVE)

        elif action == "emp":
            if self.emps <= 0:
                self.log.append("No EMP charges remaining.")
                return
            self.emps -= 1
            self.emp_turns = EMP_DURATION
            self.log.append("EMP detonated. Sensor grid down; their belief is decaying.")
            self.stamina = min(MAX_STAMINA, self.stamina + STAMINA_REGEN_MOVE)

        else:
            return

        self.turn += 1
        self.turns_survived += 1

        # 2. Objectives ----------------------------------------------------
        if self.player in self.nodes:
            self.nodes.discard(self.player)
            self.nodes_extracted += 1
            if self.nodes:
                self.log.append(
                    f"Data node secured. {len(self.nodes)} remaining."
                )
            else:
                self.log.append("All nodes secured. Extraction point is live.")

        if not self.nodes and self.player == self.extraction:
            self.waves_cleared += 1
            self.log.append(f"Extraction confirmed. Wave {self.wave} clear.")
            self.status = "extracted"
            return

        # 3. Belief diffuses through the motion model ----------------------
        self.pf.predict()

        # 4. Sensors fire --------------------------------------------------
        # Staggered cadence: hunters take turns holding position to scan, so
        # the squad never advances as a solid wall.
        for hunter in self.hunters:
            hunter.scanning = ((self.turn + hunter.index) % self.config.scan_period == 0)

        blinded = self.emp_turns > 0
        source = self.decoy_cell if self.decoy_turns > 0 and self.decoy_cell else self.player

        observations = []
        spotted = False
        for hunter in self.hunters:
            obs = hunter.sense(
                self.grid, source, self.rng, stealth_penalty=stealth, blinded=blinded
            )
            if obs["kind"] == "blind":
                continue
            if obs.get("confident"):
                spotted = True
                self.last_seen = source
            observations.append(obs)

        self.pf.update(observations)

        if spotted and source == self.player:
            self.log.append("Visual contact. They have you.")

        # 5. Hunters coordinate and move -----------------------------------
        self._move_hunters()

        # 6. Capture -------------------------------------------------------
        for hunter in self.hunters:
            d = manhattan(hunter.pos, self.player)
            if d == 0 or (d == 1 and self.grid.has_line_of_sight(hunter.pos, self.player)):
                self.status = "caught"
                self.log.append("Contact. Run terminated.")
                break

        # Timers -----------------------------------------------------------
        if self.decoy_turns > 0:
            self.decoy_turns -= 1
            if self.decoy_turns == 0:
                self.decoy_cell = None
        if self.emp_turns > 0:
            self.emp_turns -= 1
            if self.emp_turns == 0:
                self.log.append("Sensor grid back online.")

        entropy = self.pf.normalised_entropy()
        self.entropy_total += entropy
        self.entropy_samples += 1

        self.log = self.log[-6:]

    def _move_hunters(self) -> None:
        """Auction search targets, replan, then step each hunter once."""
        hypotheses = self.pf.top_hypotheses(24)
        targets = select_targets(hypotheses, max_targets=len(self.hunters))
        positions = [h.pos for h in self.hunters]
        assignment = allocate(self.grid, positions, targets)

        occupied = {h.pos for h in self.hunters}
        for i, hunter in enumerate(self.hunters):
            target = assignment.get(i)
            if target is None:
                target = hypotheses[0][0] if hypotheses else hunter.pos
            blocked = occupied - {hunter.pos}
            hunter.plan(self.grid, target, blocked)
            if hunter.scanning:
                continue  # held position this turn to take a sharper reading
            occupied.discard(hunter.pos)
            hunter.advance(blocked)
            occupied.add(hunter.pos)

    # ------------------------------------------------------------ advance

    def next_wave(self) -> None:
        """Carry the run forward into a harder arena."""
        self.wave += 1
        self.status = "active"
        self._build_wave(self.wave)

    # ------------------------------------------------------------ readouts

    @property
    def mean_entropy(self) -> float:
        if self.entropy_samples == 0:
            return 1.0
        return self.entropy_total / self.entropy_samples

    @property
    def score(self) -> int:
        return compute_score(
            self.nodes_extracted,
            self.turns_survived,
            self.waves_cleared,
            self.mean_entropy,
            self.difficulty,
        )

    def legal_moves(self) -> dict[str, bool]:
        """Which directions are walkable, for disabling dead buttons."""
        out = {}
        for key, delta in (
            ("N", (-1, 0)),
            ("S", (1, 0)),
            ("W", (0, -1)),
            ("E", (0, 1)),
        ):
            target = (self.player[0] + delta[0], self.player[1] + delta[1])
            out[key] = self.grid.walkable(target)
        return out

    def threat_level(self) -> float:
        """1.0 when the belief has collapsed onto you, 0.0 when they are lost."""
        return 1.0 - self.pf.normalised_entropy()

    def nearest_hunter_distance(self) -> int:
        return min(manhattan(h.pos, self.player) for h in self.hunters)
