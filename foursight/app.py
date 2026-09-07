"""
FOURSIGHT — Connect Four against an alpha-beta search engine.

Streamlit re-runs this file on every interaction, so the pattern is: restore
state from st.session_state, dispatch to a screen, mutate, rerun. All game
logic lives in engine/ and ai/, neither of which imports Streamlit.
"""

from __future__ import annotations

import streamlit as st

from ai.search import DEFAULT_DIFFICULTY, DIFFICULTIES
from engine.board import WIDTH
from engine.match import Session
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
    render_board,
    render_evaluation,
    render_line,
    render_search_stats,
)
from ui.theme import BONE_DIM, BRICK, CSS, SAND, TEAL

st.set_page_config(page_title="FOURSIGHT", page_icon="◆", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

DEFAULTS = {
    "screen": "menu",
    "session": None,
    "username": "",
    "difficulty": DEFAULT_DIFFICULTY,
    "commentary": "",
    "submitted": False,
    "last_rank": None,
    "last_points": 0,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


@st.cache_data(ttl=45, show_spinner=False)
def load_entries() -> list:
    return get_store().load()


def stat(label: str, value: str) -> str:
    return (
        f'<div class="bl-stat-label">{label}</div>'
        f'<div class="bl-stat-value">{value}</div>'
    )


def esc(t) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------- menu


def screen_menu() -> None:
    st.markdown('<div class="bl-title">FOURSIGHT</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="bl-sub">Connect Four against a minimax engine with '
        "alpha-beta pruning. It shows you every column it considered, the line "
        "it expects, and how much of the game tree it managed to skip.</div>",
        unsafe_allow_html=True,
    )

    entries = load_entries()
    best = champion(entries)
    if best:
        st.markdown(
            f'<div class="bl-banner">'
            f'<div class="bl-banner-role">CURRENT CHAMPION</div>'
            f'<div class="bl-banner-name">{esc(best["username"])}</div>'
            f'<div class="bl-banner-meta">{best["score"]:,} pts &nbsp;·&nbsp; '
            f'streak {best.get("wave", 0)} &nbsp;·&nbsp; '
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
            "DIFFICULTY</div>",
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

        ready = bool(st.session_state["username"].strip())
        if st.button("START RUN", type="primary", use_container_width=True, disabled=not ready):
            st.session_state["session"] = Session(st.session_state["difficulty"])
            st.session_state["screen"] = "game"
            st.session_state["commentary"] = ""
            st.session_state["submitted"] = False
            st.rerun()
        if not ready:
            st.caption("A callsign is required so runs can be attributed.")

        with st.expander("How the engine works"):
            st.markdown(
                """
The engine runs **negamax with alpha-beta pruning**, the standard adversarial
search algorithm. It assumes you play your best reply and discards any branch
that provably cannot change the outcome.

- **Bitboards.** The position is two 49-bit integers, so testing a move or a
  win is a handful of integer operations rather than nested loops.
- **Move ordering.** Centre columns are tried first because they belong to more
  winning lines, which produces early cutoffs. At depth 8 the engine examines
  around 12,000 positions instead of 7⁸ ≈ 5.7 million.
- **Transposition table.** The same position arises from many move orders, so
  results are cached and reused.
- **Iterative deepening.** It searches depth 1, then 2, and so on, stopping on
  a time budget. The shallow pass orders moves for the deep one.

A **run** is a streak of games that ends the first time you lose.
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


def screen_game() -> None:
    session: Session = st.session_state["session"]
    match = session.match

    # If the engine has the first move of this board, let it open.
    if match.status == "playing" and not match.human_to_move:
        with st.spinner("Thinking…"):
            match.play_engine()

    head = st.columns(4)
    head[0].markdown(stat("STREAK", str(session.streak)), unsafe_allow_html=True)
    head[1].markdown(stat("RUN SCORE", f"{session.total_score:,}"), unsafe_allow_html=True)
    head[2].markdown(stat("GAME", str(session.games_played + 1)), unsafe_allow_html=True)
    head[3].markdown(stat("LEVEL", session.difficulty), unsafe_allow_html=True)

    board_col, panel = st.columns([3, 2], gap="large")

    with board_col:
        drop = st.columns(WIDTH)
        for c in range(WIDTH):
            playable = match.status == "playing" and match.human_to_move and match.position.can_play(c)
            if drop[c].button(
                "▼", key=f"drop_{c}_{match.position.moves}",
                use_container_width=True, disabled=not playable,
            ):
                match.play_human(c)
                if match.status == "playing":
                    match.play_engine()
                if match.status != "playing":
                    _conclude(session, match)
                st.rerun()

        st.markdown(
            render_board(match, match.winning_bits), unsafe_allow_html=True
        )
        st.markdown(
            f'<div style="display:flex;gap:1.1rem;font-family:IBM Plex Mono,monospace;'
            f'font-size:0.74rem;color:{BONE_DIM};margin-top:0.5rem;">'
            f'<span><span style="color:{SAND};">●</span> You</span>'
            f'<span><span style="color:{BRICK};">●</span> Engine</span>'
            f'<span>Columns are numbered 1–7, left to right.</span></div>',
            unsafe_allow_html=True,
        )

    with panel:
        st.markdown("#### What the engine is thinking")
        result = match.last_result
        if result:
            st.markdown(
                f'<div class="bl-panel">'
                f'<div class="bl-stat-label">ITS READ ON THE POSITION</div>'
                f'<div style="color:{SAND};font-size:0.95rem;margin-top:0.2rem;">'
                f"{esc(result.verdict)}</div>"
                f"{render_line(result)}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="bl-panel">'
                f'<div class="bl-stat-label">HOW IT RATED EACH COLUMN</div>'
                f"{render_evaluation(result, match.legal())}"
                f'<div style="font-size:0.68rem;color:{BONE_DIM};'
                f'font-family:IBM Plex Mono,monospace;margin-top:0.3rem;">'
                f"taller means better for the engine · "
                f'<span style="color:{SAND};">gold</span> is the move it chose</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="bl-panel">'
                f'<div class="bl-stat-label">SEARCH</div>'
                f"{render_search_stats(result)}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("Make a move and the engine's analysis appears here.")

        if st.button("Resign run", use_container_width=True):
            match.status = "lost"
            _conclude(session, match)
            st.rerun()

    # --- result of the finished board ------------------------------------
    if match.status != "playing":
        points = st.session_state["last_points"]
        if match.status == "won":
            st.success(f"You won that board. +{points:,} points.")
        elif match.status == "drawn":
            st.info(f"Drawn. +{points:,} points.")
        else:
            st.error("Beaten. The run ends here.")

        if st.session_state["commentary"]:
            st.markdown(
                f'<div class="bl-panel" style="border-left:3px solid {TEAL};">'
                f'{esc(st.session_state["commentary"])}</div>',
                unsafe_allow_html=True,
            )

        if session.over:
            if st.button("SEE RESULTS", type="primary", use_container_width=True):
                st.session_state["screen"] = "over"
                st.rerun()
        else:
            if st.button("NEXT BOARD", type="primary", use_container_width=True):
                session.next_match()
                st.session_state["commentary"] = ""
                st.rerun()


def _conclude(session: Session, match) -> None:
    st.session_state["last_points"] = session.conclude_match()
    outcome = {"won": "won", "lost": "lost", "drawn": "drew"}.get(match.status, "lost")
    verdict = match.last_result.verdict if match.last_result else ""
    st.session_state["commentary"] = narrator.commentary(
        outcome, session.difficulty, match.position.moves, session.streak, verdict
    )


# ---------------------------------------------------------------------- over


def screen_over() -> None:
    session: Session = st.session_state["session"]
    st.markdown(
        f'<div class="bl-title" style="font-size:1.9rem;">RUN OVER</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### Final score")
        st.markdown(
            f'<div class="bl-stat-value" style="font-size:2.6rem;color:{SAND};">'
            f"{session.total_score:,}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "".join(
                f'<div class="bl-row"><span class="bl-name">{label}</span>'
                f'<span class="bl-score">{value}</span></div>'
                for label, value in session.match.breakdown(session.streak)
            ),
            unsafe_allow_html=True,
        )

    with right:
        c = st.columns(2)
        c[0].markdown(stat("BEST STREAK", str(session.streak)), unsafe_allow_html=True)
        c[1].markdown(stat("GAMES", str(session.games_played)), unsafe_allow_html=True)
        c[0].markdown(stat("WINS", str(session.wins)), unsafe_allow_html=True)
        c[1].markdown(stat("DRAWS", str(session.draws)), unsafe_allow_html=True)

        if not st.session_state["submitted"]:
            if st.button("SUBMIT SCORE", type="primary", use_container_width=True):
                entry = make_entry(
                    st.session_state["username"], session.total_score,
                    session.streak, session.difficulty,
                    session.wins, session.games_played, 0.0,
                )
                with st.spinner("Transmitting…"):
                    ok = get_store().append(entry)
                load_entries.clear()
                st.session_state["submitted"] = True
                st.session_state["last_rank"] = rank_of(load_entries(), session.total_score) if ok else -1
                st.rerun()
        else:
            rank = st.session_state["last_rank"]
            if rank == -1:
                st.warning("Could not reach the shared board. Run still counted locally.")
            else:
                st.success(f"Recorded. Rank #{rank}.")

        b = st.columns(2)
        if b[0].button("RUN AGAIN", use_container_width=True):
            st.session_state["session"] = Session(session.difficulty)
            st.session_state["screen"] = "game"
            st.session_state["submitted"] = False
            st.session_state["commentary"] = ""
            st.rerun()
        if b[1].button("MENU", use_container_width=True):
            st.session_state["screen"] = "menu"
            st.rerun()


SCREENS = {"menu": screen_menu, "game": screen_game, "over": screen_over}
SCREENS.get(st.session_state["screen"], screen_menu)()
