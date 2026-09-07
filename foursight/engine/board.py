"""
Connect Four board, represented as bitboards.

A 7x6 board is stored in two 49-bit integers: one for the side to move, one
mask of every occupied square. Each column occupies 7 bits — 6 playable rows
plus one sentinel bit that is never filled, which is what makes the shift-based
win detection safe across column boundaries.

    bit index = column * 7 + row      (row 0 is the bottom)

    col:   0   1   2   3   4   5   6
          --  --  --  --  --  --  --
     r6    6  13  20  27  34  41  48   <- sentinel row, always empty
     r5    5  12  19  26  33  40  47
     r4    4  11  18  25  32  39  46
     r3    3  10  17  24  31  38  45
     r2    2   9  16  23  30  37  44
     r1    1   8  15  22  29  36  43
     r0    0   7  14  21  28  35  42

Why bother, when a 7x6 list of lists is easier to read? Because the search in
`ai/search.py` evaluates hundreds of thousands of positions per move and every
one of them needs a legality test, a move application, and a win check. With
bitboards each of those is a handful of integer operations rather than nested
loops, which is the difference between an engine that thinks eight moves ahead
inside a second and one that does not.

Python's arbitrary-precision integers handle 49-bit values natively, so this
needs no external dependency.
"""

from __future__ import annotations

WIDTH = 7
HEIGHT = 6
MIN_SCORE = -(WIDTH * HEIGHT) // 2 + 3
MAX_SCORE = (WIDTH * HEIGHT + 1) // 2 - 3

# Every playable square (the sentinel row excluded).
BOARD_MASK = 0
for _c in range(WIDTH):
    for _r in range(HEIGHT):
        BOARD_MASK |= 1 << (_c * (HEIGHT + 1) + _r)

# Search order: centre columns first. In Connect Four the centre column is
# part of far more winning lines than the edges, so trying it first produces
# early cutoffs and lets alpha-beta prune the rest of the tree aggressively.
MOVE_ORDER = [3, 2, 4, 1, 5, 0, 6]


def bottom_mask(col: int) -> int:
    return 1 << (col * (HEIGHT + 1))


def top_mask(col: int) -> int:
    return 1 << (HEIGHT - 1 + col * (HEIGHT + 1))


def column_mask(col: int) -> int:
    return ((1 << HEIGHT) - 1) << (col * (HEIGHT + 1))


class Position:
    """A Connect Four position from the perspective of the side to move."""

    __slots__ = ("current", "mask", "moves")

    def __init__(self, current: int = 0, mask: int = 0, moves: int = 0):
        self.current = current  # stones of the player to move
        self.mask = mask        # all occupied squares
        self.moves = moves

    def copy(self) -> "Position":
        return Position(self.current, self.mask, self.moves)

    # ------------------------------------------------------------- legality

    def can_play(self, col: int) -> bool:
        return (self.mask & top_mask(col)) == 0

    def legal_moves(self) -> list[int]:
        return [c for c in range(WIDTH) if self.can_play(c)]

    def is_full(self) -> bool:
        return self.moves >= WIDTH * HEIGHT

    # --------------------------------------------------------------- moving

    def play(self, col: int) -> None:
        """Drop a stone and hand the turn over.

        XOR against the mask flips the perspective: `current` always describes
        whoever is about to move, which is what lets the search use plain
        negamax with no colour bookkeeping.
        """
        self.current ^= self.mask
        self.mask |= self.mask + bottom_mask(col)
        self.moves += 1

    def is_winning_move(self, col: int) -> bool:
        """Would playing `col` complete a line for the side to move?"""
        pos = self.current | ((self.mask + bottom_mask(col)) & column_mask(col))
        return alignment(pos)

    def landing_row(self, col: int) -> int:
        """Row index a stone dropped in `col` would come to rest on."""
        occupied = self.mask & column_mask(col)
        row = 0
        while occupied & (1 << (col * (HEIGHT + 1) + row)):
            row += 1
        return row

    # ------------------------------------------------------------ rendering

    def cells(self) -> list[list[int]]:
        """Grid as [row][col], row 0 at the top for display.

        Returns 0 empty, 1 for the player who moved first, 2 for the second.
        """
        first_to_move = self.moves % 2 == 0
        me = self.current
        them = self.current ^ self.mask
        p1, p2 = (me, them) if first_to_move else (them, me)

        out = []
        for display_row in range(HEIGHT):
            row_bits = HEIGHT - 1 - display_row
            line = []
            for col in range(WIDTH):
                bit = 1 << (col * (HEIGHT + 1) + row_bits)
                line.append(1 if p1 & bit else (2 if p2 & bit else 0))
            out.append(line)
        return out

    def key(self) -> int:
        """Unique position key for the transposition table."""
        return self.current + self.mask + BOARD_MASK


def alignment(pos: int) -> bool:
    """True if `pos` contains four in a row, in any orientation.

    Each test folds the bitboard onto itself twice. Shifting by 1 walks
    vertically, by 7 horizontally, and by 6 and 8 along the two diagonals; the
    sentinel row guarantees a horizontal shift cannot wrap a column into its
    neighbour and invent a false line.
    """
    # vertical
    m = pos & (pos >> 1)
    if m & (m >> 2):
        return True
    # horizontal
    m = pos & (pos >> (HEIGHT + 1))
    if m & (m >> (2 * (HEIGHT + 1))):
        return True
    # diagonal /
    m = pos & (pos >> HEIGHT)
    if m & (m >> (2 * HEIGHT)):
        return True
    # diagonal \
    m = pos & (pos >> (HEIGHT + 2))
    if m & (m >> (2 * (HEIGHT + 2))):
        return True
    return False


def winning_cells(pos: int) -> list[int]:
    """Bit indices of one completed line, for highlighting the win."""
    for shift in (1, HEIGHT + 1, HEIGHT, HEIGHT + 2):
        m = pos & (pos >> shift)
        m &= m >> (2 * shift)
        if m:
            lowest = m & -m
            base = lowest.bit_length() - 1
            return [base + shift * i for i in range(4)]
    return []


def compute_threats(pos: int, mask: int) -> int:
    """Squares where `pos` would immediately complete four.

    Used both by the evaluation and to detect forced replies.
    """
    threats = 0
    for col in range(WIDTH):
        if mask & top_mask(col):
            continue
        landing = (mask + bottom_mask(col)) & column_mask(col)
        if alignment(pos | landing):
            threats |= landing
    return threats
