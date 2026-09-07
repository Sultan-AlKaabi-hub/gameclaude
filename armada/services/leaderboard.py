"""
Leaderboard persistence.

Streamlit Community Cloud runs the app in a container with an ephemeral
filesystem: anything written to local disk is lost on reboot or redeploy. A
leaderboard written to a local file therefore works perfectly in development
and silently loses everything in production, which is the worst possible
failure mode.

The fix is a storage interface with two implementations. `GistStore` keeps the
table in a public GitHub Gist via the REST API, which survives redeploys and
is independently viewable on the web. `LocalStore` writes JSON to disk and is
selected automatically when no credentials are configured, so the game is
fully playable with zero setup.

Known limitation, stated rather than hidden: Gist updates are
read-modify-write with no compare-and-swap, so two players submitting in the
same instant can clobber one another. `_merge` re-reads and unions before
each retry, which shrinks but does not eliminate the window. At classroom
scale this is acceptable; at real concurrency you would move to Postgres.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import requests

GIST_FILENAME = "leaderboard.json"
LOCAL_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "leaderboard.json"
API_ROOT = "https://api.github.com"
REQUEST_TIMEOUT = 8


def _secret(key: str, default: str = "") -> str:
    """Read config from Streamlit secrets, falling back to the environment."""
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


def make_entry(
    username: str,
    score: int,
    wave: int,
    difficulty: str,
    nodes: int,
    turns: int,
    stealth: float,
) -> dict:
    return {
        "username": username.strip()[:18] or "ANONYMOUS",
        "score": int(score),
        "wave": int(wave),
        "difficulty": difficulty,
        "nodes": int(nodes),
        "turns": int(turns),
        "stealth": round(float(stealth), 3),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class LeaderboardStore(ABC):
    """Interface every backend satisfies. Swapping backends changes nothing else."""

    name = "abstract"
    durable = False

    @abstractmethod
    def load(self) -> list[dict]: ...

    @abstractmethod
    def append(self, entry: dict) -> bool: ...


class LocalStore(LeaderboardStore):
    """JSON on local disk. Fine locally; ephemeral on Streamlit Cloud."""

    name = "local"
    durable = False

    def load(self) -> list[dict]:
        try:
            if LOCAL_PATH.exists():
                data = json.loads(LOCAL_PATH.read_text())
                return data.get("entries", [])
        except Exception:
            pass
        return []

    def append(self, entry: dict) -> bool:
        try:
            entries = self.load()
            entries.append(entry)
            LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            LOCAL_PATH.write_text(
                json.dumps({"version": 1, "entries": entries}, indent=2)
            )
            return True
        except Exception:
            return False


class GistStore(LeaderboardStore):
    """A public GitHub Gist used as a small append-only table."""

    name = "gist"
    durable = True

    def __init__(self, gist_id: str, token: str):
        self.gist_id = gist_id
        self.token = token

    def _headers(self) -> dict:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def load(self) -> list[dict]:
        try:
            r = requests.get(
                f"{API_ROOT}/gists/{self.gist_id}",
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            files = r.json().get("files", {})
            if GIST_FILENAME not in files:
                return []
            content = files[GIST_FILENAME].get("content") or "{}"
            return json.loads(content).get("entries", [])
        except Exception:
            return []

    def append(self, entry: dict) -> bool:
        """Read, merge, write. Retries on failure with a fresh read."""
        for attempt in range(3):
            try:
                entries = self.load()
                entries = _merge(entries, [entry])
                payload = {
                    "files": {
                        GIST_FILENAME: {
                            "content": json.dumps(
                                {"version": 1, "entries": entries}, indent=1
                            )
                        }
                    }
                }
                r = requests.patch(
                    f"{API_ROOT}/gists/{self.gist_id}",
                    headers=self._headers(),
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code < 300:
                    return True
            except Exception:
                pass
            time.sleep(0.4 * (attempt + 1))
        return False


def _merge(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Union by (username, timestamp, score); newest first, capped."""
    seen = set()
    out = []
    for e in incoming + existing:
        key = (e.get("username"), e.get("at"), e.get("score"))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    out.sort(key=lambda e: e.get("score", 0), reverse=True)
    return out[:500]


def get_store() -> LeaderboardStore:
    """Pick the durable backend when configured, else fall back silently."""
    gist_id = _secret("GIST_ID")
    token = _secret("GITHUB_TOKEN")
    if gist_id and token:
        return GistStore(gist_id, token)
    return LocalStore()


# --------------------------------------------------------------- projections


def top_entries(entries: list[dict], limit: int = 10) -> list[dict]:
    return sorted(entries, key=lambda e: e.get("score", 0), reverse=True)[:limit]


def personal_best(entries: list[dict], username: str) -> dict | None:
    mine = [
        e for e in entries if e.get("username", "").lower() == username.strip().lower()
    ]
    return max(mine, key=lambda e: e.get("score", 0)) if mine else None


def personal_history(entries: list[dict], username: str, limit: int = 8) -> list[dict]:
    mine = [
        e for e in entries if e.get("username", "").lower() == username.strip().lower()
    ]
    return sorted(mine, key=lambda e: e.get("at", ""), reverse=True)[:limit]


def champion(entries: list[dict]) -> dict | None:
    """The single best run on record. Gets the banner."""
    return max(entries, key=lambda e: e.get("score", 0)) if entries else None


def rank_of(entries: list[dict], score: int) -> int:
    """1-indexed placement a given score would take."""
    return sum(1 for e in entries if e.get("score", 0) > score) + 1
