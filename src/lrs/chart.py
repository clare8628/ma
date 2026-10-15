"""零相依套件的圖表產生器：純字串組裝 SVG，輸出單一自包含 HTML 報告。

主圖：TQQQ 收盤價 + 長期 SMA(預設200日，框架) + 短期 EMA 10日/20日(觸發)，
      兩條短期 EMA 各自可用圖上開關隱藏，並標示黃金/死亡交叉點。
副圖：RSI(14)，含 45/50/55/65/70 參考線（避險/進場下緣/中線/超買/過熱）。
兩圖皆含縱軸（數值刻度）與橫軸（日期刻度）。
"""
from __future__ import annotations

from typing import List, Optional

from .signals import DailyIndicators, Recommendation

WIDTH = 920
MARGIN_LEFT = 56
MARGIN_RIGHT = 90
MARGIN_TOP = 34
MARGIN_BOTTOM = 40
PRICE_PLOT_HEIGHT = 380
RSI_PLOT_HEIGHT = 300  # 放大縱軸刻度，原為 100px 繪圖高度，現增至 300px

SVG_WIDTH = MARGIN_LEFT + WIDTH + MARGIN_RIGHT


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


def _format_price(v: float) -> str:
    if v >= 100:
        return f"{v:.0f}"
    return f"{v:.1f}"


def _y_axis(vmin: float, vmax: float, plot_top: float, plot_height: float, fmt=_format_price, ticks: int = 5) -> str:
    """畫出縱軸刻度線、數值標籤與水平格線。"""
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
        )
    return "".join(parts)


def _x_axis(dates: List[str], xs: List[float], y_bottom: float, tick_count: int = 7) -> str:
    """畫出橫軸刻度線與日期標籤。"""
    n = len(dates)
    if n == 0:
        return ""
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


