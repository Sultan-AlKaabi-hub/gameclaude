"""
Multi-agent task allocation by sequential single-item auction.

Without coordination, every hunter runs A* toward the single most probable
cell and they converge into a useless conga line, leaving most of the arena
unwatched. This module is what makes them behave like a team.

The approach is a greedy sequential single-item auction, the workhorse
simplification of the Contract Net protocol: agents bid on tasks, the highest
bid clears, both parties leave the pool, repeat. It is not optimal (that would
need the Hungarian algorithm on the full cost matrix) but it runs in
O(hunters x targets) per round, is trivially explicable, and empirically
lands within a few percent of optimal on grids this size.

Bid value trades off reward against effort:

    bid = probability_mass / (1 + path_cost)

so a hunter will abandon a slightly richer hypothesis if a rival can reach it
much faster, which is precisely the behaviour that makes them fan out.
"""

from __future__ import annotations

from ai.pathfinding import path_cost
from engine.grid import Grid, manhattan


def select_targets(
    hypotheses: list[tuple[tuple[int, int], float]],
    max_targets: int,
    min_separation: int = 3,
) -> list[tuple[tuple[int, int], float]]:
    """Thin the belief peaks into a spread of distinct search targets.

    Adjacent cells in a dense cluster all describe the same hypothesis, so
    taking the raw top-k would hand every hunter the same destination with
    extra steps. Enforcing a separation radius yields genuinely different
    places to check.
    """
    chosen: list[tuple[tuple[int, int], float]] = []
    for cell, prob in hypotheses:
        if len(chosen) >= max_targets:
            break
        if all(manhattan(cell, other) >= min_separation for other, _ in chosen):
            chosen.append((cell, prob))
    if not chosen and hypotheses:
        chosen = hypotheses[:max_targets]
    return chosen


def allocate(
    grid: Grid,
    hunter_positions: list[tuple[int, int]],
    targets: list[tuple[tuple[int, int], float]],
) -> dict[int, tuple[int, int]]:
    """Assign at most one target to each hunter. Returns {hunter_index: cell}.

    Hunters left unassigned (more hunters than distinct targets) fall back to
    the richest hypothesis in the caller.
    """
    if not targets or not hunter_positions:
        return {}

    # Bid matrix. path_cost runs A*, so this is the expensive call in the
    # turn; target count is deliberately capped by the caller.
    bids: list[tuple[float, int, int]] = []
    for h_i, pos in enumerate(hunter_positions):
        for t_i, (cell, prob) in enumerate(targets):
            cost = path_cost(grid, pos, cell)
            bids.append((prob / (1.0 + cost), h_i, t_i))

    bids.sort(key=lambda b: -b[0])

    assignment: dict[int, tuple[int, int]] = {}
    taken_hunters: set[int] = set()
    taken_targets: set[int] = set()

    for _, h_i, t_i in bids:
        if h_i in taken_hunters or t_i in taken_targets:
            continue
        assignment[h_i] = targets[t_i][0]
        taken_hunters.add(h_i)
        taken_targets.add(t_i)
        if len(taken_hunters) == len(hunter_positions):
            break

    return assignment
