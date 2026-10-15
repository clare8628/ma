"""零相依套件的圖表產生器：純字串組裝 SVG，輸出單一自包含 HTML 報告。

主圖：TQQQ 收盤價 + 長期 SMA(預設200日，框架) + 短期 EMA 10日/20日(觸發)，
      兩條短期 EMA 各自可用圖上開關隱藏，並標示黃金/死亡交叉點及重大金融事件時間點。
      支援時間軸延長追溯回 TQQQ 2010 年成立開始（全歷史 All-Time）。
      支援線性座標 (Linear) 與對數座標 (Log Scale) 即時切換，便於長週期觀察。
      右側延伸利用：繪製右側價格刻度、即時價格/均線定位標籤 (Price Pills)。
副圖：RSI(14)，含 45/50/55/65/70 參考線（避險/進場下緣/中線/超買/過熱）及最新 RSI 指標標籤。
兩圖皆含縱軸（雙側數值刻度）與橫軸（日期/年份刻度）。
報告同時整合版本時間戳記、目前遵守之「買入與賣出規則」區塊及重大金融事件時間軸。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from .rules_engine import Rule, load_rules
from .signals import DailyIndicators, Recommendation

VERSION = "v1.3.0"

# 擴充寬度以延伸利用右側空間
WIDTH = 1120
MARGIN_LEFT = 56
MARGIN_RIGHT = 140
MARGIN_TOP = 46
MARGIN_BOTTOM = 40
PRICE_PLOT_HEIGHT = 440
RSI_PLOT_HEIGHT = 280

SVG_WIDTH = MARGIN_LEFT + WIDTH + MARGIN_RIGHT  # 56 + 1120 + 140 = 1316


def load_events(path: str = "config/events.json") -> List[dict]:
    """載入重大金融事件清單。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _xs(n: int) -> List[float]:
    if n <= 1:
        return [MARGIN_LEFT]
    step = WIDTH / (n - 1)
    return [MARGIN_LEFT + i * step for i in range(n)]


def _polyline(xs: List[float], ys: List[Optional[float]], color: str, width: float = 1.6) -> str:
    points = []
    for x, y in zip(xs, ys):
        if y is None:
            continue
        points.append(f"{x:.1f},{y:.1f}")
    if len(points) < 2:
        return ""
    return f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="{width}" />'


def _format_price(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    if v >= 100:
        return f"{v:.0f}"
    if v < 1:
        return f"{v:.2f}"
    return f"{v:.1f}"


def _y_axis(vmin: float, vmax: float, plot_top: float, plot_height: float, fmt=_format_price, ticks: int = 6) -> str:
    """畫出線性縱軸刻度線、左右雙側數值標籤與水平格線，充分利用兩側空間。"""
    span = (vmax - vmin) or 1.0
    parts = []
    for i in range(ticks):
        frac = i / (ticks - 1)
        value = vmin + frac * span
        y = plot_top + plot_height - frac * plot_height
        parts.append(
            f'<line x1="{MARGIN_LEFT}" y1="{y:.1f}" x2="{MARGIN_LEFT + WIDTH}" y2="{y:.1f}" '
            f'stroke="#e2e8f0" stroke-width="1" />'
            f'<text x="{MARGIN_LEFT - 8}" y="{y + 4:.1f}" font-size="11" fill="#475569" text-anchor="end">{fmt(value)}</text>'
            f'<text x="{MARGIN_LEFT + WIDTH + 8}" y="{y + 4:.1f}" font-size="11" fill="#94a3b8" text-anchor="start">{fmt(value)}</text>'
        )
    return "".join(parts)


def _log_y_axis(vmin: float, vmax: float, plot_top: float, plot_height: float) -> Tuple[str, Any]:
    """計算對數座標刻度與水平格線，適合長達十餘年的高倍數資產展示。"""
    safe_vmin = max(vmin, 0.05)
    safe_vmax = max(vmax, safe_vmin * 1.5)
    log_min = math.log10(safe_vmin)
    log_max = math.log10(safe_vmax)
    log_span = (log_max - log_min) or 1.0

    def scale_log(v: Optional[float]) -> Optional[float]:
        if v is None or v <= 0:
            return None
        lv = math.log10(max(v, 0.05))
        return plot_top + plot_height - (lv - log_min) / log_span * plot_height

    candidates = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0]
    ticks = [c for c in candidates if safe_vmin * 0.75 <= c <= safe_vmax * 1.25]
    if len(ticks) < 4:
        ticks = [0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]

    parts = []
    for val in ticks:
        y = scale_log(val)
        if y is None or y < plot_top - 5 or y > plot_top + plot_height + 5:
            continue
        parts.append(
            f'<line x1="{MARGIN_LEFT}" y1="{y:.1f}" x2="{MARGIN_LEFT + WIDTH}" y2="{y:.1f}" '
            f'stroke="#e2e8f0" stroke-width="1" />'
            f'<text x="{MARGIN_LEFT - 8}" y="{y + 4:.1f}" font-size="11" fill="#475569" text-anchor="end">{_format_price(val)}</text>'
            f'<text x="{MARGIN_LEFT + WIDTH + 8}" y="{y + 4:.1f}" font-size="11" fill="#94a3b8" text-anchor="start">{_format_price(val)}</text>'
        )
    return "".join(parts), scale_log


