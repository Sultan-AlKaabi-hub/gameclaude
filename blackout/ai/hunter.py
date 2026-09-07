"""
The hunter agent: a sensor plus a movement policy.

Deliberately thin. All the intelligence lives in the subsystems it composes —
the shared particle filter supplies belief, the auction supplies intent, A*
supplies motion. A hunter itself holds no privileged information about the
player, and that invariant is what makes the game honest: there is no
difficulty knob that quietly gives the AI your coordinates.
"""

from __future__ import annotations

import numpy as np

from ai.pathfinding import astar
from engine.grid import Grid, manhattan


class Hunter:
    """One pursuing agent."""

    __slots__ = ("pos", "radius", "sigma", "vision", "target", "path", "glyph", "index", "scanning")

    def __init__(
        self,
        pos: tuple[int, int],
        radius: int,
        sigma: float,
        vision: int,
        glyph: str,
        index: int = 0,
    ):
        self.pos = pos
        self.index = index
        self.scanning = False
        self.radius = radius      # proximity sensor range
        self.sigma = sigma        # sensor noise, lower is more accurate
        self.vision = vision      # range at which it sees you outright
        self.target: tuple[int, int] | None = None
        self.path: list[tuple[int, int]] = []
        self.glyph = glyph

    # ------------------------------------------------------------- sensing

    def sense(
        self,
        grid: Grid,
        source: tuple[int, int],
        rng: np.random.Generator,
        stealth_penalty: int = 0,
        blinded: bool = False,
    ) -> dict:
        """Produce this turn's observation about `source`.

        `source` is whatever the sensor is actually reacting to, which is the
        player normally and a decoy while one is active — the hunters cannot
        tell the difference, which is the whole point of the ability.

        `stealth_penalty` shrinks the effective radius when the player moves
        silently. `blinded` models an EMP: the sensor returns nothing at all,
        which is different from returning "absent". An absent reading is
        evidence; a blinded sensor is the absence of evidence, and the filter
        must treat them differently or EMP would help the hunters.
        """
        if blinded:
            return {"kind": "blind"}

        # A scanning hunter has stopped to listen: it does not move this turn,
        # but its reading is markedly sharper. This is a real tradeoff for the
        # AI (coverage versus precision) and it is what gives the player the
        # tempo advantage that makes objectives reachable.
        sigma = self.sigma * 0.5 if self.scanning else self.sigma
        radius = max(0, self.radius - stealth_penalty)
        if self.scanning:
            radius += 1
        distance = manhattan(self.pos, source)
        visible = grid.has_line_of_sight(self.pos, source)

        if visible and distance <= self.vision:
            # Close visual contact. A near-certain reading rather than a
            # collapse to a single cell: an absolutely certain observation
            # would pin the posterior to a point mass that re-fires every
            # turn, and the belief could never recover. Keeping it as a very
            # tight Gaussian preserves the Bayesian structure and leaves the
            # player a way to break contact.
            return {
                "kind": "range",
                "origin": self.pos,
                "distance": float(distance),
                "sigma": 0.45,
                "radius": max(radius, self.vision),
                "confident": True,
            }

        if visible and distance <= radius:
            noisy = distance + float(rng.normal(0.0, sigma))
            return {
                "kind": "range",
                "origin": self.pos,
                "distance": max(0.0, noisy),
                "sigma": sigma,
                "radius": radius,
            }

        return {"kind": "absent", "origin": self.pos, "radius": radius}

    # ------------------------------------------------------------- movement

    def plan(
        self,
        grid: Grid,
        target: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> None:
        """Recompute the route to an assigned target.

        Replanning every turn rather than caching keeps behaviour reactive:
        the belief peak moves constantly, and a hunter following a stale plan
        looks broken in a way players notice immediately.
        """
        self.target = target
        path = astar(grid, self.pos, target, blocked=blocked)
        self.path = path[1:] if len(path) > 1 else []

    def advance(self, blocked: set[tuple[int, int]]) -> tuple[int, int]:
        """Take one step along the plan. Holds position if the way is blocked."""
        if not self.path:
            return self.pos
        nxt = self.path[0]
        if nxt in blocked:
            return self.pos
        self.pos = self.path.pop(0)
        return self.pos
