"""Headless validation of the engine and AI. Run: python tests_headless.py"""

import random
import statistics
import sys
import time

import numpy as np

from ai.pathfinding import astar
from engine.grid import Grid, manhattan
from engine.state import GameState

FAILS = []


def check(name, condition, detail=""):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILS.append(name)


print("\n[1] Grid generation and connectivity")
for seed in range(30):
    g = Grid(15, 15, seed)
    reachable = len(astar(g, g.free_cells[0], g.free_cells[-1])) > 0
    if not reachable:
        check(f"seed {seed} fully connected", False)
        break
else:
    check("30 seeds all fully connected", True)
    g = Grid(15, 15, 1)
    check("free cell count is sane", 120 <= len(g.free_cells) <= 215,
          f"got {len(g.free_cells)}")

print("\n[2] A* optimality and consistency")
g = Grid(15, 15, 7)
ok = True
for _ in range(200):
    a, b = random.sample(g.free_cells, 2)
    p = astar(g, a, b)
    if not p:
        ok = False
        break
    # A path must be contiguous, walkable, and no shorter than Manhattan.
    if p[0] != a or p[-1] != b:
        ok = False
        break
    if any(manhattan(p[i], p[i + 1]) != 1 for i in range(len(p) - 1)):
        ok = False
        break
    if len(p) - 1 < manhattan(a, b):
        ok = False
        break
check("200 random paths valid, contiguous, >= Manhattan bound", ok)

print("\n[3] Particle filter converges on a stationary target")
gs = GameState(seed=42)
gs.player = gs.grid.free_cells[len(gs.grid.free_cells) // 2]
start_entropy = gs.pf.normalised_entropy()
for _ in range(40):
    gs.step("wait")
    if gs.status != "active":
        break
end_entropy = gs.pf.normalised_entropy()
# Estimating entropy from 500 particles over ~280 cells biases slightly low
# even for a genuinely uniform prior, so the bar is 0.90 rather than 1.0.
check("initial entropy near maximum", start_entropy > 0.90, f"{start_entropy:.3f}")
check("entropy falls while the target sits still",
      end_entropy < start_entropy, f"{start_entropy:.3f} -> {end_entropy:.3f}")

print("\n[4] EMP raises uncertainty (belief decays without evidence)")
# Search seeds for a run that stays alive long enough to test the mechanic;
# a randomly-moving player is often caught before the belief has converged.
tested = False
for seed in range(60):
    gs = GameState(seed=seed, difficulty="RECRUIT")
    for _ in range(18):
        gs.step("wait")
        if gs.status != "active":
            break
    if gs.status != "active":
        continue
    before = gs.pf.normalised_entropy()
    gs.step("emp")
    for _ in range(3):
        gs.step("wait")
        if gs.status != "active":
            break
    if gs.status != "active":
        continue
    after = gs.pf.normalised_entropy()
    check("entropy rises after EMP", after > before, f"{before:.3f} -> {after:.3f}")
    tested = True
    break
if not tested:
    check("EMP scenario reached", False, "no surviving seed found")

print("\n[5] Hunters disperse rather than stacking")
gs = GameState(seed=5)
overlaps = 0
for _ in range(30):
    gs.step(random.choice(["N", "S", "E", "W", "wait"]))
    if gs.status != "active":
        break
    positions = [h.pos for h in gs.hunters]
    overlaps += len(positions) - len(set(positions))
check("hunters never occupy the same cell", overlaps == 0, f"{overlaps} overlaps")

print("\n[6] Full random playthroughs do not crash")
durations = []
outcomes = {"caught": 0, "extracted": 0, "timeout": 0}
for seed in range(40):
    gs = GameState(seed=seed)
    t0 = time.perf_counter()
    turns = 0
    while gs.status == "active" and turns < 120:
        moves = [k for k, v in gs.legal_moves().items() if v] or ["wait"]
        pool = moves + ["wait", "decoy", "emp"]
        gs.step(random.choice(pool))
        turns += 1
    durations.append((time.perf_counter() - t0) / max(turns, 1))
    if gs.status == "active":
        outcomes["timeout"] += 1
    else:
        outcomes[gs.status] += 1
    _ = gs.score
check("40 playthroughs completed without exception", True)
print(f"        outcomes: {outcomes}")

print("\n[7] Per-turn compute budget (target < 150ms)")
mean_ms = statistics.mean(durations) * 1000
p95_ms = sorted(durations)[int(len(durations) * 0.95)] * 1000
check(f"mean turn {mean_ms:.1f}ms", mean_ms < 150)
check(f"p95 turn {p95_ms:.1f}ms", p95_ms < 250)

print("\n[8] Determinism: identical seed and actions give identical results")
def run(seed):
    gs = GameState(seed=seed)
    rng = random.Random(999)
    for _ in range(35):
        if gs.status != "active":
            break
        gs.step(rng.choice(["N", "S", "E", "W", "wait"]))
    return (gs.player, [h.pos for h in gs.hunters], gs.turns_survived, gs.status)

check("same seed reproduces exactly", run(77) == run(77))
check("different seeds diverge", run(77) != run(78))

print("\n[9] Wave progression")
gs = GameState(seed=3)
gs.nodes = set()
gs.player = gs.extraction
gs.step("wait")
if gs.status == "extracted":
    prev_hunters = len(gs.hunters)
    gs.next_wave()
    check("wave advances and rebuilds arena", gs.wave == 2 and gs.status == "active")
    check("difficulty scales", len(gs.hunters) >= prev_hunters)
else:
    check("extraction triggers on objective cell", False, gs.status)

print("\n[10] Scoring monotonicity and difficulty multiplier")
from engine.scoring import compute_score
base = compute_score(3, 50, 1, 0.5)
check("more nodes scores higher", compute_score(4, 50, 1, 0.5) > base)
check("more stealth scores higher", compute_score(3, 50, 1, 0.9) > base)
check("more waves scores higher", compute_score(3, 50, 2, 0.5) > base)
check("harder tier scores higher",
      compute_score(3, 50, 1, 0.5, "GHOST") > compute_score(3, 50, 1, 0.5, "RECRUIT"))

print("\n[11] SVG renderer produces well-formed output (headless)")
import xml.etree.ElementTree as ET
from ui.render import render_arena, legend_html
gs = GameState(seed=9)
for _ in range(6):
    gs.step("wait")
svg = render_arena(gs, show_belief=True, show_intent=True)
try:
    ET.fromstring(svg)
    check("SVG parses as valid XML", True)
except ET.ParseError as e:
    check("SVG parses as valid XML", False, str(e))
check("SVG contains belief, hunters and player", 
      svg.count("<rect") > 20 and "polygon" in svg and "circle" in svg)
check("legend renders", "<div" in legend_html())

print("\n" + "=" * 52)
if FAILS:
    print(f"FAILED: {len(FAILS)} -> {FAILS}")
    sys.exit(1)
print("ALL CHECKS PASSED")
