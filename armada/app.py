"""
ARMADA — Battleship against a probability-density AI.

Streamlit re-runs this file on every interaction. Game logic lives in engine/
and ai/, neither of which imports Streamlit.

Two targeting modes are offered because Streamlit's columns can collapse into
a vertical stack on narrow viewports, which would turn a 10x10 button grid into
an unusable 100-item list. The coordinate picker needs three taps and works at
any width.
"""

from __future__ import annotations

import random

import streamlit as st

from ai.density import DEFAULT_DIFFICULTY, DIFFICULTIES
from engine.fleet import COLUMN_LABELS, HIT, MISS, SIZE, SUNK, UNKNOWN, label
from engine.match import Match
from services import narrator
from services.leaderboard import (
    champion,
    get_store,
    make_entry,
    personal_best,
    rank_of,
    top_entries,
)
from ui.render import (
    enemy_fleet_status,
    fleet_status,
    render_enemy_board,
    render_own_board,
)
from ui.theme import AMBER, BONE_DIM, BRICK, CSS, SAND, TEAL

st.set_page_config(page_title="ARMADA", page_icon="◆", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

# Slightly tighter buttons so a 10-wide grid stays on one line for longer.
st.markdown(
    """
<style>
div[data-testid="column"] { min-width: 0 !important; }
div[data-testid="column"] .stButton > button {
    padding: 0.16rem 0 !important;
    font-size: 0.78rem !important;
    min-height: 2.05rem;
}
</style>
""",
    unsafe_allow_html=True,
)

DEFAULTS = {
    "screen": "menu",
    "match": None,
    "username": "",
    "difficulty": DEFAULT_DIFFICULTY,
    "show_density": True,
    "input_mode": "Tap the grid",
    "pick_col": "A",
    "pick_row": 1,
    "commentary": "",
    "submitted": False,
    "last_rank": None,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


@st.cache_data(ttl=45, show_spinner=False)
def load_entries() -> list:
    return get_store().load()


def stat(lbl: str, value: str) -> str:
    return (
        f'<div class="bl-stat-label">{lbl}</div>'
        f'<div class="bl-stat-value">{value}</div>'
    )


def esc(t) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------- menu


def screen_menu() -> None:
    st.markdown('<div class="bl-title">ARMADA</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="bl-sub">Battleship against an opponent that never sees '
        "your ships. It counts every fleet layout still consistent with the "
        "shots it has taken and fires where the most of them overlap. You can "
        "watch it think, on your own board.</div>",
        unsafe_allow_html=True,
    )

    entries = load_entries()
    best = champion(entries)
    if best:
        st.markdown(
            f'<div class="bl-banner"><div class="bl-banner-role">FLEET COMMAND '
            f"RECORD</div>"
            f'<div class="bl-banner-name">{esc(best["username"])}</div>'
            f'<div class="bl-banner-meta">{best["score"]:,} pts &nbsp;·&nbsp; '
            f'{best.get("difficulty", "—")}</div></div>',
            unsafe_allow_html=True,
        )

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.session_state["username"] = st.text_input(
            "Callsign",
            value=st.session_state["username"],
            max_chars=18,
            placeholder="Name for the leaderboard",
        )

        st.markdown(
            '<div class="bl-stat-label" style="margin:0.6rem 0 0.35rem 0;">'
            "OPPONENT</div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(len(DIFFICULTIES))
        for i, name in enumerate(DIFFICULTIES):
            if cols[i].button(
                name,
                key=f"d_{name}",
                use_container_width=True,
                type="primary" if st.session_state["difficulty"] == name else "secondary",
            ):
                st.session_state["difficulty"] = name
                st.rerun()
        cfg = DIFFICULTIES[st.session_state["difficulty"]]
        st.caption(f"{cfg['blurb']}  Score multiplier ×{cfg['multiplier']}")

        st.session_state["input_mode"] = st.radio(
            "Targeting",
            ["Tap the grid", "Coordinate picker"],
            index=0 if st.session_state["input_mode"] == "Tap the grid" else 1,
            horizontal=True,
            help="Use the coordinate picker on a phone if the grid stacks.",
        )

        ready = bool(st.session_state["username"].strip())
        if st.button("DEPLOY FLEET", type="primary", use_container_width=True, disabled=not ready):
            st.session_state["match"] = Match(
                st.session_state["difficulty"], seed=random.randint(1, 999_999)
            )
            st.session_state["screen"] = "game"
            st.session_state["commentary"] = ""
            st.session_state["submitted"] = False
            st.rerun()
        if not ready:
            st.caption("A callsign is required so runs can be attributed.")

        with st.expander("How the AI works"):
            st.markdown(
                """
The AI is handed two things each turn: the grid of shots it has already fired,
and the lengths of your ships still afloat. Nothing else. It cannot see your
board — there is no difficulty setting that leaks it.

From that it rebuilds the position:

1. **Enumerate every legal placement** of every surviving ship — both
   orientations, every square.
2. **Discard the impossible ones**: anything covering a known miss, or
   overlapping a hull it has already sunk.
3. **Count** how many surviving placements cover each unknown square, then fire
   at the maximum.

That count is a posterior over ship positions given a uniform prior across
consistent layouts. The heat map on your board is not decoration — the colour
of a square is literally how many ways a ship could still be sitting on it.

**Hunting and targeting are not separate code.** Placements that explain an
unaccounted-for hit carry far more weight, so the instant you take damage the
distribution collapses along the two axes through that square.

**Parity**: a ship of length L must touch every L-spaced lattice, so while your
smallest survivor is length 2 there is no reason to fire off the checkerboard.
That halves the search space for free — but it is switched off the moment a hit
goes unresolved, because then every square matters.
                """
            )

    with right:
        st.markdown("#### Leaderboard")
        rows = top_entries(entries, 10)
        if not rows:
            st.caption("Nothing recorded yet.")
        else:
            me = st.session_state["username"].strip().lower()
            st.markdown(
                "".join(
                    f'<div class="bl-row {"bl-row-you" if e.get("username","").lower()==me and me else ""}">'
                    f'<span class="bl-rank">{i:02d}</span>'
                    f'<span class="bl-name">{esc(e["username"])}</span>'
                    f'<span style="color:{BONE_DIM};font-size:0.72rem;'
                    f'margin-right:0.55rem;">{e.get("difficulty","")[:3]}</span>'
                    f'<span class="bl-score">{e["score"]:,}</span></div>'
                    for i, e in enumerate(rows, 1)
                ),
                unsafe_allow_html=True,
            )
        pb = personal_best(entries, st.session_state["username"])
        if pb:
            st.markdown(
                f'<div class="bl-panel"><span class="bl-stat-label">YOUR BEST</span>'
                f'<div class="bl-stat-value" style="color:{SAND};">'
                f'{pb["score"]:,}</div></div>',
                unsafe_allow_html=True,
            )
        if not get_store().durable:
            st.caption(
                "Scores are on local storage and reset when the app restarts. "
                "Add GIST_ID and GITHUB_TOKEN in app settings to make them shared."
            )


# ---------------------------------------------------------------------- game

CELL_GLYPH = {UNKNOWN: "·", MISS: "○", HIT: "✕", SUNK: "▪"}


def screen_game() -> None:
    match: Match = st.session_state["match"]

    head = st.columns(4)
    head[0].markdown(stat("YOUR SHOTS", str(match.player_shots.shots)), unsafe_allow_html=True)
    head[1].markdown(
        stat("ACCURACY", f"{match.player_accuracy() * 100:.0f}%"), unsafe_allow_html=True
    )
    head[2].markdown(stat("THEIR SHIPS", str(match.enemy_ships_left())), unsafe_allow_html=True)
    head[3].markdown(stat("YOUR SHIPS", str(match.own_ships_left())), unsafe_allow_html=True)

    enemy, mine = st.columns(2, gap="large")

    # --- their waters: where you fire ------------------------------------
    with enemy:
        st.markdown("#### Enemy waters")
        st.markdown(render_enemy_board(match), unsafe_allow_html=True)
        st.markdown(enemy_fleet_status(match), unsafe_allow_html=True)

        if match.status == "playing":
            if st.session_state["input_mode"] == "Tap the grid":
                _tap_grid(match)
            else:
                _coordinate_picker(match)

    # --- your waters: where you watch it think ---------------------------
    with mine:
        st.markdown("#### Your waters")
        density = (
            match.ai.last_density if st.session_state["show_density"] else None
        )
        st.markdown(render_own_board(match, density), unsafe_allow_html=True)
        st.markdown(fleet_status(match.player_fleet), unsafe_allow_html=True)

        st.session_state["show_density"] = st.checkbox(
            "Show what the AI believes", value=st.session_state["show_density"]
        )

        if match.ai.last_density:
            conf = match.ai.confidence()
            st.markdown(
                f'<div class="bl-panel">'
                f'<div class="bl-stat-label">ITS REASONING</div>'
                f'<div style="color:{SAND};font-size:0.9rem;margin:0.2rem 0 0.5rem;">'
                f"{esc(match.ai.last_reason)}</div>"
                f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.72rem;'
                f'color:{BONE_DIM};line-height:1.6;">'
                f'<span style="color:#EDE4D0;">{match.ai.last_placements:,}</span> '
                f"fleet layouts still consistent with its shots<br>"
                f"confidence in its best square: "
                f'<span style="color:{AMBER};">{conf * 100:.1f}%</span></div></div>',
                unsafe_allow_html=True,
            )
        elif match.ai.last_reason:
            st.markdown(
                f'<div class="bl-panel"><div class="bl-stat-label">ITS REASONING'
                f'</div><div style="color:{SAND};font-size:0.9rem;">'
                f"{esc(match.ai.last_reason)}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown(
        "".join(f'<div class="bl-log">{esc(m)}</div>' for m in match.log[-5:]),
        unsafe_allow_html=True,
    )

    if match.status == "playing" and match.player_shots.shots == 0:
        if st.button("Reposition my fleet", use_container_width=False):
            match.reshuffle_player_fleet()
            st.rerun()

    if match.status != "playing":
        if not st.session_state["commentary"]:
            st.session_state["commentary"] = narrator.commentary(
                "won" if match.status == "won" else "lost",
                match.difficulty,
                match.player_shots.shots,
                0,
                match.ai.last_reason,
            )
        if match.status == "won":
            st.success(f"Enemy fleet destroyed in {match.player_shots.shots} shots.")
        else:
            st.error("Your fleet has been sunk.")
        if st.button("SEE RESULTS", type="primary", use_container_width=True):
            st.session_state["screen"] = "over"
            st.rerun()


def _tap_grid(match: Match) -> None:
    """10x10 of buttons. Fast on desktop; may stack on very narrow screens."""
    st.markdown(
        f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.7rem;'
        f'color:{BONE_DIM};margin-top:0.5rem;">Tap a square to fire.</div>',
        unsafe_allow_html=True,
    )
    for r in range(SIZE):
        row = st.columns(SIZE, gap="small")
        for c in range(SIZE):
            state = match.player_shots.state[r][c]
            fired = state != UNKNOWN
            if row[c].button(
                CELL_GLYPH[state],
                key=f"fire_{r}_{c}",
                use_container_width=True,
                disabled=fired,
                help=label(r, c) if not fired else None,
            ):
                match.fire(r, c)
                st.rerun()


def _coordinate_picker(match: Match) -> None:
    """Three taps, works at any viewport width."""
    st.markdown(
        f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.7rem;'
        f'color:{BONE_DIM};margin-top:0.5rem;">Pick a target and fire.</div>',
        unsafe_allow_html=True,
    )
    a, b, c = st.columns([2, 2, 3])
    col = a.selectbox("Column", COLUMN_LABELS, index=COLUMN_LABELS.index(st.session_state["pick_col"]))
    row = b.selectbox("Row", list(range(1, SIZE + 1)), index=st.session_state["pick_row"] - 1)
    st.session_state["pick_col"] = col
    st.session_state["pick_row"] = row

    r, cc = row - 1, COLUMN_LABELS.index(col)
    already = match.player_shots.already_fired(r, cc)
    c.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
    if c.button(
        f"FIRE ON {col}{row}",
        type="primary",
        use_container_width=True,
        disabled=already,
    ):
        match.fire(r, cc)
        st.rerun()
    if already:
        st.caption("You have already fired there.")


# ---------------------------------------------------------------------- over


def screen_over() -> None:
    match: Match = st.session_state["match"]
    won = match.status == "won"

    st.markdown(
        f'<div class="bl-title" style="font-size:1.9rem;'
        f'color:{SAND if won else BRICK};">'
        f'{"VICTORY" if won else "FLEET LOST"}</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### Score")
        st.markdown(
            f'<div class="bl-stat-value" style="font-size:2.6rem;color:{SAND};">'
            f"{match.score():,}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "".join(
                f'<div class="bl-row"><span class="bl-name">{lbl}</span>'
                f'<span class="bl-score">{val}</span></div>'
                for lbl, val in match.breakdown()
            ),
            unsafe_allow_html=True,
        )
        st.markdown("#### Analysis")
        st.markdown(
            f'<div class="bl-panel">{esc(st.session_state["commentary"])}</div>',
            unsafe_allow_html=True,
        )

    with right:
        c = st.columns(2)
        c[0].markdown(stat("YOUR SHOTS", str(match.player_shots.shots)), unsafe_allow_html=True)
        c[1].markdown(stat("THEIR SHOTS", str(match.ai_shots.shots)), unsafe_allow_html=True)
        c[0].markdown(
            stat("YOUR ACCURACY", f"{match.player_accuracy() * 100:.0f}%"),
            unsafe_allow_html=True,
        )
        c[1].markdown(
            stat("THEIR ACCURACY", f"{match.ai_accuracy() * 100:.0f}%"),
            unsafe_allow_html=True,
        )

        if not st.session_state["submitted"]:
            if st.button("SUBMIT SCORE", type="primary", use_container_width=True):
                entry = make_entry(
                    st.session_state["username"], match.score(),
                    len(match.player_shots.sunk_names), match.difficulty,
                    match.player_shots.hits, match.player_shots.shots,
                    match.player_accuracy(),
                )
                with st.spinner("Transmitting…"):
                    ok = get_store().append(entry)
                load_entries.clear()
                st.session_state["submitted"] = True
                st.session_state["last_rank"] = (
                    rank_of(load_entries(), match.score()) if ok else -1
                )
                st.rerun()
        else:
            rank = st.session_state["last_rank"]
            if rank == -1:
                st.warning("Could not reach the shared board. Result kept locally.")
            else:
                st.success(f"Recorded. Rank #{rank}.")

        b = st.columns(2)
        if b[0].button("PLAY AGAIN", use_container_width=True):
            st.session_state["match"] = Match(
                match.difficulty, seed=random.randint(1, 999_999)
            )
            st.session_state["screen"] = "game"
            st.session_state["commentary"] = ""
            st.session_state["submitted"] = False
            st.rerun()
        if b[1].button("MENU", use_container_width=True):
            st.session_state["screen"] = "menu"
            st.rerun()


SCREENS = {"menu": screen_menu, "game": screen_game, "over": screen_over}
SCREENS.get(st.session_state["screen"], screen_menu)()