def _x_axis(dates: List[str], xs: List[float], y_bottom: float, tick_count: int = 9) -> str:
    """畫出橫軸刻度線與日期標籤，針對長年期全歷史與短天期智慧自適應。"""
    n = len(dates)
    if n == 0:
        return ""
    if n > 700:
        # 多年度（自 2010 年 TQQQ 成立以來全歷史）
        year_indices = []
        last_year = None
        for i, d in enumerate(dates):
            yr = d[:4]
            if yr != last_year:
                year_indices.append((i, yr))
                last_year = yr
        # 標記年度刻度
        step_yr = 1 if len(year_indices) <= 18 else 2
        idxs = [item for idx, item in enumerate(year_indices) if idx % step_yr == 0]
        if idxs and idxs[-1][0] != n - 1:
            idxs.append((n - 1, dates[-1]))

        parts = []
        for i, label in idxs:
            x = xs[i]
            parts.append(
                f'<line x1="{x:.1f}" y1="{y_bottom}" x2="{x:.1f}" y2="{y_bottom + 5}" stroke="#94a3b8" stroke-width="1" />'
                f'<text x="{x:.1f}" y="{y_bottom + 18}" font-size="10" fill="#475569" text-anchor="middle">{label}</text>'
            )
        return "".join(parts)
    else:
        # 短天期或局部時間軸
        step = max(1, (n - 1) // (tick_count - 1)) if n > 1 else 1
        idxs = list(range(0, n, step))
        if idxs[-1] != n - 1:
            idxs.append(n - 1)
        parts = []
        for i in idxs:
            x = xs[i]
            parts.append(
                f'<line x1="{x:.1f}" y1="{y_bottom}" x2="{x:.1f}" y2="{y_bottom + 5}" stroke="#94a3b8" stroke-width="1" />'
                f'<text x="{x:.1f}" y="{y_bottom + 18}" font-size="10" fill="#475569" text-anchor="middle">{dates[i]}</text>'
            )
        return "".join(parts)


def _render_price_pills(items: List[Tuple[str, float, Optional[float], str]], x_start: float, plot_top: float, plot_height: float) -> str:
    """在圖表右側空白處繪製最新價格與各均線的定位標籤 (Price Pills)，避免標籤重疊。"""
    valid = [(name, val, y, color) for name, val, y, color in items if y is not None]
    if not valid:
        return ""

    valid.sort(key=lambda it: it[2])
    adjusted_y = [it[2] for it in valid]

    for i in range(1, len(adjusted_y)):
        if adjusted_y[i] - adjusted_y[i - 1] < 20:
            adjusted_y[i] = adjusted_y[i - 1] + 20

    for i in range(len(adjusted_y) - 2, -1, -1):
        if adjusted_y[i + 1] - adjusted_y[i] < 20:
            adjusted_y[i] = adjusted_y[i + 1] - 20

    svg_parts = []
    for (name, val, orig_y, color), adj_y in zip(valid, adjusted_y):
        svg_parts.append(
            f'<path d="M {x_start} {orig_y:.1f} L {x_start + 16} {adj_y:.1f} L {x_start + 24} {adj_y:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="1.2" stroke-dasharray="2,2" />'
            f'<rect x="{x_start + 26}" y="{adj_y - 9:.1f}" width="102" height="18" rx="4" fill="{color}" />'
            f'<text x="{x_start + 77}" y="{adj_y + 4:.1f}" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">'
            f'{name} {_format_price(val)}</text>'
        )
    return "".join(svg_parts)


def _render_price_svg(
    ind: DailyIndicators,
    window: int,
    long_sma_period: int,
    ema_fast_period: int,
    ema_slow_period: int,
    events: Optional[List[dict]] = None,
) -> str:
    dates = ind.dates[-window:]
    close = ind.tqqq_close[-window:]
    long_sma = ind.tqqq_sma_chart_long[-window:]
    ema_fast = ind.tqqq_ema_fast[-window:]
    ema_slow = ind.tqqq_ema_slow[-window:]

    all_vals = [
        v for v in close + [x for x in long_sma if x is not None] +
        [x for x in ema_fast if x is not None] + [x for x in ema_slow if x is not None]
        if v is not None
    ]
    vmin, vmax = min(all_vals), max(all_vals)
    pad = (vmax - vmin) * 0.05 or 1.0
    vmin_lin, vmax_lin = vmin - pad, vmax + pad
    span_lin = (vmax_lin - vmin_lin) or 1.0

    plot_top = MARGIN_TOP
    plot_height = PRICE_PLOT_HEIGHT

    # 線性座標換算
    def scale_lin(v):
        if v is None:
            return None
        return plot_top + plot_height - (v - vmin_lin) / span_lin * plot_height

    y_close_lin = [scale_lin(v) for v in close]
    y_long_lin = [scale_lin(v) for v in long_sma]
    y_fast_lin = [scale_lin(v) for v in ema_fast]
    y_slow_lin = [scale_lin(v) for v in ema_slow]
    xs = _xs(len(dates))

    # 對數座標換算
    y_axis_log_svg, scale_log = _log_y_axis(vmin, vmax, plot_top, plot_height)
    y_close_log = [scale_log(v) for v in close]
    y_long_log = [scale_log(v) for v in long_sma]
    y_fast_log = [scale_log(v) for v in ema_fast]
    y_slow_log = [scale_log(v) for v in ema_slow]

    # 黃金交叉與死亡交叉標記 (線性與對數)
    markers_lin, markers_log = [], []
    for i in range(1, len(dates)):
        f0, s0 = ema_fast[i - 1], ema_slow[i - 1]
        f1, s1 = ema_fast[i], ema_slow[i]
        if None in (f0, s0, f1, s1):
            continue
        if f0 <= s0 and f1 > s1:
            markers_lin.append((xs[i], scale_lin(close[i]), "#16a34a", "黃金交叉", dates[i]))
            markers_log.append((xs[i], scale_log(close[i]), "#16a34a", "黃金交叉", dates[i]))
        elif f0 >= s0 and f1 < s1:
            markers_lin.append((xs[i], scale_lin(close[i]), "#dc2626", "死亡交叉", dates[i]))
            markers_log.append((xs[i], scale_log(close[i]), "#dc2626", "死亡交叉", dates[i]))

    radius = 3.5 if len(dates) > 500 else 5.0
    marker_lin_svg = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}" opacity="0.85"><title>{label} {date}</title></circle>'
        for x, y, color, label, date in markers_lin if y is not None
    )
    marker_log_svg = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}" opacity="0.85"><title>{label} {date}</title></circle>'
        for x, y, color, label, date in markers_log if y is not None
    )

    # 重大金融事件標記 (垂直標記線與圖釘標籤，防文字重疊上下交錯)
    events_svg = []
    if events:
        valid_evs = [ev for ev in events if dates and dates[0] <= ev.get("date", "") <= dates[-1]]
        last_ev_x = -999.0
        stagger = 0
        for ev in valid_evs:
            ev_date = ev.get("date", "")
            match_idx = None
            for idx, d in enumerate(dates):
                if d >= ev_date:
                    match_idx = idx
                    break
            if match_idx is None:
                match_idx = len(dates) - 1

            ev_x = xs[match_idx]
            if abs(ev_x - last_ev_x) < 55:
                stagger = (stagger + 1) % 2
            else:
                stagger = 0
            last_ev_x = ev_x

            text_y = plot_top - 6 if stagger == 0 else plot_top - 18
            title = ev.get("title", "事件")
            desc = ev.get("description", "")
            events_svg.append(
                f'<g class="financial-event">'
                f'<line x1="{ev_x:.1f}" y1="{plot_top}" x2="{ev_x:.1f}" y2="{plot_top + plot_height}" '
                f'stroke="#d97706" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.75" />'
                f'<polygon points="{ev_x-4:.1f},{plot_top-2} {ev_x+4:.1f},{plot_top-2} {ev_x:.1f},{plot_top+6}" fill="#f59e0b" />'
                f'<text x="{ev_x:.1f}" y="{text_y:.1f}" font-size="9" fill="#b45309" text-anchor="middle" font-weight="600">{title}</text>'
                f'<title>[{ev_date}] {title}：{desc}</title>'
                f'</g>'
            )

    # 右側 Price Pills (線性與對數)
    pill_items_lin = [
        ("TQQQ", close[-1], y_close_lin[-1], "#2563eb"),
        (f"EMA{ema_fast_period}", ema_fast[-1], y_fast_lin[-1], "#0d9488"),
        (f"EMA{ema_slow_period}", ema_slow[-1], y_slow_lin[-1], "#ea580c"),
        (f"SMA{long_sma_period}", long_sma[-1], y_long_lin[-1], "#9333ea"),
    ]
    pills_lin_svg = _render_price_pills(pill_items_lin, MARGIN_LEFT + WIDTH, plot_top, plot_height)

    pill_items_log = [
        ("TQQQ", close[-1], y_close_log[-1], "#2563eb"),
        (f"EMA{ema_fast_period}", ema_fast[-1], y_fast_log[-1], "#0d9488"),
        (f"EMA{ema_slow_period}", ema_slow[-1], y_slow_log[-1], "#ea580c"),
        (f"SMA{long_sma_period}", long_sma[-1], y_long_log[-1], "#9333ea"),
    ]
    pills_log_svg = _render_price_pills(pill_items_log, MARGIN_LEFT + WIDTH, plot_top, plot_height)

    total_height = MARGIN_TOP + PRICE_PLOT_HEIGHT + MARGIN_BOTTOM

    labels = f'''
    <text x="{MARGIN_LEFT}" y="18" font-size="13" fill="#2563eb">■ TQQQ 收盤價</text>
    <text x="{MARGIN_LEFT + 150}" y="18" font-size="13" fill="#9333ea">■ 長期 SMA({long_sma_period}日,框架)</text>
    <text x="{MARGIN_LEFT + 360}" y="18" font-size="13" fill="#0d9488">■ 短期 EMA({ema_fast_period}日)</text>
    <text x="{MARGIN_LEFT + 520}" y="18" font-size="13" fill="#ea580c">■ 短期 EMA({ema_slow_period}日)</text>
    <text x="{MARGIN_LEFT + 680}" y="18" font-size="13" fill="#16a34a">● 黃金交叉</text>
    <text x="{MARGIN_LEFT + 780}" y="18" font-size="13" fill="#dc2626">● 死亡交叉</text>
    <text x="{MARGIN_LEFT + 890}" y="18" font-size="13" fill="#d97706">▼ 重大金融事件</text>
    '''

    y_axis_lin_svg = _y_axis(vmin_lin, vmax_lin, plot_top, plot_height)
    x_axis_svg = _x_axis(dates, xs, plot_top + plot_height)

    toggle_bar = f'''
    <div style="font-size:13px;margin:6px 0 10px;color:#334155;display:flex;flex-wrap:wrap;gap:16px;align-items:center;">
      <label style="cursor:pointer;font-weight:600;color:#0f172a;background:#f1f5f9;padding:3px 8px;border-radius:6px;border:1px solid #cbd5e1;">
        座標模式：
        <select onchange="togglePriceScale(this.value)" style="border:none;background:transparent;font-size:12px;font-weight:600;color:#0f172a;cursor:pointer;">
          <option value="linear" selected>線性座標 (Linear)</option>
          <option value="log">對數座標 (Log Scale，推薦長歷史)</option>
        </select>
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="document.querySelectorAll('.ema-fast-layer').forEach(el=>el.style.display=this.checked?'inline':'none')"> 顯示短期 EMA({ema_fast_period}日)
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="document.querySelectorAll('.ema-slow-layer').forEach(el=>el.style.display=this.checked?'inline':'none')"> 顯示短期 EMA({ema_slow_period}日)
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="document.querySelectorAll('.cross-marker-layer').forEach(el=>el.style.display=this.checked?'inline':'none')"> 顯示黃金/死亡交叉
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="document.querySelectorAll('.financial-event').forEach(el=>el.style.display=this.checked?'inline':'none')"> 顯示重大金融事件標記
      </label>
      <span style="color:#64748b;font-size:12px;margin-left:auto;">（時間軸追溯自 2010 年 TQQQ 成立開始 • 右側標記最新均線定位）</span>
    </div>
    '''

    line_width = 1.4 if len(dates) > 1000 else 1.8
    ma_width = 1.2 if len(dates) > 1000 else 1.4

    return f'''
    {toggle_bar}
    <div style="overflow-x:auto;">
      <svg viewBox="0 0 {SVG_WIDTH} {total_height}" width="100%" height="{total_height}" style="background:#fff;max-width:100%;height:auto;display:block;" xmlns="http://www.w3.org/2000/svg">
        {labels}
        {x_axis_svg}
        {"".join(events_svg)}

        <!-- 線性座標圖層 -->
        <g id="plot-linear">
          {y_axis_lin_svg}
          {_polyline(xs, y_close_lin, "#2563eb", line_width)}
          {_polyline(xs, y_long_lin, "#9333ea", ma_width)}
          <g class="ema-fast-layer">{_polyline(xs, y_fast_lin, "#0d9488", ma_width)}</g>
          <g class="ema-slow-layer">{_polyline(xs, y_slow_lin, "#ea580c", ma_width)}</g>
          <g class="cross-marker-layer">{marker_lin_svg}</g>
          {pills_lin_svg}
        </g>

        <!-- 對數座標圖層 -->
        <g id="plot-log" style="display:none;">
          {y_axis_log_svg}
          {_polyline(xs, y_close_log, "#2563eb", line_width)}
          {_polyline(xs, y_long_log, "#9333ea", ma_width)}
          <g class="ema-fast-layer">{_polyline(xs, y_fast_log, "#0d9488", ma_width)}</g>
          <g class="ema-slow-layer">{_polyline(xs, y_slow_log, "#ea580c", ma_width)}</g>
          <g class="cross-marker-layer">{marker_log_svg}</g>
          {pills_log_svg}
        </g>
      </svg>
    </div>
    '''


