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
from engine.duel import FINISHED, PLACING, PLAYING, WAITING
from engine.fleet import COLUMN_LABELS, HIT, MISS, SIZE, SUNK, UNKNOWN, label
from engine.match import Match
from services import narrator, rooms
from services.leaderboard import (
    champion,
    get_store,
    make_entry,
    personal_best,
    rank_of,
    top_entries,
)
from ui.board import enemy_pips, fleet_pips, own_board, placement_board, target_board
from ui.theme import AMBER, BONE_DIM, BRICK, CSS, SAND, TEAL

st.set_page_config(page_title="ARMADA", page_icon="◆", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

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
    "room_code": None,
    "seat_token": None,
    "seat": None,
    "room_error": "",
    "pending_code": "",
    "qp_checked": False,
    "join_code_input": "",
    "orient_h": True,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


@st.cache_data(ttl=45, show_spinner=False)
def load_entries() -> list:
    return get_store().load()


def _bootstrap_from_url() -> None:
    """Resolve ?game=CODE&seat=TOKEN once per session.

    The seat token lives in the URL rather than only in session state, so a
    refresh or a dropped phone connection reclaims the same seat instead of
    locking the player out of their own game.
    """
    if st.session_state["qp_checked"]:
        return
    st.session_state["qp_checked"] = True

    params = st.query_params
    code = params.get("game")
    token = params.get("seat")
    if not code:
        return

    duel = rooms.find_room(code)
    if duel is None:
        st.session_state["room_error"] = (
            f"Room {str(code).upper()} no longer exists. Rooms are held in "
            "memory, so they are lost when the app restarts."
        )
        return

    seat = duel.seat_of(token) if token else None
    if seat is not None:
        st.session_state.update(
            room_code=duel.code, seat_token=token, seat=seat,
            screen="duel" if duel.status != WAITING else "lobby",
        )
    else:
        st.session_state["pending_code"] = duel.code
        st.session_state["screen"] = "join"


_bootstrap_from_url()


def _auto(fn):
    """Rerun this block on a timer so a player sees the opponent's move.

    Falls back to a manual refresh button on older Streamlit builds that
    predate st.fragment.
    """
    if hasattr(st, "fragment"):
        return st.fragment(run_every="2s")(fn)
    return fn


def stat(lbl: str, value: str) -> str:
    return (
        f'<div class="bl-stat-label">{lbl}</div>'
        f'<div class="bl-stat-value">{value}</div>'
    )


def esc(t) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _EmptyShots:
    """Stands in for an opponent's shot grid before any shot is fired."""

    def __init__(self):
        self.state = [[UNKNOWN] * SIZE for _ in range(SIZE)]
        self.sunk_names = []


# ----------------------------------------------------------------- placement


def placement_ui(fleet, key_prefix: str) -> bool:
    """Lay out a fleet. Returns True once the player confirms.

    The fleet arrives already placed at random, so anyone who does not care can
    simply confirm. Anyone who does can clear it and place every ship by hand,
    with illegal squares disabled rather than rejected after the click.
    """
    pending = fleet.next_to_place()

    if pending is None:
        st.markdown(
            '<div class="bl-panel">Fleet ready. Confirm it, or rearrange below.'
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        name, length = pending
        facing = "horizontal" if st.session_state["orient_h"] else "vertical"
        st.markdown(
            f'<div class="bl-panel">Placing the <strong style="color:{SAND};">'
            f"{name}</strong> — {length} cells, {facing}. "
            f"Green squares are legal positions for its bow.</div>",
            unsafe_allow_html=True,
        )

    controls = st.columns(4)
    if controls[0].button(
        "ROTATE", key=f"{key_prefix}_rot",
        use_container_width=True, disabled=pending is None,
    ):
        st.session_state["orient_h"] = not st.session_state["orient_h"]
        st.rerun()
    if controls[1].button(
        "UNDO", key=f"{key_prefix}_undo",
        use_container_width=True, disabled=not fleet.ships,
    ):
        fleet.remove_last()
        st.rerun()
    if controls[2].button("RANDOM", key=f"{key_prefix}_rand", use_container_width=True):
        fleet.place_random(random.Random(random.randint(1, 10**6)))
        st.rerun()
    if controls[3].button(
        "CLEAR", key=f"{key_prefix}_clear",
        use_container_width=True, disabled=not fleet.ships,
    ):
        fleet.clear()
        st.rerun()

    if pending is None:
        st.markdown(own_board(fleet, _EmptyShots()), unsafe_allow_html=True)
    else:
        name, length = pending
        hit = placement_board(fleet, length, st.session_state["orient_h"], key_prefix)
        if hit:
            fleet.place(name, length, hit[0], hit[1], st.session_state["orient_h"])
            st.rerun()

    st.markdown(fleet_pips(fleet, reveal=False), unsafe_allow_html=True)

    return st.button(
        "CONFIRM FLEET", key=f"{key_prefix}_confirm", type="primary",
        use_container_width=True, disabled=not fleet.is_complete(),
    )


def screen_place() -> None:
    match: Match = st.session_state["match"]
    st.markdown(
        '<div class="bl-title" style="font-size:1.9rem;">DEPLOY YOUR FLEET</div>',
        unsafe_allow_html=True,
    )
    if placement_ui(match.player_fleet, "aiplace"):
        st.session_state["screen"] = "game"
        st.rerun()
    if st.button("BACK TO MENU", use_container_width=True):
        st.session_state["screen"] = "menu"
        st.rerun()


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
            "Callsign", value=st.session_state["username"], max_chars=18,
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
                name, key=f"d_{name}", use_container_width=True,
                type="primary" if st.session_state["difficulty"] == name else "secondary",
            ):
                st.session_state["difficulty"] = name
                st.rerun()
        cfg = DIFFICULTIES[st.session_state["difficulty"]]
        st.caption(f"{cfg['blurb']}  Score multiplier ×{cfg['multiplier']}")

        st.session_state["input_mode"] = st.radio(
            "Targeting", ["Tap the grid", "Coordinate picker"],
            index=0 if st.session_state["input_mode"] == "Tap the grid" else 1,
            horizontal=True,
            help="Switch to the picker on a phone if the grid stacks awkwardly.",
        )

        ready = bool(st.session_state["username"].strip())
        if st.button("DEPLOY FLEET", type="primary",
                     use_container_width=True, disabled=not ready):
            st.session_state["match"] = Match(
                st.session_state["difficulty"], seed=random.randint(1, 999_999)
            )
            st.session_state["screen"] = "place"
            st.session_state["commentary"] = ""
            st.session_state["submitted"] = False
            st.rerun()
        if not ready:
            st.caption("A callsign is required so runs can be attributed.")

        st.markdown(
            '<div class="bl-stat-label" style="margin:1.1rem 0 0.35rem 0;">'
            "TWO PLAYER</div>",
            unsafe_allow_html=True,
        )
        if st.session_state["room_error"]:
            st.warning(st.session_state["room_error"])
            st.session_state["room_error"] = ""
        tp = st.columns([2, 3])
        if tp[0].button("CREATE A ROOM", use_container_width=True, disabled=not ready):
            code, token, seat = rooms.create_room(st.session_state["username"])
            st.session_state.update(
                room_code=code, seat_token=token, seat=seat, screen="lobby"
            )
            st.query_params["game"] = code
            st.query_params["seat"] = token
            st.rerun()
        st.session_state["join_code_input"] = tp[1].text_input(
            "Join with a room code", value=st.session_state["join_code_input"],
            max_chars=6, placeholder="e.g. K7X2", label_visibility="collapsed",
        )
        if tp[1].button(
            "JOIN ROOM", use_container_width=True,
            disabled=not (ready and st.session_state["join_code_input"].strip()),
        ):
            token, seat, err = rooms.join_room(
                st.session_state["join_code_input"], st.session_state["username"]
            )
            if err:
                st.session_state["room_error"] = err
            else:
                st.session_state.update(
                    room_code=st.session_state["join_code_input"].strip().upper(),
                    seat_token=token, seat=seat, screen="duel",
                )
                st.query_params["game"] = st.session_state["room_code"]
                st.query_params["seat"] = token
            st.rerun()
        st.caption(
            "Both players open this same app. Rooms live in server memory, so a "
            "restart ends any game in progress — the AI game is unaffected."
        )

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
That halves the search space for free — but it switches off the moment a hit
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

    # --- their waters: the board itself is the control -------------------
    with enemy:
        st.markdown("#### Enemy waters")
        picker = st.session_state["input_mode"] == "Coordinate picker"
        hit = target_board(
            match.player_shots, "ai", disabled=picker or match.status != "playing"
        )
        if hit:
            match.fire(*hit)
            st.rerun()
        if picker and match.status == "playing":
            _coordinate_picker(match)
        st.markdown(
            enemy_pips(match.player_shots, match.ai_fleet.ships), unsafe_allow_html=True
        )

    # --- your waters: where you watch it think ---------------------------
    with mine:
        st.markdown("#### Your waters")
        density = match.ai.last_density if st.session_state["show_density"] else None
        st.markdown(
            own_board(match.player_fleet, match.ai_shots, density, match.last_ai_shot),
            unsafe_allow_html=True,
        )
        st.markdown(fleet_pips(match.player_fleet), unsafe_allow_html=True)
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
                f'<span style="color:#E9F0F5;">{match.ai.last_placements:,}</span> '
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

    if match.status != "playing":
        if not st.session_state["commentary"]:
            st.session_state["commentary"] = narrator.commentary(
                "won" if match.status == "won" else "lost",
                match.difficulty, match.player_shots.shots, 0, match.ai.last_reason,
            )
        if match.status == "won":
            st.success(f"Enemy fleet destroyed in {match.player_shots.shots} shots.")
        else:
            st.error("Your fleet has been sunk.")
        if st.button("SEE RESULTS", type="primary", use_container_width=True):
            st.session_state["screen"] = "over"
            st.rerun()


def _coordinate_picker(match: Match) -> None:
    """Three taps, works at any viewport width."""
    a, b, c = st.columns([2, 2, 3])
    col = a.selectbox("Column", COLUMN_LABELS, key="pick_col_w")
    row = b.selectbox("Row", list(range(1, SIZE + 1)), key="pick_row_w")
    r, cc = row - 1, COLUMN_LABELS.index(col)
    already = match.player_shots.already_fired(r, cc)
    c.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
    if c.button(f"FIRE ON {col}{row}", type="primary",
                use_container_width=True, disabled=already):
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
            st.session_state["screen"] = "place"
            st.session_state["commentary"] = ""
            st.session_state["submitted"] = False
            st.rerun()
        if b[1].button("MENU", use_container_width=True):
            st.session_state["screen"] = "menu"
            st.rerun()


# --------------------------------------------------------------- two player


def _leave_room() -> None:
    st.session_state.update(
        room_code=None, seat_token=None, seat=None, screen="menu"
    )
    st.query_params.clear()


def screen_join() -> None:
    """Reached by opening a shared ?game=CODE link without a seat."""
    code = st.session_state["pending_code"]
    st.markdown('<div class="bl-title">ARMADA</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="bl-sub">You have been invited to room '
        f'<strong style="color:{SAND};">{esc(code)}</strong>.</div>',
        unsafe_allow_html=True,
    )
    st.session_state["username"] = st.text_input(
        "Your callsign", value=st.session_state["username"], max_chars=18,
        placeholder="Name your opponent will see",
    )
    ready = bool(st.session_state["username"].strip())
    cols = st.columns(2)
    if cols[0].button("JOIN THE GAME", type="primary",
                      use_container_width=True, disabled=not ready):
        token, seat, err = rooms.join_room(code, st.session_state["username"])
        if err:
            st.session_state["room_error"] = err
            st.session_state["screen"] = "menu"
        else:
            st.session_state.update(
                room_code=code, seat_token=token, seat=seat, screen="duel"
            )
            st.query_params["game"] = code
            st.query_params["seat"] = token
        st.rerun()
    if cols[1].button("BACK TO MENU", use_container_width=True):
        _leave_room()
        st.rerun()


@_auto
def _lobby_body() -> None:
    code = st.session_state["room_code"]
    duel = rooms.find_room(code)
    if duel is None:
        st.session_state["room_error"] = "That room has expired."
        st.session_state["screen"] = "menu"
        st.rerun()
        return

    seat = st.session_state["seat"]
    duel.touch(seat)

    if duel.status != WAITING:
        st.session_state["screen"] = "duel"
        st.rerun()
        return

    st.info("Waiting for a second commander to join…")


def screen_lobby() -> None:
    code = st.session_state["room_code"]
    st.markdown('<div class="bl-title" style="font-size:2rem;">ROOM OPEN</div>',
                unsafe_allow_html=True)
    st.markdown(
        f'<div class="bl-banner"><div class="bl-banner-role">ROOM CODE</div>'
        f'<div class="bl-banner-name" style="letter-spacing:0.3em;">'
        f"{esc(code)}</div>"
        f'<div class="bl-banner-meta">Give this code to your opponent, or send '
        f"them this app's link with <code>?game={esc(code)}</code> on the end."
        f"</div></div>",
        unsafe_allow_html=True,
    )
    st.code(f"?game={code}", language=None)

    _lobby_body()

    if not hasattr(st, "fragment"):
        if st.button("Check for opponent", use_container_width=True):
            st.rerun()

    st.caption(
        "This page checks for an opponent every couple of seconds. You can "
        "leave at any time — nothing is lost."
    )
    if st.button("BACK TO MENU", use_container_width=True):
        _leave_room()
        st.rerun()


@_auto
def _duel_body() -> None:
    code = st.session_state["room_code"]
    seat = st.session_state["seat"]
    duel = rooms.find_room(code)
    if duel is None:
        st.session_state["room_error"] = (
            "The room disappeared — the app most likely restarted."
        )
        st.session_state["screen"] = "menu"
        st.rerun()
        return

    duel.touch(seat)
    me = duel.names[seat] or "You"
    them = duel.names[1 - seat] or "Opponent"

    head = st.columns(4)
    head[0].markdown(stat("ROOM", code), unsafe_allow_html=True)
    head[1].markdown(stat("YOUR SHOTS", str(duel.shots[seat].shots)), unsafe_allow_html=True)
    head[2].markdown(stat("YOUR SHIPS", str(duel.ships_left(seat))), unsafe_allow_html=True)
    head[3].markdown(stat("THEIR SHIPS", str(duel.ships_left(1 - seat))), unsafe_allow_html=True)

    line = duel.status_line(seat)
    colour = SAND if (duel.can_fire(seat) or duel.status == PLACING) else BONE_DIM
    st.markdown(
        f'<div class="bl-panel"><span style="color:{colour};font-size:1rem;">'
        f"{esc(line)}</span></div>",
        unsafe_allow_html=True,
    )

    # Deployment happens before either side may fire.
    if duel.status == PLACING:
        if not duel.ready[seat]:
            if placement_ui(duel.fleets[seat], f"duel{seat}"):
                rooms.act(code, lambda d: d.set_ready(seat))
                st.rerun()
        else:
            st.info(f"Waiting for {them} to finish deploying…")
        return

    if duel.status == PLAYING and not duel.opponent_present(seat):
        st.warning(f"{them} has not been seen for a moment. They may have closed the page.")

    enemy, mine = st.columns(2, gap="large")
    with enemy:
        st.markdown(f"#### {esc(them)}'s waters")
        picker = st.session_state["input_mode"] == "Coordinate picker"
        hit = target_board(
            duel.shots[seat], f"d{seat}", disabled=picker or not duel.can_fire(seat)
        )
        if hit:
            rooms.act(code, lambda d: d.fire(seat, hit[0], hit[1]))
            st.rerun()
        if picker and duel.can_fire(seat):
            _duel_picker(duel, seat)
        st.markdown(enemy_pips(duel.shots[seat], duel.fleets[1 - seat].ships),
                    unsafe_allow_html=True)

    with mine:
        st.markdown(f"#### {esc(me)}'s waters")
        st.markdown(
            own_board(duel.fleets[seat], duel.shots[1 - seat]),
            unsafe_allow_html=True,
        )
        st.markdown(fleet_pips(duel.fleets[seat]), unsafe_allow_html=True)

    st.markdown(
        "".join(f'<div class="bl-log">{esc(m)}</div>' for m in duel.log[-6:]),
        unsafe_allow_html=True,
    )

    if duel.status == FINISHED:
        if duel.winner == seat:
            st.success("You won the duel.")
        else:
            st.error("You lost the duel.")


def _duel_picker(duel, seat: int) -> None:
    a, b, c = st.columns([2, 2, 3])
    col = a.selectbox("Column", COLUMN_LABELS, key="duel_col")
    row = b.selectbox("Row", list(range(1, SIZE + 1)), key="duel_row")
    r, cc = row - 1, COLUMN_LABELS.index(col)
    already = duel.shots[seat].already_fired(r, cc)
    c.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
    if c.button(f"FIRE ON {col}{row}", type="primary",
                use_container_width=True, disabled=already):
        rooms.act(duel.code, lambda d: d.fire(seat, r, cc))
        st.rerun()


def screen_duel() -> None:
    _duel_body()

    if not hasattr(st, "fragment"):
        if st.button("Refresh board", use_container_width=True):
            st.rerun()

    cols = st.columns(2)
    if cols[0].button("LEAVE GAME", use_container_width=True):
        seat = st.session_state["seat"]
        rooms.act(st.session_state["room_code"], lambda d: d.forfeit(seat))
        _leave_room()
        st.rerun()
    if cols[1].button("BACK TO MENU", use_container_width=True):
        _leave_room()
        st.rerun()


SCREENS = {
    "menu": screen_menu,
    "place": screen_place,
    "game": screen_game,
    "over": screen_over,
    "join": screen_join,
    "lobby": screen_lobby,
    "duel": screen_duel,
}
SCREENS.get(st.session_state["screen"], screen_menu)()
