"""
Visual identity.

The subject is probabilistic inference over space — hunters searching for
something they cannot see. The obvious treatment would be a green-on-black
hacker terminal, which is both a cliché and wrong for the content. This draws
instead on hydrographic survey and sonar plotting charts: deep ink paper, fine
survey rules, and the belief density rendered as a depth-sounding ramp.

That reference is doing real work. A sounding chart is literally a picture of
inference about something hidden beneath a surface, which is exactly what the
particle filter produces, so the density ramp reads as information rather than
decoration.

Accessibility: every entity carries a glyph as well as a colour, so state is
never encoded in colour alone (WCAG 2.2, 1.4.1 Use of Colour). Body and label
contrast against the ink background exceeds 4.5:1.
"""

INK = "#0C1A24"          # chart paper
INK_RAISED = "#122736"   # panels
GRID_RULE = "#1B3547"    # fine survey rules
WALL = "#24455C"         # structure
WALL_EDGE = "#2F5A76"

BONE = "#EDE4D0"         # primary text
BONE_DIM = "#93A8B6"     # secondary text
SAND = "#D9A566"         # the player and their objectives
AMBER = "#E8C87A"
TEAL = "#3E9B93"
TEAL_DEEP = "#1F5560"
BRICK = "#C2563D"        # hunters
BRICK_DIM = "#8E3F2E"

