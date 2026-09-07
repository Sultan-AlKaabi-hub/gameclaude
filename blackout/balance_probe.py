"""Play the game with a competent heuristic agent to measure difficulty."""

import statistics
import sys

from ai.pathfinding import astar
from engine.grid import manhattan
from engine.state import GameState


def danger_map(gs):
    """Cells to avoid: adjacent to a hunter is death, near one is risky."""
    danger = {}
    for h in gs.hunters:
        for cell in gs.grid.free_cells:
            d = manhattan(cell, h.pos)
            if d <= 3:
                danger[cell] = max(danger.get(cell, 0), 4 - d)
    return danger


def safe_step_toward(gs, goal, danger):
    """One step toward goal that does not walk into a kill zone."""
    path = astar(gs.grid, gs.player, goal)
    ideal = path[1] if len(path) > 1 else None
    options = []
    for key, d in (("N", (-1, 0)), ("S", (1, 0)), ("W", (0, -1)), ("E", (0, 1))):
        cell = (gs.player[0] + d[0], gs.player[1] + d[1])
        if not gs.grid.walkable(cell):
            continue
        risk = danger.get(cell, 0)
        progress = -manhattan(cell, goal)
        options.append((risk * 10 - progress, key, cell))
    if not options:
        return "wait"
    options.sort()
    return options[0][1]


def heuristic_agent(gs):
    """A reasonable-but-not-optimal player: pursue objective, evade when close."""
    goal = None
    if gs.nodes:
        goal = min(gs.nodes, key=lambda n: manhattan(gs.player, n))
    else:
        goal = gs.extraction

    nearest = gs.nearest_hunter_distance()
    threat = gs.threat_level()
    danger = danger_map(gs)

    if gs.emps > 0 and threat > 0.7 and nearest <= 4:
        return "emp"
    if gs.decoys > 0 and threat > 0.6 and nearest <= 5:
        return "decoy"

    key = safe_step_toward(gs, goal, danger)
    if key == "wait":
        return "wait"
    if (threat > 0.45 or nearest <= 5) and gs.stamina > 25:
        return f"silent_{key}"
    return key


def probe(n_runs=60, max_waves=6):
    results = []
    for seed in range(n_runs):
        gs = GameState(seed=seed)
        turns = 0
        while gs.status != "caught" and turns < 600 and gs.waves_cleared < max_waves:
            if gs.status == "extracted":
                gs.next_wave()
                continue
            gs.step(heuristic_agent(gs))
            turns += 1
        results.append((gs.waves_cleared, gs.turns_survived, gs.score, gs.mean_entropy))
    return results


if __name__ == "__main__":
    res = probe()
    waves = [r[0] for r in res]
    turns = [r[1] for r in res]
    scores = [r[2] for r in res]
    ent = [r[3] for r in res]
    print(f"runs                 : {len(res)}")
    print(f"waves cleared  mean  : {statistics.mean(waves):.2f}")
    print(f"waves cleared  median: {statistics.median(waves)}")
    print(f"cleared wave 1 at all: {sum(1 for w in waves if w >= 1)}/{len(res)}")
    print(f"cleared wave 3+      : {sum(1 for w in waves if w >= 3)}/{len(res)}")
    print(f"turns survived mean  : {statistics.mean(turns):.1f}")
    print(f"score mean           : {statistics.mean(scores):.0f}")
    print(f"score max            : {max(scores)}")
    print(f"mean entropy         : {statistics.mean(ent):.3f}")
    dist = {}
    for w in waves:
        dist[w] = dist.get(w, 0) + 1
    print(f"wave distribution    : {dict(sorted(dist.items()))}")