def _render_rsi_svg(ind: DailyIndicators, window: int) -> str:
    dates = ind.dates[-window:]
    rsi = ind.tqqq_rsi[-window:]
    xs = _xs(len(dates))

    plot_top = MARGIN_TOP
    plot_height = RSI_PLOT_HEIGHT

    def scale_one(v):
        if v is None:
            return None
        return plot_top + plot_height - (v / 100) * plot_height

    y_rsi = [scale_one(v) for v in rsi]

    y_axis_svg = _y_axis(0, 100, plot_top, plot_height, fmt=lambda v: f"{v:.0f}", ticks=6)
    x_axis_svg = _x_axis(dates, xs, plot_top + plot_height)

    ref_lines = []
    for level, color, label in [
        (70, "#dc2626", "70 過熱止盈"),
        (65, "#f59e0b", "65 超買線"),
        (55, "#64748b", "55 中線"),
        (50, "#0ea5e9", "50 進場下緣"),
        (45, "#dc2626", "45 避險"),
    ]:
        y = scale_one(level)
        ref_lines.append(
            f'<line x1="{MARGIN_LEFT}" y1="{y:.1f}" x2="{MARGIN_LEFT + WIDTH}" y2="{y:.1f}" '
            f'stroke="{color}" stroke-width="1" stroke-dasharray="4,3" />'
            f'<text x="{MARGIN_LEFT + WIDTH + 8}" y="{y+3:.1f}" font-size="10" fill="{color}">{label}</text>'
        )

    latest_rsi_svg = ""
    if rsi and rsi[-1] is not None:
        curr_y = scale_one(rsi[-1])
        latest_rsi_svg = (
            f'<path d="M {MARGIN_LEFT + WIDTH} {curr_y:.1f} L {MARGIN_LEFT + WIDTH + 68} {curr_y:.1f}" fill="none" stroke="#0f172a" stroke-width="1.2" />'
            f'<rect x="{MARGIN_LEFT + WIDTH + 70}" y="{curr_y - 9:.1f}" width="64" height="18" rx="4" fill="#0f172a" />'
            f'<text x="{MARGIN_LEFT + WIDTH + 102}" y="{curr_y + 4:.1f}" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">RSI {rsi[-1]:.1f}</text>'
        )

    total_height = MARGIN_TOP + RSI_PLOT_HEIGHT + MARGIN_BOTTOM
    line_width = 1.2 if len(dates) > 1000 else 1.6

    return f'''
    <div style="overflow-x:auto;">
      <svg viewBox="0 0 {SVG_WIDTH} {total_height}" width="100%" height="{total_height}" style="background:#fff;max-width:100%;height:auto;display:block;" xmlns="http://www.w3.org/2000/svg">
        <text x="{MARGIN_LEFT}" y="18" font-size="13" fill="#0f172a">■ TQQQ RSI(14) 震盪指標</text>
        {y_axis_svg}
        {x_axis_svg}
        {''.join(ref_lines)}
        {latest_rsi_svg}
        {_polyline(xs, y_rsi, "#0f172a", line_width)}
      </svg>
    </div>
    '''


