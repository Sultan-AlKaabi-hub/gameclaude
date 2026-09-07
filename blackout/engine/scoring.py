"""
Difficulty curve and scoring.

Score is a pure function of what the player did, and every input to it is
derived from `seed` plus the action log. That determinism is what lets the
leaderboard mean anything: a run can be replayed and verified, and the daily
challenge puts every player on an identical arena.

The stealth term is the unusual one. It pays out the mean normalised entropy
of the hunters' belief across the run, so points come from how *uncertain*
you kept the AI, not merely from surviving. A player who sprints to the
objectives through open ground and one who ghosts the same route while
feeding the filter bad evidence do not earn the same score.
"""

from __future__ import annotations

from dataclasses import dataclass

POINTS_PER_NODE = 250
POINTS_PER_TURN = 5
POINTS_WAVE_BASE = 1500
POINTS_STEALTH_MAX = 1000

GRID_HEIGHT = 19
GRID_WIDTH = 19
WALL_DENSITY = 0.18


# Difficulty tiers. Each axis is tuned independently so the tiers feel
# different rather than merely scaled: RECRUIT gives more tempo (hunters scan
# more often), GHOST gives the AI sharper sensors rather than just more of them.
DIFFICULTIES = {
    "RECRUIT": {
        "hunter_offset": 0, "radius_offset": -1, "sigma_scale": 1.30,
        "scan_period": 2, "multiplier": 0.75,
        "blurb": "Wider sensor noise, hunters pause often. Learn the systems.",
    },
    "OPERATIVE": {
        "hunter_offset": 0, "radius_offset": 0, "sigma_scale": 1.00,
        "scan_period": 3, "multiplier": 1.00,
        "blurb": "The intended balance. Standard leaderboard tier.",
    },
    "GHOST": {
        "hunter_offset": 1, "radius_offset": 1, "sigma_scale": 0.78,
        "scan_period": 4, "multiplier": 1.60,
        "blurb": "Extra hunter, sharper readings, relentless pursuit.",
    },
}
DEFAULT_DIFFICULTY = "OPERATIVE"


@dataclass(frozen=True)
class WaveConfig:
    """Every difficulty parameter for one wave, derived from the wave number."""

    wave: int
    hunters: int
    sensor_radius: int
    sensor_sigma: float
    vision: int
    nodes: int
    particles: int
    scan_period: int
    difficulty: str

    @property
    def label(self) -> str:
        return f"WAVE {self.wave:02d}"


def wave_config(wave: int, difficulty: str = DEFAULT_DIFFICULTY) -> WaveConfig:
    """Escalate pressure along independent axes.

    Adding hunters raises spatial coverage. Widening the radius raises the
    rate of evidence. Cutting sigma raises the quality of each reading. These
    feel different to play against, so the ramp stays interesting rather than
    just becoming numerically harder.
    """
    d = DIFFICULTIES.get(difficulty, DIFFICULTIES[DEFAULT_DIFFICULTY])
    return WaveConfig(
        wave=wave,
        hunters=min(2 + wave // 3 + d["hunter_offset"], 6),
        sensor_radius=max(2, min(3 + wave // 2 + d["radius_offset"], 8)),
        sensor_sigma=max(0.8, (2.8 - 0.18 * wave) * d["sigma_scale"]),
        vision=min(2 + wave // 4, 4),
        nodes=min(2 + wave // 3, 5),
        particles=500,
        scan_period=d["scan_period"],
        difficulty=difficulty,
    )


def wave_clear_bonus(wave: int) -> int:
    return POINTS_WAVE_BASE * wave


def difficulty_multiplier(difficulty: str) -> float:
    return DIFFICULTIES.get(difficulty, DIFFICULTIES[DEFAULT_DIFFICULTY])["multiplier"]


def compute_score(
    nodes_extracted: int,
    turns_survived: int,
    waves_cleared: int,
    mean_entropy: float,
    difficulty: str = DEFAULT_DIFFICULTY,
) -> int:
    """Assemble the final score from the run's summary statistics.

    The difficulty multiplier is applied last so the leaderboard can rank
    every tier on one table without a harder tier being strictly dominated.
    """
    node_points = nodes_extracted * POINTS_PER_NODE
    turn_points = turns_survived * POINTS_PER_TURN
    wave_points = sum(wave_clear_bonus(w) for w in range(1, waves_cleared + 1))
    stealth_points = int(mean_entropy * POINTS_STEALTH_MAX)
    raw = node_points + turn_points + wave_points + stealth_points
    return int(raw * difficulty_multiplier(difficulty))


def score_breakdown(
    nodes_extracted: int,
    turns_survived: int,
    waves_cleared: int,
    mean_entropy: float,
) -> list[tuple[str, int]]:
    """Itemised score, for the debrief screen."""
    return [
        ("Data nodes secured", nodes_extracted * POINTS_PER_NODE),
        ("Turns survived", turns_survived * POINTS_PER_TURN),
        (
            "Waves cleared",
            sum(wave_clear_bonus(w) for w in range(1, waves_cleared + 1)),
        ),
        ("Stealth rating", int(mean_entropy * POINTS_STEALTH_MAX)),
    ]
