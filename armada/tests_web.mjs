// Headless validation of the browser engine in web/index.html.
// Run: node tests_web.mjs
// The engine block is extracted between the ENGINE-START / ENGINE-END markers
// and evaluated in Node, so the same code the browser runs is what is tested.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "web", "index.html"), "utf8");
const src = html.split("/*ENGINE-START*/")[1].split("/*ENGINE-END*/")[0];
const E = new Function(src + `
  return { SIZE, SHIP_TYPES, TOTAL_CELLS, UNKNOWN, MISS, HIT, SUNK, RNG, Fleet, ShotGrid, AI, Match, Duel, DIFFICULTIES, key };
`)();
const { SIZE, SHIP_TYPES, TOTAL_CELLS, UNKNOWN, MISS, HIT, SUNK, RNG, Fleet, ShotGrid, AI, Match, Duel, DIFFICULTIES, key } = E;

const fails = [];
function check(name, cond, detail = "") {
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${name} ${cond ? "" : detail}`);
  if (!cond) fails.push(name);
}

console.log("\n[1] Fleet placement");
{
  let ok = true, five = true;
  for (let s = 1; s <= 200; s++) {
    const f = new Fleet(); f.placeRandom(new RNG(s));
    const cells = f.ships.flatMap(sh => sh.cells);
    if (new Set(cells.map(([r, c]) => key(r, c))).size !== cells.length) ok = false;
    if (cells.length !== TOTAL_CELLS) ok = false;
    if (cells.some(([r, c]) => r < 0 || r >= SIZE || c < 0 || c >= SIZE)) ok = false;
    for (const sh of f.ships) {
      const rs = new Set(sh.cells.map(x => x[0])), cs = new Set(sh.cells.map(x => x[1]));
      if (!(rs.size === 1 || cs.size === 1)) ok = false;
    }
    if (f.ships.length !== 5) five = false;
  }
  check("200 fleets: no overlap, in bounds, straight, 17 cells", ok);
  check("every fleet has 5 ships", five);
}

console.log("\n[2] Shot resolution");
{
  const f = new Fleet(); f.placeRandom(new RNG(1));
  const sh = f.ships[0], g = new ShotGrid();
  let last;
  sh.cells.forEach(([r, c], i) => {
    last = f.receive(r, c); g.record(r, c, last.outcome, last.ship);
    if (i < sh.cells.length - 1) check(`partial damage ${i} reports hit`, last.outcome === "hit", last.outcome);
  });
  check("final hit reports sunk", last.outcome === "sunk" && last.ship === sh);
  check("sunk hull marked SUNK on the shot grid", sh.cells.every(([r, c]) => g.state[r][c] === SUNK));
  check("sunk ship leaves no unresolved hits", g.unresolvedHits().length === 0);
  let empty;
  for (let r = 0; r < SIZE && !empty; r++) for (let c = 0; c < SIZE; c++) if (f.grid[r][c] === -1) { empty = [r, c]; break; }
  check("empty water is a miss", f.receive(...empty).outcome === "miss");
}

console.log("\n[3] Density model respects evidence");
{
  const ai = new AI("ADMIRAL", new RNG(0));
  const g = new ShotGrid();
  const d = ai.densityMap(g, [5, 4, 3, 3, 2]).density;
  check("opening density peaks in the centre, not a corner", d[4][4] > d[0][0] && d[5][5] > d[0][9]);
  const g2 = new ShotGrid(); g2.state[0][0] = MISS;
  const d2 = ai.densityMap(g2, [5, 4, 3, 3, 2]).density;
  check("a known miss scores zero density", d2[0][0] === 0);
  check("a miss lowers its neighbours' density", d2[0][1] < d[0][1]);
  const g3 = new ShotGrid(); g3.state[4][4] = HIT;
  const d3 = ai.densityMap(g3, [5, 4, 3, 3, 2]).density;
  check("an unresolved hit concentrates density on its axes", Math.min(d3[4][3], d3[4][5], d3[3][4], d3[5][4]) > d3[7][7] * 3);
}

console.log("\n[4] Parity is applied only while hunting");
{
  const ai = new AI("ADMIRAL", new RNG(2));
  const g = new ShotGrid();
  let [r, c] = ai.choose(g, [5, 4, 3, 3, 2]);
  check("first shot lands on the parity lattice", (r + c) % 2 === 0, `${r},${c}`);
  check("hunt reason is reported", /lattice/i.test(ai.lastReason));
  g.state[4][4] = HIT;
  [r, c] = ai.choose(g, [5, 4, 3, 3, 2]);
  check("with a live hit it targets an adjacent square", Math.abs(r - 4) + Math.abs(c - 4) === 1, `${r},${c}`);
}

console.log("\n[5] AI never fires twice at the same square");
for (const diff of Object.keys(DIFFICULTIES)) {
  const m = new Match(diff, 7);
  let guard = 0;
  while (m.status === "playing" && guard < 200) {
    const opts = [];
    for (let r = 0; r < SIZE; r++) for (let c = 0; c < SIZE; c++) if (!m.playerShots.alreadyFired(r, c)) opts.push([r, c]);
    if (!opts.length) break;
    m.playerFire(...opts[guard % opts.length]);
    if (m.status === "playing") m.aiFire();
    guard++;
  }
  let distinct = 0;
  for (let r = 0; r < SIZE; r++) for (let c = 0; c < SIZE; c++) if (m.aiShots.state[r][c] !== UNKNOWN) distinct++;
  check(`${diff}: AI shot count matches distinct squares`, m.aiShots.shots === distinct, `${m.aiShots.shots} vs ${distinct}`);
}

console.log("\n[6] Skill ordering: shots the AI needs to win");
function shotsToClear(diff, trials = 40) {
  let total = 0;
  for (let s = 0; s < trials; s++) {
    const rng = new RNG(s + 1);
    const fleet = new Fleet(); fleet.placeRandom(rng);
    const grid = new ShotGrid(); const ai = new AI(diff, new RNG(s + 999));
    let n = 0;
    while (!fleet.allSunk() && n < 100) {
      let [r, c] = ai.choose(grid, fleet.remainingLengths());
      if (grid.alreadyFired(r, c)) throw new Error("duplicate fire");
      const o = fleet.receive(r, c); grid.record(r, c, o.outcome, o.ship); n++;
    }
    total += n;
  }
  return total / trials;
}
{
  const res = {};
  for (const d of Object.keys(DIFFICULTIES)) { res[d] = shotsToClear(d); console.log(`        ${d}: ${res[d].toFixed(1)} shots (perfect = 17)`); }
  check("ADMIRAL beats OFFICER", res.ADMIRAL < res.OFFICER);
  check("OFFICER beats CADET", res.OFFICER < res.CADET);
  check("ADMIRAL is genuinely strong (< 45 shots)", res.ADMIRAL < 45);
}

console.log("\n[7] Match completes and scores");
{
  const m = new Match("ADMIRAL", 3);
  let guard = 0;
  while (m.status === "playing" && guard < 200) {
    outer: for (let r = 0; r < SIZE; r++) for (let c = 0; c < SIZE; c++) if (!m.playerShots.alreadyFired(r, c)) { m.playerFire(r, c); break outer; }
    if (m.status === "playing") m.aiFire();
    guard++;
  }
  check("match reaches a result", m.status === "won" || m.status === "lost");
  check("score is non-negative", m.score() >= 0);
  check("breakdown is populated", m.breakdown().length >= 2);
  const w = new Match("ADMIRAL", 5);
  for (const sh of w.aiFleet.ships) for (const [r, c] of sh.cells) w.playerFire(r, c);
  check("a perfect game is a win with full fleet", w.status === "won" && w.playerShots.shots === 17);
  check("perfect ADMIRAL score is (1500 + 83*25 + 17*60) * 2", w.score() === (1500 + 83 * 25 + 17 * 60) * 2, String(w.score()));
}

console.log("\n[8] Fairness: the AI cannot see the fleet");
{
  const aiSrc = src.slice(src.indexOf("class AI"), src.indexOf("const WIN_POINTS"));
  check("AI class never touches a fleet or its grid", !/fleet|\.grid\b|shipAt/i.test(aiSrc));
  check("choose() only receives a shot grid and ship lengths", /choose\(grid, lengths\)/.test(aiSrc));
}

console.log("\n[9] Move latency");
{
  const m = new Match("ADMIRAL", 11);
  for (let i = 0; i < 12 && m.status === "playing"; i++) {
    outer: for (let r = 0; r < SIZE; r++) for (let c = 0; c < SIZE; c++) if (!m.playerShots.alreadyFired(r, c)) { m.playerFire(r, c); break outer; }
    if (m.status === "playing") m.aiFire();
  }
  const t = performance.now();
  m.ai.choose(m.aiShots, m.playerFleet.remainingLengths());
  const ms = performance.now() - t;
  check(`density shot computed in ${ms.toFixed(1)}ms`, ms < 50);
}

console.log("\n[10] Hot-seat duel");
{
  const d = new Duel(["Alice", "Bob"], 4);
  check("seat 0 moves first", d.canFire(0) && !d.canFire(1));
  check("out-of-turn fire rejected", d.fire(1, 0, 0) === null);
  check("in-turn fire accepted", d.fire(0, 0, 0) !== null);
  check("turn passes", d.canFire(1) && !d.canFire(0));
  d.fire(1, 5, 5);
  check("turn returns", d.canFire(0));
  d.fire(0, 0, 1);
  check("duplicate square rejected", d.fire(1, 5, 5) === null);
  const d2 = new Duel(["A", "B"], 8);
  const target = d2.fleets[1].ships[0].cells[0];
  d2.fire(0, ...target);
  check("shot resolves against the opponent's fleet", d2.fleets[1].ships[0].hits.size === 1 && d2.fleets[0].ships[0].hits.size === 0);
  check("victim's own shot grid untouched", d2.shots[1].shots === 0);
  const d3 = new Duel(["A", "B"], 12);
  for (const cell of d3.fleets[1].ships.flatMap(s => s.cells)) {
    if (d3.status !== "playing") break;
    if (!d3.canFire(0)) {
      outer: for (let r = 0; r < SIZE; r++) for (let c = 0; c < SIZE; c++) if (!d3.shots[1].alreadyFired(r, c)) { d3.fire(1, r, c); break outer; }
    }
    d3.fire(0, ...cell);
  }
  check("sinking every enemy ship wins", d3.status === "finished" && d3.winner === 0);
  check("no further fire after the game ends", d3.fire(1, 9, 9) === null);
}

console.log("\n[11] Manual ship placement");
{
  const f = new Fleet();
  check("starts empty, Carrier first", f.nextToPlace()[0] === "Carrier" && !f.isComplete());
  check("legal placement accepted", f.place("Carrier", 5, 0, 0, true));
  check("overlapping placement rejected", !f.place("Battleship", 4, 0, 0, true));
  check("off-board placement rejected", !f.canPlace(5, 0, 7, true));
  const v = f.validCells(5, true);
  check("validCells excludes overhang", v.has(key(0, 5)) && !v.has(key(0, 6)) && v.has(key(1, 5)) && !v.has(key(1, 6)));
  check("vertical orientation works", f.place("Battleship", 4, 2, 0, false));
  check("undo removes the last ship", f.removeLast() && f.ships.length === 1);
  for (const [name, length] of SHIP_TYPES.slice(1)) {
    let ok = false;
    for (let r = 0; r < SIZE && !ok; r++) for (let c = 0; c < SIZE; c++) if (f.place(name, length, r, c, true)) { ok = true; break; }
  }
  check("a full fleet can be placed by hand", f.isComplete() && f.nextToPlace() === null);
  const cells = f.ships.flatMap(s => s.cells);
  check("hand-placed fleet has no overlaps", new Set(cells.map(([r, c]) => key(r, c))).size === cells.length);
  f.clear();
  check("clear resets the board", f.ships.length === 0 && f.nextToPlace()[0] === "Carrier");
}

console.log("\n" + "=".repeat(52));
if (fails.length) { console.log(`FAILED: ${fails.length} -> ${fails.join(", ")}`); process.exit(1); }
console.log("ALL CHECKS PASSED");
