"""
SVG rendering of the arena.

The belief density is the hero of this screen. Everything else is deliberately
quiet so that the one thing the player watches — the cloud of the hunters'
uncertainty moving and tightening — carries the drama on its own.

Output is a plain SVG string injected with `st.markdown(..., unsafe_allow_html=True)`.
No canvas, no JS, no custom component: it re-renders cleanly under Streamlit's
script-rerun model and scales to mobile through the viewBox.
"""

from __future__ import annotations

import html

from engine.grid import WALL
from ui.theme import (
    BONE_DIM,
    BRICK,
    GRID_RULE,
    INK,
    SAND,
    TEAL,
    WALL as WALL_COLOUR,
    WALL_EDGE,
    belief_colour,
)

CELL = 24
PAD = 6


def render_arena(gs, show_belief: bool = True, show_intent: bool = False) -> str:
    """Draw the current game state. `gs` is a GameState."""
    g = gs.grid
    w = g.width * CELL + PAD * 2
    h = g.height * CELL + PAD * 2
    out: list[str] = [
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="Arena map showing hunter belief density" '
        f'style="width:100%;height:auto;display:block;border:1px solid {GRID_RULE};'
        f'border-radius:3px;background:{INK};">'
    ]

    def px(r: int, c: int) -> tuple[float, float]:
        return PAD + c * CELL, PAD + r * CELL

    # --- belief density -------------------------------------------------
    if show_belief:
        belief = gs.pf.belief_grid()
        peak = float(belief.max()) or 1.0
        for r in range(g.height):
            for c in range(g.width):
                p = belief[r, c]
                if p <= 0:
                    continue
                # Normalise against the peak so the map stays legible whether
                # the belief is a tight spike or spread thin across the arena.
                t = (p / peak) ** 0.55
                if t < 0.06:
                    continue
                x, y = px(r, c)
                out.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                    f'fill="{belief_colour(t)}" opacity="{0.20 + 0.72 * t:.2f}"/>'
                )

    # --- survey rules ---------------------------------------------------
    for r in range(g.height + 1):
        y = PAD + r * CELL
        out.append(
            f'<line x1="{PAD}" y1="{y}" x2="{PAD + g.width * CELL}" y2="{y}" '
            f'stroke="{GRID_RULE}" stroke-width="0.5" opacity="0.5"/>'
        )
    for c in range(g.width + 1):
        x = PAD + c * CELL
        out.append(
            f'<line x1="{x}" y1="{PAD}" x2="{x}" y2="{PAD + g.height * CELL}" '
            f'stroke="{GRID_RULE}" stroke-width="0.5" opacity="0.5"/>'
        )

    # --- structure ------------------------------------------------------
    for r in range(g.height):
        for c in range(g.width):
            if g.cells[r, c] == WALL:
                x, y = px(r, c)
                out.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                    f'fill="{WALL_COLOUR}" stroke="{WALL_EDGE}" stroke-width="0.5"/>'
                )

    # --- extraction pad -------------------------------------------------
    ex, ey = px(*gs.extraction)
    open_now = not gs.nodes
    pad_colour = SAND if open_now else BONE_DIM
    # Built outside the f-string: a backslash inside an f-string expression is
    # a syntax error before Python 3.12, and Streamlit Cloud may run 3.11.
    pad_dash = "" if open_now else 'stroke-dasharray="3 3"'
    out.append(
        f'<rect x="{ex + 2}" y="{ey + 2}" width="{CELL - 4}" height="{CELL - 4}" '
        f'fill="none" stroke="{pad_colour}" stroke-width="1.6" {pad_dash} rx="2"/>'
        f'<text x="{ex + CELL / 2}" y="{ey + CELL / 2 + 4}" text-anchor="middle" '
        f'font-family="IBM Plex Mono, monospace" font-size="11" '
        f'fill="{pad_colour}">E</text>'
    )

    # --- data nodes -----------------------------------------------------
    for (r, c) in gs.nodes:
        x, y = px(r, c)
        cx, cy = x + CELL / 2, y + CELL / 2
        out.append(
            f'<rect x="{cx - 5}" y="{cy - 5}" width="10" height="10" '
            f'fill="{TEAL}" transform="rotate(45 {cx} {cy})"/>'
        )

    # --- decoy ----------------------------------------------------------
    if gs.decoy_turns > 0 and gs.decoy_cell:
        x, y = px(*gs.decoy_cell)
        cx, cy = x + CELL / 2, y + CELL / 2
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="8" fill="none" stroke="{SAND}" '
            f'stroke-width="1.3" stroke-dasharray="2 3" opacity="0.85"/>'
            f'<text x="{cx}" y="{cy + 3.5}" text-anchor="middle" '
            f'font-family="IBM Plex Mono, monospace" font-size="9" '
            f'fill="{SAND}" opacity="0.9">D</text>'
        )

    # --- hunters --------------------------------------------------------
    for hunter in gs.hunters:
        x, y = px(*hunter.pos)
        cx, cy = x + CELL / 2, y + CELL / 2
        if hunter.scanning:
            # A scanning hunter is stationary with a sharper sensor. Shown as a
            # ring so the player can read tempo at a glance and time a dash.
            out.append(
                f'<circle cx="{cx}" cy="{cy}" r="{CELL * 0.55}" fill="none" '
                f'stroke="{BRICK}" stroke-width="0.9" opacity="0.5" '
                f'stroke-dasharray="2 2"/>'
            )
        if show_intent and hunter.target:
            tx, ty = px(*hunter.target)
            out.append(
                f'<line x1="{cx}" y1="{cy}" x2="{tx + CELL / 2}" y2="{ty + CELL / 2}" '
                f'stroke="{BRICK}" stroke-width="0.7" opacity="0.4" '
                f'stroke-dasharray="3 4"/>'
            )
        out.append(
            f'<polygon points="{cx},{cy - 8} {cx + 7},{cy + 6} {cx - 7},{cy + 6}" '
            f'fill="{BRICK}"/>'
            f'<text x="{cx}" y="{cy + 4.5}" text-anchor="middle" '
            f'font-family="IBM Plex Mono, monospace" font-size="8" '
            f'font-weight="600" fill="{INK}">{html.escape(hunter.glyph)}</text>'
        )

    # --- player ---------------------------------------------------------
    x, y = px(*gs.player)
    cx, cy = x + CELL / 2, y + CELL / 2
    out.append(
        f'<circle cx="{cx}" cy="{cy}" r="8.5" fill="none" stroke="{SAND}" '
        f'stroke-width="1.2" opacity="0.55"/>'
        f'<circle cx="{cx}" cy="{cy}" r="4.2" fill="{SAND}"/>'
        f'<line x1="{cx - 11}" y1="{cy}" x2="{cx - 7}" y2="{cy}" '
        f'stroke="{SAND}" stroke-width="1.2"/>'
        f'<line x1="{cx + 7}" y1="{cy}" x2="{cx + 11}" y2="{cy}" '
        f'stroke="{SAND}" stroke-width="1.2"/>'
    )

    out.append("</svg>")
    return "".join(out)


