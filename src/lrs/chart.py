"""零相依套件的圖表產生器：純字串組裝 SVG，輸出單一自包含 HTML 報告。

主圖：QQQ 收盤價(訊號基礎) + 長期 SMA(預設200日，框架) + 短期 EMA 10日/20日(觸發) +
      TQQQ 實際價格(右側次軸，虛線參考，實際買賣標的) + VIX 恐慌指標曲線(含 45 抄底門檻)，
      均線、TQQQ 參考線與 VIX 曲線各自可用圖上開關隱藏，並標示黃金/死亡交叉點及重大金融事件時間點。
      支援時間軸延長追溯回 TQQQ 2010 年成立開始（全歷史 All-Time）。
      支援線性座標 (Linear) 與對數座標 (Log Scale) 即時切換，便於長週期觀察。
      支援觀察時間區間方便可調（1M/3M/6M/1Y/2Y/5Y/10Y/ALL 及關鍵歷史情境跳轉），避免全時間長度過於擁擠。
      版面左右兩側充分利用：最大寬度擴充至寬螢幕友善自適應（1760px），右側標記最新均線與 VIX 定位 (Price Pills)。
副圖：QQQ RSI(14)(訊號基礎)，含 45/50/55/65/70 參考線（避險/進場下緣/中線/超買/過熱）及最新 RSI 指標標籤。
兩圖皆含縱軸（雙側數值刻度）與橫軸（日期/年份刻度）。
報告同時整合版本時間戳記、目前遵守之「買入與賣出規則」區塊及重大金融事件時間軸。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from . import allocation, cape
from .rules_engine import Rule, load_rules
from .signals import DailyIndicators, Recommendation

VERSION = "v1.7.0"

# 擴充畫布寬度與高度以充分利用寬螢幕與兩側空間
WIDTH = 1380
MARGIN_LEFT = 56
MARGIN_RIGHT = 164
MARGIN_TOP = 64
MARGIN_BOTTOM = 40
PRICE_PLOT_HEIGHT = 460
RSI_PLOT_HEIGHT = 240

SVG_WIDTH = MARGIN_LEFT + WIDTH + MARGIN_RIGHT  # 56 + 1380 + 164 = 1600


def load_events(path: str = "config/events.json") -> List[dict]:
    """載入重大金融事件清單。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _xs(n: int, width: float = WIDTH, margin_left: float = MARGIN_LEFT) -> List[float]:
    if n <= 1:
        return [margin_left]
    step = width / (n - 1)
    return [margin_left + i * step for i in range(n)]


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


def _x_axis(dates: List[str], xs: List[float], y_bottom: float, tick_count: int = 10) -> str:
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
            f'<rect x="{x_start + 26}" y="{adj_y - 9:.1f}" width="112" height="18" rx="4" fill="{color}" />'
            f'<text x="{x_start + 82}" y="{adj_y + 4:.1f}" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">'
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
    # 主線：訊號基礎為 QQQ（長期SMA框架 + 短期EMA觸發皆計算在 QQQ 收盤價上）
    close = ind.qqq_close[-window:]
    long_sma = ind.qqq_sma_chart_long[-window:]
    ema_fast = ind.qqq_ema_fast[-window:]
    ema_slow = ind.qqq_ema_slow[-window:]
    # 次線：TQQQ 實際買賣標的之成交價格，僅供參考顯示（右側獨立次軸，虛線呈現）
    tqqq_close = ind.tqqq_close[-window:]

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

    # TQQQ 實際價格換算 (獨立次軸，量級與 QQQ 不同，比例尺各自獨立計算)
    valid_tqqq = [v for v in tqqq_close if v is not None]
    scale_tqqq_lin = None
    scale_tqqq_log = None
    y_tqqq_lin: List[Optional[float]] = [None] * len(tqqq_close)
    y_tqqq_log: List[Optional[float]] = [None] * len(tqqq_close)
    tqqq_layer_svg = ""
    if valid_tqqq:
        tqqq_vmin, tqqq_vmax = min(valid_tqqq), max(valid_tqqq)
        tqqq_pad = (tqqq_vmax - tqqq_vmin) * 0.05 or 1.0
        tqqq_vmin_lin, tqqq_vmax_lin = tqqq_vmin - tqqq_pad, tqqq_vmax + tqqq_pad
        tqqq_span_lin = (tqqq_vmax_lin - tqqq_vmin_lin) or 1.0

        def _scale_tqqq_lin(v):
            if v is None:
                return None
            return plot_top + plot_height - (v - tqqq_vmin_lin) / tqqq_span_lin * plot_height

        scale_tqqq_lin = _scale_tqqq_lin
        y_tqqq_lin = [scale_tqqq_lin(v) for v in tqqq_close]

        _, scale_tqqq_log = _log_y_axis(tqqq_vmin, tqqq_vmax, plot_top, plot_height)
        y_tqqq_log = [scale_tqqq_log(v) for v in tqqq_close]

        tqqq_line_width = 1.2 if len(dates) > 1000 else 1.6
        tqqq_polyline_lin = _polyline(xs, y_tqqq_lin, "#2563eb", tqqq_line_width)
        tqqq_polyline_log = _polyline(xs, y_tqqq_log, "#2563eb", tqqq_line_width)
        tqqq_layer_svg = (
            f'<g class="tqqq-ref-layer">'
            f'<g stroke-dasharray="6,4" opacity="0.6">{tqqq_polyline_lin}</g>'
            f'</g>'
        )
        tqqq_layer_log_svg = (
            f'<g class="tqqq-ref-layer">'
            f'<g stroke-dasharray="6,4" opacity="0.6">{tqqq_polyline_log}</g>'
            f'</g>'
        )
    else:
        tqqq_layer_log_svg = ""

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

    # 重大金融事件標記 (垂直標記線與圖釘標籤，防文字重疊上下三層交錯)
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
            if abs(ev_x - last_ev_x) < 65:
                stagger = (stagger + 1) % 3
            else:
                stagger = 0
            last_ev_x = ev_x

            text_y = plot_top - 6 - stagger * 14
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

    # VIX 恐慌指標曲線換算 (映射至主圖專屬波動率刻度 10~80+)
    vix = ind.vix_close[-window:] if getattr(ind, "vix_close", None) else []
    valid_vix = [v for v in vix if v is not None]
    vix_layer_svg = ""
    scale_vix = None
    if valid_vix:
        vix_min = 10.0
        vix_max = max(80.0, max(valid_vix) + 5.0)
        vix_span = (vix_max - vix_min) or 1.0

        def _scale_vix_fn(v: Optional[float]) -> Optional[float]:
            if v is None:
                return None
            return plot_top + plot_height - (v - vix_min) / vix_span * plot_height

        scale_vix = _scale_vix_fn
        y_vix = [scale_vix(v) for v in vix]
        vix_line_width = 1.4 if len(dates) > 1000 else 1.6
        vix_polyline = _polyline(xs, y_vix, "#e11d48", vix_line_width)

        y_45 = scale_vix(45.0)
        vix_ref_svg = (
            f'<line x1="{MARGIN_LEFT}" y1="{y_45:.1f}" x2="{MARGIN_LEFT + WIDTH}" y2="{y_45:.1f}" '
            f'stroke="#fda4af" stroke-width="1.2" stroke-dasharray="4,3" opacity="0.85" />'
            f'<text x="{MARGIN_LEFT + WIDTH - 8}" y="{y_45 - 4:.1f}" font-size="10" fill="#be123c" font-weight="600" text-anchor="end">VIX 45 抄底門檻</text>'
        )

        vix_ticks_svg = []
        for tick_val in [20, 30, 60]:
            y_t = scale_vix(float(tick_val))
            if y_t is not None and plot_top <= y_t <= plot_top + plot_height:
                vix_ticks_svg.append(
                    f'<text x="{MARGIN_LEFT + WIDTH - 8}" y="{y_t + 3:.1f}" font-size="9" fill="#fda4af" text-anchor="end">VIX {tick_val}</text>'
                )

        vix_layer_svg = (
            f'<g class="vix-line-layer">'
            f'{vix_ref_svg}'
            f'{"".join(vix_ticks_svg)}'
            f'{vix_polyline}'
            f'</g>'
        )

    # 右側 Price Pills (線性與對數)
    pill_items_lin = [
        ("QQQ", close[-1], y_close_lin[-1], "#2563eb"),
        (f"EMA{ema_fast_period}", ema_fast[-1], y_fast_lin[-1], "#0d9488"),
        (f"EMA{ema_slow_period}", ema_slow[-1], y_slow_lin[-1], "#ea580c"),
        (f"SMA{long_sma_period}", long_sma[-1], y_long_lin[-1], "#9333ea"),
    ]
    pill_items_log = [
        ("QQQ", close[-1], y_close_log[-1], "#2563eb"),
        (f"EMA{ema_fast_period}", ema_fast[-1], y_fast_log[-1], "#0d9488"),
        (f"EMA{ema_slow_period}", ema_slow[-1], y_slow_log[-1], "#ea580c"),
        (f"SMA{long_sma_period}", long_sma[-1], y_long_log[-1], "#9333ea"),
    ]
    if valid_tqqq and y_tqqq_lin[-1] is not None:
        pill_items_lin.append(("TQQQ", tqqq_close[-1], y_tqqq_lin[-1], "#64748b"))
    if valid_tqqq and y_tqqq_log[-1] is not None:
        pill_items_log.append(("TQQQ", tqqq_close[-1], y_tqqq_log[-1], "#64748b"))
    if vix and vix[-1] is not None and scale_vix is not None:
        y_vix_last = scale_vix(vix[-1])
        pill_items_lin.append(("VIX", vix[-1], y_vix_last, "#e11d48"))
        pill_items_log.append(("VIX", vix[-1], y_vix_last, "#e11d48"))

    pills_lin_svg = _render_price_pills(pill_items_lin, MARGIN_LEFT + WIDTH, plot_top, plot_height)
    pills_log_svg = _render_price_pills(pill_items_log, MARGIN_LEFT + WIDTH, plot_top, plot_height)

    total_height = MARGIN_TOP + PRICE_PLOT_HEIGHT + MARGIN_BOTTOM

    labels = f'''
    <text x="{MARGIN_LEFT}" y="18" font-size="13" fill="#2563eb">■ QQQ 收盤價(訊號基礎)</text>
    <text x="{MARGIN_LEFT + 180}" y="18" font-size="13" fill="#9333ea">■ 長期 SMA({long_sma_period}日,框架)</text>
    <text x="{MARGIN_LEFT + 400}" y="18" font-size="13" fill="#0d9488">■ 短期 EMA({ema_fast_period}日)</text>
    <text x="{MARGIN_LEFT + 570}" y="18" font-size="13" fill="#ea580c">■ 短期 EMA({ema_slow_period}日)</text>
    <text x="{MARGIN_LEFT + 740}" y="18" font-size="13" fill="#64748b">- - TQQQ 實際價格(右側次軸)</text>
    <text x="{MARGIN_LEFT + 970}" y="18" font-size="13" fill="#16a34a">● 黃金交叉</text>
    <text x="{MARGIN_LEFT + 1080}" y="18" font-size="13" fill="#dc2626">● 死亡交叉</text>
    <text x="{MARGIN_LEFT}" y="36" font-size="13" fill="#d97706">▼ 重大金融事件</text>
    <text x="{MARGIN_LEFT + 140}" y="36" font-size="13" fill="#e11d48">■ VIX 恐慌指數</text>
    <text x="{MARGIN_LEFT + 270}" y="36" font-size="12" fill="#be123c">-- VIX 45 抄底門檻</text>
    '''

    y_axis_lin_svg = _y_axis(vmin_lin, vmax_lin, plot_top, plot_height)
    x_axis_svg = _x_axis(dates, xs, plot_top + plot_height)

    toggle_bar = f'''
    <div class="range-toolbar">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        <span style="font-size:13px;font-weight:700;color:#0f172a;">觀察時間區間：</span>
        <div class="btn-range-group">
          <button type="button" class="btn-range" data-range="1m" onclick="setChartRange('1m')">1個月</button>
          <button type="button" class="btn-range" data-range="3m" onclick="setChartRange('3m')">3個月</button>
          <button type="button" class="btn-range" data-range="6m" onclick="setChartRange('6m')">6個月</button>
          <button type="button" class="btn-range active" data-range="1y" onclick="setChartRange('1y')">1年</button>
          <button type="button" class="btn-range" data-range="2y" onclick="setChartRange('2y')">2年</button>
          <button type="button" class="btn-range" data-range="5y" onclick="setChartRange('5y')">5年</button>
          <button type="button" class="btn-range" data-range="10y" onclick="setChartRange('10y')">10年</button>
          <button type="button" class="btn-range" data-range="all" onclick="setChartRange('all')">全歷史 (自2010成立)</button>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <span style="font-size:12.5px;color:#475569;">情境跳轉：</span>
        <select id="preset-period-select" onchange="setPresetPeriod(this.value)" style="padding:4px 8px;border-radius:6px;border:1px solid #cbd5e1;background:#fff;font-size:12px;color:#0f172a;cursor:pointer;">
          <option value="1y" selected>近 1 年 (推薦日常觀察 • 清爽清晰)</option>
          <option value="2y">近 2 年 (中期波動歷程)</option>
          <option value="5y">近 5 年 (完整牛熊歷程)</option>
          <option value="ai_era">2024~2026 (AI 浪潮與降息循環)</option>
          <option value="rate_hike">2022~2023 (激進升息暴跌與觸底)</option>
          <option value="covid_era">2020~2021 (疫情熔斷與無限QE大牛市)</option>
          <option value="trade_war">2018~2019 (中美貿易戰與平安夜重挫)</option>
          <option value="early_era">2010~2014 (成立初期、閃崩與歐債降評)</option>
          <option value="all">全歷史 (2010 至今共 {len(ind.dates)} 交易日)</option>
        </select>
        <div id="range-info-badge" class="range-info" style="font-size:12px;color:#0284c7;background:#e0f2fe;padding:4px 10px;border-radius:6px;font-weight:600;border:1px solid #bae6fd;">
          目前觀察區間：{dates[0]} 至 {dates[-1]} • 共 {len(dates)} 交易日
        </div>
      </div>
    </div>
    <div style="font-size:13px;margin:6px 0 10px;color:#334155;display:flex;flex-wrap:wrap;gap:16px;align-items:center;">
      <label style="cursor:pointer;font-weight:600;color:#0f172a;background:#f1f5f9;padding:3px 8px;border-radius:6px;border:1px solid #cbd5e1;">
        座標模式：
        <select id="price-scale-select" onchange="togglePriceScale(this.value)" style="border:none;background:transparent;font-size:12px;font-weight:600;color:#0f172a;cursor:pointer;">
          <option value="linear" selected>線性座標 (Linear)</option>
          <option value="log">對數座標 (Log Scale，長歷史推薦)</option>
        </select>
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="toggleLayer('ema-fast', this.checked)"> 顯示短期 EMA({ema_fast_period}日)
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="toggleLayer('ema-slow', this.checked)"> 顯示短期 EMA({ema_slow_period}日)
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="toggleLayer('cross-marker', this.checked)"> 顯示黃金/死亡交叉
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="toggleLayer('tqqq-ref', this.checked)"> 顯示 TQQQ 實際價格參考線(虛線)
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="toggleLayer('financial-event', this.checked)"> 顯示重大金融事件標記
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="toggleLayer('vix-line', this.checked)"> 顯示 VIX 恐慌指標曲線
      </label>
      <span style="color:#64748b;font-size:12px;margin-left:auto;">（可自由切換區間以避免擁擠 • 右側標記最新均線與 VIX 定位）</span>
    </div>
    '''

    line_width = 1.4 if len(dates) > 1000 else 1.8
    ma_width = 1.2 if len(dates) > 1000 else 1.4

    price_crosshair_svg = f'''
        <!-- 游標垂直導引線與高亮焦點標記 (滑鼠滑移時顯示價格與VIX) -->
        <g id="price-crosshair" style="display:none;pointer-events:none;">
          <line id="price-crosshair-line" x1="0" y1="{plot_top}" x2="0" y2="{plot_top + plot_height}" stroke="#64748b" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.85" />
          <circle id="price-dot-close" cx="0" cy="0" r="4.5" fill="#2563eb" stroke="#ffffff" stroke-width="1.5" />
          <circle id="price-dot-fast" cx="0" cy="0" r="4" fill="#0d9488" stroke="#ffffff" stroke-width="1.5" />
          <circle id="price-dot-slow" cx="0" cy="0" r="4" fill="#ea580c" stroke="#ffffff" stroke-width="1.5" />
          <circle id="price-dot-long" cx="0" cy="0" r="4" fill="#9333ea" stroke="#ffffff" stroke-width="1.5" />
          <circle id="price-dot-tqqq" cx="0" cy="0" r="4" fill="#64748b" stroke="#ffffff" stroke-width="1.5" />
          <circle id="price-dot-vix" cx="0" cy="0" r="4.5" fill="#e11d48" stroke="#ffffff" stroke-width="1.5" />
          <g id="price-date-pill">
            <rect id="price-date-pill-bg" x="-42" y="{plot_top + plot_height + 2}" width="84" height="18" rx="4" fill="#0f172a" />
            <text id="price-date-pill-text" x="0" y="{plot_top + plot_height + 15}" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">----</text>
          </g>
        </g>
    '''

    return f'''
    {toggle_bar}
    <div id="price-hover-bar" class="chart-hover-bar">
      <span style="color:#2563eb;font-weight:700;">💡 互動指示：</span>
      <span>滑鼠在圖表任意處滑移可即時檢視該交易日之收盤價格、VIX恐慌指數、均線與動能指標精確數值</span>
    </div>
    <div id="price-chart-svg-wrap" class="chart-wrap" style="position:relative;overflow-x:auto;">
      <svg id="price-chart-svg" viewBox="0 0 {SVG_WIDTH} {total_height}" width="100%" height="{total_height}" style="background:#fff;max-width:100%;height:auto;display:block;" xmlns="http://www.w3.org/2000/svg">
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
          {tqqq_layer_svg}
          <g class="cross-marker-layer">{marker_lin_svg}</g>
          {vix_layer_svg}
          {pills_lin_svg}
        </g>

        <!-- 對數座標圖層 -->
        <g id="plot-log" style="display:none;">
          {y_axis_log_svg}
          {_polyline(xs, y_close_log, "#2563eb", line_width)}
          {_polyline(xs, y_long_log, "#9333ea", ma_width)}
          <g class="ema-fast-layer">{_polyline(xs, y_fast_log, "#0d9488", ma_width)}</g>
          <g class="ema-slow-layer">{_polyline(xs, y_slow_log, "#ea580c", ma_width)}</g>
          {tqqq_layer_log_svg}
          <g class="cross-marker-layer">{marker_log_svg}</g>
          {vix_layer_svg}
          {pills_log_svg}
        </g>

        {price_crosshair_svg}
      </svg>
    </div>
    '''