def _render_rules_block(rules: List[Rule], recommendation: Recommendation) -> str:
    """產生目前遵守的「買入與賣出規則」區塊。"""
    matched_ids = {r["id"] for r in recommendation.matched_rules}

    def get_category_badge(action: str) -> str:
        if action == "BUY":
            return '<span class="badge-cat badge-buy">買入進場</span>'
        elif action in ("FORCE_EXIT", "SELL_ALL"):
            return '<span class="badge-cat badge-sell">賣出出場</span>'
        elif action in ("REDUCE_50", "TRIM_PARTIAL"):
            return '<span class="badge-cat badge-trim">減碼止盈</span>'
        elif action == "SKIP_ENTRY_OVERBOUGHT":
            return '<span class="badge-cat badge-filter">進場濾網</span>'
        elif action == "REBALANCE":
            return '<span class="badge-cat badge-rebal">年度再平衡</span>'
        return '<span class="badge-cat badge-neutral">監控規則</span>'

    def format_condition_friendly(rule_id: str, conds: List[dict]) -> str:
        mapping = {
            "R1_bear_lockout": "QQQ 收盤價 &lt; 200日 SMA（大盤跌破多空分界線）",
            "R2_death_cross_exit": "TQQQ 10EMA 向下死亡交叉 20EMA",
            "R3_rsi_defensive_warning": "持股中 且 TQQQ RSI(14) &lt; 45（動能顯著轉弱）",
            "R4_overheat_trim": "TQQQ RSI(14) &gt; 70 且 高於 20EMA 超過 15%（極端過熱）",
            "R5_golden_cross_entry": "大盤 QQQ &gt; 200SMA 且 TQQQ 10EMA 金叉 20EMA 且 50 &lt; RSI &lt; 65",
            "R6_entry_rejected_overbought": "大盤 QQQ &gt; 200SMA 且 TQQQ 10EMA 金叉 20EMA 但 RSI &ge; 65（防追高）",
            "R-REBAL": "每年 11/1 前後 3 天窗口，防禦性資產偏離 50% 目標配置",
        }
        if rule_id in mapping:
            return mapping[rule_id]
        parts = []
        for c in conds:
            parts.append(f"{c.get('left')} {c.get('op')} {c.get('right')}")
        return " 且 ".join(parts)

    rows = []
    for r in rules:
        is_triggered = r.id in matched_ids
        status_badge = (
            '<span class="status-pill status-active">⚡ 今日符合觸發</span>'
            if is_triggered
            else '<span class="status-pill status-idle">⚪ 監控中</span>'
        )
        row_class = ' class="row-highlight"' if is_triggered else ''
        cond_text = format_condition_friendly(r.id, r.conditions)
        cat_badge = get_category_badge(r.action)

        rows.append(f"""
        <tr{row_class}>
          <td style="font-weight:600;font-family:monospace;">{r.id.split('_')[0]}</td>
          <td>{cat_badge}</td>
          <td style="font-weight:600;">{r.name}</td>
          <td style="font-size:13px;color:#334155;">{cond_text}</td>
          <td style="font-size:13px;">{r.message}</td>
          <td>{status_badge}</td>
        </tr>
        """)

    rows.append("""
    <tr>
      <td style="font-weight:600;font-family:monospace;">REBAL</td>
      <td><span class="badge-cat badge-rebal">年度再平衡</span></td>
      <td style="font-weight:600;">11/1 資產再平衡</td>
      <td style="font-size:13px;color:#334155;">每年 11/1 (±3天窗口) 檢核防禦性資產 (CASH/SHY/BIL)</td>
      <td style="font-size:13px;">維持 50% 防禦性資產基準配置，偏離時透過再平衡機制恢復平衡。</td>
      <td><span class="status-pill status-idle">⚪ 監控中</span></td>
    </tr>
    """)

    return f"""
    <div class="card" id="trading-rules-block">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;font-size:18px;color:#0f172a;">策略執行規範：目前遵守之「買入與賣出規則」</h3>
        <span style="font-size:12px;color:#475569;background:#f1f5f9;padding:4px 10px;border-radius:12px;border:1px solid #cbd5e1;">
          嚴格量化執行 • 雙重濾網架構 (200SMA 大盤過濾 + 10/20EMA 雙線觸發 + RSI 動能濾網)
        </span>
      </div>
      <div style="overflow-x:auto;">
        <table class="rules-table">
          <thead>
            <tr>
              <th style="width:70px;">代號</th>
              <th style="width:100px;">規則類別</th>
              <th style="width:160px;">規則名稱</th>
              <th>觸發條件</th>
              <th>策略動作與指示</th>
              <th style="width:110px;">本日狀態</th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
      </div>
    </div>
    """


