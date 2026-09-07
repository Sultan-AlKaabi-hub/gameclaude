"""
Rendering.

Two boards are drawn. Your own shows your ships and the AI's incoming fire,
with its probability density laid underneath — that overlay is the point of the
project, because it lets you watch the AI reason about squares it has never
touched. The enemy board shows only what you have discovered.
"""

from __future__ import annotations

from engine.fleet import COLUMN_LABELS, HIT, MISS, SIZE, SUNK, UNKNOWN
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
    TEAL_DEEP,
    belief_colour,
)

CELL = 34
GUTTER = 20


def _frame(width: int, height: int) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" style="width:100%;height:auto;display:block;">'
    )


def _labels(out: list) -> None:
    for c in range(SIZE):
        x = GUTTER + c * CELL + CELL / 2
        out.append(
            f'<text x="{x}" y="{GUTTER - 6}" text-anchor="middle" '
            f'font-family="IBM Plex Mono, monospace" font-size="10" '
            f'fill="{BONE_DIM}">{COLUMN_LABELS[c]}</text>'
        )
    for r in range(SIZE):
        y = GUTTER + r * CELL + CELL / 2 + 4
        out.append(
            f'<text x="{GUTTER - 7}" y="{y}" text-anchor="end" '
            f'font-family="IBM Plex Mono, monospace" font-size="10" '
            f'fill="{BONE_DIM}">{r + 1}</text>'
        )


def render_own_board(match, density: list | None = None) -> str:
    """Your fleet, the AI's shots, and optionally its density overlay."""
    w = GUTTER + SIZE * CELL + 6
    h = GUTTER + SIZE * CELL + 6
    grid = match.ai_shots
    fleet = match.player_fleet

    out = [_frame(w, h)]
    out.append(
        f'<rect x="{GUTTER}" y="{GUTTER}" width="{SIZE * CELL}" '
        f'height="{SIZE * CELL}" fill="{INK}" stroke="{GRID_RULE}"/>'
    )
    _labels(out)

    peak = 0.0
    if density:
        peak = max((v for row in density for v in row), default=0.0) or 1.0

    for r in range(SIZE):
        for c in range(SIZE):
            x = GUTTER + c * CELL
            y = GUTTER + r * CELL

            if density and grid.state[r][c] == UNKNOWN:
                t = (density[r][c] / peak) ** 0.6
                if t > 0.04:
                    out.append(
                        f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                        f'fill="{belief_colour(t)}" opacity="{0.18 + 0.66 * t:.2f}"/>'
                    )

            out.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                f'fill="none" stroke="{GRID_RULE}" stroke-width="0.5"/>'
            )

    # Ship hulls, drawn over the density so you can see what is being hunted.
    for ship in fleet.ships:
        for (r, c) in ship.cells:
            x = GUTTER + c * CELL
            y = GUTTER + r * CELL
            damaged = (r, c) in ship.hits
            fill = BRICK if ship.sunk else (AMBER if damaged else TEAL_DEEP)
            out.append(
                f'<rect x="{x + 3}" y="{y + 3}" width="{CELL - 6}" '
                f'height="{CELL - 6}" rx="3" fill="{fill}" '
                f'opacity="{0.95 if damaged or ship.sunk else 0.8}"/>'
            )

    # Incoming fire.
    for r in range(SIZE):
        for c in range(SIZE):
            cx = GUTTER + c * CELL + CELL / 2
            cy = GUTTER + r * CELL + CELL / 2
            state = grid.state[r][c]
            if state == MISS:
                out.append(
                    f'<circle cx="{cx}" cy="{cy}" r="3.5" fill="{BONE_DIM}" '
                    f'opacity="0.75"/>'
                )
            elif state in (HIT, SUNK):
                out.append(
                    f'<line x1="{cx - 7}" y1="{cy - 7}" x2="{cx + 7}" y2="{cy + 7}" '
                    f'stroke="{BONE}" stroke-width="2.2"/>'
                    f'<line x1="{cx + 7}" y1="{cy - 7}" x2="{cx - 7}" y2="{cy + 7}" '
                    f'stroke="{BONE}" stroke-width="2.2"/>'
                )

    if match.last_ai_shot:
        r, c = match.last_ai_shot
        out.append(
            f'<rect x="{GUTTER + c * CELL}" y="{GUTTER + r * CELL}" '
            f'width="{CELL}" height="{CELL}" fill="none" stroke="{SAND}" '
            f'stroke-width="2"/>'
        )

    out.append("</svg>")
    return "".join(out)