def _render_rsi_svg(ind: DailyIndicators, window: int) -> str:
    dates = ind.dates[-window:]
    rsi = ind.qqq_rsi[-window:]
    xs = _xs(len(dates))

    plot_top = 36
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
            f'<rect x="{MARGIN_LEFT + WIDTH + 70}" y="{curr_y - 9:.1f}" width="68" height="18" rx="4" fill="#0f172a" />'
            f'<text x="{MARGIN_LEFT + WIDTH + 104}" y="{curr_y + 4:.1f}" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">RSI {rsi[-1]:.1f}</text>'
        )

    total_height = plot_top + RSI_PLOT_HEIGHT + MARGIN_BOTTOM
    line_width = 1.2 if len(dates) > 1000 else 1.6

    rsi_crosshair_svg = f'''
        <!-- 游標垂直導引線與高亮焦點標記 (RSI副圖同步) -->
        <g id="rsi-crosshair" style="display:none;pointer-events:none;">
          <line id="rsi-crosshair-line" x1="0" y1="{plot_top}" x2="0" y2="{plot_top + plot_height}" stroke="#64748b" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.85" />
          <circle id="rsi-dot" cx="0" cy="0" r="4.5" fill="#0f172a" stroke="#ffffff" stroke-width="1.5" />
          <g id="rsi-date-pill">
            <rect id="rsi-date-pill-bg" x="-42" y="{plot_top + plot_height + 2}" width="84" height="18" rx="4" fill="#0f172a" />
            <text id="rsi-date-pill-text" x="0" y="{plot_top + plot_height + 15}" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">----</text>
          </g>
        </g>
    '''

    return f'''
    <div id="rsi-chart-svg-wrap" class="chart-wrap" style="position:relative;overflow-x:auto;">
      <svg id="rsi-chart-svg" viewBox="0 0 {SVG_WIDTH} {total_height}" width="100%" height="{total_height}" style="background:#fff;max-width:100%;height:auto;display:block;" xmlns="http://www.w3.org/2000/svg">
        <text x="{MARGIN_LEFT}" y="18" font-size="13" fill="#0f172a">■ QQQ RSI(14) 震盪指標(訊號基礎)</text>
        {y_axis_svg}
        {x_axis_svg}
        {''.join(ref_lines)}
        {latest_rsi_svg}
        {_polyline(xs, y_rsi, "#0f172a", line_width)}
        {rsi_crosshair_svg}
      </svg>
    </div>
    '''


def _render_rules_block(rules: List[Rule], recommendation: Recommendation) -> str:
    """產生目前遵守的「買入與賣出規則」區塊。"""
    matched_ids = {r["id"] for r in recommendation.matched_rules}

    def get_category_badge(action: str) -> str:
        if action == "BUY_DIP_PANIC":
            return '<span class="badge-cat" style="background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;">恐慌抄底</span>'
        elif action == "BUY":
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
            "R0_vix_panic_bottom": "VIX 恐慌指數 &ge; 45（極端恐慌拋售，歷史抄底勝率極高）",
            "R1_bear_lockout": "QQQ 收盤價 &lt; 200日 SMA（大盤跌破多空分界線）",
            "R2_death_cross_exit": "QQQ 10EMA 向下死亡交叉 20EMA（訊號基礎為QQQ，賣出TQQQ）",
            "R3_rsi_defensive_warning": "持股中 且 QQQ RSI(14) &lt; 45（大盤動能顯著轉弱）",
            "R4_overheat_trim": "QQQ RSI(14) &gt; 70 且 高於其 20EMA 超過 15%（大盤極端過熱）",
            "R5_golden_cross_entry": "大盤 QQQ &gt; 200SMA 且 QQQ 10EMA 金叉 20EMA 且 50 &lt; RSI &lt; 65（買進TQQQ）",
            "R6_entry_rejected_overbought": "大盤 QQQ &gt; 200SMA 且 QQQ 10EMA 金叉 20EMA 但 RSI &ge; 65（防追高）",
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
    v_ctx = ctx.get("vix", {})

    tqqq_close = t_ctx.get("close")
    ema_slow_dist = q_ctx.get("ema_slow_distance_pct")
    rsi_val = q_ctx.get("rsi")
    qqq_close = q_ctx.get("close")
    qqq_sma = q_ctx.get("sma200")
    vix_val = v_ctx.get("close")

    qqq_above_sma = (qqq_close is not None and qqq_sma is not None and qqq_close > qqq_sma)
    dist_str = f"{ema_slow_dist:+.2f}%" if ema_slow_dist is not None else "N/A"
    rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "N/A"
    vix_str = f"{vix_val:.2f}" if vix_val is not None else "N/A"
    vix_badge_color = v_ctx.get("badge_color", "#64748b")
    vix_label = v_ctx.get("label", "無資料")

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

    vix_desc = "超過 45 觸發歷史級恐慌抄底" if (vix_val is None or vix_val < 45) else "⚡ 滿足 ≥45 歷史級抄底條件"

    return f"""
    <div class="metrics-grid">
      <div class="metric-box">
        <div class="metric-title">TQQQ 最新收盤（實際買賣標的）</div>
        <div class="metric-val" style="color:#2563eb;">{_format_price(tqqq_close)}</div>
        <div class="metric-desc">交易基準日：{recommendation.date}</div>
      </div>
      <div class="metric-box">
        <div class="metric-title">QQQ 20EMA 乖離幅度（訊號基礎）</div>
        <div class="metric-val" style="color:{'#dc2626' if (ema_slow_dist or 0) > 15 else '#0f172a'};">{dist_str}</div>
        <div class="metric-desc">超過 +15% 觸發分批止盈 TQQQ</div>
      </div>
      <div class="metric-box">
        <div class="metric-title">QQQ RSI(14) 動能（訊號基礎）</div>
        <div class="metric-val" style="color:#0f172a;">{rsi_str}</div>
        <div class="metric-desc">{rsi_eval}</div>
      </div>
      <div class="metric-box">
        <div class="metric-title">大盤環境 (QQQ vs 200SMA)</div>
        <div class="metric-val" style="font-size:16px;line-height:28px;">{qqq_status}</div>
        <div class="metric-desc">QQQ {_format_price(qqq_close)} / 200SMA {_format_price(qqq_sma)}</div>
      </div>
      <div class="metric-box">
        <div class="metric-title">VIX 恐慌指數綜合判斷</div>
        <div class="metric-val" style="color:{'#dc2626' if (vix_val or 0) >= 45 else '#0f172a'};">{vix_str}</div>
        <div class="metric-desc"><span style="color:{vix_badge_color};font-weight:700;">{vix_label}</span> • {vix_desc}</div>
      </div>
    </div>
    """


def _render_vix_analysis_block(ind: DailyIndicators, recommendation: Recommendation) -> str:
    """繪製 VIX 恐慌指數綜合判斷與歷史抄底勝率分析卡片。"""
    ctx = recommendation.context
    v_ctx = ctx.get("vix", {})
    vix_val = v_ctx.get("close")
    vix_str = f"{vix_val:.2f}" if vix_val is not None else "無資料"
    vix_label = v_ctx.get("label", "無資料")
    vix_desc = v_ctx.get("description", "")
    vix_guidance = v_ctx.get("guidance", "")
    is_panic = v_ctx.get("is_panic_bottom", False)

    alert_banner = ""
    if is_panic:
        alert_banner = """
        <div style="background:#fef2f2;border:1px solid #f87171;border-radius:8px;padding:12px 16px;margin-bottom:14px;color:#991b1b;display:flex;align-items:center;gap:10px;">
          <span style="font-size:24px;">🚨</span>
          <div>
            <div style="font-weight:700;font-size:15px;">極度恐慌警報觸發：VIX 指數超過 45！</div>
            <div style="font-size:13px;margin-top:2px;">市場出現歷史級斷頭與流動性恐慌，統計顯示此時進場抄底勝率極高，策略已啟動恐慌抄底買進建議 (BUY_DIP_PANIC)。</div>
          </div>
        </div>
        """

    return f"""
    <div class="card" id="vix-analysis-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;font-size:18px;color:#0f172a;">VIX 恐慌指數綜合判斷與歷史抄底勝率分析</h3>
        <span style="font-size:12px;color:#475569;background:#f1f5f9;padding:4px 10px;border-radius:12px;border:1px solid #cbd5e1;">
          市場恐慌極值量化模型 • VIX &gt; 45 歷史級逆勢抄底依據
        </span>
      </div>
      {alert_banner}
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px;margin-bottom:16px;">
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;">
          <div style="font-size:12px;color:#64748b;font-weight:600;">當前 VIX 狀態與情緒分級</div>
          <div style="font-size:24px;font-weight:700;margin:6px 0;color:{'#dc2626' if is_panic else '#0f172a'};">{vix_str} <span style="font-size:14px;font-weight:600;color:{v_ctx.get('badge_color', '#64748b')};">[{vix_label}]</span></div>
          <div style="font-size:13px;color:#334155;line-height:1.4;">{vix_desc}</div>
          <div style="font-size:12px;color:#2563eb;font-weight:600;margin-top:6px;">策略指引：{vix_guidance}</div>
        </div>

        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;">
          <div style="font-size:12px;color:#64748b;font-weight:600;">歷史經典 VIX &gt; 45 抄底標誌點</div>
          <ul style="margin:6px 0 0;padding-left:18px;font-size:12.5px;color:#334155;line-height:1.5;">
            <li><b>2020 疫情熔斷 (VIX 82.69)</b>：標普單月觸底反轉，隨後迎來納斯達克史詩級大牛市。</li>
            <li><b>2008 雷曼風暴 (VIX 89.53)</b>：極端恐慌後迎來十年科技超級多頭循環起點。</li>
            <li><b>2024 日圓套利閃崩 (VIX 65.73)</b>：盤中衝破 65 確立短線底部，科技股隨後迅速收復失土。</li>
          </ul>
        </div>
      </div>

      <div style="font-size:13px;color:#475569;background:#f8fafc;padding:10px 14px;border-radius:6px;border:1px solid #e2e8f0;line-height:1.6;">
        💡 <b>量化研究依據</b>：歷史統計顯示，當 VIX 超過 45 時，代表市場流動性遭遇非理性踩踏與全市場斷頭拋售，實質上賣壓已近極限（Capitulation）。在歷史所有 VIX 突破 45 的情境中，隨後 3 個月、6 個月與 1 年期間標普與那斯達克指數的獲利勝率超過 90%~100%，具備極高的不對稱風險報酬比。因此本系統將 VIX &ge; 45 賦予最高優先級抄底訊號 (BUY_DIP_PANIC)，不受大盤常規 200SMA 跌破限制。
      </div>
    </div>
    """


def _render_cape_block() -> str:
    """繪製 S&P 500 席勒本益比 (CAPE) 與超額本益比報酬率 (ECY) 宏觀估值卡片（純向量動態圖表版）。"""
    cape_stats = cape.get_cape_statistics()
    latest = cape_stats.get("latest", {})
    history = cape_stats.get("history", [])
    source_url = cape_stats.get("source_url", "https://www.wantgoo.com/global/macroeconomics/cape")

    cape_val = latest.get("cape", 40.71)
    ecy_val = latest.get("ecy", 0.56)
    eval_info = cape.evaluate_cape_valuation(cape_val)

    # 歷史月份表格 rows
    table_rows = []
    for h in history:
        table_rows.append(f"""
        <tr>
          <td style="font-weight:600;color:#1e293b;padding:8px 12px;border-bottom:1px solid #e2e8f0;">{h.get('date')}</td>
          <td style="font-weight:700;color:#2563eb;padding:8px 12px;border-bottom:1px solid #e2e8f0;">{h.get('cape'):.2f}</td>
          <td style="font-weight:700;color:#dc2626;padding:8px 12px;border-bottom:1px solid #e2e8f0;">{h.get('ecy'):.2f}%</td>
          <td style="color:#64748b;padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:12px;">{h.get('valuation', '歷史高檔')}</td>
        </tr>
        """)
    rows_html = "".join(table_rows)

    return f"""
    <div class="card" id="cape-analysis-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
        <div style="display:flex;align-items:center;gap:10px;">
          <h3 style="margin:0;font-size:18px;color:#0f172a;">S&P 500 席勒本益比 (CAPE) 與超額報酬率 (ECY)</h3>
          <span style="font-size:12px;color:#ffffff;background:{eval_info['badge_color']};padding:3px 8px;border-radius:10px;font-weight:600;">
            當前估值：{eval_info['tier']}
          </span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:12px;color:#64748b;">資料日期：{latest.get('date')}</span>
          <a href="{source_url}" target="_blank" rel="noopener noreferrer"
             style="font-size:12px;color:#2563eb;background:#eff6ff;padding:4px 10px;border-radius:6px;border:1px solid #bfdbfe;text-decoration:none;font-weight:600;">
            🔗 玩股網 WantGoo 統計來源 ↗
          </a>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px;margin-bottom:16px;">
        <!-- 當前指標速覽 -->
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;">
          <div style="font-size:12px;color:#64748b;font-weight:600;">最新席勒本益比 (CAPE)</div>
          <div style="font-size:26px;font-weight:800;color:#2563eb;margin:4px 0;">{cape_val:.2f}</div>
          <div style="font-size:12.5px;color:#475569;line-height:1.4;">
            百年歷史中位數約 <b>16.0</b>，歷史平均約 <b>17.5</b>。目前處於百年歷史最高前 2% 區間（僅次於 2000 年網路泡沫頂峰 44.19）。
          </div>
          <div style="margin-top:10px;padding-top:8px;border-top:1px dashed #cbd5e1;font-size:12px;color:#b91c1c;font-weight:600;">
            ⚠️ 宏觀意涵：長期預期報酬率壓縮，中短線操作更須仰賴均線過濾與風控紀律保護。
          </div>
        </div>

        <!-- 最新 ECY -->
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;">
          <div style="font-size:12px;color:#64748b;font-weight:600;">超額調整後本益比報酬率 (ECY)</div>
          <div style="font-size:26px;font-weight:800;color:#dc2626;margin:4px 0;">{ecy_val:.2f}%</div>
          <div style="font-size:12.5px;color:#475569;line-height:1.4;">
            公式為 <code>(1 / CAPE) - 美國10年期實質公債殖利率</code>。代表股票實質獲利率相對於無風險公債之「超額報酬安全邊際」。
          </div>
          <div style="margin-top:10px;padding-top:8px;border-top:1px dashed #cbd5e1;font-size:12px;color:#475569;">
            💡 ECY 越低代表股市相對於公債越昂貴、溢價風險偏高；反之越高代表股市相對於債券更具吸引力。
          </div>
        </div>

        <!-- 歷史月份統計清單 -->
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;">
          <div style="font-size:12px;color:#64748b;font-weight:600;margin-bottom:8px;">近半年數據統計</div>
          <table style="width:100%;border-collapse:collapse;font-size:12px;text-align:left;">
            <thead>
              <tr style="background:#e2e8f0;color:#475569;">
                <th style="padding:4px 8px;">年度/月份</th>
                <th style="padding:4px 8px;">CAPE</th>
                <th style="padding:4px 8px;">ECY</th>
                <th style="padding:4px 8px;">估值評估</th>
              </tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
        </div>
      </div>

      <!-- 動態互動走勢圖容器 -->
      <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:14px;margin-bottom:14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px;">
          <!-- 區間切換按鈕 -->
          <div class="range-selector" id="cape-range-selector">
            <span style="font-size:12px;color:#64748b;font-weight:600;margin-right:4px;">觀察區間：</span>
            <button type="button" class="range-btn" onclick="setCapeRange('1y')">1Y</button>
            <button type="button" class="range-btn" onclick="setCapeRange('3y')">3Y</button>
            <button type="button" class="range-btn" onclick="setCapeRange('5y')">5Y</button>
            <button type="button" class="range-btn" onclick="setCapeRange('10y')">10Y</button>
            <button type="button" class="range-btn" onclick="setCapeRange('20y')">20Y</button>
            <button type="button" class="range-btn active" onclick="setCapeRange('all')">All</button>
          </div>

          <!-- 圖例與開關 -->
          <div style="display:flex;gap:12px;align-items:center;font-size:12px;flex-wrap:wrap;">
            <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;color:#2563eb;font-weight:600;">
              <input type="checkbox" id="toggle-cape-line" checked onchange="toggleCapeSeries('cape', this.checked)">
              <span style="display:inline-block;width:12px;height:3px;background:#2563eb;border-radius:2px;"></span> CAPE 席勒本益比
            </label>
            <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;color:#dc2626;font-weight:600;">
              <input type="checkbox" id="toggle-ecy-line" checked onchange="toggleCapeSeries('ecy', this.checked)">
              <span style="display:inline-block;width:12px;height:3px;background:#dc2626;border-radius:2px;"></span> ECY 超額報酬率
            </label>
            <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;color:#eab308;font-weight:600;">
              <input type="checkbox" id="toggle-sp500-line" checked onchange="toggleCapeSeries('sp500', this.checked)">
              <span style="display:inline-block;width:12px;height:3px;background:#eab308;border-radius:2px;"></span> S&P 500 指數
            </label>
            <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;color:#64748b;">
              <input type="checkbox" id="toggle-recession-bands" checked onchange="toggleCapeSeries('recession', this.checked)">
              <span style="display:inline-block;width:10px;height:10px;background:#e2e8f0;border-radius:2px;"></span> 歷史經濟衰退陰影
            </label>
          </div>
        </div>

        <!-- 即時數值指示狀態列 -->
        <div id="cape-hover-bar" style="font-size:12px;color:#475569;background:#f8fafc;padding:6px 12px;border-radius:4px;border:1px solid #e2e8f0;margin-bottom:8px;min-height:18px;">
          <span style="color:#64748b;">💡 游標滑移至圖上可即時檢視歷史任一月份的 CAPE、ECY 與標普指數精確數值</span>
        </div>

        <!-- SVG 畫布容器 -->
        <div id="cape-svg-container" style="position:relative;width:100%;overflow-x:auto;">
          <!-- SVG 由前端 JavaScript 動態精確計算與向量渲染 -->
        </div>
      </div>

      <!-- 指標與學理說明 -->
      <div style="font-size:12.5px;color:#475569;background:#f8fafc;padding:12px 16px;border-radius:6px;border:1px solid #e2e8f0;line-height:1.6;">
        <div><b>📘 指標說明</b>：席勒本益比（Shiller PE, PE10）= 股價 / 近10年平均實質EPS，經通膨與季節性調整，由 2013 年諾貝爾經濟學獎得主 Robert Shiller 教授提出，一般用於預估大盤實質中長期回報潛力，較不適用於短線擇時。</div>
        <div style="margin-top:4px;"><b>📘 ECY 說明</b>：超額調整後本益比報酬率 ECY = (1/CAPE) - 美國實質10年債利率，同樣由席勒教授提出，進一步考量利率環境對股票估值的影響。ECY 代表股票相對於公債的實質超額報酬，ECY 越低表示股市相對高估。</div>
      </div>
    </div>
    """