# Belief density ramp, shallow to deep certainty.
BELIEF_RAMP = [
    (0.00, "#16323F"),
    (0.25, "#1F5560"),
    (0.50, "#3E9B93"),
    (0.78, "#D9A566"),
    (1.00, "#F0D9A0"),
]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def belief_colour(t: float) -> str:
    """Interpolate the density ramp at t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    for i in range(len(BELIEF_RAMP) - 1):
        t0, c0 = BELIEF_RAMP[i]
        t1, c1 = BELIEF_RAMP[i + 1]
        if t0 <= t <= t1:
            span = (t1 - t0) or 1.0
            f = (t - t0) / span
            r0, g0, b0 = _hex_to_rgb(c0)
            r1, g1, b1 = _hex_to_rgb(c1)
            return "#%02x%02x%02x" % (
                int(r0 + (r1 - r0) * f),
                int(g0 + (g1 - g0) * f),
                int(b0 + (b1 - b0) * f),
            )
    return BELIEF_RAMP[-1][1]


def threat_colour(threat: float) -> str:
    if threat > 0.7:
        return BRICK
    if threat > 0.4:
        return SAND
    return TEAL


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

/* ------------------------------------------------------------------ *
 * These rules must work whether or not .streamlit/config.toml is
 * present. If it is missing, Streamlit serves its LIGHT theme, whose
 * default text colour is near-black -- unreadable on this background.
 * So text colour is forced on the elements Streamlit renders itself,
 * targeting tags (p, h1-h6, label) rather than div, so the custom
 * .bl-* markup below keeps its own inline accent colours.
 * ------------------------------------------------------------------ */

.stApp, [data-testid="stAppViewContainer"] {{
    background: {INK};
    background-image:
        radial-gradient(ellipse at 22% 8%, rgba(62,155,147,0.09), transparent 55%),
        radial-gradient(ellipse at 82% 92%, rgba(194,86,61,0.07), transparent 55%);
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
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ letter-spacing: -0.01em; }}

/* Text input: light-theme default is a white box. */
.stTextInput input, [data-testid="stTextInput"] input {{
    background: {INK_RAISED} !important;
    color: {BONE} !important;
    border: 1px solid {GRID_RULE} !important;
    font-family: 'IBM Plex Mono', monospace !important;
}}
.stTextInput input::placeholder {{ color: {BONE_DIM} !important; opacity: 0.75; }}
.stTextInput input:focus {{ border-color: {SAND} !important; }}
[data-baseweb="input"], [data-baseweb="base-input"] {{
    background: {INK_RAISED} !important; border-color: {GRID_RULE} !important;
}}

/* Checkbox accent: default is Streamlit red, which clashes badly. */
input[type="checkbox"], input[type="radio"] {{ accent-color: {SAND} !important; }}
[data-testid="stCheckbox"] svg {{ fill: {SAND}; }}
[data-baseweb="checkbox"] div[aria-checked="true"] {{
    background-color: {SAND} !important; border-color: {SAND} !important;
}}

[data-testid="stExpander"] {{
    background: {INK_RAISED}; border: 1px solid {GRID_RULE}; border-radius: 3px;
}}
[data-testid="stExpander"] summary {{ color: {BONE} !important; }}

[data-testid="stAlert"] {{
    background: {INK_RAISED} !important; border: 1px solid {TEAL};
    border-radius: 3px;
}}
[data-testid="stAlert"] p {{ color: {BONE} !important; }}

.bl-title {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2.6rem; font-weight: 600; letter-spacing: 0.34em;
    color: {BONE}; margin: 0 0 0.1rem 0; text-indent: 0.34em;
}}
.bl-sub {{ color: {BONE_DIM}; font-size: 0.92rem; margin: 0 0 1.1rem 0; }}
.bl-readout {{ font-family: 'IBM Plex Mono', monospace; }}

.bl-panel {{
    background: {INK_RAISED}; border: 1px solid {GRID_RULE};
    border-radius: 3px; padding: 0.85rem 1rem; margin-bottom: 0.7rem;
    color: {BONE};
}}

.bl-banner {{
    background: linear-gradient(100deg, {INK_RAISED} 0%, #1A3D3A 100%);
    border: 1px solid {TEAL}; border-left: 4px solid {SAND};
    border-radius: 3px; padding: 0.9rem 1.15rem; margin-bottom: 0.9rem;
}}
.bl-banner-role {{
    font-family: 'IBM Plex Mono', monospace;
    color: {SAND}; font-size: 0.7rem; letter-spacing: 0.22em;
}}
.bl-banner-name {{ font-size: 1.65rem; font-weight: 600; color: {BONE}; line-height: 1.15; }}
.bl-banner-meta {{
    font-family: 'IBM Plex Mono', monospace; color: {BONE_DIM}; font-size: 0.82rem;
}}

.bl-stat-label {{
    font-family: 'IBM Plex Mono', monospace;
    color: {BONE_DIM}; font-size: 0.68rem; letter-spacing: 0.16em;
}}
.bl-stat-value {{
    font-family: 'IBM Plex Mono', monospace;
    color: {BONE}; font-size: 1.3rem; font-weight: 600;
}}

.bl-meter {{ height: 7px; background: #0A1620; border-radius: 4px; overflow: hidden; margin-top: 4px; }}
.bl-meter-fill {{ height: 100%; border-radius: 4px; }}

.bl-log {{
    font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: {BONE_DIM};
    border-left: 2px solid {GRID_RULE}; padding-left: 0.7rem; margin: 0.16rem 0;
}}

.bl-row {{
    display: flex; justify-content: space-between; align-items: baseline;
    font-family: 'IBM Plex Mono', monospace;
    padding: 0.34rem 0.1rem; border-bottom: 1px solid {GRID_RULE}; font-size: 0.86rem;
}}
.bl-row-you {{ background: rgba(217,165,102,0.10); }}
.bl-rank {{ color: {BONE_DIM}; width: 2.4rem; }}
.bl-name {{ color: {BONE}; flex: 1; }}
.bl-score {{ color: {SAND}; font-weight: 600; }}

.stButton > button, [data-testid="stBaseButton-secondary"] {{
    background: {INK_RAISED} !important;
    color: {BONE} !important;
    border: 1px solid {GRID_RULE} !important;
    border-radius: 3px;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 500;
}}
.stButton > button:hover, [data-testid="stBaseButton-secondary"]:hover {{
    border-color: {SAND} !important; color: {AMBER} !important; background: #16303F !important;
}}
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"] {{
    background: {SAND} !important; color: {INK} !important; border-color: {SAND} !important;
    font-weight: 600;
}}
.stButton > button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{
    background: {AMBER} !important; color: {INK} !important;
}}
.stButton > button:focus-visible {{ outline: 2px solid {SAND}; outline-offset: 2px; }}
.stButton > button:disabled, .stButton > button:disabled p {{
    opacity: 0.5 !important; color: {BONE_DIM} !important;
}}

@media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; transition: none !important; }}
}}
</style>
"""
