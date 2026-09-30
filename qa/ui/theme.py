"""TradingView 風格的深色主題：配色、CSS、Plotly 樣式、共用的 HTML 元件。"""
from __future__ import annotations

import html

import plotly.graph_objects as go

# ── 配色（和 TradingView 深色主題一致，嵌入的圖表才會像同一個產品） ──
BG = "#131722"          # 頁面底色
PANEL = "#1e222d"       # 卡片 / 圖表底色
PANEL_HI = "#262b38"    # 次要底色
BORDER = "#2a2e39"
GRID = "#252936"
INK = "#f0f3fa"         # 主要文字（亮）
TEXT = "#d1d4dc"        # 一般文字
MUTED = "#787b86"       # 次要文字、座標軸
ACCENT = "#2962ff"      # 重點色
UP = "#26a69a"          # 獲利 / 上漲（搭配 ▲ 符號，不只靠顏色）
DOWN = "#ef5350"        # 虧損 / 下跌（搭配 ▼）
WARN = "#ff9800"
# 類別色：依固定順序使用；漲跌色保留給盈虧，不拿來當類別
SERIES = ["#2962ff", "#ff9800", "#ab47bc", "#00bcd4", "#e91e63", "#8bc34a", "#fdd835", "#90a4ae"]
DIVERGING = [[0.0, DOWN], [0.5, "#2a2e39"], [1.0, UP]]   # 虧 ↔ 平 ↔ 賺

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Noto+Sans+TC:wght@400;500;700&display=swap');

html, body, .stApp, button, input, textarea, select, [data-testid="stSidebar"] {{
  font-family: 'Inter', 'Noto Sans TC', -apple-system, sans-serif !important;
}}
.stApp {{ background: {BG}; }}
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], #MainMenu, footer {{ display: none !important; }}
[data-testid="stDecoration"] {{ display: none !important; }}
[data-testid="stHeader"] {{ background: {BG}; border-bottom: 1px solid {BORDER}; }}
.block-container {{ padding-top: 4.2rem; padding-bottom: 4rem; max-width: 1480px; }}

/* 標題 */
.qa-title {{ display:flex; align-items:baseline; gap:.8rem; flex-wrap:wrap; margin: .2rem 0 .15rem; }}
.qa-title h1 {{ font-size:1.55rem; font-weight:600; color:{INK}; margin:0; padding:0; letter-spacing:-.01em; }}
.qa-title .tag {{ font-size:.7rem; letter-spacing:.12em; text-transform:uppercase; color:{ACCENT};
  border:1px solid rgba(41,98,255,.45); border-radius:4px; padding:.1rem .45rem; }}
.qa-sub {{ color:{MUTED}; font-size:.88rem; margin-bottom:1.1rem; }}
.qa-section {{ font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; color:{MUTED};
  font-weight:600; margin:1.4rem 0 .5rem; }}

/* 標籤 */
.chip {{ display:inline-block; font-family:'JetBrains Mono', monospace; font-size:.74rem; color:{TEXT};
  background:{PANEL}; border:1px solid {BORDER}; border-radius:4px; padding:.12rem .5rem; margin:0 .3rem .35rem 0; }}
.chip.src-mt5 {{ color:{WARN}; border-color:rgba(255,152,0,.45); }}
.chip.src-python {{ color:#82a8ff; border-color:rgba(41,98,255,.45); }}

/* KPI 卡片 */
.kpi-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:.6rem; margin:.4rem 0 1rem; }}
.kpi {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:6px; padding:.75rem .9rem .7rem; }}
.kpi-label {{ color:{MUTED}; font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; margin-bottom:.3rem; }}
.kpi-value {{ font-family:'JetBrains Mono', monospace; font-size:1.4rem; font-weight:500; color:{INK}; line-height:1.15; }}
.kpi-delta {{ font-family:'JetBrains Mono', monospace; font-size:.75rem; margin-top:.28rem; color:{MUTED}; }}
.kpi-delta.up {{ color:{UP}; }} .kpi-delta.down {{ color:{DOWN}; }}

/* 報告表 */
.rep-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(270px, 1fr)); gap:.6rem; margin:.3rem 0 1rem; }}
.rep {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:6px; padding:.75rem .95rem .5rem; }}
.rep h4 {{ margin:0 0 .45rem; font-size:.7rem; letter-spacing:.1em; text-transform:uppercase; color:{MUTED}; font-weight:600; }}
.rep-row {{ display:flex; justify-content:space-between; gap:1rem; padding:.27rem 0; border-bottom:1px solid {GRID}; font-size:.85rem; }}
.rep-row:last-child {{ border-bottom:none; }}
.rep-row span:first-child {{ color:{TEXT}; }}
.rep-row span:last-child {{ font-family:'JetBrains Mono', monospace; color:{INK}; text-align:right; }}
.rep-row .up {{ color:{UP} !important; }} .rep-row .down {{ color:{DOWN} !important; }}

/* 「怎麼看」說明 */
.explain {{ border-left:2px solid {ACCENT}; background:rgba(41,98,255,.06); border-radius:0 6px 6px 0;
  padding:.55rem .85rem; margin:-.2rem 0 1.2rem; color:{TEXT}; font-size:.84rem; line-height:1.65; }}