def render_enemy_board(match) -> str:
    """What you have learned about their fleet. Never reveals unhit ships."""
    w = GUTTER + SIZE * CELL + 6
    h = GUTTER + SIZE * CELL + 6
    grid = match.player_shots

    out = [_frame(w, h)]
    out.append(
        f'<rect x="{GUTTER}" y="{GUTTER}" width="{SIZE * CELL}" '
        f'height="{SIZE * CELL}" fill="{INK}" stroke="{GRID_RULE}"/>'
    )
    _labels(out)

    for r in range(SIZE):
        for c in range(SIZE):
            x = GUTTER + c * CELL
            y = GUTTER + r * CELL
            state = grid.state[r][c]
            cx, cy = x + CELL / 2, y + CELL / 2

            if state == SUNK:
                out.append(
                    f'<rect x="{x + 2}" y="{y + 2}" width="{CELL - 4}" '
                    f'height="{CELL - 4}" rx="3" fill="{BRICK}" opacity="0.9"/>'
                )
            elif state == HIT:
                out.append(
                    f'<rect x="{x + 2}" y="{y + 2}" width="{CELL - 4}" '
                    f'height="{CELL - 4}" rx="3" fill="{AMBER}" opacity="0.85"/>'
                )
            elif state == MISS:
                out.append(
                    f'<circle cx="{cx}" cy="{cy}" r="3.5" fill="{BONE_DIM}" '
                    f'opacity="0.6"/>'
                )

            out.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                f'fill="none" stroke="{GRID_RULE}" stroke-width="0.5"/>'
            )

    out.append("</svg>")
    return "".join(out)


def fleet_status(fleet, reveal: bool = True) -> str:
    """A row of ship pips: intact, damaged, or sunk."""
    parts = [
        '<div style="display:flex;flex-wrap:wrap;gap:0.5rem;'
        'font-family:IBM Plex Mono,monospace;font-size:0.7rem;margin-top:0.4rem;">'
    ]
    for ship in fleet.ships:
        if ship.sunk:
            colour, mark = BRICK, "SUNK"
        elif ship.hits and reveal:
            colour, mark = AMBER, f"{len(ship.hits)}/{ship.length}"
        else:
            colour, mark = TEAL, f"{ship.length}"
        parts.append(
            f'<span style="color:{colour};border:1px solid {colour};'
            f'border-radius:2px;padding:1px 5px;">{ship.name} {mark}</span>'
        )
    parts.append("</div>")
    return "".join(parts)


def enemy_fleet_status(match) -> str:
    """Only ships you have actually sunk are named."""
    sunk = set(match.player_shots.sunk_names)
    parts = [
        '<div style="display:flex;flex-wrap:wrap;gap:0.5rem;'
        'font-family:IBM Plex Mono,monospace;font-size:0.7rem;margin-top:0.4rem;">'
    ]
    for ship in match.ai_fleet.ships:
        if ship.name in sunk and ship.sunk:
            parts.append(
                f'<span style="color:{BRICK};border:1px solid {BRICK};'
                f'border-radius:2px;padding:1px 5px;">{ship.name} SUNK</span>'
            )
        else:
            parts.append(
                f'<span style="color:{BONE_DIM};border:1px solid {GRID_RULE};'
                f'border-radius:2px;padding:1px 5px;">{ship.name} ?</span>'
            )
    parts.append("</div>")
    return "".join(parts)
