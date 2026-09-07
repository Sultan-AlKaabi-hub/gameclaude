"""
BLACKOUT — entry point.

Streamlit re-executes this file top to bottom on every interaction, so the
structure is: restore state, dispatch to one screen function, mutate state,
rerun. Nothing here holds game logic; `engine` and `ai` own the rules and stay
importable without Streamlit so they can be tested headlessly.
"""

from __future__ import annotations

import datetime as _dt
import random

import streamlit as st

from engine.scoring import DIFFICULTIES, score_breakdown
from engine.state import SILENT_MOVE_COST, GameState
from services import narrator
from services.leaderboard import (
    champion,
    get_store,
    make_entry,
    personal_best,
    personal_history,
    rank_of,
    top_entries,
)
from ui.render import legend_html, render_arena
from ui.theme import BONE, BONE_DIM, BRICK, SAND, TEAL, CSS, threat_colour

st.set_page_config(page_title="BLACKOUT", page_icon="◆", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------- state setup

DEFAULTS = {
    "screen": "terminal",
    "gs": None,
    "username": "",
    "difficulty": "OPERATIVE",
    "briefing": "",
    "debrief": "",
    "submitted": False,
    "show_belief": True,
    "show_intent": False,
    "silent": False,
    "last_rank": None,
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


@st.cache_data(ttl=45, show_spinner=False)
def load_entries() -> list[dict]:
    """Cached leaderboard read. Cleared explicitly after a submission."""
    return get_store().load()


def store_status() -> tuple[str, bool]:
    store = get_store()
    return store.name, store.durable


def daily_seed() -> int:
    """Same arena for everyone, changing at UTC midnight."""
    today = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    return abs(hash(today)) % 1_000_000


def meter(value: float, colour: str) -> str:
    pct = max(0.0, min(1.0, value)) * 100
    return (
        f'<div class="bl-meter"><div class="bl-meter-fill" '
        f'style="width:{pct:.0f}%;background:{colour};"></div></div>'
    )


def stat(label: str, value: str) -> str:
    return (
        f'<div class="bl-stat-label">{label}</div>'
        f'<div class="bl-stat-value">{value}</div>'
    )


# ------------------------------------------------------------------ terminal


def screen_terminal() -> None:
    st.markdown('<div class="bl-title">BLACKOUT</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="bl-sub">They cannot see you. They can only infer you. '
        "Every hunter on this station shares one probabilistic belief about "
        "where you are — your job is to keep it wrong.</div>",
        unsafe_allow_html=True,
    )

    entries = load_entries()
    top = champion(entries)

    if top:
        st.markdown(
            f'<div class="bl-banner">'
            f'<div class="bl-banner-role">STATION RECORD HOLDER</div>'
            f'<div class="bl-banner-name">{_esc(top["username"])}</div>'
            f'<div class="bl-banner-meta">{top["score"]:,} pts &nbsp;·&nbsp; '
            f'wave {top.get("wave", 1)} &nbsp;·&nbsp; {top.get("difficulty", "—")} '
            f'&nbsp;·&nbsp; stealth {int(top.get("stealth", 0) * 100)}%</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown("#### Insertion")
        st.session_state["username"] = st.text_input(
            "Callsign",
            value=st.session_state["username"],
            max_chars=18,
            placeholder="Enter a callsign for the leaderboard",
        )

        st.session_state["difficulty"] = st.radio(
            "Difficulty",
            options=list(DIFFICULTIES.keys()),
            index=list(DIFFICULTIES.keys()).index(st.session_state["difficulty"]),
            horizontal=True,
        )
        d = DIFFICULTIES[st.session_state["difficulty"]]
        st.caption(f"{d['blurb']}  Score multiplier ×{d['multiplier']}")

        daily = st.checkbox(
            "Daily challenge (everyone plays the identical arena today)",
            value=False,
        )

        can_start = bool(st.session_state["username"].strip())
        if st.button(
            "BEGIN INSERTION",
            type="primary",
            use_container_width=True,
            disabled=not can_start,
        ):
            seed = daily_seed() if daily else random.randint(1, 999_999)
            gs = GameState(seed=seed, daily=daily, difficulty=st.session_state["difficulty"])
            st.session_state["gs"] = gs
            st.session_state["submitted"] = False
            st.session_state["debrief"] = ""
            st.session_state["last_rank"] = None
            with st.spinner("Receiving mission briefing…"):
                st.session_state["briefing"] = narrator.briefing(
                    1,
                    st.session_state["difficulty"],
                    gs.config.hunters,
                    gs.config.nodes,
                )
            st.session_state["screen"] = "arena"
            st.rerun()

        if not can_start:
            st.caption("A callsign is required so runs can be attributed.")

        with st.expander("How this actually works"):
            st.markdown(
                """
**The hunters never receive your position.** They maintain a *particle filter* —
a few hundred weighted hypotheses about where you might be — and update it with
Bayes' rule every turn from noisy proximity readings. The coloured cloud on the
map is that belief, drawn directly from the filter.

- **Silence is evidence.** A hunter that detects nothing rules out the cells it
  was covering, which is why holes open in the cloud around them.
- **Your stealth score is the Shannon entropy of their belief.** You are scored
  on how *uncertain* you kept the AI, not merely on surviving.
- **They coordinate by auction.** Each turn the hunters bid on search targets
  weighted by probability mass over travel cost, so they fan out instead of
  queueing behind one another.
- **Scanning hunters (ringed) hold position** but take a sharper reading. That
  pause is your tempo advantage — time your dashes against it.
- **EMP blinds the sensors**, so the filter has nothing to update on and the
  belief decays outward. **Decoys** feed it a false reading and tear the cloud
  in two.
                """
            )

    with right:
        st.markdown("#### Station records")
        rows = top_entries(entries, 10)
        if not rows:
            st.caption("No runs recorded. The board is yours to open.")
        else:
            me = st.session_state["username"].strip().lower()
            html_rows = []
            for i, e in enumerate(rows, start=1):
                mine = e.get("username", "").lower() == me and me != ""
                html_rows.append(
                    f'<div class="bl-row {"bl-row-you" if mine else ""}">'
                    f'<span class="bl-rank">{i:02d}</span>'
                    f'<span class="bl-name">{_esc(e["username"])}</span>'
                    f'<span style="color:{BONE_DIM};font-size:0.74rem;'
                    f'margin-right:0.6rem;">W{e.get("wave", 1)} '
                    f'{e.get("difficulty", "")[:3]}</span>'
                    f'<span class="bl-score">{e["score"]:,}</span></div>'
                )
            st.markdown("".join(html_rows), unsafe_allow_html=True)

        pb = personal_best(entries, st.session_state["username"])
        if pb:
            st.markdown("#### Your best")
            st.markdown(
                f'<div class="bl-panel"><span class="bl-readout" '
                f'style="color:{SAND};font-size:1.4rem;font-weight:600;">'
                f'{pb["score"]:,}</span>'
                f'<span class="bl-readout" style="color:{BONE_DIM};'
                f'font-size:0.8rem;"> pts · wave {pb.get("wave", 1)} · '
                f'{pb.get("difficulty", "")}</span></div>',
                unsafe_allow_html=True,
            )
            history = personal_history(entries, st.session_state["username"], 5)
            if len(history) > 1:
                st.caption("Recent runs")
                st.markdown(
                    "".join(
                        f'<div class="bl-log">{h.get("at", "")[:10]} · '
                        f'{h["score"]:,} pts · wave {h.get("wave", 1)}</div>'
                        for h in history
                    ),
                    unsafe_allow_html=True,
                )

        name, durable = store_status()
        if not durable:
            st.caption(
                "Leaderboard is running on local storage, so scores reset when "
                "the app restarts. Add GIST_ID and GITHUB_TOKEN in app settings "
                "to make it permanent and shared."
            )


# --------------------------------------------------------------------- arena


def screen_arena() -> None:
    gs: GameState = st.session_state["gs"]
    if gs is None:
        st.session_state["screen"] = "terminal"
        st.rerun()
        return

    threat = gs.threat_level()

    head = st.columns([1, 1, 1, 1, 2])
    head[0].markdown(stat("WAVE", f"{gs.wave:02d}"), unsafe_allow_html=True)
    head[1].markdown(stat("SCORE", f"{gs.score:,}"), unsafe_allow_html=True)
    head[2].markdown(stat("TURN", f"{gs.turn:03d}"), unsafe_allow_html=True)
    head[3].markdown(
        stat("NODES", f"{gs.config.nodes - len(gs.nodes)}/{gs.config.nodes}"),
        unsafe_allow_html=True,
    )
    head[4].markdown(
        stat("DIFFICULTY", gs.difficulty)
        + (
            f'<div class="bl-readout" style="color:{BONE_DIM};font-size:0.7rem;">'
            f"DAILY CHALLENGE · SEED {gs.seed}</div>"
            if gs.daily
            else f'<div class="bl-readout" style="color:{BONE_DIM};'
            f'font-size:0.7rem;">SEED {gs.seed}</div>'
        ),
        unsafe_allow_html=True,
    )

    if st.session_state["briefing"]:
        st.markdown(
            f'<div class="bl-panel" style="border-left:3px solid {TEAL};">'
            f'<span class="bl-stat-label">BRIEFING</span><br>'
            f'<span style="color:{BONE};font-size:0.92rem;">'
            f'{_esc(st.session_state["briefing"])}</span></div>',
            unsafe_allow_html=True,
        )

    board, panel = st.columns([3, 2], gap="large")

    with board:
        st.markdown(
            render_arena(
                gs,
                show_belief=st.session_state["show_belief"],
                show_intent=st.session_state["show_intent"],
            ),
            unsafe_allow_html=True,
        )
        st.markdown(legend_html(), unsafe_allow_html=True)
        toggles = st.columns(2)
        st.session_state["show_belief"] = toggles[0].checkbox(
            "Show belief density", value=st.session_state["show_belief"]
        )
        st.session_state["show_intent"] = toggles[1].checkbox(
            "Show hunter intent", value=st.session_state["show_intent"]
        )

    with panel:
        # --- telemetry ---------------------------------------------------
        st.markdown(
            f'<div class="bl-panel">'
            f'<div class="bl-stat-label">THEIR CERTAINTY ABOUT YOU</div>'
            f'<div class="bl-stat-value" style="color:{threat_colour(threat)};">'
            f"{threat * 100:.0f}%</div>"
            f"{meter(threat, threat_colour(threat))}"
            f'<div class="bl-readout" style="color:{BONE_DIM};font-size:0.74rem;'
            f'margin-top:0.5rem;">{_esc(narrator.taunt(threat))}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="bl-panel">'
            f'<div class="bl-stat-label">STAMINA</div>'
            f"{meter(gs.stamina / 100.0, TEAL)}"
            f'<div class="bl-readout" style="color:{BONE_DIM};font-size:0.74rem;'
            f'margin-top:0.5rem;">nearest hunter {gs.nearest_hunter_distance()} '
            f"cells · effective hypotheses "
            f"{gs.pf.effective_sample_size():.0f}/{gs.config.particles}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # --- movement ----------------------------------------------------
        st.session_state["silent"] = st.checkbox(
            f"Silent movement (−{SILENT_MOVE_COST:.0f} stamina, shrinks their sensor range)",
            value=st.session_state["silent"],
            disabled=gs.stamina < 10,
        )
        prefix = "silent_" if st.session_state["silent"] and gs.stamina >= 10 else ""
        legal = gs.legal_moves()

        def move_button(container, label: str, key: str) -> None:
            if container.button(
                label,
                key=f"mv_{key}",
                use_container_width=True,
                disabled=not legal[key],
            ):
                _act(gs, f"{prefix}{key}")

        r1 = st.columns(3)
        r1[0].markdown("&nbsp;", unsafe_allow_html=True)
        move_button(r1[1], "▲  N", "N")
        r1[2].markdown("&nbsp;", unsafe_allow_html=True)

        r2 = st.columns(3)
        move_button(r2[0], "◀  W", "W")
        if r2[1].button("HOLD", key="mv_wait", use_container_width=True):
            _act(gs, "wait")
        move_button(r2[2], "E  ▶", "E")

        r3 = st.columns(3)
        r3[0].markdown("&nbsp;", unsafe_allow_html=True)
        move_button(r3[1], "▼  S", "S")
        r3[2].markdown("&nbsp;", unsafe_allow_html=True)

        # --- abilities ---------------------------------------------------
        ab = st.columns(2)
        if ab[0].button(
            f"DECOY ({gs.decoys})",
            use_container_width=True,
            disabled=gs.decoys <= 0,
            help="Feeds the filter a false observation. Splits their belief.",
        ):
            _act(gs, "decoy")
        if ab[1].button(
            f"EMP ({gs.emps})",
            use_container_width=True,
            disabled=gs.emps <= 0,
            help="Blinds every sensor for 3 turns. Their belief decays outward.",
        ):
            _act(gs, "emp")

        # --- log ---------------------------------------------------------
        st.markdown(
            "".join(f'<div class="bl-log">{_esc(m)}</div>' for m in gs.log[-5:]),
            unsafe_allow_html=True,
        )

        if st.button("Abort run", use_container_width=True):
            gs.status = "caught"
            _finish(gs, "aborted")

    # --- wave transition ---------------------------------------------------
    if gs.status == "extracted":
        st.success(
            f"Extraction confirmed. Wave {gs.wave} clear — "
            f"{gs.nodes_extracted} nodes secured, {gs.turns_survived} turns survived."
        )
        cols = st.columns(2)
        if cols[0].button("PUSH TO NEXT WAVE", type="primary", use_container_width=True):
            gs.next_wave()
            st.session_state["briefing"] = narrator.briefing(
                gs.wave, gs.difficulty, gs.config.hunters, gs.config.nodes
            )
            st.rerun()
        if cols[1].button("EXTRACT AND BANK SCORE", use_container_width=True):
            _finish(gs, "extracted")

    if gs.status == "caught":
        _finish(gs, "caught")


def _act(gs: GameState, action: str) -> None:
    gs.step(action)
    st.rerun()


def _finish(gs: GameState, outcome: str) -> None:
    st.session_state["outcome"] = outcome
    st.session_state["screen"] = "debrief"
    st.rerun()


# ------------------------------------------------------------------- debrief


def screen_debrief() -> None:
    gs: GameState = st.session_state["gs"]
    outcome = st.session_state.get("outcome", "caught")

    if outcome == "caught":
        st.markdown(
            f'<div class="bl-title" style="font-size:1.9rem;color:{BRICK};">'
            "RUN TERMINATED</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="bl-title" style="font-size:1.9rem;color:{SAND};">'
            "EXTRACTED</div>",
            unsafe_allow_html=True,
        )

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown("#### Score breakdown")
        rows = score_breakdown(
            gs.nodes_extracted, gs.turns_survived, gs.waves_cleared, gs.mean_entropy
        )
        html_rows = "".join(
            f'<div class="bl-row"><span class="bl-name">{label}</span>'
            f'<span class="bl-score">{value:,}</span></div>'
            for label, value in rows
        )
        mult = DIFFICULTIES[gs.difficulty]["multiplier"]
        html_rows += (
            f'<div class="bl-row"><span class="bl-name">'
            f"{gs.difficulty} multiplier</span>"
            f'<span class="bl-score">×{mult}</span></div>'
            f'<div class="bl-row" style="border-bottom:none;">'
            f'<span class="bl-name" style="font-weight:600;">FINAL</span>'
            f'<span class="bl-score" style="font-size:1.25rem;">'
            f"{gs.score:,}</span></div>"
        )
        st.markdown(html_rows, unsafe_allow_html=True)

        st.markdown("#### Analysis")
        if not st.session_state["debrief"]:
            with st.spinner("Compiling after-action report…"):
                st.session_state["debrief"] = narrator.debrief(
                    gs.waves_cleared,
                    gs.nodes_extracted,
                    gs.turns_survived,
                    gs.mean_entropy,
                    gs.score,
                    gs.difficulty,
                    outcome,
                )
        st.markdown(
            f'<div class="bl-panel">{_esc(st.session_state["debrief"])}</div>',
            unsafe_allow_html=True,
        )

    with right:
        st.markdown("#### Run summary")
        c = st.columns(2)
        c[0].markdown(stat("WAVES CLEARED", str(gs.waves_cleared)), unsafe_allow_html=True)
        c[1].markdown(stat("TURNS", str(gs.turns_survived)), unsafe_allow_html=True)
        c[0].markdown(stat("NODES", str(gs.nodes_extracted)), unsafe_allow_html=True)
        c[1].markdown(
            stat("STEALTH", f"{gs.mean_entropy * 100:.0f}%"), unsafe_allow_html=True
        )

        if not st.session_state["submitted"]:
            if st.button("SUBMIT TO LEADERBOARD", type="primary", use_container_width=True):
                entry = make_entry(
                    st.session_state["username"],
                    gs.score,
                    gs.wave,
                    gs.difficulty,
                    gs.nodes_extracted,
                    gs.turns_survived,
                    gs.mean_entropy,
                )
                with st.spinner("Transmitting…"):
                    ok = get_store().append(entry)
                load_entries.clear()
                st.session_state["submitted"] = True
                if ok:
                    st.session_state["last_rank"] = rank_of(load_entries(), gs.score)
                else:
                    st.session_state["last_rank"] = -1
                st.rerun()
        else:
            rank = st.session_state.get("last_rank")
            if rank == -1:
                st.warning(
                    "Score could not be transmitted to the shared board. Your run "
                    "still counted locally."
                )
            elif rank:
                st.success(f"Recorded. Station rank #{rank}.")

            entries = load_entries()
            pb = personal_best(entries, st.session_state["username"])
            if pb and pb["score"] == gs.score:
                st.markdown(
                    f'<div class="bl-banner"><div class="bl-banner-role">'
                    f"NEW PERSONAL BEST</div>"
                    f'<div class="bl-banner-name">{gs.score:,}</div></div>',
                    unsafe_allow_html=True,
                )

        cols = st.columns(2)
        if cols[0].button("RUN AGAIN", use_container_width=True):
            seed = daily_seed() if gs.daily else random.randint(1, 999_999)
            new = GameState(seed=seed, daily=gs.daily, difficulty=gs.difficulty)
            st.session_state["gs"] = new
            st.session_state["submitted"] = False
            st.session_state["debrief"] = ""
            st.session_state["briefing"] = narrator.briefing(
                1, new.difficulty, new.config.hunters, new.config.nodes
            )
            st.session_state["screen"] = "arena"
            st.rerun()
        if cols[1].button("TERMINAL", use_container_width=True):
            st.session_state["screen"] = "terminal"
            st.rerun()


# ---------------------------------------------------------------------- util


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


SCREENS = {
    "terminal": screen_terminal,
    "arena": screen_arena,
    "debrief": screen_debrief,
}
SCREENS.get(st.session_state["screen"], screen_terminal)()
