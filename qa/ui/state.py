"""跨頁共用：回測紀錄庫、頁面切換、數字格式。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import runs as R

PAGES: dict = {}          # 由 app.py 註冊：名稱 → st.Page，用來 st.switch_page


# ── 格式 ──
def money(v):
    return "—" if v is None or pd.isna(v) else f"{v:,.0f}"


def pct(v, d=1):
    return "—" if v is None or pd.isna(v) else f"{v * 100:.{d}f}%"


def num(v, d=2):
    if v is None or pd.isna(v):
        return "—"
    return "∞" if np.isinf(v) else f"{v:.{d}f}"


def sign(v):
    return None if v is None or pd.isna(v) or v == 0 else ("up" if v > 0 else "down")


# ── 回測紀錄庫 ──
@st.cache_data(ttl=60, show_spinner=False)
def _repo_runs_json() -> list[str]:
    return [r.to_json() for r in R.load_dir()]


def library() -> dict[str, R.Run]:
    """全部回測：repo 裡永久保存的 + 這次連線新增的（快速測試 / 上傳）。新的在前。"""
    lib = {}
    for text in _repo_runs_json():
        try:
            r = R.Run.from_json(text, persisted=True)
            lib[r.id] = r
        except Exception:
            continue
    lib.update(st.session_state.get("runs", {}))
    return dict(sorted(lib.items(), key=lambda kv: kv[1].created, reverse=True))


def add_run(run: R.Run):
    st.session_state.setdefault("runs", {})[run.id] = run
    st.session_state.setdefault("stats_cache", {}).pop(run.id, None)


def stats_of(run: R.Run) -> dict:
    cache = st.session_state.setdefault("stats_cache", {})
    if run.id not in cache:
        cache[run.id] = run.stats()
    return cache[run.id]


def open_run(run_id: str):
    st.session_state["active_run"] = run_id
    go("回測分析")


def compare(run_ids: list[str]):
    st.session_state["compare_ids"] = list(run_ids)
    go("比較")


def go(page: str):
    if page in PAGES:
        st.switch_page(PAGES[page])
