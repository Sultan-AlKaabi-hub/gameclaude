"""
Visual identity.

The previous palette failed for a specific, diagnosable reason: ship hulls were
dark teal sitting on a dark navy sea, roughly one tonal step apart, so the board
read as a single muddy field and nothing separated. Contrast was doing no work.

This version gives every layer a distinct value:

    page      very dark, almost black-blue     the frame, recedes entirely
    water     clearly lighter than the page    reads as a surface, not a void
    hull      light warm steel                 a hull is a bright object on dark
                                               water, as it is in life
    damage    amber, then red                  saturated, unmistakable
    accent    warm amber                       actions and whose turn it is

Ships being *lighter* than the water is the key inversion, and light-on-dark is
easier to sustain over a long session than the near-isoluminant scheme it
replaces.

Cell buttons are coloured by encoding their state into the widget key.
Streamlit assigns a `.st-key-<key>` class to any keyed widget, so
`[class*="st-key-cellhit_"]` styles every hit cell at once. That is what lets
the board be built from real buttons instead of a picture with controls beneath.
"""

# --- core palette --------------------------------------------------------
INK = "#080F16"           # page
INK_RAISED = "#101E2A"    # panels
GRID_RULE = "#27455C"     # rules and borders

WATER = "#173447"         # an unknown square
WATER_HOVER = "#22506B"   # hover target
WATER_DIM = "#122A3A"     # your own untouched water

HULL = "#95A9B8"          # an intact ship of yours
HULL_EDGE = "#C2D2DD"
DAMAGE = "#F0A63C"        # a hit ship, still afloat
SUNK_RED = "#CE4437"      # a sunk ship
HIT_MARK = "#FF7A55"      # a hit on the enemy board
MISS_MARK = "#6E8798"     # a miss

BONE = "#E9F0F5"
BONE_DIM = "#93AABB"
SAND = "#F0A742"
AMBER = "#FFC46B"
TEAL = "#3FA9A0"
TEAL_DEEP = "#1D5E63"
BRICK = SUNK_RED
BRICK_DIM = "#8E3226"

VALID_CELL = "#2C6E56"
INVALID_CELL = "#2A1B22"

# --- belief heat ramp ----------------------------------------------------
# Sequential and monotonically brightening, so "more likely" always reads as
# "brighter" without needing the legend.
BELIEF_RAMP = [
    (0.00, "#12283A"),
    (0.30, "#1C5B75"),
    (0.55, "#2A98A0"),
    (0.78, "#E0A93F"),
    (1.00, "#FFE9A8"),
]


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def belief_colour(t: float) -> str:
    t = max(0.0, min(1.0, t))
    for i in range(len(BELIEF_RAMP) - 1):
        t0, c0 = BELIEF_RAMP[i]
        t1, c1 = BELIEF_RAMP[i + 1]
        if t0 <= t <= t1:
            f = (t - t0) / ((t1 - t0) or 1.0)
            r0, g0, b0 = _hex_to_rgb(c0)
            r1, g1, b1 = _hex_to_rgb(c1)
            return "#%02x%02x%02x" % (
                int(r0 + (r1 - r0) * f),
                int(g0 + (g1 - g0) * f),
                int(b0 + (b1 - b0) * f),
            )
    return BELIEF_RAMP[-1][1]


def threat_colour(t: float) -> str:
    if t > 0.7:
        return SUNK_RED
    if t > 0.4:
        return SAND
    return TEAL


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

/* Text colour is forced on elements Streamlit draws itself, because without
   .streamlit/config.toml the light theme's near-black text is invisible here.
   Tags are targeted rather than div, so custom markup keeps its own colours. */
