"""
Board widgets.

The enemy board and the placement board are built from real Streamlit buttons,
one per square, so the board *is* the control surface. Previously the board was
a picture with a separate grid of buttons underneath it, which meant looking at
one thing and clicking another.

Colour comes from the widget key. Streamlit attaches a `.st-key-<key>` class to
any keyed widget, so encoding the square's state in its key — `cellhit_3_4`,
`cellsea_0_0` — lets one CSS rule in `theme.py` paint every cell of a given
state. See `[class*="st-key-cellhit_"]` there.

Your own board is display-only, so it is drawn as a CSS grid of divs instead:
100 divs render far more cheaply than 100 widgets, and it can carry the AI's
heat map underneath the hulls.
"""

from __future__ import annotations

import streamlit as st

from engine.fleet import COLUMN_LABELS, HIT, MISS, SIZE, SUNK, UNKNOWN, label
from ui.theme import (
    BONE,
    BONE_DIM,
    DAMAGE,
    GRID_RULE,
    HULL,
    HULL_EDGE,
    INK,
    MISS_MARK,
    SAND,
    SUNK_RED,
    WATER_DIM,
    belief_colour,
)

# Glyphs as well as colour, so state never depends on hue alone (WCAG 1.4.1).
STATE_KEY = {UNKNOWN: "sea", MISS: "miss", HIT: "hit", SUNK: "sunk"}
STATE_GLYPH = {UNKNOWN: "·", MISS: "•", HIT: "✕", SUNK: "▪"}


def _axis_header() -> None:
    """Column letters, aligned to the grid below."""
    cols = st.columns([1] + [2] * SIZE)
    cols[0].markdown("&nbsp;", unsafe_allow_html=True)
    for i, letter in enumerate(COLUMN_LABELS):
        cols[i + 1].markdown(
            f'<div class="bl-axis">{letter}</div>', unsafe_allow_html=True
        )


def target_board(shots, key_prefix: str = "t", disabled: bool = False):
    """The enemy's waters as clickable cells. Returns (r, c) if one was hit."""
    clicked = None
    st.markdown('<div class="bl-board">', unsafe_allow_html=True)
    _axis_header()
    for r in range(SIZE):
        cols = st.columns([1] + [2] * SIZE)
        cols[0].markdown(
            f'<div class="bl-axis">{r + 1}</div>', unsafe_allow_html=True
        )
        for c in range(SIZE):
            state = shots.state[r][c]
            fired = state != UNKNOWN
            if cols[c + 1].button(
                STATE_GLYPH[state],
                key=f"cell{STATE_KEY[state]}_{key_prefix}_{r}_{c}",
                disabled=disabled or fired,
                help=None if fired else label(r, c),
            ):
                clicked = (r, c)
    st.markdown("</div>", unsafe_allow_html=True)
    return clicked


def placement_board(fleet, length: int, horizontal: bool, key_prefix: str = "p"):
    """Your waters during setup. Legal bow positions are lit; illegal are dead.

    Disabling the illegal squares means the board answers "can this go here?"
    before you click, rather than after.
    """
    valid = fleet.valid_cells(length, horizontal)
    occupied = {
        cell: fleet.ships[fleet.owner_grid[cell[0]][cell[1]]]
        for cell in (
            (r, c)
            for r in range(SIZE)
            for c in range(SIZE)
            if fleet.owner_grid[r][c] != -1
        )
    }

    clicked = None
    st.markdown('<div class="bl-board">', unsafe_allow_html=True)
    _axis_header()
    for r in range(SIZE):
        cols = st.columns([1] + [2] * SIZE)
        cols[0].markdown(f'<div class="bl-axis">{r + 1}</div>', unsafe_allow_html=True)
        for c in range(SIZE):
            if (r, c) in occupied:
                state, glyph, dead = "ship", occupied[(r, c)].name[0], True
            elif (r, c) in valid:
                state, glyph, dead = "ok", "·", False
            else:
                state, glyph, dead = "bad", "×", True
            if cols[c + 1].button(
                glyph,
                key=f"cell{state}_{key_prefix}_{r}_{c}",
                disabled=dead,
                help=None if dead else f"Place at {label(r, c)}",
            ):
                clicked = (r, c)
    st.markdown("</div>", unsafe_allow_html=True)
    return clicked