def legend_html() -> str:
    """Static key. Every entity has a shape as well as a colour."""
    items = [
        (SAND, "circle", "You"),
        (BRICK, "triangle", "Hunter (letter = unit ID)"),
        (TEAL, "diamond", "Data node"),
        (SAND, "square", "Extraction pad (solid = open)"),
        ("#3E9B93", "heat", "Hunter belief density"),
    ]
    parts = [
        '<div style="display:flex;flex-wrap:wrap;gap:0.9rem;'
        'font-family:IBM Plex Mono, monospace;font-size:0.72rem;'
        f'color:{BONE_DIM};margin-top:0.45rem;">'
    ]
    for colour, shape, label in items:
        if shape == "heat":
            swatch = (
                '<span style="display:inline-block;width:26px;height:9px;'
                'background:linear-gradient(90deg,#16323F,#3E9B93,#D9A566,#F0D9A0);'
                'border-radius:1px;"></span>'
            )
        else:
            radius = {"circle": "50%", "diamond": "1px", "square": "1px", "triangle": "1px"}[shape]
            rotate = "transform:rotate(45deg);" if shape == "diamond" else ""
            fill = "transparent" if shape == "square" else colour
            border = f"1.4px solid {colour}"
            swatch = (
                f'<span style="display:inline-block;width:9px;height:9px;'
                f'background:{fill};border:{border};border-radius:{radius};{rotate}"></span>'
            )
        parts.append(
            f'<span style="display:inline-flex;align-items:center;gap:0.34rem;">'
            f"{swatch}{html.escape(label)}</span>"
        )
    parts.append("</div>")
    return "".join(parts)