.stApp, [data-testid="stAppViewContainer"] {{
    background: {INK};
    background-image:
        radial-gradient(ellipse at 20% 0%, rgba(63,169,160,0.10), transparent 58%),
        radial-gradient(ellipse at 85% 100%, rgba(240,167,66,0.07), transparent 58%);
}}
[data-testid="stHeader"], [data-testid="stToolbar"] {{ background: transparent; }}
html, body, .stApp {{ font-family: 'IBM Plex Sans', system-ui, sans-serif; }}

.stApp p, .stApp li, .stApp label, .stApp summary,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p,
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{
    color: {BONE} !important;
}}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
    color: {BONE_DIM} !important;
}}

.stTextInput input, [data-testid="stTextInput"] input {{
    background: {INK_RAISED} !important; color: {BONE} !important;
    border: 1px solid {GRID_RULE} !important;
    font-family: 'IBM Plex Mono', monospace !important;
}}
.stTextInput input::placeholder {{ color: {BONE_DIM} !important; opacity: 0.75; }}
.stTextInput input:focus {{ border-color: {SAND} !important; }}
[data-baseweb="input"], [data-baseweb="base-input"] {{
    background: {INK_RAISED} !important; border-color: {GRID_RULE} !important;
}}
input[type="checkbox"], input[type="radio"] {{ accent-color: {SAND} !important; }}
[data-baseweb="checkbox"] div[aria-checked="true"] {{
    background-color: {SAND} !important; border-color: {SAND} !important;
}}

[data-testid="stExpander"] {{
    background: {INK_RAISED}; border: 1px solid {GRID_RULE}; border-radius: 4px;
}}
[data-testid="stExpander"] summary {{ color: {BONE} !important; }}
[data-testid="stAlert"] {{
    background: {INK_RAISED} !important; border: 1px solid {GRID_RULE};
    border-radius: 4px;
}}
[data-testid="stAlert"] p {{ color: {BONE} !important; }}

/* ---------------- board cells ---------------- */
.bl-board [data-testid="column"] {{ padding: 0 1px !important; min-width: 0 !important; }}
.bl-board [data-testid="stHorizontalBlock"] {{ gap: 0 !important; margin-bottom: 2px; }}

[class*="st-key-cell"] button {{
    width: 100% !important;
    aspect-ratio: 1 / 1;
    min-height: 0 !important;
    height: auto !important;
    padding: 0 !important;
    border-radius: 3px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    line-height: 1 !important;
    border: 1px solid {GRID_RULE} !important;
    transition: none !important;
}}
[class*="st-key-cellsea_"] button {{
    background: {WATER} !important; color: rgba(0,0,0,0) !important;
}}
[class*="st-key-cellsea_"] button:hover {{
    background: {WATER_HOVER} !important; border-color: {SAND} !important;
}}
[class*="st-key-cellmiss_"] button {{
    background: {WATER_DIM} !important; color: {MISS_MARK} !important; opacity: 1 !important;
}}
[class*="st-key-cellhit_"] button {{
    background: {HIT_MARK} !important; color: {INK} !important;
    border-color: {HIT_MARK} !important; opacity: 1 !important;
}}
[class*="st-key-cellsunk_"] button {{
    background: {SUNK_RED} !important; color: #FFFFFF !important;
    border-color: {SUNK_RED} !important; opacity: 1 !important;
}}
[class*="st-key-cellship_"] button {{
    background: {HULL} !important; color: {INK} !important;
    border-color: {HULL_EDGE} !important; opacity: 1 !important;
}}
[class*="st-key-cellok_"] button {{
    background: {VALID_CELL} !important; color: rgba(0,0,0,0) !important;
}}
[class*="st-key-cellok_"] button:hover {{
    background: #3E9B78 !important; border-color: {AMBER} !important;
}}
[class*="st-key-cellbad_"] button {{
    background: {INVALID_CELL} !important; color: {BRICK_DIM} !important; opacity: 1 !important;
}}
[class*="st-key-cell"] button:focus-visible {{
    outline: 2px solid {SAND} !important; outline-offset: 1px;
}}

