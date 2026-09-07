"""
The opponent: a negamax search with alpha-beta pruning.

This is the canonical adversarial search algorithm. The engine explores the
game tree assuming both sides play their best, and alpha-beta pruning discards
subtrees that provably cannot affect the result, which is what makes searching
eight or more plies feasible in pure Python.

Layered on top of plain negamax:

* **Move ordering** — centre columns first (`MOVE_ORDER`), with the
  transposition table's previous best move tried ahead of everything. Good
  ordering is what alpha-beta lives on: with perfect ordering it examines
  roughly the square root of the nodes that plain minimax would.
* **Transposition table** — Connect Four transposes heavily (the same position
  arises from many move orders), so results are cached by position key with a
  depth and a bound flag.
* **Iterative deepening** — search depth 1, then 2, and so on. The shallower
  search seeds the table with good moves that make the deeper one faster, and
  it lets the engine stop on a time budget while always holding a usable move.

Everything the search learns is reported back in `SearchResult` rather than
discarded, because the point of this project is to make the AI's reasoning
visible: per-column valuations, the line it expects, how many positions it
looked at, and how many it skipped.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from engine.board import (
    HEIGHT,
    MOVE_ORDER,
    WIDTH,
    Position,
    column_mask,
    compute_threats,
)

WIN_BASE = 100_000
EXACT, LOWER, UPPER = 0, 1, 2

try:  # Python 3.10+
    _popcount = int.bit_count
except AttributeError:  # pragma: no cover
    def _popcount(x: int) -> int:  # type: ignore[misc]
        return bin(x).count("1")


DIFFICULTIES = {
    "CASUAL": {
        "depth": 2, "budget": 0.30, "multiplier": 0.5,
        "blurb": "Looks two moves ahead. It will miss things.",
    },
    "SHARP": {
        "depth": 5, "budget": 0.80, "multiplier": 1.0,
        "blurb": "Five plies. Punishes loose play.",
    },
    "BRUTAL": {
        "depth": 8, "budget": 1.60, "multiplier": 2.0,
        "blurb": "Eight plies. You will need a real plan.",
    },
    "ORACLE": {
        "depth": 13, "budget": 3.00, "multiplier": 3.5,
        "blurb": "Searches until the clock stops it. Near-perfect.",
    },
}
DEFAULT_DIFFICULTY = "SHARP"


@dataclass
class SearchResult:
    """Everything the engine worked out, including how it worked it out."""

    best_move: int
    column_scores: dict = field(default_factory=dict)
    nodes: int = 0
    cutoffs: int = 0
    tt_hits: int = 0
    depth_reached: int = 0
    elapsed: float = 0.0
    principal_variation: list = field(default_factory=list)
    verdict: str = ""

    @property
    def nodes_per_second(self) -> float:
        return self.nodes / self.elapsed if self.elapsed > 0 else 0.0


class Engine:
    """Alpha-beta Connect Four engine."""

    def __init__(self, depth: int = 5, budget: float = 1.0):
        self.max_depth = depth
        self.budget = budget
        self.table: dict[int, tuple] = {}
        self.nodes = 0
        self.cutoffs = 0
        self.tt_hits = 0
        self._deadline = 0.0

    # ---------------------------------------------------------- evaluation

    @staticmethod
    def _shape_counts(bits: int) -> tuple[int, int]:
        """Adjacent pairs and triples along all four orientations.

        Folding the bitboard onto itself by one step counts pairs; folding the
        result again counts triples. A cheap proxy for "how close is this side
        to a line" that costs eight integer ops rather than a window scan.
        """
        pairs = triples = 0
        for shift in (1, HEIGHT + 1, HEIGHT, HEIGHT + 2):
            m = bits & (bits >> shift)
            pairs += _popcount(m)
            triples += _popcount(m & (m >> shift))
        return pairs, triples

    def evaluate(self, pos: Position) -> int:
        """Heuristic value at the search horizon, side-to-move relative.

        Only consulted when the depth limit is reached; wins and losses are
        detected exactly, so this never decides a settled position.
        """
        me = pos.current
        them = pos.current ^ pos.mask

        my_threats = _popcount(compute_threats(me, pos.mask))
        their_threats = _popcount(compute_threats(them, pos.mask))

        my_pairs, my_triples = self._shape_counts(me)
        their_pairs, their_triples = self._shape_counts(them)

        centre = column_mask(WIDTH // 2)
        centre_edge = _popcount(me & centre) - _popcount(them & centre)

        # Opponent threats are weighted slightly higher than our own: in a game
        # decided by forced sequences, failing to see their threat loses faster
        # than missing one of ours.
        return (
            18 * my_threats
            - 22 * their_threats
            + 10 * (my_triples - their_triples)
            + 3 * (my_pairs - their_pairs)
            + 4 * centre_edge
        )

    # -------------------------------------------------------------- search

    def _negamax(self, pos: Position, depth: int, alpha: int, beta: int) -> int:
        self.nodes += 1

        # An immediate win is worth more the sooner it arrives, so the engine
        # finishes games instead of dawdling in a won position.
        for col in pos.legal_moves():
            if pos.is_winning_move(col):
                return WIN_BASE - pos.moves

        if pos.is_full():
            return 0
        if depth <= 0:
            return self.evaluate(pos)

        # Check the clock only occasionally; perf_counter is not free.
        if self.nodes % 2048 == 0 and time.perf_counter() > self._deadline:
            raise TimeoutError

        alpha_orig = alpha
        key = pos.key()
        tt_move = -1
        cached = self.table.get(key)
        if cached is not None:
            c_depth, c_flag, c_value, c_move = cached
            tt_move = c_move
            if c_depth >= depth:
                self.tt_hits += 1
                if c_flag == EXACT:
                    return c_value
                if c_flag == LOWER:
                    alpha = max(alpha, c_value)
                elif c_flag == UPPER:
                    beta = min(beta, c_value)
                if alpha >= beta:
                    return c_value

        order = ([tt_move] if tt_move >= 0 else []) + [
            c for c in MOVE_ORDER if c != tt_move
        ]

        best = -WIN_BASE * 2
        best_move = -1
        for col in order:
            if not pos.can_play(col):
                continue
            child = pos.copy()
            child.play(col)
            score = -self._negamax(child, depth - 1, -beta, -alpha)
            if score > best:
                best, best_move = score, col
            alpha = max(alpha, score)
            if alpha >= beta:
                self.cutoffs += 1
                break

        flag = EXACT
        if best <= alpha_orig:
            flag = UPPER
        elif best >= beta:
            flag = LOWER
        self.table[key] = (depth, flag, best, best_move)
        return best

    # ----------------------------------------------------------------- API

    def analyse(self, pos: Position) -> SearchResult:
        """Search the position and report both the move and the reasoning."""
        self.nodes = self.cutoffs = self.tt_hits = 0
        started = time.perf_counter()
        self._deadline = started + self.budget

        legal = pos.legal_moves()
        if not legal:
            return SearchResult(best_move=-1, verdict="The board is full.")

        # Immediate tactics are answered without a search, so the engine never
        # times out into a blunder on a one-move win or an unavoidable block.
        for col in legal:
            if pos.is_winning_move(col):
                return SearchResult(
                    best_move=col,
                    column_scores={col: WIN_BASE},
                    depth_reached=1,
                    elapsed=time.perf_counter() - started,
                    verdict="That is four. Good game.",
                )

        best_move = legal[0]
        scores: dict[int, int] = {}
        depth_reached = 0

        for depth in range(1, self.max_depth + 1):
            try:
                round_scores: dict[int, int] = {}
                alpha = -WIN_BASE * 2
                # Search the previous iteration's best move first.
                ordered = [best_move] + [c for c in MOVE_ORDER if c != best_move]
                for col in ordered:
                    if col not in legal:
                        continue
                    child = pos.copy()
                    child.play(col)
                    value = -self._negamax(child, depth - 1, -WIN_BASE * 2, -alpha)
                    round_scores[col] = value
                    if value > alpha:
                        alpha = value
                scores = round_scores
                best_move = max(round_scores, key=lambda c: round_scores[c])
                depth_reached = depth
            except TimeoutError:
                break  # keep the last completed iteration's result

        elapsed = time.perf_counter() - started
        return SearchResult(
            best_move=best_move,
            column_scores=scores,
            nodes=self.nodes,
            cutoffs=self.cutoffs,
            tt_hits=self.tt_hits,
            depth_reached=depth_reached,
            elapsed=elapsed,
            principal_variation=self._extract_pv(pos, best_move),
            verdict=self._verdict(scores.get(best_move, 0), pos),
        )

    def _extract_pv(self, pos: Position, first: int, length: int = 5) -> list[int]:
        """Follow transposition-table best moves to recover the expected line."""
        line = [first]
        cursor = pos.copy()
        cursor.play(first)
        for _ in range(length - 1):
            cached = self.table.get(cursor.key())
            if not cached or cached[3] < 0 or not cursor.can_play(cached[3]):
                break
            move = cached[3]
            line.append(move)
            cursor.play(move)
            if cursor.is_full():
                break
        return line

    @staticmethod
    def _verdict(score: int, pos: Position) -> str:
        """Plain-language read on the position, from the engine's side."""
        if score > WIN_BASE - 100:
            plies = WIN_BASE - score - pos.moves
            return f"Forced win found, {max(1, plies // 2)} moves out."
        if score < -WIN_BASE + 100:
            return "You have a forced win. Well played."
        if score > 60:
            return "Clearly better for me."
        if score > 15:
            return "Slight edge to me."
        if score < -60:
            return "You are clearly better here."
        if score < -15:
            return "Slight edge to you."
        return "Roughly balanced."


def build_engine(difficulty: str) -> Engine:
    cfg = DIFFICULTIES.get(difficulty, DIFFICULTIES[DEFAULT_DIFFICULTY])
    return Engine(depth=cfg["depth"], budget=cfg["budget"])