def _render_metrics_panel(ind: DailyIndicators, recommendation: Recommendation) -> str:
    """繪製右側/寬螢幕延伸利用的指標即時速報面板。"""
    ctx = recommendation.context
    t_ctx = ctx.get("tqqq", {})
    q_ctx = ctx.get("qqq", {})

    tqqq_close = t_ctx.get("close")
    ema_slow_dist = t_ctx.get("ema_slow_distance_pct")
    rsi_val = t_ctx.get("rsi")
    qqq_close = q_ctx.get("close")
    qqq_sma = q_ctx.get("sma200")

    qqq_above_sma = (qqq_close is not None and qqq_sma is not None and qqq_close > qqq_sma)
    dist_str = f"{ema_slow_dist:+.2f}%" if ema_slow_dist is not None else "N/A"
    rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "N/A"

    if rsi_val is not None:
        if rsi_val >= 70:
            rsi_eval = '<span style="color:#dc2626;font-weight:700;">過熱警戒 (&ge;70)</span>'
        elif rsi_val >= 65:
            rsi_eval = '<span style="color:#f59e0b;font-weight:700;">超買區間 (65~70)</span>'
        elif rsi_val >= 50:
            rsi_eval = '<span style="color:#16a34a;font-weight:700;">多頭動能 (50~65 買點)</span>'
        elif rsi_val >= 45:
            rsi_eval = '<span style="color:#64748b;font-weight:700;">中性整理 (45~50)</span>'
        else:
            rsi_eval = '<span style="color:#dc2626;font-weight:700;">避險減碼 (&lt;45)</span>'
    else:
        rsi_eval = "無資料"

    qqq_status = (
        '<span style="color:#16a34a;font-weight:700;">多頭市場許可 (高於200SMA)</span>'
        if qqq_above_sma
        else '<span style="color:#dc2626;font-weight:700;">空頭禁令限制 (低於200SMA)</span>'
    )

    return f"""
    <div class="metrics-grid">
      <div class="metric-box">
        <div class="metric-title">TQQQ 最新收盤</div>
        <div class="metric-val" style="color:#2563eb;">{_format_price(tqqq_close)}</div>
        <div class="metric-desc">交易基準日：{recommendation.date}</div>
      </div>
      <div class="metric-box">
        <div class="metric-title">20EMA 乖離幅度</div>
        <div class="metric-val" style="color:{'#dc2626' if (ema_slow_dist or 0) > 15 else '#0f172a'};">{dist_str}</div>
        <div class="metric-desc">超過 +15% 觸發分批止盈</div>
      </div>
      <div class="metric-box">
        <div class="metric-title">TQQQ RSI(14) 動能</div>
        <div class="metric-val" style="color:#0f172a;">{rsi_str}</div>
        <div class="metric-desc">{rsi_eval}</div>
      </div>
      <div class="metric-box">
        <div class="metric-title">大盤環境 (QQQ vs 200SMA)</div>
        <div class="metric-val" style="font-size:16px;line-height:28px;">{qqq_status}</div>
        <div class="metric-desc">QQQ {_format_price(qqq_close)} / 200SMA {_format_price(qqq_sma)}</div>
      </div>
    </div>
    """


