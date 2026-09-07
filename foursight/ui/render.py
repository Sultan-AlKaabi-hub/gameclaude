"""
Rendering: the board, and the engine's reasoning.

The reasoning panel is the point of the project. A Connect Four AI that simply
plays a good move is invisible; the same AI with its per-column valuations,
expected line, and search statistics on screen is legible. Everything drawn
here comes straight out of `SearchResult` — nothing is dramatised or faked.
"""

from __future__ import annotations

from engine.board import HEIGHT, WIDTH
from ui.theme import (
    AMBER,
    BONE,
    BONE_DIM,
    BRICK,
    GRID_RULE,
    INK,
    INK_RAISED,
    SAND,
    TEAL,
)

CELL = 62
PAD = 10
RADIUS = 24

HUMAN, ENGINE = 1, 2


def render_board(match, highlight: list[int] | None = None) -> str:
    """Draw the grid. `highlight` holds bit indices of a winning line."""
    grid = match.board()
    w = WIDTH * CELL + PAD * 2
    h = HEIGHT * CELL + PAD * 2
    win_cells = set()
    for bit in (highlight or []):
        col = bit // (HEIGHT + 1)
        row_bits = bit % (HEIGHT + 1)
        win_cells.add((HEIGHT - 1 - row_bits, col))

    out = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="Connect Four board" '
        f'style="width:100%;height:auto;display:block;">'
        f'<rect x="0" y="0" width="{w}" height="{h}" rx="6" '
        f'fill="{INK_RAISED}" stroke="{GRID_RULE}"/>'
    ]

    for r in range(HEIGHT):
        for c in range(WIDTH):
            cx = PAD + c * CELL + CELL / 2
            cy = PAD + r * CELL + CELL / 2
            value = grid[r][c]

            if value == 0:
                out.append(
                    f'<circle cx="{cx}" cy="{cy}" r="{RADIUS}" fill="{INK}" '
                    f'stroke="{GRID_RULE}" stroke-width="1"/>'
                )
                continue

            fill = SAND if value == HUMAN else BRICK
            won = (r, c) in win_cells
            out.append(
                f'<circle cx="{cx}" cy="{cy}" r="{RADIUS}" fill="{fill}" '
                f'stroke="{AMBER if won else INK}" '
                f'stroke-width="{3 if won else 1.5}"/>'
            )
            # A glyph as well as a colour, so the board is readable without
            # relying on hue (WCAG 2.2, 1.4.1).
            out.append(
                f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" '
                f'font-family="IBM Plex Mono, monospace" font-size="15" '
                f'font-weight="600" fill="{INK}">'
                f'{"YOU"[0] if value == HUMAN else "AI"[0]}</text>'
            )

    out.append("</svg>")
    return "".join(out)


def render_evaluation(result, legal: list[int]) -> str:
    """Per-column valuations as bars: what the engine thinks of each option.

    Scores are the engine's own, in its favour, so a tall bar means a column is
    good *for the AI*. They are rescaled to the range actually present rather
    than an absolute scale, because the interesting information is the relative
    ranking of the options.
    """
    if not result or not result.column_scores:
        return ""

    scores = result.column_scores
    values = list(scores.values())
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1

    rows = [
        '<div style="display:flex;gap:5px;align-items:flex-end;height:74px;'
        'margin-top:0.3rem;">'
    ]
    for col in range(WIDTH):
        if col not in scores:
            rows.append(
                f'<div style="flex:1;text-align:center;">'
                f'<div style="height:60px;background:{INK};border-radius:2px;'
                f'opacity:0.3;"></div>'
                f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.6rem;'
                f'color:{BONE_DIM};">—</div></div>'
            )
            continue
        norm = (scores[col] - lo) / span
        height = 8 + norm * 52
        best = col == result.best_move
        colour = SAND if best else TEAL
        rows.append(
            f'<div style="flex:1;text-align:center;">'
            f'<div style="height:60px;display:flex;align-items:flex-end;">'
            f'<div style="width:100%;height:{height:.0f}px;background:{colour};'
            f'border-radius:2px;opacity:{1.0 if best else 0.55};"></div></div>'
            f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.6rem;'
            f'color:{SAND if best else BONE_DIM};">{col + 1}</div></div>'
        )
    rows.append("</div>")
    return "".join(rows)


def render_search_stats(result) -> str:
    """Search telemetry: depth, nodes, pruning, speed."""
    if not result:
        return ""
    brute = 7 ** max(result.depth_reached, 1)
    saved = max(0.0, 1 - result.nodes / brute) * 100 if brute else 0
    return (
        f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.72rem;'
        f'color:{BONE_DIM};line-height:1.65;">'
        f'searched <span style="color:{BONE};">{result.depth_reached}</span> moves ahead'
        f'<br>examined <span style="color:{BONE};">{result.nodes:,}</span> positions '
        f'in <span style="color:{BONE};">{result.elapsed * 1000:.0f}ms</span>'
        f'<br>pruning skipped <span style="color:{TEAL};">{saved:.1f}%</span> '
        f'of the tree'
        f'<br><span style="color:{BONE};">{result.cutoffs:,}</span> cutoffs · '
        f'<span style="color:{BONE};">{result.tt_hits:,}</span> cache hits'
        f"</div>"
    )


def render_line(result) -> str:
    """The sequence the engine expects, in human column numbers."""
    if not result or len(result.principal_variation) < 2:
        return ""
    moves = " → ".join(str(c + 1) for c in result.principal_variation)
    return (
        f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.74rem;'
        f'color:{BONE_DIM};margin-top:0.45rem;">'
        f'expects: <span style="color:{AMBER};">{moves}</span></div>'
    )