def own_board(fleet, incoming, density=None, last_shot=None) -> str:
    """Your waters, rendered as a CSS grid of divs. Display only.

    When `density` is supplied it is painted under the hulls, which is how the
    AI's belief about your fleet becomes visible.
    """
    peak = 0.0
    if density:
        peak = max((v for row in density for v in row), default=0.0) or 1.0

    ship_at = {}
    for ship in fleet.ships:
        for cell in ship.cells:
            ship_at[cell] = ship

    cells = []
    for r in range(SIZE):
        for c in range(SIZE):
            state = incoming.state[r][c]
            ship = ship_at.get((r, c))
            style = f"border:1px solid {GRID_RULE};"
            glyph = ""

            if density and state == UNKNOWN and not ship:
                t = (density[r][c] / peak) ** 0.6
                style += f"background:{belief_colour(t)};opacity:{0.25 + 0.7 * t:.2f};"
            elif not ship:
                style += f"background:{WATER_DIM};"

            if ship:
                if ship.sunk:
                    style += f"background:{SUNK_RED};color:#fff;"
                    glyph = "▪"
                elif (r, c) in ship.hits:
                    style += f"background:{DAMAGE};color:{INK};"
                    glyph = "✕"
                else:
                    style += f"background:{HULL};color:{INK};border-color:{HULL_EDGE};"
                    glyph = ship.name[0]
            elif state == MISS:
                style += f"color:{MISS_MARK};"
                glyph = "•"

            if last_shot == (r, c):
                style += f"box-shadow:inset 0 0 0 2px {SAND};"

            cells.append(
                f'<div style="{style}display:flex;align-items:center;'
                f"justify-content:center;aspect-ratio:1/1;border-radius:3px;"
                f'font-size:0.72rem;font-weight:600;">{glyph}</div>'
            )

    header = "".join(
        f'<div class="bl-axis">{l}</div>' for l in [""] + list(COLUMN_LABELS)
    )
    rows = []
    for r in range(SIZE):
        rows.append(f'<div class="bl-axis">{r + 1}</div>')
        rows.extend(cells[r * SIZE : (r + 1) * SIZE])

    return (
        f'<div style="display:grid;grid-template-columns:1.1rem repeat({SIZE},1fr);'
        f'gap:2px;align-items:center;">{header}{"".join(rows)}</div>'
    )


def fleet_pips(fleet, reveal: bool = True) -> str:
    """Ship status chips: intact, damaged, sunk."""
    parts = [
        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;'
        'font-family:IBM Plex Mono,monospace;font-size:0.68rem;margin-top:0.5rem;">'
    ]
    for ship in fleet.ships:
        if ship.sunk:
            colour, mark = SUNK_RED, "SUNK"
        elif ship.hits and reveal:
            colour, mark = DAMAGE, f"{len(ship.hits)}/{ship.length}"
        else:
            colour, mark = HULL, str(ship.length)
        parts.append(
            f'<span style="color:{colour};border:1px solid {colour};'
            f'border-radius:3px;padding:1px 6px;">{ship.name} {mark}</span>'
        )
    parts.append("</div>")
    return "".join(parts)


def enemy_pips(shots, ships) -> str:
    """Only ships you have actually sunk are revealed."""
    sunk = set(shots.sunk_names)
    parts = [
        '<div style="display:flex;flex-wrap:wrap;gap:0.4rem;'
        'font-family:IBM Plex Mono,monospace;font-size:0.68rem;margin-top:0.5rem;">'
    ]
    for ship in ships:
        if ship.name in sunk and ship.sunk:
            colour, mark = SUNK_RED, "SUNK"
        else:
            colour, mark = BONE_DIM, "?"
        parts.append(
            f'<span style="color:{colour};border:1px solid {colour};'
            f'border-radius:3px;padding:1px 6px;">{ship.name} {mark}</span>'
        )
    parts.append("</div>")
    return "".join(parts)