def _render_events_table(events: List[dict], dates: List[str]) -> str:
    """產生自 TQQQ 成立以來重大金融事件時序紀錄表。"""
    if not events or not dates:
        return ""
    start_date, end_date = dates[0], dates[-1]
    filtered = [e for e in events if start_date <= e.get("date", "") <= end_date]
    if not filtered:
        filtered = events

    # 依日期由新至舊排列便於閱讀
    sorted_evs = sorted(filtered, key=lambda e: e.get("date", ""), reverse=True)

    rows = []
    cat_badges = {
        "inception": '<span class="badge-cat" style="background:#e0f2fe;color:#0369a1;">上市成立</span>',
        "market": '<span class="badge-cat" style="background:#fef3c7;color:#b45309;">市場行情</span>',
        "crisis": '<span class="badge-cat badge-sell">重大危機</span>',
        "debt": '<span class="badge-cat badge-sell">債信評等</span>',
        "fed": '<span class="badge-cat badge-rebal">貨幣政策</span>',
        "election": '<span class="badge-cat badge-buy">大選政局</span>',
        "earnings": '<span class="badge-cat badge-trim">產業財報</span>',
        "policy": '<span class="badge-cat badge-filter">政府政策</span>',
        "strategy": '<span class="badge-cat badge-neutral">策略機制</span>',
    }

    for ev in sorted_evs:
        cat_badge = cat_badges.get(ev.get("category", ""), '<span class="badge-cat badge-neutral">金融事件</span>')
        rows.append(f"""
        <tr>
          <td style="font-family:monospace;font-weight:600;">{ev.get('date')}</td>
          <td>{cat_badge}</td>
          <td style="font-weight:600;color:#0f172a;">{ev.get('title')}</td>
          <td style="font-size:13px;color:#475569;">{ev.get('description')}</td>
        </tr>
        """)

    return f"""
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;font-size:18px;">重大金融事件時序紀錄 (2010年 TQQQ 成立至今)</h3>
        <span style="font-size:12px;color:#64748b;background:#f8fafc;padding:3px 8px;border-radius:4px;border:1px solid #e2e8f0;">
          共收錄 {len(sorted_evs)} 項重大事件 • 依時間最新順序呈現
        </span>
      </div>
      <p style="color:#64748b;font-size:13px;margin:4px 0 12px;">圖表上方已精準標示歷年總體經濟決策、利率政策、黑天鵝崩盤與科技牛市轉折點，方便比對均線策略在歷史重大考驗下的執行表現。</p>
      <div style="overflow-x:auto;">
        <table class="rules-table">
          <thead>
            <tr>
              <th style="width:110px;">事件日期</th>
              <th style="width:100px;">類別</th>
              <th style="width:230px;">事件名稱</th>
              <th>事件背景與市場影響</th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
      </div>
    </div>
    """