.explain b.k {{ color:#82a8ff; font-weight:600; margin-right:.35rem; }}

/* 狀態列 */
.status {{ border-radius:6px; padding:.5rem .85rem; font-size:.84rem; margin:0 0 1rem; border:1px solid; }}
.status.ok {{ background:rgba(38,166,154,.08); border-color:rgba(38,166,154,.4); color:#7fd6cd; }}
.status.bad {{ background:rgba(239,83,80,.08); border-color:rgba(239,83,80,.45); color:#f5a3a1; }}
.status.warn {{ background:rgba(255,152,0,.08); border-color:rgba(255,152,0,.45); color:#ffc266; }}

/* 空狀態 */
.empty {{ border:1px dashed {BORDER}; border-radius:8px; padding:2.2rem 1.5rem; text-align:center; color:{MUTED}; margin:1rem 0; }}
.empty h3 {{ color:{INK}; font-size:1.05rem; font-weight:600; margin:0 0 .4rem; }}

/* 原生元件微調 */
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color:{BORDER} !important; border-radius:8px !important; background:{PANEL}; }}
button[data-baseweb="tab"] {{ font-size:.88rem; padding:.55rem .1rem; }}
button[data-baseweb="tab"][aria-selected="true"] {{ color:{INK}; }}
[data-baseweb="tab-highlight"] {{ background:{ACCENT} !important; height:2px !important; }}
[data-baseweb="tab-border"] {{ background:{BORDER} !important; }}
[data-testid="stDataFrame"] {{ border:1px solid {BORDER}; border-radius:6px; }}
[data-testid="stExpander"] details {{ border-color:{BORDER}; border-radius:6px; background:{PANEL}; }}
.hint {{ color:{MUTED}; font-size:.82rem; line-height:1.6; }}
</style>
"""


def esc(s) -> str:
    return html.escape(str(s))


def header(title: str, sub: str = "", tag: str = "") -> str:
    t = f'<span class="tag">{esc(tag)}</span>' if tag else ""
    s = f'<div class="qa-sub">{esc(sub)}</div>' if sub else ""
    return f'<div class="qa-title"><h1>{esc(title)}</h1>{t}</div>{s}'


def section(title: str) -> str:
    return f'<div class="qa-section">{esc(title)}</div>'


def chips(items: list) -> str:
    """items：字串，或 (字串, css class)"""
    out = []
    for it in items:
        text, cls = (it, "") if isinstance(it, str) else it
        out.append(f'<span class="chip {cls}">{esc(text)}</span>')
    return "".join(out)


def kpi_cards(items: list[dict]) -> str:
    """items: [{label, value, delta?, trend? ('up'|'down'|None)}]"""
    cards = []
    for it in items:
        delta = ""
        if it.get("delta"):
            trend = it.get("trend")
            icon = "▲ " if trend == "up" else "▼ " if trend == "down" else ""
            delta = f'<div class="kpi-delta {trend or ""}">{icon}{esc(it["delta"])}</div>'
        cards.append(f'<div class="kpi"><div class="kpi-label">{esc(it["label"])}</div>'
                     f'<div class="kpi-value">{esc(it["value"])}</div>{delta}</div>')
    return f'<div class="kpi-grid">{"".join(cards)}</div>'


def report_table(sections: list[tuple[str, list[tuple]]]) -> str:
    """sections: [(標題, [(名稱, 數值字串, 'up'|'down'|None), ...]), ...]"""
    out = []
    for title, rows in sections:
        body = "".join(
            f'<div class="rep-row"><span>{esc(r[0])}</span>'
            f'<span class="{r[2] if len(r) > 2 and r[2] else ""}">{esc(r[1])}</span></div>' for r in rows)
        out.append(f'<div class="rep"><h4>{esc(title)}</h4>{body}</div>')
    return f'<div class="rep-grid">{"".join(out)}</div>'


def explain(text: str) -> str:
    """圖表下方的「怎麼看」說明。text 可含簡單 HTML（<b>）。"""
    return f'<div class="explain"><b class="k">怎麼看</b>{text}</div>'


def status(kind: str, text: str) -> str:
    icon = {"ok": "✓", "bad": "✕", "warn": "!"}[kind]
    return f'<div class="status {kind}">{icon}&nbsp; {esc(text)}</div>'


def empty(title: str, text: str) -> str:
    return f'<div class="empty"><h3>{esc(title)}</h3>{esc(text)}</div>'


def style(fig: go.Figure, height: int = 360, title: str | None = None, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, template="plotly_dark",
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        font=dict(family="Inter, Noto Sans TC, sans-serif", color=TEXT, size=12),
        title=dict(text=title, font=dict(size=13, color=INK), x=0.012, y=0.975) if title else None,
        margin=dict(l=12, r=16, t=46 if title else 14, b=12),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=PANEL_HI, bordercolor=BORDER, font=dict(color=INK, family="JetBrains Mono, monospace")),
        showlegend=legend,
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", yanchor="bottom",
                    bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT, size=11)),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=BORDER, zerolinecolor=BORDER, tickfont=dict(color=MUTED, size=11))
    fig.update_yaxes(gridcolor=GRID, linecolor=BORDER, zerolinecolor=BORDER, tickfont=dict(color=MUTED, size=11))
    return fig
