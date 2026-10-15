"""零相依套件的圖表產生器：純字串組裝 SVG，輸出單一自包含 HTML 報告。

主圖：TQQQ 收盤價 + 長期 SMA(預設200日，框架) + 短期 EMA(預設20日，觸發)，
      並標示黃金/死亡交叉點。
副圖：RSI(14)，含 45/50/55/65/70 參考線（避險/進場下緣/中線/超買/過熱）。
"""
from __future__ import annotations

from typing import List, Optional

from .signals import DailyIndicators, Recommendation

WIDTH = 920
PRICE_HEIGHT = 380
RSI_HEIGHT = 180
MARGIN = 40


def _xs(n: int, width: int) -> List[float]:
    if n <= 1:
        return [MARGIN]
    step = (width - 2 * MARGIN) / (n - 1)
    return [MARGIN + i * step for i in range(n)]


def _polyline(xs: List[float], ys: List[Optional[float]], color: str, width: float = 1.6) -> str:
    points = []
    for x, y in zip(xs, ys):
        if y is None:
            continue
        points.append(f"{x:.1f},{y:.1f}")
    if len(points) < 2:
        return ""
    return f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="{width}" />'


def _render_price_svg(ind: DailyIndicators, window: int) -> str:
    dates = ind.dates[-window:]
    close = ind.tqqq_close[-window:]
    long_sma = ind.tqqq_sma_chart_long[-window:]
    short_ema = ind.tqqq_ema_chart_short[-window:]
    ema_fast = ind.tqqq_ema_fast[-window:]
    ema_slow = ind.tqqq_ema_slow[-window:]

    all_vals = [v for v in close + [x for x in long_sma if x is not None] + [x for x in short_ema if x is not None] if v is not None]
    vmin, vmax = min(all_vals), max(all_vals)
    span = (vmax - vmin) or 1.0

    def scale_one(v):
        if v is None:
            return None
        return PRICE_HEIGHT - MARGIN - (v - vmin) / span * (PRICE_HEIGHT - 2 * MARGIN)

    y_close = [scale_one(v) for v in close]
    y_long = [scale_one(v) for v in long_sma]
    y_short = [scale_one(v) for v in short_ema]
    xs = _xs(len(dates), WIDTH)

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

    labels = f'''
    <text x="{MARGIN}" y="16" font-size="13" fill="#2563eb">■ TQQQ 收盤價</text>
    <text x="180" y="16" font-size="13" fill="#9333ea">■ 長期 SMA(框架)</text>
    <text x="340" y="16" font-size="13" fill="#ea580c">■ 短期 EMA(觸發)</text>
    <text x="500" y="16" font-size="13" fill="#16a34a">● 黃金交叉</text>
    <text x="600" y="16" font-size="13" fill="#dc2626">● 死亡交叉</text>
    '''

    return f'''
    <svg width="{WIDTH}" height="{PRICE_HEIGHT}" xmlns="http://www.w3.org/2000/svg" style="background:#fff">
      {labels}
      {_polyline(xs, y_close, "#2563eb", 1.8)}
      {_polyline(xs, y_long, "#9333ea", 1.4)}
      {_polyline(xs, y_short, "#ea580c", 1.4)}
      {marker_svg}
    </svg>
    '''


def _render_rsi_svg(ind: DailyIndicators, window: int) -> str:
    dates = ind.dates[-window:]
    rsi = ind.tqqq_rsi[-window:]
    xs = _xs(len(dates), WIDTH)

    def scale_one(v):
        if v is None:
            return None
        return RSI_HEIGHT - MARGIN - (v / 100) * (RSI_HEIGHT - 2 * MARGIN)

    y_rsi = [scale_one(v) for v in rsi]

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
            f'<line x1="{MARGIN}" y1="{y:.1f}" x2="{WIDTH-MARGIN}" y2="{y:.1f}" '
            f'stroke="{color}" stroke-width="1" stroke-dasharray="4,3" />'
            f'<text x="{WIDTH-MARGIN+4}" y="{y+3:.1f}" font-size="10" fill="{color}">{label}</text>'
        )

    return f'''
    <svg width="{WIDTH+70}" height="{RSI_HEIGHT}" xmlns="http://www.w3.org/2000/svg" style="background:#fff">
      <text x="{MARGIN}" y="16" font-size="13" fill="#0f172a">■ TQQQ RSI(14)</text>
      {''.join(ref_lines)}
      {_polyline(xs, y_rsi, "#0f172a", 1.6)}
    </svg>
    '''


def render_html_report(path: str, ind: DailyIndicators, recommendation: Recommendation, window: int = 250) -> None:
    price_svg = _render_price_svg(ind, window)
    rsi_svg = _render_rsi_svg(ind, window)

    rules_html = "".join(
        f"<li><b>{r['id']}</b> {r['name']} — {r['message']}</li>" for r in recommendation.matched_rules
    ) or "<li>（無規則觸發，維持觀望）</li>"

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>LRS 槓桿輪換策略報告 - {recommendation.date}</title>
<style>
body {{ font-family: -apple-system, "Noto Sans TC", sans-serif; margin: 24px; color: #0f172a; }}
.card {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
.action {{ font-size: 22px; font-weight: 700; }}
</style></head>
<body>
  <h1>TQQQ 槓桿輪換策略 (LRS) — {recommendation.date}</h1>
  <div class="card">
    <div class="action">建議動作：{recommendation.action_label}</div>
    <h3>符合規則</h3>
    <ul>{rules_html}</ul>
  </div>
  <div class="card"><h3>價格與均線（長期SMA框架 + 短期EMA觸發）</h3>{price_svg}</div>
  <div class="card"><h3>RSI(14) 震盪指標</h3>{rsi_svg}</div>
</body></html>"""

    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