def render_html_report(
    path: str,
    ind: DailyIndicators,
    recommendation: Recommendation,
    settings: Optional[dict] = None,
    rules: Optional[List[Rule]] = None,
    events_path: str = "config/events.json",
    window: Optional[int] = None,
) -> None:
    # 若未指定 window，預設取完整時間軸（追溯回 TQQQ 成立之初）
    if window is None:
        window = len(ind.dates)

    ma_cfg = (settings or {}).get("moving_averages", {})
    long_sma_period = ma_cfg.get("chart_long_sma", 200)
    ema_fast_period = ma_cfg.get("target_fast_ema", 10)
    ema_slow_period = ma_cfg.get("target_slow_ema", 20)

    # 載入規則與重大事件
    if rules is None:
        rules = load_rules("config/rules.json")
    events = load_events(events_path)

    # 繪製圖表與區塊
    price_svg = _render_price_svg(ind, window, long_sma_period, ema_fast_period, ema_slow_period, events=events)
    rsi_svg = _render_rsi_svg(ind, window)
    rules_block_html = _render_rules_block(rules, recommendation)
    metrics_panel_html = _render_metrics_panel(ind, recommendation)
    events_table_html = _render_events_table(events, ind.dates[-window:])

    rules_html = "".join(
        f"<li><b>{r['id']}</b> {r['name']} — {r['message']}</li>" for r in recommendation.matched_rules
    ) or "<li>（無規則觸發，維持觀望）</li>"

    tqqq_close = ind.tqqq_close[-1]
    qqq_close = ind.qqq_close[-1]
    first_date = ind.dates[-window]
    last_date = ind.dates[-1]

    # 版本與時間戳記
    now_cst = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LRS 槓桿輪換策略報告 - {recommendation.date}</title>
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif;
  margin: 24px auto;
  max-width: 1360px;
  padding: 0 16px;
  background: #f8fafc;
  color: #0f172a;
  line-height: 1.5;
}}
.header-bar {{
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  border-bottom: 2px solid #e2e8f0;
  padding-bottom: 12px;
  margin-bottom: 18px;
  flex-wrap: wrap;
  gap: 10px;
}}
.header-bar h1 {{ margin: 0; font-size: 24px; color: #0f172a; }}
.version-badge-group {{
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}}
.badge-version {{
  background: #0284c7;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
}}
.badge-timestamp {{
  background: #f1f5f9;
  color: #475569;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
}}
.badge-inception {{
  background: #f0fdf4;
  color: #166534;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid #bbf7d0;
  font-weight: 600;
}}
.card {{
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 18px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}
.action {{ font-size: 22px; font-weight: 700; color: #1e293b; }}
.asof {{ font-size: 14px; color: #475569; margin-top: 6px; }}
.rules-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  text-align: left;
}}
.rules-table th {{
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
  padding: 10px 12px;
  border-bottom: 2px solid #e2e8f0;
}}
.rules-table td {{
  padding: 10px 12px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
}}
.rules-table tr:hover {{ background: #f8fafc; }}
.row-highlight {{ background: #fef2f2 !important; }}
.badge-cat {{
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 700;
  border-radius: 4px;
}}
.badge-buy {{ background: #dcfce7; color: #15803d; }}
.badge-sell {{ background: #fee2e2; color: #b91c1c; }}
.badge-trim {{ background: #ffedd5; color: #c2410c; }}
.badge-filter {{ background: #f1f5f9; color: #475569; }}
.badge-rebal {{ background: #f3e8ff; color: #7e22ce; }}
.badge-neutral {{ background: #e2e8f0; color: #334155; }}
.status-pill {{
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 12px;
}}
.status-active {{ background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }}
.status-idle {{ background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }}
.metrics-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}}
.metric-box {{
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 14px;
}}
.metric-title {{ font-size: 12px; color: #64748b; font-weight: 600; }}
.metric-val {{ font-size: 22px; font-weight: 700; margin: 4px 0; }}
.metric-desc {{ font-size: 12px; color: #475569; }}
footer {{
  margin-top: 32px;
  padding: 16px 0;
  border-top: 1px solid #e2e8f0;
  font-size: 13px;
  color: #64748b;
  text-align: center;
}}
</style>
<script>
function togglePriceScale(mode) {{
  var isLog = mode === 'log';
  var pLin = document.getElementById('plot-linear');
  var pLog = document.getElementById('plot-log');
  if (pLin) pLin.style.display = isLog ? 'none' : 'inline';
  if (pLog) pLog.style.display = isLog ? 'inline' : 'none';
}}
</script>
</head>
<body>
  <div class="header-bar">
    <div>
      <h1>TQQQ 槓桿輪換策略 (LRS) — {recommendation.date}</h1>
      <div style="font-size:13px;color:#64748b;margin-top:2px;">以大盤長天期均線與高槓桿標的雙 EMA 觸發之多空輪換架構</div>
    </div>
    <div class="version-badge-group">
      <span class="badge-version">平台版本：{VERSION}</span>
      <span class="badge-timestamp">產出時間戳記：{now_cst}</span>
      <span class="badge-inception">全歷史時間軸：{first_date} 至 {last_date}（自 TQQQ 成立開始）</span>
    </div>
  </div>

  <!-- 1. 建議動作區塊 -->
  <div class="card">
    <div class="action">建議動作：{recommendation.action_label}</div>
    <div class="asof">資料日期：{recommendation.date}　TQQQ 收盤：{_format_price(tqqq_close)}　QQQ 收盤：{_format_price(qqq_close)}（美股交易日自動更新）</div>
    <h3 style="margin-top:14px;font-size:16px;">本日觸發規則</h3>
    <ul>{rules_html}</ul>
  </div>

  <!-- 2. 目前遵守的買入與賣出規則區塊（位於「建議動作」與「價格與均線」中間） -->
  {rules_block_html}

  <!-- 3. 市場指標即時速覽（延伸利用橫向與右側空間） -->
  <div class="card">
    <h3 style="margin-top:0;font-size:16px;color:#0f172a;margin-bottom:12px;">即時量化指標與均線乖離率速覽</h3>
    {metrics_panel_html}
  </div>

  <!-- 4. 價格與均線區塊 -->
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px;">
      <h3 style="margin:0;font-size:18px;">價格與均線（長期SMA框架 + 短期EMA 10日/20日觸發）</h3>
      <span style="font-size:12px;color:#475569;background:#f8fafc;padding:3px 8px;border-radius:4px;border:1px solid #e2e8f0;">
        時間軸已延長追溯回 TQQQ 成立首日 ({first_date}) • 共 {window} 交易日
      </span>
    </div>
    {price_svg}
  </div>

  <!-- 5. RSI(14) 震盪指標區塊 -->
  <div class="card">
    <h3 style="margin-top:0;font-size:18px;">RSI(14) 震盪指標</h3>
    {rsi_svg}
  </div>

  <!-- 6. 重大金融事件時間軸 -->
  {events_table_html}

  <footer>
    TQQQ 槓桿輪換策略 (LRS) 平台 • 版本：{VERSION} • 報表時間戳記：{now_cst} • 時間軸追溯自 2010 年成立首日 • 零外部套件相依純標準庫架構
  </footer>
</body></html>"""

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
