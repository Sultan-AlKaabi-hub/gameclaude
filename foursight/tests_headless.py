"""Headless validation of the board and engine. Run: python tests_headless.py"""
import random, statistics, sys, time
from engine.board import Position, alignment, winning_cells, WIDTH, HEIGHT
from engine.match import Match, Session
from ai.search import Engine, build_engine, WIN_BASE

FAILS=[]
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {detail if not cond else ''}")
    if not cond: FAILS.append(name)

print("\n[1] Bitboard win detection")
p=Position()
for c in [0,1,0,1,0,1]: p.play(c)
check("no false win before four", not p.is_winning_move(2))
p2=Position()
for c in [3,0,3,0,3,0]: p2.play(c)
check("vertical four detected", p2.is_winning_move(3))
p3=Position()
for c in [0,0,1,1,2,2]: p3.play(c)
check("horizontal four detected", p3.is_winning_move(3))
# Sentinel row must stop a wrap-around false positive across columns.
p4=Position()
for c in [6,6,6,6,6,6]: p4.play(c)
check("column fills without wrapping", not p4.can_play(6))

print("\n[2] Legality and gravity")
p=Position()
for _ in range(HEIGHT): p.play(2)
check("column rejects overfill", not p.can_play(2))
check("other columns still open", len(p.legal_moves())==WIDTH-1)
p=Position(); p.play(4)
check("landing row rises", p.landing_row(4)==1)

print("\n[3] Engine finds a mate in one")
ok=True
for trial in range(30):
    p=Position(); rng=random.Random(trial)
    for _ in range(rng.randint(4,12)):
        moves=p.legal_moves()
        if not moves: break
        safe=[c for c in moves if not p.is_winning_move(c)]
        if not safe: break
        p.play(rng.choice(safe))
    wins=[c for c in p.legal_moves() if p.is_winning_move(c)]
    if not wins: continue
    r=build_engine("SHARP").analyse(p)
    if r.best_move not in wins: ok=False; break
check("always plays an available mate in one", ok)

print("\n[4] Engine blocks a mate in one")
ok=True; tested=0
for trial in range(200):
    p=Position(); rng=random.Random(trial+500)
    for _ in range(rng.randint(3,9)):
        moves=p.legal_moves()
        if not moves: break
        p.play(rng.choice(moves))
        if any(p.is_winning_move(c) for c in p.legal_moves()): break
    if any(p.is_winning_move(c) for c in p.legal_moves()): continue
    opp=Position(p.current ^ p.mask, p.mask, p.moves+1)
    threats=[c for c in opp.legal_moves() if opp.is_winning_move(c)]
    if len(threats)!=1: continue
    tested+=1
    r=build_engine("BRUTAL").analyse(p)
    if r.best_move!=threats[0]: ok=False; break
    if tested>=12: break
check(f"blocks the single threat ({tested} positions)", ok and tested>0)

print("\n[5] Alpha-beta prunes (deeper search is not exponentially slower)")
p=Position()
for c in [3,3,4,2]: p.play(c)
timings={}
for d in (4,6,8):
    e=Engine(depth=d, budget=30.0); t=time.perf_counter(); e.analyse(p)
    timings[d]=(e.nodes, time.perf_counter()-t)
n4,n8=timings[4][0], timings[8][0]
check(f"depth 8 explores {n8/max(n4,1):.0f}x depth 4's nodes, not 7^4=2401x", n8/max(n4,1) < 400)
check(f"depth 8 completes in {timings[8][1]:.2f}s", timings[8][1] < 6.0)
print(f"        nodes: d4={timings[4][0]:,}  d6={timings[6][0]:,}  d8={timings[8][0]:,}")

print("\n[6] Stronger settings beat weaker ones")
def duel(a,b,games=14):
    wins_a=0
    for g in range(games):
        p=Position(); ea,eb=build_engine(a),build_engine(b)
        turn = g%2  # alternate who starts
        while True:
            eng = ea if turn==0 else eb
            r=eng.analyse(p)
            if r.best_move<0: break
            won=p.is_winning_move(r.best_move); p.play(r.best_move)
            if won:
                if turn==0: wins_a+=1
                break
            if p.is_full(): break
            turn^=1
    return wins_a
w=duel("BRUTAL","CASUAL")
check(f"BRUTAL beats CASUAL {w}/14", w>=10)

print("\n[7] Match and session bookkeeping")
m=Match("SHARP", human_first=True)
m.play_human(3); check("human move registers", m.position.moves==1)
check("turn passes to engine", not m.human_to_move)
m.play_engine(); check("engine replies", m.position.moves==2)
check("turn returns to human", m.human_to_move)
s=Session("SHARP")
s.match.status="won"; pts=s.conclude_match()
check("win increments streak", s.streak==1 and pts>0)
check("run continues after a win", not s.over)
s.next_match(); check("sides alternate", s.match.human_first is False)
s.match.status="lost"; s.conclude_match()
check("run ends on a loss", s.over)

print("\n[8] Scoring behaves sensibly")
a=Match("BRUTAL"); a.status="won"
b=Match("CASUAL"); b.status="won"
check("harder difficulty pays more", a.score(1) > b.score(1))
check("streak increases payout", a.score(4) > a.score(1))
c=Match("SHARP"); c.status="lost"
d=Match("SHARP"); d.status="won"
check("winning beats losing", d.score(1) > c.score(1))

print("\n[9] Board rendering maps players correctly")
m=Match("CASUAL", human_first=True); m.play_human(0)
grid=m.board()
check("human disc appears at bottom-left", grid[HEIGHT-1][0]==1)
check("grid dimensions correct", len(grid)==HEIGHT and len(grid[0])==WIDTH)
m2=Match("CASUAL", human_first=False); m2.play_engine()
check("engine disc marked as engine", any(2 in row for row in m2.board()))

print("\n[10] Move latency stays interactive")
lat=[]
for diff in ["CASUAL","SHARP","BRUTAL"]:
    p=Position()
    for c in [3,3,2,4]: p.play(c)
    t=time.perf_counter(); build_engine(diff).analyse(p); lat.append((diff,time.perf_counter()-t))
for name,t in lat: print(f"        {name}: {t*1000:.0f}ms")
check("every difficulty responds within its budget", all(t<3.6 for _,t in lat))

print("\n"+"="*52)
if FAILS: print(f"FAILED: {len(FAILS)} -> {FAILS}"); sys.exit(1)
print("ALL CHECKS PASSED")
