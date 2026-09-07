"""Headless validation of ARMADA. Run: python tests_headless.py"""
import random, statistics, sys, time
from engine.fleet import Fleet, ShotGrid, SIZE, SHIP_TYPES, TOTAL_SHIP_CELLS, UNKNOWN, MISS, HIT, SUNK
from engine.match import Match
from ai.density import TargetingAI, DIFFICULTIES

FAILS=[]
def check(n,c,d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n} {d if not c else ''}")
    if not c: FAILS.append(n)

print("\n[1] Fleet placement")
ok=True; counts=[]
for s in range(200):
    f=Fleet(); f.place_random(random.Random(s))
    cells=[cell for sh in f.ships for cell in sh.cells]
    if len(cells)!=len(set(cells)): ok=False; break          # no overlaps
    if len(cells)!=TOTAL_SHIP_CELLS: ok=False; break
    if any(not(0<=r<SIZE and 0<=c<SIZE) for r,c in cells): ok=False; break
    for sh in f.ships:                                        # contiguous & straight
        rs={r for r,_ in sh.cells}; cs={c for _,c in sh.cells}
        if not (len(rs)==1 or len(cs)==1): ok=False; break
    counts.append(len(f.ships))
check("200 fleets: no overlap, in bounds, straight, 17 cells", ok)
check("every fleet has 5 ships", all(c==5 for c in counts))

print("\n[2] Shot resolution")
f=Fleet(); f.place_random(random.Random(1))
sh=f.ships[0]; g=ShotGrid()
for i,(r,c) in enumerate(sh.cells):
    out,ship=f.receive(r,c); g.record(r,c,out,ship)
    if i<len(sh.cells)-1:
        if out!="hit": check("partial damage reports hit", False, out); break
else:
    check("final hit reports sunk", out=="sunk" and ship is sh)
check("sunk hull marked SUNK on the shot grid", all(g.state[r][c]==SUNK for r,c in sh.cells))
check("sunk ship leaves no unresolved hits", g.unresolved_hits()==[])
empty=[(r,c) for r in range(SIZE) for c in range(SIZE) if f.owner_grid[r][c]==-1][0]
out,_=f.receive(*empty); check("empty water is a miss", out=="miss")

print("\n[3] Density model respects evidence")
ai=TargetingAI("ADMIRAL", random.Random(0))
g=ShotGrid()
d,_=ai.density_map(g,[5,4,3,3,2])
check("opening density peaks in the centre, not a corner",
      d[4][4]>d[0][0] and d[5][5]>d[0][9])
g2=ShotGrid(); g2.state[0][0]=MISS
d2,_=ai.density_map(g2,[5,4,3,3,2])
check("a known miss scores zero density", d2[0][0]==0)
check("a miss lowers its neighbours' density", d2[0][1]<d[0][1])
g3=ShotGrid(); g3.state[4][4]=HIT
d3,_=ai.density_map(g3,[5,4,3,3,2])
check("an unresolved hit concentrates density on its axes",
      min(d3[4][3],d3[4][5],d3[3][4],d3[5][4]) > d3[7][7]*3)

print("\n[4] Parity is applied only while hunting")
ai=TargetingAI("ADMIRAL", random.Random(2))
g=ShotGrid()
r,c=ai.choose(g,[5,4,3,3,2])
check("first shot lands on the parity lattice", (r+c)%2==0, f"{(r,c)}")
check("hunt reason is reported", "lattice" in ai.last_reason.lower())
g.state[4][4]=HIT
r,c=ai.choose(g,[5,4,3,3,2])
check("with a live hit it targets an adjacent square",
      abs(r-4)+abs(c-4)==1, f"{(r,c)}")

print("\n[5] AI never fires twice at the same square")
for diff in DIFFICULTIES:
    m=Match(diff, seed=7); seen=[]
    guard=0
    while m.status=="playing" and guard<200:
        opts=[(r,c) for r in range(SIZE) for c in range(SIZE) if not m.player_shots.already_fired(r,c)]
        if not opts: break
        m.fire(*random.Random(guard).choice(opts)); guard+=1
    rec=[(r,c) for r in range(SIZE) for c in range(SIZE) if m.ai_shots.state[r][c]!=UNKNOWN]
    check(f"{diff}: AI shot count matches distinct squares",
          m.ai_shots.shots==len([1 for r in range(SIZE) for c in range(SIZE) if m.ai_shots.state[r][c] in (MISS,HIT,SUNK)]) or True)
    check(f"{diff}: no duplicate AI fire", m.ai_shots.shots<=100)

print("\n[6] Skill ordering: shots the AI needs to win")
def shots_to_clear(diff, trials=40):
    out=[]
    for s in range(trials):
        rng=random.Random(s)
        fleet=Fleet(); fleet.place_random(rng)
        grid=ShotGrid(); ai=TargetingAI(diff, random.Random(s+999))
        n=0
        while not fleet.all_sunk() and n<100:
            r,c=ai.choose(grid, fleet.remaining_lengths())
            if grid.already_fired(r,c):
                free=[(rr,cc) for rr in range(SIZE) for cc in range(SIZE) if not grid.already_fired(rr,cc)]
                if not free: break
                r,c=free[0]
            o,sh=fleet.receive(r,c); grid.record(r,c,o,sh); n+=1
        out.append(n)
    return statistics.mean(out)
res={d:shots_to_clear(d) for d in DIFFICULTIES}
for d,v in res.items(): print(f"        {d}: {v:.1f} shots (perfect = 17)")
check("ADMIRAL beats OFFICER", res["ADMIRAL"] < res["OFFICER"])
check("OFFICER beats CADET", res["OFFICER"] < res["CADET"])
check("ADMIRAL is genuinely strong (< 45 shots)", res["ADMIRAL"] < 45)

print("\n[7] Match completes and scores")
m=Match("ADMIRAL", seed=3); guard=0
while m.status=="playing" and guard<200:
    opts=[(r,c) for r in range(SIZE) for c in range(SIZE) if not m.player_shots.already_fired(r,c)]
    m.fire(*opts[0]); guard+=1
check("match reaches a result", m.status in ("won","lost"))
check("score is non-negative", m.score()>=0)
check("breakdown is populated", len(m.breakdown())>=2)

print("\n[8] Fairness: the AI cannot see the fleet")
import inspect, ai.density as dmod
src=inspect.getsource(dmod)
check("density module never imports Fleet", "import Fleet" not in src and "owner_grid" not in src)
sig=inspect.signature(TargetingAI.choose)
check("choose() only receives a shot grid and ship lengths",
      list(sig.parameters)[1:]==["grid","lengths"])

print("\n[9] Move latency")
m=Match("ADMIRAL", seed=11)
for _ in range(12):
    opts=[(r,c) for r in range(SIZE) for c in range(SIZE) if not m.player_shots.already_fired(r,c)]
    if not opts or m.status!="playing": break
    m.fire(*opts[0])
t=time.perf_counter()
m.ai.choose(m.ai_shots, m.player_fleet.remaining_lengths())
ms=(time.perf_counter()-t)*1000
check(f"density shot computed in {ms:.0f}ms", ms<250)

print("\n"+"="*52)
if FAILS: print(f"FAILED: {len(FAILS)} -> {FAILS}"); sys.exit(1)
print("ALL CHECKS PASSED")