def _render_price_svg(ind: DailyIndicators, window: int, long_sma_period: int, ema_fast_period: int, ema_slow_period: int) -> str:
    dates = ind.dates[-window:]
    close = ind.tqqq_close[-window:]
    long_sma = ind.tqqq_sma_chart_long[-window:]
    ema_fast = ind.tqqq_ema_fast[-window:]
    ema_slow = ind.tqqq_ema_slow[-window:]

    all_vals = [v for v in close + [x for x in long_sma if x is not None] + [x for x in ema_fast if x is not None] + [x for x in ema_slow if x is not None] if v is not None]
    vmin, vmax = min(all_vals), max(all_vals)
    pad = (vmax - vmin) * 0.05 or 1.0
    vmin, vmax = vmin - pad, vmax + pad
    span = (vmax - vmin) or 1.0

    plot_top = MARGIN_TOP
    plot_height = PRICE_PLOT_HEIGHT

    def scale_one(v):
        if v is None:
            return None
        return plot_top + plot_height - (v - vmin) / span * plot_height

    y_close = [scale_one(v) for v in close]
    y_long = [scale_one(v) for v in long_sma]
    y_fast = [scale_one(v) for v in ema_fast]
    y_slow = [scale_one(v) for v in ema_slow]
    xs = _xs(len(dates))

    markers = []
    for i in range(1, len(dates)):
        f0, s0 = ema_fast[i - 1], ema_slow[i - 1]
        f1, s1 = ema_fast[i], ema_slow[i]
        if None in (f0, s0, f1, s1):
            continue
        if f0 <= s0 and f1 > s1:
            markers.append((xs[i], scale_one(close[i]), "#16a34a", "黃金交叉", dates[i]))
        elif f0 >= s0 and f1 < s1:
            markers.append((xs[i], scale_one(close[i]), "#dc2626", "死亡交叉", dates[i]))

    marker_svg = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"><title>{label} {date}</title></circle>'
        for x, y, color, label, date in markers
    )

    total_height = MARGIN_TOP + PRICE_PLOT_HEIGHT + MARGIN_BOTTOM

    labels = f'''
    <text x="{MARGIN_LEFT}" y="16" font-size="13" fill="#2563eb">■ TQQQ 收盤價</text>
    <text x="{MARGIN_LEFT + 140}" y="16" font-size="13" fill="#9333ea">■ 長期 SMA({long_sma_period}日,框架)</text>
    <text x="{MARGIN_LEFT + 320}" y="16" font-size="13" fill="#0d9488">■ 短期 EMA({ema_fast_period}日)</text>
    <text x="{MARGIN_LEFT + 470}" y="16" font-size="13" fill="#ea580c">■ 短期 EMA({ema_slow_period}日)</text>
    <text x="{MARGIN_LEFT + 620}" y="16" font-size="13" fill="#16a34a">● 黃金交叉</text>
    <text x="{MARGIN_LEFT + 710}" y="16" font-size="13" fill="#dc2626">● 死亡交叉</text>
    '''

    y_axis_svg = _y_axis(vmin, vmax, plot_top, plot_height)
    x_axis_svg = _x_axis(dates, xs, plot_top + plot_height)

    toggle_bar = f'''
    <div style="font-size:13px;margin:4px 0 8px;color:#334155;">
      <label style="margin-right:16px;cursor:pointer;">
        <input type="checkbox" checked onchange="document.getElementById('ema-fast-line').style.display=this.checked?'inline':'none'"> 顯示短期 EMA({ema_fast_period}日)
      </label>
      <label style="cursor:pointer;">
        <input type="checkbox" checked onchange="document.getElementById('ema-slow-line').style.display=this.checked?'inline':'none'"> 顯示短期 EMA({ema_slow_period}日)
      </label>
    </div>
    '''

    return f'''
    {toggle_bar}
    <svg width="{SVG_WIDTH}" height="{total_height}" xmlns="http://www.w3.org/2000/svg" style="background:#fff">
      {labels}
      {y_axis_svg}
      {x_axis_svg}
      {_polyline(xs, y_close, "#2563eb", 1.8)}
      {_polyline(xs, y_long, "#9333ea", 1.4)}
      <g id="ema-fast-line">{_polyline(xs, y_fast, "#0d9488", 1.4)}</g>
      <g id="ema-slow-line">{_polyline(xs, y_slow, "#ea580c", 1.4)}</g>
      {marker_svg}
    </svg>
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
            f'<text x="{MARGIN_LEFT + WIDTH + 4}" y="{y+3:.1f}" font-size="10" fill="{color}">{label}</text>'
        )

    total_height = MARGIN_TOP + RSI_PLOT_HEIGHT + MARGIN_BOTTOM

    return f'''
    <svg width="{SVG_WIDTH}" height="{total_height}" xmlns="http://www.w3.org/2000/svg" style="background:#fff">
      <text x="{MARGIN_LEFT}" y="16" font-size="13" fill="#0f172a">■ TQQQ RSI(14)</text>
      {y_axis_svg}
      {x_axis_svg}
      {''.join(ref_lines)}
      {_polyline(xs, y_rsi, "#0f172a", 1.6)}
    </svg>
    '''


def render_html_report(
    path: str,
    ind: DailyIndicators,
    recommendation: Recommendation,
    settings: Optional[dict] = None,
    window: int = 250,
) -> None:
    ma_cfg = (settings or {}).get("moving_averages", {})
    long_sma_period = ma_cfg.get("chart_long_sma", 200)
    ema_fast_period = ma_cfg.get("target_fast_ema", 10)
    ema_slow_period = ma_cfg.get("target_slow_ema", 20)

    price_svg = _render_price_svg(ind, window, long_sma_period, ema_fast_period, ema_slow_period)
    rsi_svg = _render_rsi_svg(ind, window)

    rules_html = "".join(
        f"<li><b>{r['id']}</b> {r['name']} — {r['message']}</li>" for r in recommendation.matched_rules
    ) or "<li>（無規則觸發，維持觀望）</li>"

    tqqq_close = ind.tqqq_close[-1]
    qqq_close = ind.qqq_close[-1]

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>LRS 槓桿輪換策略報告 - {recommendation.date}</title>
<style>
body {{ font-family: -apple-system, "Noto Sans TC", sans-serif; margin: 24px; color: #0f172a; }}
.card {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
.action {{ font-size: 22px; font-weight: 700; }}
.asof {{ font-size: 14px; color: #475569; margin-top: 4px; }}
</style></head>
<body>
  <h1>TQQQ 槓桿輪換策略 (LRS) — {recommendation.date}</h1>
  <div class="card">
    <div class="action">建議動作：{recommendation.action_label}</div>
    <div class="asof">資料日期：{recommendation.date}　TQQQ 收盤：{_format_price(tqqq_close)}　QQQ 收盤：{_format_price(qqq_close)}（每日交易日自動更新）</div>
    <h3>符合規則</h3>
    <ul>{rules_html}</ul>
  </div>
  <div class="card"><h3>價格與均線（長期SMA框架 + 短期EMA 10日/20日觸發）</h3>{price_svg}</div>
  <div class="card"><h3>RSI(14) 震盪指標</h3>{rsi_svg}</div>
</body></html>"""

    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