def _render_allocation_block(check: "allocation.AllocationCheck", settings: Optional[dict]) -> str:
    """繪製現金/QQQ/TQQQ三資產配置卡片（財富種植園策略，含可互動即時輸入與試算面板）。"""
    target = check.target
    actual = check.actual or {"cash": 0.0, "qqq": 0.0, "tqqq": 0.0}
    amounts = check.amounts or {"cash": 0.0, "qqq": 0.0, "tqqq": 0.0, "total": 0.0}
    threshold = (settings or {}).get("allocation", {}).get("drift_threshold_pct", 5)

    def _bar(id_prefix: str, label: str, pct: float, color: str) -> str:
        return f"""
        <div style="margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;font-size:12px;color:#334155;margin-bottom:2px;">
            <span>{label}</span><span id="{id_prefix}-pct-label" style="font-weight:700;">{pct:.1f}%</span>
          </div>
          <div style="background:#e2e8f0;border-radius:4px;height:10px;overflow:hidden;">
            <div id="{id_prefix}-bar-fill" style="background:{color};height:100%;width:{max(0, min(100, pct)):.1f}%;transition:width 0.25s ease;"></div>
          </div>
        </div>
        """

    target_bars = (
        _bar("target-cash", "現金", target["cash"], "#64748b")
        + _bar("target-qqq", "QQQ", target["qqq"], "#2563eb")
        + _bar("target-tqqq", "TQQQ", target["tqqq"], "#dc2626")
    )

    actual_bars = (
        _bar("actual-cash", "現金 (SGOV/活存)", actual["cash"], "#64748b")
        + _bar("actual-qqq", "QQQ", actual["qqq"], "#2563eb")
        + _bar("actual-tqqq", "TQQQ", actual["tqqq"], "#dc2626")
    )

    banner_style = "display:block;" if check.needs_rebalance else "display:none;"
    banner_text = check.message if check.needs_rebalance else ""

    note_html = ""
    if check.note:
        note_html = f"""
        <div style="background:#eff6ff;border:1px solid #93c5fd;border-radius:8px;padding:10px 14px;margin-bottom:14px;color:#1e3a8a;font-size:13px;">
          🔒 <b>鐵律狀態</b>：{check.note}
        </div>
        """

    return f"""
    <div class="card" id="allocation-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;font-size:18px;color:#0f172a;">現金 / QQQ / TQQQ 三資產配置（財富種植園策略）</h3>
        <span style="font-size:12px;color:#475569;background:#f1f5f9;padding:4px 10px;border-radius:12px;border:1px solid #cbd5e1;">
          {check.regime_label}
        </span>
      </div>

      <div id="alloc-rebalance-banner" style="background:#fff7ed;border:1px solid #fb923c;border-radius:8px;padding:10px 14px;margin-bottom:14px;color:#9a3412;font-size:13px;{banner_style}">
        ⚖️ <b>再平衡提醒</b>：<span id="alloc-rebalance-text">{banner_text}</span>
      </div>

      {note_html}

      <!-- 持倉金額即時調整輸入面板 -->
      <div style="background:#f1f5f9;border:1px solid #cbd5e1;border-radius:8px;padding:12px 16px;margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px;">
          <div style="font-weight:700;font-size:13px;color:#1e293b;display:flex;align-items:center;gap:6px;">
            <span>💵 目前持倉金額調整 (美金 USD)</span>
            <span style="font-weight:400;font-size:12px;color:#64748b;">修改後即時連動計算權重與再平衡差額</span>
          </div>
          <div style="font-size:12px;color:#0f172a;font-weight:700;">
            資產總額：<span id="alloc-total-usd-label" style="color:#0284c7;font-size:14px;">${amounts.get('total', 0):,.2f}</span>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:12px;align-items:center;">
          <div>
            <label style="display:block;font-size:11.5px;color:#475569;margin-bottom:4px;font-weight:600;">現金 / SGOV (USD)</label>
            <input type="number" id="input-amt-cash" value="{amounts.get('cash', 0):.2f}" step="10" min="0"
              style="width:100%;padding:6px 10px;border:1px solid #94a3b8;border-radius:6px;font-size:13px;box-sizing:border-box;font-weight:600;color:#334155;"
              oninput="onAllocationAmountChange()">
          </div>
          <div>
            <label style="display:block;font-size:11.5px;color:#475569;margin-bottom:4px;font-weight:600;">QQQ 市值 (USD)</label>
            <input type="number" id="input-amt-qqq" value="{amounts.get('qqq', 0):.2f}" step="10" min="0"
              style="width:100%;padding:6px 10px;border:1px solid #94a3b8;border-radius:6px;font-size:13px;box-sizing:border-box;font-weight:600;color:#1d4ed8;"
              oninput="onAllocationAmountChange()">
          </div>
          <div>
            <label style="display:block;font-size:11.5px;color:#475569;margin-bottom:4px;font-weight:600;">TQQQ 市值 (USD)</label>
            <input type="number" id="input-amt-tqqq" value="{amounts.get('tqqq', 0):.2f}" step="10" min="0"
              style="width:100%;padding:6px 10px;border:1px solid #94a3b8;border-radius:6px;font-size:13px;box-sizing:border-box;font-weight:600;color:#b91c1c;"
              oninput="onAllocationAmountChange()">
          </div>
          <div style="display:flex;gap:8px;align-items:flex-end;padding-top:16px;">
            <button type="button" onclick="resetAllocationDefault()"
              style="padding:7px 12px;background:#e2e8f0;color:#334155;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">
              重設初始
            </button>
            <button type="button" onclick="saveAllocationToLocal()"
              style="padding:7px 12px;background:#0284c7;color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">
              記住金額
            </button>
          </div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px;margin-bottom:12px;">
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;">
          <div style="font-size:12px;color:#64748b;font-weight:600;margin-bottom:8px;">目標配置權重（已套用鐵律一/二後之今日應持倉位）</div>
          {target_bars}
        </div>
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div style="font-size:12px;color:#64748b;font-weight:600;">實際持倉權重</div>
            <div id="alloc-actual-source-tag" style="font-size:11px;color:#0284c7;background:#e0f2fe;padding:2px 6px;border-radius:4px;">即時計算中</div>
          </div>
          {actual_bars}
        </div>
      </div>

      <!-- 即時建議調倉金額試算明細卡 -->
      <div id="alloc-actions-container" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;margin-bottom:12px;display:none;">
        <div style="font-weight:700;font-size:12.5px;color:#0f172a;margin-bottom:6px;">⚖️ 建議再平衡調倉細項 (拉回目標權重)：</div>
        <div id="alloc-actions-list" style="font-size:12.5px;color:#334155;line-height:1.7;"></div>
      </div>

      <div style="font-size:12.5px;color:#475569;background:#f8fafc;padding:10px 14px;border-radius:6px;border:1px solid #e2e8f0;line-height:1.6;">
        💡 10%底倉（現金，除非QQQ從高點崩跌逾30%否則不動用）+ 90%機動倉依QQQ的200日均線多空、
        距歷史高點回落幅度、20日均線與其斜率，在QQQ/TQQQ/現金間切換（規則與參數見
        <code>config/settings.json</code> 的 <code>allocation</code> 區塊）。鐵律一「今天賣明天買」：
        加碼訊號延後一天執行；鐵律二「防假反彈」：由防守轉攻擊須防守滿
        {(settings or {}).get("allocation", {}).get("thresholds", {}).get("defensive_min_days", 2)}天且20日均線斜率向上。
        實際權重與目標偏離超過±{threshold}%時提醒再平衡。
        完整規則來源與假設說明見 <code>docs/allocation-strategy.md</code>。
      </div>
    </div>
    """