.bl-axis {{
    font-family: 'IBM Plex Mono', monospace; font-size: 0.66rem;
    color: {BONE_DIM}; text-align: center; line-height: 1.9;
}}

/* ---------------- panels and type ---------------- */
.bl-title {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2.5rem; font-weight: 600; letter-spacing: 0.3em;
    color: {BONE}; margin: 0 0 0.1rem 0; text-indent: 0.3em;
}}
.bl-sub {{ color: {BONE_DIM}; font-size: 0.92rem; margin: 0 0 1.1rem 0; }}
.bl-readout {{ font-family: 'IBM Plex Mono', monospace; }}
.bl-panel {{
    background: {INK_RAISED}; border: 1px solid {GRID_RULE};
    border-radius: 4px; padding: 0.85rem 1rem; margin-bottom: 0.7rem; color: {BONE};
}}
.bl-banner {{
    background: linear-gradient(100deg, {INK_RAISED} 0%, #17423F 100%);
    border: 1px solid {TEAL}; border-left: 4px solid {SAND};
    border-radius: 4px; padding: 0.9rem 1.15rem; margin-bottom: 0.9rem;
}}
.bl-banner-role {{
    font-family: 'IBM Plex Mono', monospace; color: {SAND};
    font-size: 0.7rem; letter-spacing: 0.22em;
}}
.bl-banner-name {{ font-size: 1.65rem; font-weight: 600; color: {BONE}; line-height: 1.15; }}
.bl-banner-meta {{
    font-family: 'IBM Plex Mono', monospace; color: {BONE_DIM}; font-size: 0.82rem;
}}
.bl-stat-label {{
    font-family: 'IBM Plex Mono', monospace; color: {BONE_DIM};
    font-size: 0.68rem; letter-spacing: 0.16em;
}}
.bl-stat-value {{
    font-family: 'IBM Plex Mono', monospace; color: {BONE};
    font-size: 1.3rem; font-weight: 600;
}}
.bl-meter {{ height: 7px; background: #07131C; border-radius: 4px; overflow: hidden; margin-top: 4px; }}
.bl-meter-fill {{ height: 100%; border-radius: 4px; }}
.bl-log {{
    font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: {BONE_DIM};
    border-left: 2px solid {GRID_RULE}; padding-left: 0.7rem; margin: 0.16rem 0;
}}
.bl-row {{
    display: flex; justify-content: space-between; align-items: baseline;
    font-family: 'IBM Plex Mono', monospace; padding: 0.34rem 0.1rem;
    border-bottom: 1px solid {GRID_RULE}; font-size: 0.86rem;
}}
.bl-row-you {{ background: rgba(240,167,66,0.12); }}
.bl-rank {{ color: {BONE_DIM}; width: 2.4rem; }}
.bl-name {{ color: {BONE}; flex: 1; }}
.bl-score {{ color: {SAND}; font-weight: 600; }}

/* ---------------- ordinary buttons ---------------- */
.stButton > button, [data-testid="stBaseButton-secondary"] {{
    background: {INK_RAISED} !important; color: {BONE} !important;
    border: 1px solid {GRID_RULE} !important; border-radius: 4px;
    font-family: 'IBM Plex Mono', monospace; font-weight: 500;
}}
.stButton > button:hover, [data-testid="stBaseButton-secondary"]:hover {{
    border-color: {SAND} !important; color: {AMBER} !important; background: #16303F !important;
}}
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"] {{
    background: {SAND} !important; color: {INK} !important;
    border-color: {SAND} !important; font-weight: 600;
}}
.stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{
    background: {AMBER} !important; color: {INK} !important;
}}
.stButton > button:focus-visible {{ outline: 2px solid {SAND}; outline-offset: 2px; }}
.stButton > button:disabled, .stButton > button:disabled p {{ opacity: 0.45 !important; }}

@media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; transition: none !important; }}
}}
</style>
"""
