"""
Match state and scoring.

A *game* is one board. A *run* is a streak of games that ends the moment you
lose, which is what gives the leaderboard something to rank: anyone can win
once on CASUAL, but stringing wins together on BRUTAL is a real result.

Nothing here imports Streamlit, so the whole thing is testable headlessly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.search import DIFFICULTIES, SearchResult, build_engine
from engine.board import Position, alignment, winning_cells

HUMAN = 1
ENGINE = 2

WIN_POINTS = 1000
DRAW_POINTS = 300
LOSS_POINTS = 50
EFFICIENCY_POINTS = 20  # per move saved against the 42-move maximum


@dataclass
class Match:
    """One board, played to a result."""

    difficulty: str
    human_first: bool = True
    position: Position = field(default_factory=Position)
    status: str = "playing"        # playing | won | lost | drawn
    move_log: list = field(default_factory=list)
    last_result: SearchResult | None = None
    winning_bits: list = field(default_factory=list)
    thinking_ms: float = 0.0

    def __post_init__(self) -> None:
        self.engine = build_engine(self.difficulty)

    # ------------------------------------------------------------- helpers

    @property
    def human_to_move(self) -> bool:
        """`position.moves` is even when the first player is to move."""
        first_to_move = self.position.moves % 2 == 0
        return first_to_move == self.human_first

    def legal(self) -> list[int]:
        return self.position.legal_moves()

    def board(self) -> list[list[int]]:
        """Display grid, mapped to HUMAN / ENGINE rather than first / second."""
        raw = self.position.cells()
        first, second = (HUMAN, ENGINE) if self.human_first else (ENGINE, HUMAN)
        return [[0 if v == 0 else (first if v == 1 else second) for v in row] for row in raw]

    # --------------------------------------------------------------- moves

    def play_human(self, col: int) -> bool:
        if self.status != "playing" or not self.human_to_move:
            return False
        if not self.position.can_play(col):
            return False
        self._apply(col, human=True)
        return True

    def play_engine(self) -> SearchResult | None:
        """Let the engine think and move. Returns its analysis for display."""
        if self.status != "playing" or self.human_to_move:
            return None
        result = self.engine.analyse(self.position)
        self.last_result = result
        self.thinking_ms = result.elapsed * 1000
        if result.best_move >= 0:
            self._apply(result.best_move, human=False)
        return result

    def _apply(self, col: int, human: bool) -> None:
        winning = self.position.is_winning_move(col)
        mover = self.position.current  # stones of the side about to move
        self.position.play(col)
        self.move_log.append(col)

        if winning:
            # After play(), the winner's stones are the *non*-current set.
            final = self.position.current ^ self.position.mask
            self.winning_bits = winning_cells(final)
            self.status = "won" if human else "lost"
        elif self.position.is_full():
            self.status = "drawn"

    # ------------------------------------------------------------- scoring

    def score(self, streak: int) -> int:
        """Points for this board, given the streak it was played on."""
        mult = DIFFICULTIES.get(self.difficulty, DIFFICULTIES["SHARP"])["multiplier"]
        streak_bonus = 1.0 + 0.15 * max(0, streak - 1)

        if self.status == "won":
            efficiency = max(0, 42 - self.position.moves) * EFFICIENCY_POINTS
            return int((WIN_POINTS + efficiency) * mult * streak_bonus)
        if self.status == "drawn":
            return int(DRAW_POINTS * mult * streak_bonus)
        if self.status == "lost":
            # Lasting a long time against a strong engine is worth something.
            return int(LOSS_POINTS * mult * (1 + self.position.moves / 42))
        return 0

    def breakdown(self, streak: int) -> list[tuple[str, str]]:
        mult = DIFFICULTIES.get(self.difficulty, DIFFICULTIES["SHARP"])["multiplier"]
        rows = []
        if self.status == "won":
            rows.append(("Victory", f"{WIN_POINTS:,}"))
            saved = max(0, 42 - self.position.moves)
            rows.append((f"Efficiency ({saved} moves spare)", f"{saved * EFFICIENCY_POINTS:,}"))
        elif self.status == "drawn":
            rows.append(("Draw", f"{DRAW_POINTS:,}"))
        else:
            rows.append(("Defeat", f"{LOSS_POINTS:,}"))
            rows.append(("Moves survived", f"×{1 + self.position.moves / 42:.2f}"))
        rows.append((f"{self.difficulty} difficulty", f"×{mult}"))
        if streak > 1:
            rows.append((f"Streak of {streak}", f"×{1 + 0.15 * (streak - 1):.2f}"))
        return rows


@dataclass
class Session:
    """A run: consecutive games, ending on the first loss."""

    difficulty: str
    streak: int = 0
    total_score: int = 0
    games_played: int = 0
    wins: int = 0
    draws: int = 0
    over: bool = False
    match: Match = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.match is None:
            self.match = Match(self.difficulty, human_first=True)

    def conclude_match(self) -> int:
        """Bank the finished board and update the streak. Returns points won."""
        m = self.match
        if m.status == "playing":
            return 0
        self.games_played += 1
        if m.status == "won":
            self.streak += 1
            self.wins += 1
        elif m.status == "drawn":
            self.draws += 1
        points = m.score(self.streak)
        self.total_score += points
        if m.status == "lost":
            self.over = True
        return points

    def next_match(self) -> None:
        """Alternate who starts, so neither side keeps the first-move edge."""
        self.match = Match(
            self.difficulty,
            human_first=not self.match.human_first,
        )