def _render_events_table(events: List[dict], dates: List[str]) -> str:
    """產生自 TQQQ 成立以來重大金融事件時序紀錄表。"""
    if not events:
        return ""

    # 依日期由新至舊排列便於閱讀
    sorted_evs = sorted(events, key=lambda e: e.get("date", ""), reverse=True)

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
        ev_d = ev.get('date', '')
        rows.append(f"""
        <tr class="event-tr" data-date="{ev_d}">
          <td style="font-family:monospace;font-weight:600;">{ev_d}</td>
          <td>{cat_badge}</td>
          <td style="font-weight:600;color:#0f172a;">{ev.get('title')}</td>
          <td style="font-size:13px;color:#475569;">{ev.get('description')}</td>
        </tr>
        """)

    return f"""
    <div class="card" id="events-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;font-size:18px;">重大金融事件時序紀錄 (2010年 TQQQ 成立至今)</h3>
        <div style="display:flex;align-items:center;gap:10px;">
          <label style="font-size:12px;color:#475569;cursor:pointer;">
            <input type="checkbox" id="filter-events-by-range" onchange="toggleEventsTableFilter(this.checked)"> 僅顯示當前觀察區間內事件
          </label>
          <span id="events-count-badge" style="font-size:12px;color:#64748b;background:#f8fafc;padding:3px 8px;border-radius:4px;border:1px solid #e2e8f0;">
            共收錄 {len(sorted_evs)} 項重大事件 • 依時間最新順序呈現
          </span>
        </div>
      </div>
      <p style="color:#64748b;font-size:13px;margin:4px 0 12px;">圖表上方已精準標示歷年總體經濟決策、利率政策、黑天鵝崩盤與科技牛市轉折點，方便比對均線策略在歷史重大考驗下的執行表現。</p>
      <div style="overflow-x:auto;">
        <table class="rules-table" id="events-table">
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
    allocation_check: Optional["allocation.AllocationCheck"] = None,
) -> None:
    # 預設展示視窗：若未指定 window，後端 SSR 預設近 1 年（252 交易日，若不足則全量），以避免一進來全時間長度過於擁擠
    # 前端 JavaScript 提供 1M/3M/6M/1Y/2Y/5Y/10Y/ALL 完整隨時無縫切換
    total_dates_count = len(ind.dates)
    if window is None:
        chart_cfg = (settings or {}).get("chart", {})
        cfg_win = chart_cfg.get("default_range") or chart_cfg.get("window", "1y")
        if cfg_win == "all":
            window = total_dates_count
        else:
            window = min(total_dates_count, 252)

    ma_cfg = (settings or {}).get("moving_averages", {})
    long_sma_period = ma_cfg.get("chart_long_sma", 200)
    ema_fast_period = ma_cfg.get("target_fast_ema", 10)
    ema_slow_period = ma_cfg.get("target_slow_ema", 20)

    # 載入規則與重大事件
    if rules is None:
        rules = load_rules("config/rules.json")
    events = load_events(events_path)

    # 繪製預設圖表與區塊
    price_svg = _render_price_svg(ind, window, long_sma_period, ema_fast_period, ema_slow_period, events=events)
    rsi_svg = _render_rsi_svg(ind, window)
    rules_block_html = _render_rules_block(rules, recommendation)
    metrics_panel_html = _render_metrics_panel(ind, recommendation)
    vix_analysis_html = _render_vix_analysis_block(ind, recommendation)
    alloc_check = allocation_check or allocation.AllocationCheck(
        regime=None, regime_label="尚無資料", target=allocation._target_weights(settings),
        actual=None, drift=None, needs_rebalance=False, note=None,
        message="尚無財富種植園策略檢核資料。",
    )
    alloc_target = alloc_check.target
    alloc_amounts = alloc_check.amounts or {"cash": 0.0, "qqq": 0.0, "tqqq": 0.0, "total": 0.0}
    alloc_threshold = (settings or {}).get("allocation", {}).get("drift_threshold_pct", 5)
    allocation_html = _render_allocation_block(alloc_check, settings)
    cape_block_html = _render_cape_block()
    cape_full_history = cape.get_full_cape_history()
    events_table_html = _render_events_table(events, ind.dates)

    rules_html = "".join(
        f"<li><b>{r['id']}</b> {r['name']} — {r['message']}</li>" for r in recommendation.matched_rules
    ) or "<li>（無規則觸發，維持觀望）</li>"

    tqqq_close = ind.tqqq_close[-1]
    qqq_close = ind.qqq_close[-1]
    first_full_date = ind.dates[0]
    last_date = ind.dates[-1]

    # 版本與時間戳記
    now_cst = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    # 構建前端全歷史資料 Payload (JSON)
    chart_payload = {
        "dates": ind.dates,
        "qqq_close": [round(c, 2) if c is not None else None for c in ind.qqq_close],
        "tqqq_close": [round(c, 2) if c is not None else None for c in ind.tqqq_close],
        "long_sma": [round(v, 2) if v is not None else None for v in ind.qqq_sma_chart_long],
        "ema_fast": [round(v, 2) if v is not None else None for v in ind.qqq_ema_fast],
        "ema_slow": [round(v, 2) if v is not None else None for v in ind.qqq_ema_slow],
        "rsi": [round(v, 1) if v is not None else None for v in ind.qqq_rsi],
        "vix": [round(v, 2) if v is not None else None for v in ind.vix_close] if ind.vix_close else [],
        "events": events,
        "long_sma_period": long_sma_period,
        "ema_fast_period": ema_fast_period,
        "ema_slow_period": ema_slow_period,
        "default_range": "1y" if total_dates_count >= 252 else "all",
    }
    chart_json = json.dumps(chart_payload, ensure_ascii=False)
    cape_history_json = json.dumps(cape_full_history, ensure_ascii=False)
    nber_recessions_json = json.dumps(cape.NBER_RECESSIONS, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LRS 槓桿輪換策略報告 - {recommendation.date}</title>
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif;
  margin: 16px auto;
  max-width: 1760px;
  width: calc(100% - 32px);
  padding: 0 12px;
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
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
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
.range-toolbar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  background: #f8fafc;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  margin-bottom: 12px;
}}
.btn-range-group {{
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  align-items: center;
}}
.btn-range {{
  background: #ffffff;
  border: 1px solid #cbd5e1;
  color: #334155;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}}
.btn-range:hover {{
  background: #f1f5f9;
  border-color: #94a3b8;
  color: #0f172a;
}}
.btn-range.active {{
  background: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
  box-shadow: 0 1px 2px rgba(37, 99, 235, 0.25);
}}
.chart-hover-bar {{
  font-size: 12.5px;
  color: #334155;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px 12px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-height: 22px;
}}
.chart-tooltip {{
  position: fixed;
  display: none;
  pointer-events: none;
  z-index: 9999;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid #cbd5e1;
  box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.2), 0 8px 10px -6px rgba(15, 23, 42, 0.1);
  border-radius: 8px;
  padding: 10px 14px;
  min-width: 240px;
  max-width: 330px;
  font-size: 12px;
  color: #0f172a;
  line-height: 1.5;
  transition: opacity 0.08s ease;
}}
.chart-tooltip-grid {{
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 12px;
  align-items: center;
  margin-top: 6px;
}}
.chart-tooltip-row-val {{
  font-weight: 700;
  text-align: right;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
}}
footer {{
  margin-top: 32px;
  padding: 16px 0;
  border-top: 1px solid #e2e8f0;
  font-size: 13px;
  color: #64748b;
  text-align: center;
}}
</style>
<script id="chart-data" type="application/json">
{chart_json}
</script>
<script>
// 零外部依賴、純原生 JavaScript 時間區間重繪引擎
var CHART_WIDTH = 1380;
var CHART_MARGIN_LEFT = 56;
var CHART_MARGIN_RIGHT = 164;
var CHART_MARGIN_TOP = 64;
var CHART_MARGIN_BOTTOM = 40;
var CHART_PRICE_HEIGHT = 460;
var CHART_RSI_HEIGHT = 240;
var CHART_SVG_WIDTH = CHART_MARGIN_LEFT + CHART_WIDTH + CHART_MARGIN_RIGHT; // 1600

var currentScaleMode = 'linear';
var currentRangeKey = '1y';
var layerVisibility = {{
  'ema-fast': true,
  'ema-slow': true,
  'cross-marker': true,
  'tqqq-ref': true,
  'financial-event': true,
  'vix-line': true
}};

var chartData = null;
var currentSliceData = null;
try {{
  var el = document.getElementById('chart-data');
  if (el) chartData = JSON.parse(el.textContent);
}} catch(e) {{
  console.error("Failed to parse chart data", e);
}}

function formatPrice(v) {{
  if (v === null || v === undefined) return "N/A";
  if (v >= 100) return v.toFixed(0);
  if (v < 1) return v.toFixed(2);
  return v.toFixed(1);
}}

function getVixRegime(v) {{
  if (v === null || v === undefined) return {{ label: '無資料', color: '#64748b', bg: '#f1f5f9' }};
  if (v >= 45) return {{ label: '🚨 極端恐慌抄底 (≥45)', color: '#b91c1c', bg: '#fee2e2' }};
  if (v >= 30) return {{ label: '⚠️ 恐慌警戒 (30~45)', color: '#c2410c', bg: '#ffedd5' }};
  if (v >= 20) return {{ label: '⚡ 中度波動 (20~30)', color: '#b45309', bg: '#fef3c7' }};
  return {{ label: '✅ 低波動平穩 (<20)', color: '#15803d', bg: '#dcfce7' }};
}}

function getSliceIndices(rangeKey) {{
  if (!chartData || !chartData.dates) return [0, 0];
  var n = chartData.dates.length;
  var endIdx = n;
  var startIdx = 0;

  if (rangeKey === '1m') {{
    startIdx = Math.max(0, n - 21);
  }} else if (rangeKey === '3m') {{
    startIdx = Math.max(0, n - 63);
  }} else if (rangeKey === '6m') {{
    startIdx = Math.max(0, n - 126);
  }} else if (rangeKey === '1y') {{
    startIdx = Math.max(0, n - 252);
  }} else if (rangeKey === '2y') {{
    startIdx = Math.max(0, n - 504);
  }} else if (rangeKey === '5y') {{
    startIdx = Math.max(0, n - 1260);
  }} else if (rangeKey === '10y') {{
    startIdx = Math.max(0, n - 2520);
  }} else if (rangeKey === 'all') {{
    startIdx = 0;
  }} else if (rangeKey === 'ai_era') {{
    // 2024-01-01 至今
    for (var i = 0; i < n; i++) {{
      if (chartData.dates[i] >= '2024-01-01') {{ startIdx = i; break; }}
    }}
  }} else if (rangeKey === 'rate_hike') {{
    // 2022-01-01 至 2023-12-31
    for (var i = 0; i < n; i++) {{
      if (chartData.dates[i] >= '2022-01-01') {{ startIdx = i; break; }}
    }}
    for (var j = startIdx; j < n; j++) {{
      if (chartData.dates[j] > '2023-12-31') {{ endIdx = j; break; }}
    }}
  }} else if (rangeKey === 'covid_era') {{
    // 2020-01-01 至 2021-12-31
    for (var i = 0; i < n; i++) {{
      if (chartData.dates[i] >= '2020-01-01') {{ startIdx = i; break; }}
    }}
    for (var j = startIdx; j < n; j++) {{
      if (chartData.dates[j] > '2021-12-31') {{ endIdx = j; break; }}
    }}
  }} else if (rangeKey === 'trade_war') {{
    // 2018-01-01 至 2019-12-31
    for (var i = 0; i < n; i++) {{
      if (chartData.dates[i] >= '2018-01-01') {{ startIdx = i; break; }}
    }}
    for (var j = startIdx; j < n; j++) {{
      if (chartData.dates[j] > '2019-12-31') {{ endIdx = j; break; }}
    }}
  }} else if (rangeKey === 'early_era') {{
    // 2010-02-11 至 2014-12-31
    startIdx = 0;
    for (var j = 0; j < n; j++) {{
      if (chartData.dates[j] > '2014-12-31') {{ endIdx = j; break; }}
    }}
  }}

  return [startIdx, endIdx];
}}

function renderDynamicSVG(rangeKey) {{
  if (!chartData) return;
  var bounds = getSliceIndices(rangeKey);
  var s = bounds[0], e = bounds[1];
  var subDates = chartData.dates.slice(s, e);
  var subClose = chartData.qqq_close.slice(s, e);
  var subTqqq = chartData.tqqq_close.slice(s, e);
  var subLongSma = chartData.long_sma.slice(s, e);
  var subEmaFast = chartData.ema_fast.slice(s, e);
  var subEmaSlow = chartData.ema_slow.slice(s, e);
  var subRsi = chartData.rsi.slice(s, e);
  var n = subDates.length;
  if (n === 0) return;

  // 1. 更新觀察區間標籤
  var infoBadge = document.getElementById('range-info-badge');
  if (infoBadge) {{
    infoBadge.innerText = '目前觀察區間：' + subDates[0] + ' 至 ' + subDates[n - 1] + ' • 共 ' + n + ' 交易日';
  }}
  var windowBadge = document.getElementById('chart-window-badge');
  if (windowBadge) {{
    windowBadge.innerText = '時間軸觀察區間：' + subDates[0] + ' 至 ' + subDates[n - 1] + ' • 共 ' + n + ' 交易日（可上方自選）';
  }}

  // 2. 算 X 座標
  var xs = [];
  var stepX = n > 1 ? CHART_WIDTH / (n - 1) : 0;
  for (var i = 0; i < n; i++) {{
    xs.push(CHART_MARGIN_LEFT + i * stepX);
  }}

  // 3. 算價格 Y 座標 (線性)
  var allP = [];
  for (var i = 0; i < n; i++) {{
    if (subClose[i] !== null) allP.push(subClose[i]);
    if (subLongSma[i] !== null) allP.push(subLongSma[i]);
    if (subEmaFast[i] !== null) allP.push(subEmaFast[i]);
    if (subEmaSlow[i] !== null) allP.push(subEmaSlow[i]);
  }}
  var vmin = Math.min.apply(null, allP);
  var vmax = Math.max.apply(null, allP);
  var pad = (vmax - vmin) * 0.05 || 1.0;
  var vminLin = vmin - pad;
  var vmaxLin = vmax + pad;
  var spanLin = (vmaxLin - vminLin) || 1.0;

  function scaleLin(val) {{
    if (val === null || val === undefined) return null;
    return CHART_MARGIN_TOP + CHART_PRICE_HEIGHT - ((val - vminLin) / spanLin) * CHART_PRICE_HEIGHT;
  }}

  // 4. 對數 Y 座標
  var safeVmin = Math.max(vmin, 0.05);
  var safeVmax = Math.max(vmax, safeVmin * 1.5);
  var logMin = Math.log10(safeVmin);
  var logMax = Math.log10(safeVmax);
  var logSpan = (logMax - logMin) || 1.0;

  function scaleLog(val) {{
    if (val === null || val === undefined || val <= 0) return null;
    var lv = Math.log10(Math.max(val, 0.05));
    return CHART_MARGIN_TOP + CHART_PRICE_HEIGHT - ((lv - logMin) / logSpan) * CHART_PRICE_HEIGHT;
  }}

  // 輔助 polyline 產生器
  function buildPolyline(vals, scaleFn, color, width) {{
    var pts = [];
    for (var i = 0; i < n; i++) {{
      var y = scaleFn(vals[i]);
      if (y !== null) pts.push(xs[i].toFixed(1) + ',' + y.toFixed(1));
    }}
    if (pts.length < 2) return '';
    return '<polyline points="' + pts.join(' ') + '" fill="none" stroke="' + color + '" stroke-width="' + width + '" />';
  }}

  // 5. 產生格線與刻度 (線性)
  var yAxisLinSvg = '';
  var ticksCount = 6;
  for (var k = 0; k < ticksCount; k++) {{
    var frac = k / (ticksCount - 1);
    var val = vminLin + frac * spanLin;
    var yPos = CHART_MARGIN_TOP + CHART_PRICE_HEIGHT - frac * CHART_PRICE_HEIGHT;
    yAxisLinSvg += '<line x1="' + CHART_MARGIN_LEFT + '" y1="' + yPos.toFixed(1) + '" x2="' + (CHART_MARGIN_LEFT + CHART_WIDTH) + '" y2="' + yPos.toFixed(1) + '" stroke="#e2e8f0" stroke-width="1" />' +
      '<text x="' + (CHART_MARGIN_LEFT - 8) + '" y="' + (yPos + 4).toFixed(1) + '" font-size="11" fill="#475569" text-anchor="end">' + formatPrice(val) + '</text>' +
      '<text x="' + (CHART_MARGIN_LEFT + CHART_WIDTH + 8) + '" y="' + (yPos + 4).toFixed(1) + '" font-size="11" fill="#94a3b8" text-anchor="start">' + formatPrice(val) + '</text>';
  }}

  // 對數格線與刻度
  var yAxisLogSvg = '';
  var candidates = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0];
  var logTicks = candidates.filter(function(c) {{ return safeVmin * 0.75 <= c && c <= safeVmax * 1.25; }});
  if (logTicks.length < 4) logTicks = [0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0];
  for (var t = 0; t < logTicks.length; t++) {{
    var lvVal = logTicks[t];
    var yPosLog = scaleLog(lvVal);
    if (yPosLog === null || yPosLog < CHART_MARGIN_TOP - 5 || yPosLog > CHART_MARGIN_TOP + CHART_PRICE_HEIGHT + 5) continue;
    yAxisLogSvg += '<line x1="' + CHART_MARGIN_LEFT + '" y1="' + yPosLog.toFixed(1) + '" x2="' + (CHART_MARGIN_LEFT + CHART_WIDTH) + '" y2="' + yPosLog.toFixed(1) + '" stroke="#e2e8f0" stroke-width="1" />' +
      '<text x="' + (CHART_MARGIN_LEFT - 8) + '" y="' + (yPosLog + 4).toFixed(1) + '" font-size="11" fill="#475569" text-anchor="end">' + formatPrice(lvVal) + '</text>' +
      '<text x="' + (CHART_MARGIN_LEFT + CHART_WIDTH + 8) + '" y="' + (yPosLog + 4).toFixed(1) + '" font-size="11" fill="#94a3b8" text-anchor="start">' + formatPrice(lvVal) + '</text>';
  }}

  // 6. X 軸刻度
  var xAxisSvg = '';
  var yBottom = CHART_MARGIN_TOP + CHART_PRICE_HEIGHT;
  if (n > 700) {{
    var yearIndices = [];
    var lastYear = null;
    for (var i = 0; i < n; i++) {{
      var yr = subDates[i].substring(0, 4);
      if (yr !== lastYear) {{
        yearIndices.push([i, yr]);
        lastYear = yr;
      }}
    }}
    var stepYr = yearIndices.length <= 18 ? 1 : 2;
    var idxs = [];
    for (var m = 0; m < yearIndices.length; m++) {{
      if (m % stepYr === 0) idxs.push(yearIndices[m]);
    }}
    if (idxs.length && idxs[idxs.length - 1][0] !== n - 1) idxs.push([n - 1, subDates[n - 1]]);
    for (var k = 0; k < idxs.length; k++) {{
      var xVal = xs[idxs[k][0]];
      xAxisSvg += '<line x1="' + xVal.toFixed(1) + '" y1="' + yBottom + '" x2="' + xVal.toFixed(1) + '" y2="' + (yBottom + 5) + '" stroke="#94a3b8" stroke-width="1" />' +
        '<text x="' + xVal.toFixed(1) + '" y="' + (yBottom + 18) + '" font-size="10" fill="#475569" text-anchor="middle">' + idxs[k][1] + '</text>';
    }}
  }} else {{
    var tickCount = 10;
    var stepTick = Math.max(1, Math.floor((n - 1) / (tickCount - 1)));
    var idxList = [];
    for (var i = 0; i < n; i += stepTick) idxList.push(i);
    if (idxList[idxList.length - 1] !== n - 1) idxList.push(n - 1);
    for (var k = 0; k < idxList.length; k++) {{
      var curIdx = idxList[k];
      var xVal = xs[curIdx];
      xAxisSvg += '<line x1="' + xVal.toFixed(1) + '" y1="' + yBottom + '" x2="' + xVal.toFixed(1) + '" y2="' + (yBottom + 5) + '" stroke="#94a3b8" stroke-width="1" />' +
        '<text x="' + xVal.toFixed(1) + '" y="' + (yBottom + 18) + '" font-size="10" fill="#475569" text-anchor="middle">' + subDates[curIdx] + '</text>';
    }}
  }}

  // 7. 交叉點 (金叉 / 死叉)
  var markersLin = '';
  var markersLog = '';
  var radius = n > 500 ? 3.5 : 5.0;
  for (var i = 1; i < n; i++) {{
    var f0 = subEmaFast[i - 1], s0 = subEmaSlow[i - 1];
    var f1 = subEmaFast[i], s1 = subEmaSlow[i];
    if (f0 === null || s0 === null || f1 === null || s1 === null) continue;
    var isGold = (f0 <= s0 && f1 > s1);
    var isDead = (f0 >= s0 && f1 < s1);
    if (isGold || isDead) {{
      var clr = isGold ? '#16a34a' : '#dc2626';
      var lbl = isGold ? '黃金交叉' : '死亡交叉';
      var yLin = scaleLin(subClose[i]);
      var yLog = scaleLog(subClose[i]);
      if (yLin !== null) {{
        markersLin += '<circle cx="' + xs[i].toFixed(1) + '" cy="' + yLin.toFixed(1) + '" r="' + radius + '" fill="' + clr + '" opacity="0.85"><title>' + lbl + ' ' + subDates[i] + '</title></circle>';
      }}
      if (yLog !== null) {{
        markersLog += '<circle cx="' + xs[i].toFixed(1) + '" cy="' + yLog.toFixed(1) + '" r="' + radius + '" fill="' + clr + '" opacity="0.85"><title>' + lbl + ' ' + subDates[i] + '</title></circle>';
      }}
    }}
  }}

  // 8. 重大金融事件 (只過濾出落在本區間內的事件，並做防重疊交錯)
  var eventsSvg = '';
  if (chartData.events) {{
    var startD = subDates[0], endD = subDates[n - 1];
    var inRangeEvs = chartData.events.filter(function(ev) {{
      return ev.date >= startD && ev.date <= endD;
    }});

    var lastEvX = -999.0;
    var stagger = 0;
    for (var k = 0; k < inRangeEvs.length; k++) {{
      var ev = inRangeEvs[k];
      var evDate = ev.date;
      var matchIdx = n - 1;
      for (var idx = 0; idx < n; idx++) {{
        if (subDates[idx] >= evDate) {{ matchIdx = idx; break; }}
      }}
      var evX = xs[matchIdx];
      if (Math.abs(evX - lastEvX) < 65) {{
        stagger = (stagger + 1) % 3;
      }} else {{
        stagger = 0;
      }}
      lastEvX = evX;

      var textY = CHART_MARGIN_TOP - 6 - stagger * 14;
      var evTitle = ev.title || '事件';
      var evDesc = ev.description || '';
      eventsSvg += '<g class="financial-event">' +
        '<line x1="' + evX.toFixed(1) + '" y1="' + CHART_MARGIN_TOP + '" x2="' + evX.toFixed(1) + '" y2="' + (CHART_MARGIN_TOP + CHART_PRICE_HEIGHT) + '" stroke="#d97706" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.75" />' +
        '<polygon points="' + (evX - 4).toFixed(1) + ',' + (CHART_MARGIN_TOP - 2) + ' ' + (evX + 4).toFixed(1) + ',' + (CHART_MARGIN_TOP - 2) + ' ' + evX.toFixed(1) + ',' + (CHART_MARGIN_TOP + 6) + '" fill="#f59e0b" />' +
        '<text x="' + evX.toFixed(1) + '" y="' + textY.toFixed(1) + '" font-size="9" fill="#b45309" text-anchor="middle" font-weight="600">' + evTitle + '</text>' +
        '<title>[' + evDate + '] ' + evTitle + '：' + evDesc + '</title>' +
        '</g>';
    }}
  }}

  // 8.5 VIX 恐慌指標曲線
  var subVix = chartData.vix ? chartData.vix.slice(s, e) : [];
  var validVix = [];
  for (var i = 0; i < n; i++) {{
    if (subVix[i] !== null && subVix[i] !== undefined) validVix.push(subVix[i]);
  }}
  var vixLayerSvg = '';
  var vixPillItem = null;
  if (validVix.length > 0) {{
    var vixMin = 10.0;
    var maxInVix = Math.max.apply(null, validVix);
    var vixMax = Math.max(80.0, maxInVix + 5.0);
    var vixSpan = (vixMax - vixMin) || 1.0;

    function scaleVix(v) {{
      if (v === null || v === undefined) return null;
      return CHART_MARGIN_TOP + CHART_PRICE_HEIGHT - ((v - vixMin) / vixSpan) * CHART_PRICE_HEIGHT;
    }}

    var vixLineWidth = n > 1000 ? 1.4 : 1.6;
    var vixPolyline = buildPolyline(subVix, scaleVix, '#e11d48', vixLineWidth);
    var y45 = scaleVix(45.0);
    var vixRefSvg = '<line x1="' + CHART_MARGIN_LEFT + '" y1="' + y45.toFixed(1) + '" x2="' + (CHART_MARGIN_LEFT + CHART_WIDTH) + '" y2="' + y45.toFixed(1) + '" stroke="#fda4af" stroke-width="1.2" stroke-dasharray="4,3" opacity="0.85" />' +
      '<text x="' + (CHART_MARGIN_LEFT + CHART_WIDTH - 8) + '" y="' + (y45 - 4).toFixed(1) + '" font-size="10" fill="#be123c" font-weight="600" text-anchor="end">VIX 45 抄底門檻</text>';

    var vixTicksSvg = '';
    var tickVals = [20, 30, 60];
    for (var tv = 0; tv < tickVals.length; tv++) {{
      var yt = scaleVix(tickVals[tv]);
      if (yt !== null && yt >= CHART_MARGIN_TOP && yt <= CHART_MARGIN_TOP + CHART_PRICE_HEIGHT) {{
        vixTicksSvg += '<text x="' + (CHART_MARGIN_LEFT + CHART_WIDTH - 8) + '" y="' + (yt + 3).toFixed(1) + '" font-size="9" fill="#fda4af" text-anchor="end">VIX ' + tickVals[tv] + '</text>';
      }}
    }}

    vixLayerSvg = '<g class="vix-line-layer" style="display:' + (layerVisibility['vix-line'] !== false ? 'inline' : 'none') + ';">' +
      vixRefSvg +
      vixTicksSvg +
      vixPolyline +
      '</g>';

    var lastVixVal = subVix[n - 1];
    if (lastVixVal !== null && lastVixVal !== undefined) {{
      vixPillItem = {{ name: 'VIX', val: lastVixVal, color: '#e11d48', customScale: scaleVix }};
    }}
  }}

  // 8.6 TQQQ 實際價格曲線 (獨立次軸，虛線參考；實際買賣標的，量級與 QQQ 不同)
  var validTqqq = [];
  for (var i = 0; i < n; i++) {{
    if (subTqqq[i] !== null && subTqqq[i] !== undefined) validTqqq.push(subTqqq[i]);
  }}
  var tqqqLayerLinSvg = '', tqqqLayerLogSvg = '';
  var tqqqPillItemLin = null, tqqqPillItemLog = null;
  if (validTqqq.length > 0) {{
    var tqqqVmin = Math.min.apply(null, validTqqq);
    var tqqqVmax = Math.max.apply(null, validTqqq);
    var tqqqPad = (tqqqVmax - tqqqVmin) * 0.05 || 1.0;
    var tqqqVminLin = tqqqVmin - tqqqPad, tqqqVmaxLin = tqqqVmax + tqqqPad;
    var tqqqSpanLin = (tqqqVmaxLin - tqqqVminLin) || 1.0;

    function scaleTqqqLin(v) {{
      if (v === null || v === undefined) return null;
      return CHART_MARGIN_TOP + CHART_PRICE_HEIGHT - ((v - tqqqVminLin) / tqqqSpanLin) * CHART_PRICE_HEIGHT;
    }}

    var tqqqSafeVmin = Math.max(tqqqVmin, 0.05);
    var tqqqSafeVmax = Math.max(tqqqVmax, tqqqSafeVmin * 1.5);
    var tqqqLogMin = Math.log10(tqqqSafeVmin);
    var tqqqLogMax = Math.log10(tqqqSafeVmax);
    var tqqqLogSpan = (tqqqLogMax - tqqqLogMin) || 1.0;

    function scaleTqqqLog(v) {{
      if (v === null || v === undefined || v <= 0) return null;
      var lv = Math.log10(Math.max(v, 0.05));
      return CHART_MARGIN_TOP + CHART_PRICE_HEIGHT - ((lv - tqqqLogMin) / tqqqLogSpan) * CHART_PRICE_HEIGHT;
    }}

    var tqqqLineWidth = n > 1000 ? 1.2 : 1.6;
    var tqqqDisplay = layerVisibility['tqqq-ref'] !== false ? 'inline' : 'none';
    tqqqLayerLinSvg = '<g class="tqqq-ref-layer" style="display:' + tqqqDisplay + ';"><g stroke-dasharray="6,4" opacity="0.6">' + buildPolyline(subTqqq, scaleTqqqLin, '#64748b', tqqqLineWidth) + '</g></g>';
    tqqqLayerLogSvg = '<g class="tqqq-ref-layer" style="display:' + tqqqDisplay + ';"><g stroke-dasharray="6,4" opacity="0.6">' + buildPolyline(subTqqq, scaleTqqqLog, '#64748b', tqqqLineWidth) + '</g></g>';

    var lastTqqqVal = subTqqq[n - 1];
    if (lastTqqqVal !== null && lastTqqqVal !== undefined) {{
      tqqqPillItemLin = {{ name: 'TQQQ', val: lastTqqqVal, color: '#64748b', customScale: scaleTqqqLin }};
      tqqqPillItemLog = {{ name: 'TQQQ', val: lastTqqqVal, color: '#64748b', customScale: scaleTqqqLog }};
    }}
  }}

  // 9. 右側 Price Pills (防重疊)
  function buildPills(items, scaleFn) {{
    var valid = [];
    for (var k = 0; k < items.length; k++) {{
      var itemScale = items[k].customScale || scaleFn;
      var y = itemScale(items[k].val);
      if (y !== null) valid.push({{ name: items[k].name, val: items[k].val, origY: y, color: items[k].color }});
    }}
    if (!valid.length) return '';
    valid.sort(function(a, b) {{ return a.origY - b.origY; }});
    var adjY = valid.map(function(it) {{ return it.origY; }});
    for (var i = 1; i < adjY.length; i++) {{
      if (adjY[i] - adjY[i - 1] < 20) adjY[i] = adjY[i - 1] + 20;
    }}
    for (var i = adjY.length - 2; i >= 0; i--) {{
      if (adjY[i + 1] - adjY[i] < 20) adjY[i] = adjY[i + 1] - 20;
    }}
    var pSvg = '';
    var xStart = CHART_MARGIN_LEFT + CHART_WIDTH;
    for (var i = 0; i < valid.length; i++) {{
      var it = valid[i];
      var ay = adjY[i];
      pSvg += '<path d="M ' + xStart + ' ' + it.origY.toFixed(1) + ' L ' + (xStart + 16) + ' ' + ay.toFixed(1) + ' L ' + (xStart + 24) + ' ' + ay.toFixed(1) + '" fill="none" stroke="' + it.color + '" stroke-width="1.2" stroke-dasharray="2,2" />' +
        '<rect x="' + (xStart + 26) + '" y="' + (ay - 9).toFixed(1) + '" width="112" height="18" rx="4" fill="' + it.color + '" />' +
        '<text x="' + (xStart + 82) + '" y="' + (ay + 4).toFixed(1) + '" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">' + it.name + ' ' + formatPrice(it.val) + '</text>';
    }}
    return pSvg;
  }}

  var lastClose = subClose[n - 1];
  var lastFast = subEmaFast[n - 1];
  var lastSlow = subEmaSlow[n - 1];
  var lastLong = subLongSma[n - 1];

  var pillDefLin = [
    {{ name: 'QQQ', val: lastClose, color: '#2563eb' }},
    {{ name: 'EMA' + chartData.ema_fast_period, val: lastFast, color: '#0d9488' }},
    {{ name: 'EMA' + chartData.ema_slow_period, val: lastSlow, color: '#ea580c' }},
    {{ name: 'SMA' + chartData.long_sma_period, val: lastLong, color: '#9333ea' }}
  ];
  var pillDefLog = pillDefLin.slice();
  if (tqqqPillItemLin) pillDefLin.push(tqqqPillItemLin);
  if (tqqqPillItemLog) pillDefLog.push(tqqqPillItemLog);
  if (vixPillItem) {{
    pillDefLin.push(vixPillItem);
    pillDefLog.push(vixPillItem);
  }}

  var pillsLinSvg = buildPills(pillDefLin, scaleLin);
  var pillsLogSvg = buildPills(pillDefLog, scaleLog);

  // 10. 組裝主圖 SVG
  var lineWidth = n > 1000 ? 1.4 : 1.8;
  var maWidth = n > 1000 ? 1.2 : 1.4;
  var totalHeight = CHART_MARGIN_TOP + CHART_PRICE_HEIGHT + CHART_MARGIN_BOTTOM;

  var labelsSvg = '<text x="' + CHART_MARGIN_LEFT + '" y="18" font-size="13" fill="#2563eb">■ QQQ 收盤價(訊號基礎)</text>' +
    '<text x="' + (CHART_MARGIN_LEFT + 180) + '" y="18" font-size="13" fill="#9333ea">■ 長期 SMA(' + chartData.long_sma_period + '日,框架)</text>' +
    '<text x="' + (CHART_MARGIN_LEFT + 400) + '" y="18" font-size="13" fill="#0d9488">■ 短期 EMA(' + chartData.ema_fast_period + '日)</text>' +
    '<text x="' + (CHART_MARGIN_LEFT + 570) + '" y="18" font-size="13" fill="#ea580c">■ 短期 EMA(' + chartData.ema_slow_period + '日)</text>' +
    '<text x="' + (CHART_MARGIN_LEFT + 740) + '" y="18" font-size="13" fill="#64748b">- - TQQQ 實際價格(右側次軸)</text>' +
    '<text x="' + (CHART_MARGIN_LEFT + 970) + '" y="18" font-size="13" fill="#16a34a">● 黃金交叉</text>' +
    '<text x="' + (CHART_MARGIN_LEFT + 1080) + '" y="18" font-size="13" fill="#dc2626">● 死亡交叉</text>' +
    '<text x="' + CHART_MARGIN_LEFT + '" y="36" font-size="13" fill="#d97706">▼ 重大金融事件</text>' +
    '<text x="' + (CHART_MARGIN_LEFT + 140) + '" y="36" font-size="13" fill="#e11d48">■ VIX 恐慌指數</text>' +
    '<text x="' + (CHART_MARGIN_LEFT + 270) + '" y="36" font-size="12" fill="#be123c">-- VIX 45 抄底門檻</text>';

  var isLog = currentScaleMode === 'log';
  var priceSvgHtml = '<svg id="price-chart-svg" viewBox="0 0 ' + CHART_SVG_WIDTH + ' ' + totalHeight + '" width="100%" height="' + totalHeight + '" style="background:#fff;max-width:100%;height:auto;display:block;" xmlns="http://www.w3.org/2000/svg">' +
    labelsSvg +
    xAxisSvg +
    eventsSvg +
    '<!-- 線性座標圖層 -->' +
    '<g id="plot-linear" style="display:' + (isLog ? 'none' : 'inline') + ';">' +
      yAxisLinSvg +
      buildPolyline(subClose, scaleLin, '#2563eb', lineWidth) +
      buildPolyline(subLongSma, scaleLin, '#9333ea', maWidth) +
      '<g class="ema-fast-layer" style="display:' + (layerVisibility['ema-fast'] ? 'inline' : 'none') + ';">' + buildPolyline(subEmaFast, scaleLin, '#0d9488', maWidth) + '</g>' +
      '<g class="ema-slow-layer" style="display:' + (layerVisibility['ema-slow'] ? 'inline' : 'none') + ';">' + buildPolyline(subEmaSlow, scaleLin, '#ea580c', maWidth) + '</g>' +
      tqqqLayerLinSvg +
      '<g class="cross-marker-layer" style="display:' + (layerVisibility['cross-marker'] ? 'inline' : 'none') + ';">' + markersLin + '</g>' +
      vixLayerSvg +
      pillsLinSvg +
    '</g>' +
    '<!-- 對數座標圖層 -->' +
    '<g id="plot-log" style="display:' + (isLog ? 'inline' : 'none') + ';">' +
      yAxisLogSvg +
      buildPolyline(subClose, scaleLog, '#2563eb', lineWidth) +
      buildPolyline(subLongSma, scaleLog, '#9333ea', maWidth) +
      '<g class="ema-fast-layer" style="display:' + (layerVisibility['ema-fast'] ? 'inline' : 'none') + ';">' + buildPolyline(subEmaFast, scaleLog, '#0d9488', maWidth) + '</g>' +
      '<g class="ema-slow-layer" style="display:' + (layerVisibility['ema-slow'] ? 'inline' : 'none') + ';">' + buildPolyline(subEmaSlow, scaleLog, '#ea580c', maWidth) + '</g>' +
      tqqqLayerLogSvg +
      '<g class="cross-marker-layer" style="display:' + (layerVisibility['cross-marker'] ? 'inline' : 'none') + ';">' + markersLog + '</g>' +
      vixLayerSvg +
      pillsLogSvg +
    '</g>';

  var priceCrosshairSvg = '<g id="price-crosshair" style="display:none;pointer-events:none;">' +
    '<line id="price-crosshair-line" x1="0" y1="' + CHART_MARGIN_TOP + '" x2="0" y2="' + (CHART_MARGIN_TOP + CHART_PRICE_HEIGHT) + '" stroke="#64748b" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.85" />' +
    '<circle id="price-dot-close" cx="0" cy="0" r="4.5" fill="#2563eb" stroke="#ffffff" stroke-width="1.5" />' +
    '<circle id="price-dot-fast" cx="0" cy="0" r="4" fill="#0d9488" stroke="#ffffff" stroke-width="1.5" />' +
    '<circle id="price-dot-slow" cx="0" cy="0" r="4" fill="#ea580c" stroke="#ffffff" stroke-width="1.5" />' +
    '<circle id="price-dot-long" cx="0" cy="0" r="4" fill="#9333ea" stroke="#ffffff" stroke-width="1.5" />' +
    '<circle id="price-dot-tqqq" cx="0" cy="0" r="4" fill="#64748b" stroke="#ffffff" stroke-width="1.5" />' +
    '<circle id="price-dot-vix" cx="0" cy="0" r="4.5" fill="#e11d48" stroke="#ffffff" stroke-width="1.5" />' +
    '<g id="price-date-pill">' +
      '<rect id="price-date-pill-bg" x="-42" y="' + (CHART_MARGIN_TOP + CHART_PRICE_HEIGHT + 2) + '" width="84" height="18" rx="4" fill="#0f172a" />' +
      '<text id="price-date-pill-text" x="0" y="' + (CHART_MARGIN_TOP + CHART_PRICE_HEIGHT + 15) + '" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">----</text>' +
    '</g>' +
  '</g>';

  priceSvgHtml += priceCrosshairSvg + '</svg>';

  var priceWrap = document.getElementById('price-chart-svg-wrap');
  if (priceWrap) priceWrap.innerHTML = priceSvgHtml;

  // 11. 重繪副圖 RSI(14)
  var rsiPlotTop = 36;
  var rsiPlotHeight = CHART_RSI_HEIGHT;
  function scaleRsi(v) {{
    if (v === null || v === undefined) return null;
    return rsiPlotTop + rsiPlotHeight - (v / 100) * rsiPlotHeight;
  }}

  var rsiYAxisSvg = '';
  for (var k = 0; k < ticksCount; k++) {{
    var frac = k / (ticksCount - 1);
    var val = frac * 100;
    var yPos = rsiPlotTop + rsiPlotHeight - frac * rsiPlotHeight;
    rsiYAxisSvg += '<line x1="' + CHART_MARGIN_LEFT + '" y1="' + yPos.toFixed(1) + '" x2="' + (CHART_MARGIN_LEFT + CHART_WIDTH) + '" y2="' + yPos.toFixed(1) + '" stroke="#e2e8f0" stroke-width="1" />' +
      '<text x="' + (CHART_MARGIN_LEFT - 8) + '" y="' + (yPos + 4).toFixed(1) + '" font-size="11" fill="#475569" text-anchor="end">' + val.toFixed(0) + '</text>' +
      '<text x="' + (CHART_MARGIN_LEFT + CHART_WIDTH + 8) + '" y="' + (yPos + 4).toFixed(1) + '" font-size="11" fill="#94a3b8" text-anchor="start">' + val.toFixed(0) + '</text>';
  }}

  var rsiXAxisSvg = '';
  var rsiYBottom = rsiPlotTop + rsiPlotHeight;
  if (n > 700) {{
    var yearIndices = [];
    var lastYear = null;
    for (var i = 0; i < n; i++) {{
      var yr = subDates[i].substring(0, 4);
      if (yr !== lastYear) {{
        yearIndices.push([i, yr]);
        lastYear = yr;
      }}
    }}
    var stepYr = yearIndices.length <= 18 ? 1 : 2;
    var idxs = [];
    for (var m = 0; m < yearIndices.length; m++) {{
      if (m % stepYr === 0) idxs.push(yearIndices[m]);
    }}
    if (idxs.length && idxs[idxs.length - 1][0] !== n - 1) idxs.push([n - 1, subDates[n - 1]]);
    for (var k = 0; k < idxs.length; k++) {{
      var xVal = xs[idxs[k][0]];
      rsiXAxisSvg += '<line x1="' + xVal.toFixed(1) + '" y1="' + rsiYBottom + '" x2="' + xVal.toFixed(1) + '" y2="' + (rsiYBottom + 5) + '" stroke="#94a3b8" stroke-width="1" />' +
        '<text x="' + xVal.toFixed(1) + '" y="' + (rsiYBottom + 18) + '" font-size="10" fill="#475569" text-anchor="middle">' + idxs[k][1] + '</text>';
    }}
  }} else {{
    var tickCount = 10;
    var stepTick = Math.max(1, Math.floor((n - 1) / (tickCount - 1)));
    var idxList = [];
    for (var i = 0; i < n; i += stepTick) idxList.push(i);
    if (idxList[idxList.length - 1] !== n - 1) idxList.push(n - 1);
    for (var k = 0; k < idxList.length; k++) {{
      var curIdx = idxList[k];
      var xVal = xs[curIdx];
      rsiXAxisSvg += '<line x1="' + xVal.toFixed(1) + '" y1="' + rsiYBottom + '" x2="' + xVal.toFixed(1) + '" y2="' + (rsiYBottom + 5) + '" stroke="#94a3b8" stroke-width="1" />' +
        '<text x="' + xVal.toFixed(1) + '" y="' + (rsiYBottom + 18) + '" font-size="10" fill="#475569" text-anchor="middle">' + subDates[curIdx] + '</text>';
    }}
  }}

  var refLinesSvg = '';
  var refDefs = [
    [70, "#dc2626", "70 過熱止盈"],
    [65, "#f59e0b", "65 超買線"],
    [55, "#64748b", "55 中線"],
    [50, "#0ea5e9", "50 進場下緣"],
    [45, "#dc2626", "45 避險"]
  ];
  for (var k = 0; k < refDefs.length; k++) {{
    var lv = refDefs[k][0], clr = refDefs[k][1], lb = refDefs[k][2];
    var yRef = scaleRsi(lv);
    refLinesSvg += '<line x1="' + CHART_MARGIN_LEFT + '" y1="' + yRef.toFixed(1) + '" x2="' + (CHART_MARGIN_LEFT + CHART_WIDTH) + '" y2="' + yRef.toFixed(1) + '" stroke="' + clr + '" stroke-width="1" stroke-dasharray="4,3" />' +
      '<text x="' + (CHART_MARGIN_LEFT + CHART_WIDTH + 8) + '" y="' + (yRef + 3).toFixed(1) + '" font-size="10" fill="' + clr + '">' + lb + '</text>';
  }}

  var latestRsiSvg = '';
  var lastRsiVal = subRsi[n - 1];
  if (lastRsiVal !== null && lastRsiVal !== undefined) {{
    var curRsiY = scaleRsi(lastRsiVal);
    var xStart = CHART_MARGIN_LEFT + CHART_WIDTH;
    latestRsiSvg = '<path d="M ' + xStart + ' ' + curRsiY.toFixed(1) + ' L ' + (xStart + 68) + ' ' + curRsiY.toFixed(1) + '" fill="none" stroke="#0f172a" stroke-width="1.2" />' +
      '<rect x="' + (xStart + 70) + '" y="' + (curRsiY - 9).toFixed(1) + '" width="68" height="18" rx="4" fill="#0f172a" />' +
      '<text x="' + (xStart + 104) + '" y="' + (curRsiY + 4).toFixed(1) + '" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">RSI ' + lastRsiVal.toFixed(1) + '</text>';
  }}

  var rsiCrosshairSvg = '<g id="rsi-crosshair" style="display:none;pointer-events:none;">' +
    '<line id="rsi-crosshair-line" x1="0" y1="' + rsiPlotTop + '" x2="0" y2="' + (rsiPlotTop + rsiPlotHeight) + '" stroke="#64748b" stroke-width="1.2" stroke-dasharray="3,3" opacity="0.85" />' +
    '<circle id="rsi-dot" cx="0" cy="0" r="4.5" fill="#0f172a" stroke="#ffffff" stroke-width="1.5" />' +
    '<g id="rsi-date-pill">' +
      '<rect id="rsi-date-pill-bg" x="-42" y="' + (rsiPlotTop + rsiPlotHeight + 2) + '" width="84" height="18" rx="4" fill="#0f172a" />' +
      '<text id="rsi-date-pill-text" x="0" y="' + (rsiPlotTop + rsiPlotHeight + 15) + '" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">----</text>' +
    '</g>' +
  '</g>';

  var rsiTotalHeight = rsiPlotTop + rsiPlotHeight + CHART_MARGIN_BOTTOM;
  var rsiLineWidth = n > 1000 ? 1.2 : 1.6;

  var rsiSvgHtml = '<svg id="rsi-chart-svg" viewBox="0 0 ' + CHART_SVG_WIDTH + ' ' + rsiTotalHeight + '" width="100%" height="' + rsiTotalHeight + '" style="background:#fff;max-width:100%;height:auto;display:block;" xmlns="http://www.w3.org/2000/svg">' +
    '<text x="' + CHART_MARGIN_LEFT + '" y="18" font-size="13" fill="#0f172a">■ QQQ RSI(14) 震盪指標(訊號基礎)</text>' +
    rsiYAxisSvg +
    rsiXAxisSvg +
    refLinesSvg +
    latestRsiSvg +
    buildPolyline(subRsi, scaleRsi, '#0f172a', rsiLineWidth) +
    rsiCrosshairSvg +
  '</svg>';

  var rsiWrap = document.getElementById('rsi-chart-svg-wrap');
  if (rsiWrap) rsiWrap.innerHTML = rsiSvgHtml;

  // 12. 更新重大金融事件時序紀錄表格 (若有勾選過濾)
  filterEventsTable(subDates[0], subDates[n - 1]);

  // 13. 保存當前展示區間資料供滑鼠懸浮游標 (Crosshair / Tooltip) 即時計算使用
  currentSliceData = {{
    dates: subDates,
    close: subClose,
    tqqqClose: subTqqq,
    longSma: subLongSma,
    emaFast: subEmaFast,
    emaSlow: subEmaSlow,
    rsi: subRsi,
    vix: subVix,
    xs: xs,
    n: n,
    scaleLin: scaleLin,
    scaleLog: scaleLog,
    scaleVix: scaleVix,
    scaleTqqqLin: validTqqq.length > 0 ? scaleTqqqLin : null,
    scaleTqqqLog: validTqqq.length > 0 ? scaleTqqqLog : null,
    scaleRsi: scaleRsi
  }};
  hideCrosshairs();
}}

function setChartRange(rangeKey) {{
  currentRangeKey = rangeKey;
  // 更新按鈕樣式
  var btns = document.querySelectorAll('.btn-range');
  btns.forEach(function(b) {{
    if (b.getAttribute('data-range') === rangeKey) {{
      b.classList.add('active');
    }} else {{
      b.classList.remove('active');
    }}
  }});
  var select = document.getElementById('preset-period-select');
  if (select) select.value = rangeKey;

  renderDynamicSVG(rangeKey);
}}

function setPresetPeriod(presetKey) {{
  setChartRange(presetKey);
}}

var activeHoverIdx = null;
var activeClientX = 0;
var activeClientY = 0;

function togglePriceScale(mode) {{
  currentScaleMode = mode;
  var pLin = document.getElementById('plot-linear');
  var pLog = document.getElementById('plot-log');
  if (pLin) pLin.style.display = mode === 'log' ? 'none' : 'inline';
  if (pLog) pLog.style.display = mode === 'log' ? 'inline' : 'none';

  var scSel = document.getElementById('price-scale-select');
  if (scSel && scSel.value !== mode) scSel.value = mode;

  if (activeHoverIdx !== null && currentSliceData) {{
    updateCrosshairAndTooltip(activeHoverIdx, activeClientX, activeClientY);
  }}
}}

function toggleLayer(layerName, isChecked) {{
  layerVisibility[layerName] = isChecked;
  var cls = layerName === 'financial-event' ? '.financial-event' : ('.' + layerName + '-layer');
  document.querySelectorAll(cls).forEach(function(el) {{
    el.style.display = isChecked ? 'inline' : 'none';
  }});
}}

function toggleEventsTableFilter(isChecked) {{
  var bounds = getSliceIndices(currentRangeKey);
  var subDates = chartData.dates.slice(bounds[0], bounds[1]);
  if (!subDates.length) return;
  filterEventsTable(subDates[0], subDates[subDates.length - 1], isChecked);
}}

function filterEventsTable(startDate, endDate, forceChecked) {{
  var chk = document.getElementById('filter-events-by-range');
  var shouldFilter = forceChecked !== undefined ? forceChecked : (chk && chk.checked);
  var trs = document.querySelectorAll('.event-tr');
  var visibleCount = 0;
  trs.forEach(function(tr) {{
    var d = tr.getAttribute('data-date');
    if (!shouldFilter || (d >= startDate && d <= endDate)) {{
      tr.style.display = '';
      visibleCount++;
    }} else {{
      tr.style.display = 'none';
    }}
  }});
  var countBadge = document.getElementById('events-count-badge');
  if (countBadge) {{
    if (shouldFilter) {{
      countBadge.innerText = '當前區間收錄 ' + visibleCount + ' 項重大事件（' + startDate + ' 至 ' + endDate + '）';
    }} else {{
      countBadge.innerText = '共收錄 ' + trs.length + ' 項重大事件 • 依時間最新順序呈現';
    }}
  }}
}}

function hideCrosshairs() {{
  activeHoverIdx = null;
  var pCross = document.getElementById('price-crosshair');
  var rCross = document.getElementById('rsi-crosshair');
  var tt = document.getElementById('chart-tooltip');
  if (pCross) pCross.style.display = 'none';
  if (rCross) rCross.style.display = 'none';
  if (tt) tt.style.display = 'none';

  var hBar = document.getElementById('price-hover-bar');
  if (hBar && chartData && currentSliceData && currentSliceData.n > 0) {{
    var n = currentSliceData.n;
    var d = currentSliceData.dates[n - 1];
    var c = currentSliceData.close[n - 1];
    var tq = currentSliceData.tqqqClose ? currentSliceData.tqqqClose[n - 1] : null;
    var v = (currentSliceData.vix && currentSliceData.vix.length > n - 1) ? currentSliceData.vix[n - 1] : null;
    var r = (currentSliceData.rsi && currentSliceData.rsi.length > n - 1) ? currentSliceData.rsi[n - 1] : null;
    var vInfo = getVixRegime(v);
    hBar.innerHTML = '<span style="color:#2563eb;font-weight:700;">最新交易日 (' + d + ')：</span>' +
      '<span>QQQ 收盤 <b>$' + formatPrice(c) + '</b></span> • ' +
      '<span>TQQQ 實際 <b style="color:#64748b;">$' + formatPrice(tq) + '</b></span> • ' +
      '<span>VIX 恐慌指數 <b style="color:' + vInfo.color + ';">' + formatPrice(v) + '</b> (' + vInfo.label + ')</span> • ' +
      '<span>RSI(14) <b>' + (r !== null && r !== undefined ? r.toFixed(1) : 'N/A') + '</b></span>' +
      '<span style="color:#64748b;margin-left:auto;font-size:11.5px;">（💡 在圖表任意處滑移可檢視歷史價格、VIX與均線精確數值）</span>';
  }}
}}

function handleChartHover(chartType, evt) {{
  if (!currentSliceData || !currentSliceData.n) return;
  var svgId = chartType === 'rsi' ? 'rsi-chart-svg' : 'price-chart-svg';
  var svg = document.getElementById(svgId);
  if (!svg) return;

  var rect = svg.getBoundingClientRect();
  if (rect.width <= 0) return;

  var clientX = evt.clientX;
  var clientY = evt.clientY;
  if (evt.touches && evt.touches.length > 0) {{
    clientX = evt.touches[0].clientX;
    clientY = evt.touches[0].clientY;
  }}

  var svgX = ((clientX - rect.left) / rect.width) * CHART_SVG_WIDTH;

  if (svgX < CHART_MARGIN_LEFT - 12 || svgX > CHART_MARGIN_LEFT + CHART_WIDTH + 12) {{
    hideCrosshairs();
    return;
  }}

  var clampedX = Math.max(CHART_MARGIN_LEFT, Math.min(CHART_MARGIN_LEFT + CHART_WIDTH, svgX));
  var ratio = (clampedX - CHART_MARGIN_LEFT) / CHART_WIDTH;
  var idx = Math.round(ratio * (currentSliceData.n - 1));
  idx = Math.max(0, Math.min(currentSliceData.n - 1, idx));

  activeHoverIdx = idx;
  activeClientX = clientX;
  activeClientY = clientY;

  updateCrosshairAndTooltip(idx, clientX, clientY);
}}

function updateCrosshairAndTooltip(idx, clientX, clientY) {{
  if (!currentSliceData || idx < 0 || idx >= currentSliceData.n) return;

  var d = currentSliceData.dates[idx];
  var c = currentSliceData.close[idx];
  var tq = currentSliceData.tqqqClose ? currentSliceData.tqqqClose[idx] : null;
  var f = currentSliceData.emaFast[idx];
  var s = currentSliceData.emaSlow[idx];
  var l = currentSliceData.longSma[idx];
  var v = (currentSliceData.vix && currentSliceData.vix.length > idx) ? currentSliceData.vix[idx] : null;
  var r = (currentSliceData.rsi && currentSliceData.rsi.length > idx) ? currentSliceData.rsi[idx] : null;
  var xPos = currentSliceData.xs[idx];

  var scaleFn = currentScaleMode === 'log' ? currentSliceData.scaleLog : currentSliceData.scaleLin;
  var scaleTqqqFn = currentScaleMode === 'log' ? currentSliceData.scaleTqqqLog : currentSliceData.scaleTqqqLin;

  // 1. 更新主圖 Crosshair
  var pCross = document.getElementById('price-crosshair');
  if (pCross) {{
    pCross.style.display = 'inline';
    var pLine = document.getElementById('price-crosshair-line');
    if (pLine) {{
      pLine.setAttribute('x1', xPos.toFixed(1));
      pLine.setAttribute('x2', xPos.toFixed(1));
    }}

    function setDot(dotId, val, customScale, isVisible) {{
      var dot = document.getElementById(dotId);
      if (!dot) return;
      if (val === null || val === undefined || isVisible === false) {{
        dot.style.display = 'none';
        return;
      }}
      var sf = customScale || scaleFn;
      var y = sf(val);
      if (y === null || isNaN(y)) {{
        dot.style.display = 'none';
      }} else {{
        dot.style.display = 'inline';
        dot.setAttribute('cx', xPos.toFixed(1));
        dot.setAttribute('cy', y.toFixed(1));
      }}
    }}

    setDot('price-dot-close', c, null, true);
    setDot('price-dot-fast', f, null, layerVisibility['ema-fast']);
    setDot('price-dot-slow', s, null, layerVisibility['ema-slow']);
    setDot('price-dot-long', l, null, true);
    setDot('price-dot-tqqq', tq, scaleTqqqFn, layerVisibility['tqqq-ref']);
    setDot('price-dot-vix', v, currentSliceData.scaleVix, layerVisibility['vix-line']);

    var pDateBg = document.getElementById('price-date-pill-bg');
    var pDateText = document.getElementById('price-date-pill-text');
    if (pDateBg && pDateText) {{
      pDateBg.setAttribute('x', (xPos - 42).toFixed(1));
      pDateText.setAttribute('x', xPos.toFixed(1));
      pDateText.textContent = d;
    }}
  }}

  // 2. 更新副圖 Crosshair
  var rCross = document.getElementById('rsi-crosshair');
  if (rCross) {{
    rCross.style.display = 'inline';
    var rLine = document.getElementById('rsi-crosshair-line');
    if (rLine) {{
      rLine.setAttribute('x1', xPos.toFixed(1));
      rLine.setAttribute('x2', xPos.toFixed(1));
    }}
    var rDot = document.getElementById('rsi-dot');
    if (rDot) {{
      if (r !== null && r !== undefined && currentSliceData.scaleRsi) {{
        var ry = currentSliceData.scaleRsi(r);
        if (ry !== null && !isNaN(ry)) {{
          rDot.style.display = 'inline';
          rDot.setAttribute('cx', xPos.toFixed(1));
          rDot.setAttribute('cy', ry.toFixed(1));
        }} else {{
          rDot.style.display = 'none';
        }}
      }} else {{
        rDot.style.display = 'none';
      }}
    }}
    var rDateBg = document.getElementById('rsi-date-pill-bg');
    var rDateText = document.getElementById('rsi-date-pill-text');
    if (rDateBg && rDateText) {{
      rDateBg.setAttribute('x', (xPos - 42).toFixed(1));
      rDateText.setAttribute('x', xPos.toFixed(1));
      rDateText.textContent = d;
    }}
  }}

  // 3. 漲跌幅計算
  var pctStr = '';
  var pctColor = '#64748b';
  if (idx > 0 && currentSliceData.close[idx - 1] !== null && c !== null) {{
    var prevC = currentSliceData.close[idx - 1];
    var pct = ((c - prevC) / prevC) * 100;
    pctStr = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
    pctColor = pct >= 0 ? '#16a34a' : '#dc2626';
  }}

  // 4. VIX 狀態與顏色
  var vInfo = getVixRegime(v);

  // 5. RSI 顏色與標籤
  var rsiColor = '#0f172a';
  var rsiTag = '';
  if (r !== null && r !== undefined) {{
    if (r >= 70) {{ rsiColor = '#dc2626'; rsiTag = '過熱'; }}
    else if (r >= 65) {{ rsiColor = '#f59e0b'; rsiTag = '超買'; }}
    else if (r <= 45) {{ rsiColor = '#dc2626'; rsiTag = '弱勢'; }}
    else {{ rsiColor = '#16a34a'; rsiTag = '健康'; }}
  }}

  // 6. 查找當日事件
  var evHtml = '';
  if (chartData.events) {{
    var ev = null;
    for (var k = 0; k < chartData.events.length; k++) {{
      if (chartData.events[k].date === d) {{ ev = chartData.events[k]; break; }}
    }}
    if (ev) {{
      evHtml = '<div style="margin-top:8px;padding-top:6px;border-top:1px dashed #e2e8f0;font-size:11px;color:#b45309;">' +
        '📌 <b>' + (ev.title || '金融事件') + '</b>' + (ev.description ? '：' + ev.description : '') +
        '</div>';
    }}
  }}

  // 7. 更新浮動 Tooltip 內容與定位
  var tt = document.getElementById('chart-tooltip');
  if (tt) {{
    tt.innerHTML = '<div style="font-weight:700;font-size:13px;border-bottom:1px solid #e2e8f0;padding-bottom:5px;display:flex;justify-content:space-between;align-items:center;">' +
      '<span>📅 ' + d + '</span>' +
      (pctStr ? '<span style="font-size:12px;font-weight:700;color:' + pctColor + ';">' + pctStr + '</span>' : '') +
      '</div>' +
      '<div class="chart-tooltip-grid">' +
        '<span style="color:#2563eb;font-weight:600;">■ QQQ 收盤(訊號基礎)：</span>' +
        '<span class="chart-tooltip-row-val" style="color:#2563eb;">$' + formatPrice(c) + '</span>' +

        '<span style="color:#64748b;font-weight:600;">- - TQQQ 實際價格：</span>' +
        '<span class="chart-tooltip-row-val" style="color:#64748b;">$' + formatPrice(tq) + '</span>' +

        '<span style="color:#e11d48;font-weight:600;">■ VIX 恐慌指數：</span>' +
        '<span class="chart-tooltip-row-val" style="color:' + vInfo.color + ';">' + formatPrice(v) + ' <span style="font-size:10px;padding:1px 5px;border-radius:4px;background:' + vInfo.bg + ';color:' + vInfo.color + ';">' + vInfo.label + '</span></span>' +

        '<span style="color:#0d9488;font-weight:600;">■ EMA ' + chartData.ema_fast_period + '日：</span>' +
        '<span class="chart-tooltip-row-val" style="color:#0d9488;">$' + formatPrice(f) + '</span>' +

        '<span style="color:#ea580c;font-weight:600;">■ EMA ' + chartData.ema_slow_period + '日：</span>' +
        '<span class="chart-tooltip-row-val" style="color:#ea580c;">$' + formatPrice(s) + '</span>' +

        '<span style="color:#9333ea;font-weight:600;">■ SMA ' + chartData.long_sma_period + '日：</span>' +
        '<span class="chart-tooltip-row-val" style="color:#9333ea;">$' + formatPrice(l) + '</span>' +

        '<span style="color:#0f172a;font-weight:600;">■ RSI(14)：</span>' +
        '<span class="chart-tooltip-row-val" style="color:' + rsiColor + ';">' + (r !== null && r !== undefined ? r.toFixed(1) : 'N/A') + (rsiTag ? ' (' + rsiTag + ')' : '') + '</span>' +
      '</div>' +
      evHtml;

    tt.style.display = 'block';

    var ttW = tt.offsetWidth || 240;
    var ttH = tt.offsetHeight || 220;
    var posX = clientX + 16;
    var posY = clientY + 16;
    if (posX + ttW > window.innerWidth - 12) {{
      posX = clientX - ttW - 16;
    }}
    if (posY + ttH > window.innerHeight - 12) {{
      posY = clientY - ttH - 16;
    }}
    tt.style.left = Math.max(8, posX) + 'px';
    tt.style.top = Math.max(8, posY) + 'px';
  }}

  // 8. 同步更新主圖上方指示列
  var hBar = document.getElementById('price-hover-bar');
  if (hBar) {{
    hBar.innerHTML = '<span style="color:#2563eb;font-weight:700;">' + d + '：</span>' +
      '<span>QQQ <b>$' + formatPrice(c) + '</b> <span style="color:' + pctColor + ';">(' + (pctStr || '基準') + ')</span></span> • ' +
      '<span>TQQQ <b style="color:#64748b;">$' + formatPrice(tq) + '</b></span> • ' +
      '<span>VIX <b style="color:' + vInfo.color + ';">' + formatPrice(v) + '</b> (' + vInfo.label + ')</span> • ' +
      '<span>EMA10 <b>$' + formatPrice(f) + '</b></span> • ' +
      '<span>EMA20 <b>$' + formatPrice(s) + '</b></span> • ' +
      '<span>SMA200 <b>$' + formatPrice(l) + '</b></span> • ' +
      '<span>RSI <b>' + (r !== null && r !== undefined ? r.toFixed(1) : 'N/A') + '</b></span>';
  }}
}}

function initHoverEvents() {{
  var pWrap = document.getElementById('price-chart-svg-wrap');
  var rWrap = document.getElementById('rsi-chart-svg-wrap');

  if (pWrap) {{
    pWrap.addEventListener('mousemove', function(e) {{ handleChartHover('price', e); }});
    pWrap.addEventListener('mouseleave', function() {{ hideCrosshairs(); }});
    pWrap.addEventListener('touchmove', function(e) {{ handleChartHover('price', e); }}, {{ passive: true }});
    pWrap.addEventListener('touchstart', function(e) {{ handleChartHover('price', e); }}, {{ passive: true }});
    pWrap.addEventListener('touchend', function() {{ hideCrosshairs(); }});
  }}

  if (rWrap) {{
    rWrap.addEventListener('mousemove', function(e) {{ handleChartHover('rsi', e); }});
    rWrap.addEventListener('mouseleave', function() {{ hideCrosshairs(); }});
    rWrap.addEventListener('touchmove', function(e) {{ handleChartHover('rsi', e); }}, {{ passive: true }});
    rWrap.addEventListener('touchstart', function(e) {{ handleChartHover('rsi', e); }}, {{ passive: true }});
    rWrap.addEventListener('touchend', function() {{ hideCrosshairs(); }});
  }}
}}

// === 持倉金額即時調整與試算 (財富種植園策略) ===
var allocConfig = {{
  target: {{
    cash: {alloc_target['cash']:.2f},
    qqq: {alloc_target['qqq']:.2f},
    tqqq: {alloc_target['tqqq']:.2f}
  }},
  defaultAmounts: {{
    cash: {alloc_amounts.get('cash', 0):.2f},
    qqq: {alloc_amounts.get('qqq', 0):.2f},
    tqqq: {alloc_amounts.get('tqqq', 0):.2f}
  }},
  threshold: {alloc_threshold}
}};

function onAllocationAmountChange() {{
  var cInput = document.getElementById('input-amt-cash');
  var qInput = document.getElementById('input-amt-qqq');
  var tInput = document.getElementById('input-amt-tqqq');
  if (!cInput || !qInput || !tInput) return;

  var c = parseFloat(cInput.value) || 0;
  var q = parseFloat(qInput.value) || 0;
  var t = parseFloat(tInput.value) || 0;
  var tot = c + q + t;

  var totLabel = document.getElementById('alloc-total-usd-label');
  if (totLabel) {{
    totLabel.textContent = '$' + tot.toLocaleString('en-US', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
  }}

  var cPct = tot > 0 ? (c / tot * 100) : 0;
  var qPct = tot > 0 ? (q / tot * 100) : 0;
  var tPct = tot > 0 ? (t / tot * 100) : 0;

  var cFill = document.getElementById('actual-cash-bar-fill');
  var qFill = document.getElementById('actual-qqq-bar-fill');
  var tFill = document.getElementById('actual-tqqq-bar-fill');
  var cLbl = document.getElementById('actual-cash-pct-label');
  var qLbl = document.getElementById('actual-qqq-pct-label');
  var tLbl = document.getElementById('actual-tqqq-pct-label');

  if (cFill) cFill.style.width = Math.max(0, Math.min(100, cPct)).toFixed(1) + '%';
  if (qFill) qFill.style.width = Math.max(0, Math.min(100, qPct)).toFixed(1) + '%';
  if (tFill) tFill.style.width = Math.max(0, Math.min(100, tPct)).toFixed(1) + '%';
  if (cLbl) cLbl.textContent = cPct.toFixed(1) + '%';
  if (qLbl) qLbl.textContent = qPct.toFixed(1) + '%';
  if (tLbl) tLbl.textContent = tPct.toFixed(1) + '%';

  // 偏離度與再平衡檢查
  var driftC = cPct - allocConfig.target.cash;
  var driftQ = qPct - allocConfig.target.qqq;
  var driftT = tPct - allocConfig.target.tqqq;
  var th = allocConfig.threshold;

  var needsRebalance = (Math.abs(driftC) > th || Math.abs(driftQ) > th || Math.abs(driftT) > th);
  var banner = document.getElementById('alloc-rebalance-banner');
  var bannerText = document.getElementById('alloc-rebalance-text');
  var actCard = document.getElementById('alloc-actions-container');
  var actList = document.getElementById('alloc-actions-list');

  if (needsRebalance && tot > 0) {{
    var parts = [];
    if (Math.abs(driftQ) > th) parts.push('QQQ' + (driftQ > 0 ? '超重' : '低配') + Math.abs(driftQ).toFixed(1) + '%');
    if (Math.abs(driftT) > th) parts.push('TQQQ' + (driftT > 0 ? '超重' : '低配') + Math.abs(driftT).toFixed(1) + '%');
    if (Math.abs(driftC) > th) parts.push('現金' + (driftC > 0 ? '超重' : '低配') + Math.abs(driftC).toFixed(1) + '%');

    if (banner) banner.style.display = 'block';
    if (bannerText) {{
      bannerText.textContent = '再平衡警示（門檻 ±' + th + '%）：' + parts.join('; ') + '。實際與目標權重偏離過大，建議調整部位。';
    }}

    // 計算建議買賣金額 (目標金額 - 目前金額)
    var targetCUsd = tot * (allocConfig.target.cash / 100);
    var targetQUsd = tot * (allocConfig.target.qqq / 100);
    var targetTUsd = tot * (allocConfig.target.tqqq / 100);

    var diffC = targetCUsd - c;
    var diffQ = targetQUsd - q;
    var diffT = targetTUsd - t;

    var actHtml = '<ul style="margin:4px 0 0 18px;padding:0;">';
    function fmtAct(sym, diff, pctDrift) {{
      if (Math.abs(pctDrift) <= th) return '';
      if (diff > 0) {{
        return '<li>' + sym + ' 低配 ' + Math.abs(pctDrift).toFixed(1) + '%：建議 <b>加碼/買入 $' + Math.round(diff).toLocaleString('en-US') + '</b> (目標 $' + Math.round(targetCUsd).toLocaleString('en-US') + ')</li>';
      }} else {{
        return '<li>' + sym + ' 超重 ' + Math.abs(pctDrift).toFixed(1) + '%：建議 <b>減碼/賣出 $' + Math.round(Math.abs(diff)).toLocaleString('en-US') + '</b> (目標 $' + Math.round(targetCUsd).toLocaleString('en-US') + ')</li>';
      }}
    }}
    if (Math.abs(driftQ) > th) {{
      actHtml += '<li>QQQ ' + (driftQ > 0 ? '超重' : '低配') + ' ' + Math.abs(driftQ).toFixed(1) + '%：建議 <b style="color:' + (diffQ > 0 ? '#16a34a' : '#dc2626') + ';">' + (diffQ > 0 ? '加碼買入' : '減碼賣出') + ' $' + Math.round(Math.abs(diffQ)).toLocaleString('en-US') + '</b> (拉至目標 $' + Math.round(targetQUsd).toLocaleString('en-US') + ')</li>';
    }}
    if (Math.abs(driftT) > th) {{
      actHtml += '<li>TQQQ ' + (driftT > 0 ? '超重' : '低配') + ' ' + Math.abs(driftT).toFixed(1) + '%：建議 <b style="color:' + (diffT > 0 ? '#16a34a' : '#dc2626') + ';">' + (diffT > 0 ? '加碼買入' : '減碼賣出') + ' $' + Math.round(Math.abs(diffT)).toLocaleString('en-US') + '</b> (拉至目標 $' + Math.round(targetTUsd).toLocaleString('en-US') + ')</li>';
    }}
    if (Math.abs(driftC) > th) {{
      actHtml += '<li>現金 ' + (driftC > 0 ? '超重' : '低配') + ' ' + Math.abs(driftC).toFixed(1) + '%：建議 <b style="color:' + (diffC > 0 ? '#16a34a' : '#dc2626') + ';">' + (diffC > 0 ? '補足保留現金' : '挪用部分現金加碼標的') + ' $' + Math.round(Math.abs(diffC)).toLocaleString('en-US') + '</b> (拉至目標 $' + Math.round(targetCUsd).toLocaleString('en-US') + ')</li>';
    }}
    actHtml += '</ul>';

    if (actCard) actCard.style.display = 'block';
    if (actList) actList.innerHTML = actHtml;
  }} else {{
    if (banner) banner.style.display = 'none';
    if (actCard) actCard.style.display = 'none';
  }}
}}

function saveAllocationToLocal() {{
  var c = document.getElementById('input-amt-cash').value;
  var q = document.getElementById('input-amt-qqq').value;
  var t = document.getElementById('input-amt-tqqq').value;
  localStorage.setItem('lrs_alloc_amounts', JSON.stringify({{ cash: c, qqq: q, tqqq: t }}));
  var tag = document.getElementById('alloc-actual-source-tag');
  if (tag) tag.textContent = '已保存於此瀏覽器';
  alert('持倉金額已保存於本機瀏覽器！下次開啟將自動帶入此組金額。');
}}

function resetAllocationDefault() {{
  document.getElementById('input-amt-cash').value = allocConfig.defaultAmounts.cash;
  document.getElementById('input-amt-qqq').value = allocConfig.defaultAmounts.qqq;
  document.getElementById('input-amt-tqqq').value = allocConfig.defaultAmounts.tqqq;
  localStorage.removeItem('lrs_alloc_amounts');
  var tag = document.getElementById('alloc-actual-source-tag');
  if (tag) tag.textContent = '系統快照預設值';
  onAllocationAmountChange();
}}

function initSavedAllocation() {{
  try {{
    var saved = localStorage.getItem('lrs_alloc_amounts');
    if (saved) {{
      var parsed = JSON.parse(saved);
      if (parsed && parsed.cash !== undefined) {{
        document.getElementById('input-amt-cash').value = parsed.cash;
        document.getElementById('input-amt-qqq').value = parsed.qqq;
        document.getElementById('input-amt-tqqq').value = parsed.tqqq;
        var tag = document.getElementById('alloc-actual-source-tag');
        if (tag) tag.textContent = '載入自瀏覽器暫存';
      }}
    }}
  }} catch(e) {{}}
  onAllocationAmountChange();
}}

// === S&P 500 席勒本益比 (CAPE) 與超額報酬率 (ECY) 動態向量圖表 ===
var capeHistoryData = {cape_history_json};
var nberRecessions = {nber_recessions_json};
var currentCapeRange = 'all';
var capeSeriesVisible = {{
  cape: true,
  ecy: true,
  sp500: true,
  recession: true
}};

function setCapeRange(range) {{
  currentCapeRange = range;
  var sel = document.getElementById('cape-range-selector');
  if (sel) {{
    var btns = sel.querySelectorAll('.range-btn');
    btns.forEach(function(b) {{
      if (b.textContent.trim().toLowerCase() === range.toLowerCase()) {{
        b.classList.add('active');
      }} else {{
        b.classList.remove('active');
      }}
    }});
  }}
  renderCapeDynamicChart();
}}

function toggleCapeSeries(seriesName, isVisible) {{
  capeSeriesVisible[seriesName] = isVisible;
  renderCapeDynamicChart();
}}

function renderCapeDynamicChart() {{
  var container = document.getElementById('cape-svg-container');
  if (!container || !capeHistoryData || capeHistoryData.length === 0) return;

  var totalLen = capeHistoryData.length;
  var filtered = capeHistoryData;

  // 計算區間過濾點數 (以月份為單位，1年=12個月)
  var countMap = {{ '1y': 12, '3y': 36, '5y': 60, '10y': 120, '20y': 240 }};
  if (countMap[currentCapeRange]) {{
    var cnt = countMap[currentCapeRange];
    filtered = capeHistoryData.slice(Math.max(0, totalLen - cnt));
  }}

  if (filtered.length === 0) return;

  var width = Math.max(900, container.clientWidth || 1320);
  var height = 420;
  var padLeft = 56;
  var padRight = 64;
  var padTop = 32;
  var padBottom = 48;
  var plotW = width - padLeft - padRight;
  var plotH = height - padTop - padBottom;

  // 1. 計算左軸範圍 (CAPE 與 ECY，刻度如 -12 ~ 48)
  var leftMin = -12.0;
  var leftMax = 48.0;
  if (currentCapeRange === '1y' || currentCapeRange === '3y' || currentCapeRange === '5y') {{
    var minVal = Infinity, maxVal = -Infinity;
    filtered.forEach(function(d) {{
      if (capeSeriesVisible.cape) {{ minVal = Math.min(minVal, d.cape); maxVal = Math.max(maxVal, d.cape); }}
      if (capeSeriesVisible.ecy) {{ minVal = Math.min(minVal, d.ecy); maxVal = Math.max(maxVal, d.ecy); }}
    }});
    if (minVal !== Infinity) {{
      leftMin = Math.floor(Math.min(-5, minVal - 3));
      leftMax = Math.ceil(Math.max(25, maxVal + 5));
    }}
  }}

  // 2. 計算右軸範圍 (S&P 500 指數)
  var rightMin = 0;
  var rightMax = 8000;
  var spVals = filtered.map(function(d) {{ return d.sp500; }}).filter(function(v) {{ return v !== null && v !== undefined; }});
  if (spVals.length > 0) {{
    var spMax = Math.max.apply(null, spVals);
    rightMax = Math.ceil(spMax * 1.1 / 1000) * 1000;
  }}

  function getX(idx) {{
    return padLeft + (idx / (filtered.length - 1 || 1)) * plotW;
  }}
  function getYLeft(val) {{
    return padTop + plotH - ((val - leftMin) / (leftMax - leftMin || 1)) * plotH;
  }}
  function getYRight(val) {{
    return padTop + plotH - ((val - rightMin) / (rightMax - rightMin || 1)) * plotH;
  }}

  // 3. 繪製衰退期背景陰影條 (NBER Recessions)
  var recessionsSvg = '';
  if (capeSeriesVisible.recession) {{
    var startDateStr = filtered[0].date;
    var endDateStr = filtered[filtered.length - 1].date;
    nberRecessions.forEach(function(rec) {{
      var rStart = rec[0], rEnd = rec[1];
      if (rEnd < startDateStr || rStart > endDateStr) return;
      var effStart = rStart < startDateStr ? startDateStr : rStart;
      var effEnd = rEnd > endDateStr ? endDateStr : rEnd;

      var sIdx = filtered.findIndex(function(d) {{ return d.date >= effStart; }});
      var eIdx = filtered.findIndex(function(d) {{ return d.date >= effEnd; }});
      if (sIdx === -1) sIdx = 0;
      if (eIdx === -1) eIdx = filtered.length - 1;

      var x1 = getX(sIdx);
      var x2 = getX(eIdx);
      var w = Math.max(2, x2 - x1);
      recessionsSvg += '<rect x="' + x1.toFixed(1) + '" y="' + padTop + '" width="' + w.toFixed(1) + '" height="' + plotH + '" fill="#f1f5f9" opacity="0.85" />';
    }});
  }}

  // 4. 繪製左軸與橫軸格線 (Y 軸 0 基準線、橫軸刻度)
  var gridSvg = '';
  var yTicks = 6;
  for (var i = 0; i <= yTicks; i++) {{
    var yVal = leftMin + (i / yTicks) * (leftMax - leftMin);
    var yPos = getYLeft(yVal);
    var isZero = Math.abs(yVal) < 0.1;
    var strokeColor = isZero ? '#94a3b8' : '#f1f5f9';
    var strokeWidth = isZero ? '1.5' : '1';
    var strokeDash = isZero ? '' : 'stroke-dasharray="3,3"';

    gridSvg += '<line x1="' + padLeft + '" y1="' + yPos.toFixed(1) + '" x2="' + (padLeft + plotW) + '" y2="' + yPos.toFixed(1) + '" stroke="' + strokeColor + '" stroke-width="' + strokeWidth + '" ' + strokeDash + ' />';
    // 左側刻度文字 (CAPE / ECY)
    gridSvg += '<text x="' + (padLeft - 10) + '" y="' + (yPos + 4).toFixed(1) + '" font-size="11" fill="#64748b" text-anchor="end">' + Math.round(yVal) + '</text>';

    // 右側刻度文字 (S&P 500)
    var rVal = rightMin + (i / yTicks) * (rightMax - rightMin);
    var rLabel = rVal >= 1000 ? (rVal / 1000).toFixed(0) + 'k' : Math.round(rVal);
    gridSvg += '<text x="' + (padLeft + plotW + 10) + '" y="' + (yPos + 4).toFixed(1) + '" font-size="11" fill="#eab308" text-anchor="start">' + rLabel + '</text>';
  }}

  // 橫軸年份刻度
  var xTicksSvg = '';
  var xStep = Math.max(1, Math.floor(filtered.length / 10));
  for (var j = 0; j < filtered.length; j += xStep) {{
    var xPos = getX(j);
    var dtStr = filtered[j].date;
    var yrLabel = dtStr.substring(0, 4);
    xTicksSvg += '<line x1="' + xPos.toFixed(1) + '" y1="' + (padTop + plotH) + '" x2="' + xPos.toFixed(1) + '" y2="' + (padTop + plotH + 5) + '" stroke="#cbd5e1" />';
    xTicksSvg += '<text x="' + xPos.toFixed(1) + '" y="' + (padTop + plotH + 18) + '" font-size="11" fill="#64748b" text-anchor="middle">' + yrLabel + '</text>';
  }}

  // 5. 繪製折線 (CAPE: #2563eb, ECY: #dc2626, S&P 500: #eab308)
  function buildPathD(arr, isRightAxis) {{
    var dStr = '';
    arr.forEach(function(pt, idx) {{
      var x = getX(idx);
      var y = isRightAxis ? getYRight(pt) : getYLeft(pt);
      dStr += (idx === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
    }});
    return dStr;
  }}

  var capePath = capeSeriesVisible.cape ? '<path d="' + buildPathD(filtered.map(function(d) {{ return d.cape; }}), false) + '" fill="none" stroke="#2563eb" stroke-width="2.2" />' : '';
  var ecyPath = capeSeriesVisible.ecy ? '<path d="' + buildPathD(filtered.map(function(d) {{ return d.ecy; }}), false) + '" fill="none" stroke="#dc2626" stroke-width="2.0" />' : '';
  var sp500Path = capeSeriesVisible.sp500 ? '<path d="' + buildPathD(filtered.map(function(d) {{ return d.sp500; }}), true) + '" fill="none" stroke="#eab308" stroke-width="1.8" />' : '';

  // 浮水印商標 (對齊玩股網風格 WantGoo 玩股網)
  var watermark = '<text x="' + (padLeft + plotW / 2) + '" y="' + (padTop + 40) + '" font-size="15" fill="#cbd5e1" font-weight="600" text-anchor="middle" letter-spacing="1">WantGoo 玩股網 宏觀數據核心統計</text>';

  // 組合 SVG
  var svgHtml = '<svg id="cape-dynamic-svg" viewBox="0 0 ' + width + ' ' + height + '" width="100%" height="' + height + '" style="display:block;cursor:crosshair;">' +
    recessionsSvg +
    watermark +
    gridSvg +
    xTicksSvg +
    capePath +
    ecyPath +
    sp500Path +
    '<line id="cape-crosshair-line" x1="0" y1="' + padTop + '" x2="0" y2="' + (padTop + plotH) + '" stroke="#64748b" stroke-width="1" stroke-dasharray="3,3" style="display:none;" />' +
    '<circle id="cape-dot-cape" r="4.5" fill="#2563eb" stroke="#fff" stroke-width="2" style="display:none;" />' +
    '<circle id="cape-dot-ecy" r="4.5" fill="#dc2626" stroke="#fff" stroke-width="2" style="display:none;" />' +
    '<circle id="cape-dot-sp500" r="4.5" fill="#eab308" stroke="#fff" stroke-width="2" style="display:none;" />' +
    '</svg>';

  container.innerHTML = svgHtml;

  // 6. 綁定滑鼠懸浮 Crosshair 與動態指示列
  var svgEl = document.getElementById('cape-dynamic-svg');
  if (svgEl) {{
    svgEl.addEventListener('mousemove', function(e) {{
      var rect = svgEl.getBoundingClientRect();
      var mouseX = (e.clientX - rect.left) * (width / rect.width);
      if (mouseX < padLeft || mouseX > padLeft + plotW) {{
        hideCapeCrosshair();
        return;
      }}
      var ratio = (mouseX - padLeft) / plotW;
      var idx = Math.round(ratio * (filtered.length - 1));
      idx = Math.max(0, Math.min(filtered.length - 1, idx));
      var pt = filtered[idx];

      var xPos = getX(idx);
      var cLine = document.getElementById('cape-crosshair-line');
      if (cLine) {{
        cLine.setAttribute('x1', xPos);
        cLine.setAttribute('x2', xPos);
        cLine.style.display = 'block';
      }}

      var dotC = document.getElementById('cape-dot-cape');
      var dotE = document.getElementById('cape-dot-ecy');
      var dotS = document.getElementById('cape-dot-sp500');

      if (dotC && capeSeriesVisible.cape) {{
        dotC.setAttribute('cx', xPos);
        dotC.setAttribute('cy', getYLeft(pt.cape));
        dotC.style.display = 'block';
      }}
      if (dotE && capeSeriesVisible.ecy) {{
        dotE.setAttribute('cx', xPos);
        dotE.setAttribute('cy', getYLeft(pt.ecy));
        dotE.style.display = 'block';
      }}
      if (dotS && capeSeriesVisible.sp500) {{
        dotS.setAttribute('cx', xPos);
        dotS.setAttribute('cy', getYRight(pt.sp500));
        dotS.style.display = 'block';
      }}

      // 更新 Hover 狀態列文字
      var hBar = document.getElementById('cape-hover-bar');
      if (hBar) {{
        hBar.innerHTML = '<span style="color:#0f172a;font-weight:700;">' + pt.date + '：</span>' +
          '<span><b style="color:#2563eb;">● CAPE 席勒本益比</b>: <b>' + pt.cape.toFixed(2) + '</b></span> • ' +
          '<span><b style="color:#dc2626;">● ECY 超額報酬率</b>: <b>' + pt.ecy.toFixed(2) + '%</b></span> • ' +
          '<span><b style="color:#eab308;">● S&P 500 指數</b>: <b>' + pt.sp500.toLocaleString('en-US', {{ minimumFractionDigits: 1 }}) + '</b></span>';
      }}
    }});

    svgEl.addEventListener('mouseleave', function() {{
      hideCapeCrosshair();
    }});
  }}
}}

function hideCapeCrosshair() {{
  var cLine = document.getElementById('cape-crosshair-line');
  var dotC = document.getElementById('cape-dot-cape');
  var dotE = document.getElementById('cape-dot-ecy');
  var dotS = document.getElementById('cape-dot-sp500');
  if (cLine) cLine.style.display = 'none';
  if (dotC) dotC.style.display = 'none';
  if (dotE) dotE.style.display = 'none';
  if (dotS) dotS.style.display = 'none';
  var hBar = document.getElementById('cape-hover-bar');
  if (hBar) {{
    hBar.innerHTML = '<span style="color:#64748b;">💡 游標滑移至圖上可即時檢視歷史任一月份的 CAPE、ECY 與標普指數精確數值</span>';
  }}
}}

function bootChart() {{
  if (chartData) {{
    var initRange = chartData.default_range || '1y';
    setChartRange(initRange);
  }}
  initHoverEvents();
  initSavedAllocation();
  renderCapeDynamicChart();
}}

window.addEventListener('resize', function() {{
  renderCapeDynamicChart();
}});

if (document.readyState === 'loading') {{
  document.addEventListener('DOMContentLoaded', bootChart);
}} else {{
  bootChart();
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
      <span class="badge-inception">全歷史時間軸：{first_full_date} 至 {last_date}（自 TQQQ 成立開始）</span>
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

  <!-- 3. 市場指標即時速覽（充分利用寬螢幕與兩側空間） -->
  <div class="card">
    <h3 style="margin-top:0;font-size:16px;color:#0f172a;margin-bottom:12px;">即時量化指標與均線乖離率速覽</h3>
    {metrics_panel_html}
  </div>

  <!-- 4. VIX 恐慌指數綜合判斷與歷史抄底勝率分析 -->
  {vix_analysis_html}

  <!-- 4.2 S&P 500 席勒本益比 (CAPE) 與超額報酬率 (ECY) 宏觀估值分析 -->
  {cape_block_html}

  <!-- 4.5 現金/QQQ/TQQQ 三資產配置（財富種植園策略） -->
  {allocation_html}

  <!-- 5. 價格與均線區塊 -->
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px;">
      <h3 style="margin:0;font-size:18px;">價格與均線（長期SMA框架 + 短期EMA 10日/20日觸發）</h3>
      <span id="chart-window-badge" style="font-size:12px;color:#475569;background:#f8fafc;padding:3px 8px;border-radius:4px;border:1px solid #e2e8f0;">
        時間軸已延長追溯回 TQQQ 成立首日 ({first_full_date}) • 共 {total_dates_count} 交易日
      </span>
    </div>
    <p style="margin:0 0 10px;font-size:12.5px;color:#64748b;">
      訊號基礎已改採 <b style="color:#2563eb;">QQQ</b>（長期SMA框架與短期EMA黃金/死亡交叉皆計算於 QQQ 收盤價，假訊號率更低），
      圖中 <b style="color:#64748b;">TQQQ 實際價格</b> 以虛線呈現於右側獨立次軸，僅供參考（實際買賣標的仍是 TQQQ）。
    </p>
    {price_svg}
  </div>

  <!-- 6. RSI(14) 震盪指標區塊 -->
  <div class="card">
    <h3 style="margin-top:0;font-size:18px;">RSI(14) 震盪指標</h3>
    {rsi_svg}
  </div>

  <!-- 7. 重大金融事件時間軸 -->
  {events_table_html}

  <footer>
    TQQQ 槓桿輪換策略 (LRS) 平台 • 版本：{VERSION} • 報表時間戳記：{now_cst} • 時間軸追溯自 2010 年成立首日 • 零外部套件相依純標準庫架構
  </footer>

  <!-- 滑鼠懸浮浮動資訊卡 (Tooltip，呈現當日價格、VIX指數等精確數值) -->
  <div id="chart-tooltip" class="chart-tooltip"></div>
</body></html>"""

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
