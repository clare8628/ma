# LRS — TQQQ 槓桿輪換策略 (Leverage Rotation Strategy)

觀察美股大盤 (QQQ) 的移動平均線狀態，搭配 TQQQ 的 EMA 交叉與 RSI(14) 震盪
過濾，給出進場 / 出場 / 減碼 / 止盈建議，並標註符合的具體規則。零第三方相依，
只用 Python 標準庫（`urllib`、`json`、`csv`），可直接在任何有 Python 3.8+
的環境執行或部署。

## 快速開始

```bash
# 抓取最新 QQQ/TQQQ 資料並輸出建議 + state/report.html 圖表報告
python3 main.py

# 離線模式（自備 CSV，欄位: date,close）
python3 main.py --qqq-csv qqq.csv --tqqq-csv tqqq.csv

# 依建議實際進出場後，更新本地持倉狀態（用於「持股期間」風控規則）
python3 main.py --mark-filled --price 85.3
python3 main.py --mark-closed

# 執行測試
python3 -m unittest discover -s tests -v
```

## 架構

```
config/settings.json   均線週期、RSI 門檻、再平衡日期等全域參數
config/rules.json      可編輯的判斷/提醒規則（新增規則不需改程式碼）
src/lrs/
  indicators.py         SMA / EMA / RSI(Wilder) 純函式
  data.py               Yahoo Finance chart API 擷取 + 本地快取 + CSV 離線載入
  rules_engine.py        資料驅動規則引擎（>, <, crosses_above, crosses_below ...）
  signals.py             整合 QQQ/TQQQ 指標、建立 context、產生最終建議
  rebalance.py            每年 11/1 再平衡窗口檢核
  chart.py               零相依 SVG 圖表產生器（寫出 state/report.html）
  position_state.py       本地持倉狀態（JSON），供風控規則使用
main.py                  CLI 入口
```

## 規則總覽（對應任務指示第 7–9 點）

| ID | 條件 | 動作 |
|---|---|---|
| R1_bear_lockout | QQQ 收盤 < 200日SMA | 強制清倉、禁止任何進場 |
| R2_death_cross_exit | TQQQ 10EMA 向下穿越 20EMA | 無條件全數賣出 |
| R3_rsi_defensive_warning | 持股中且 RSI(14) < 45 | 減碼50%／移至成本線停損 |
| R4_overheat_trim | RSI(14) > 70 且股價高於20EMA超過15% | 分批賣出1/3~1/2 |
| R5_golden_cross_entry | QQQ>200SMA + 10EMA黃金交叉20EMA + 50<RSI<65 | 買進 |
| R6_entry_rejected_overbought | 黃金交叉時 RSI(14)>=65 | 放棄本次進場 |

多規則同時觸發時，依 `FORCE_EXIT > SELL_ALL > REDUCE_50 > TRIM_PARTIAL > SKIP_ENTRY_OVERBOUGHT > BUY` 優先序決定最終建議（`src/lrs/signals.py: ACTION_PRIORITY`），完全比照「大盤空頭禁令優先於任何進場訊號」「死亡交叉無條件出場」的要求。

**新增/調整規則**：直接編輯 `config/rules.json`，每筆規則是
`{id, name, action, priority, logic, conditions, message}`，`conditions` 的
`left`/`right` 可為 context 路徑（如 `tqqq.rsi`）或常數，`op` 支援
`>, <, >=, <=, ==, !=, crosses_above, crosses_below`。不需修改程式碼。

## 圖表

`state/report.html` 同時呈現：
- 主圖：TQQQ 收盤價 + 長期 SMA(預設200日，框架) + 短期 EMA(預設20日，觸發) + 黃金/死亡交叉標記
- 副圖：RSI(14) 搭配 45 / 50 / 55 / 65 / 70 參考線（避險 / 進場下緣 / 中線 / 超買 / 過熱止盈）

## 年度再平衡 (11/1) 與資產配置站整合 — 已知限制

`src/lrs/rebalance.py` 會在每年 11/1（±可設定天數）提醒檢核防禦性資產
（現金/國債）是否已達目標比例（預設 50%）。

**`https://mgtasset.clare8628.workers.dev/` 尚未串接自動查詢**：該站台需要
帳密登入，但未提供公開 API 文件，為避免猜測端點造成誤判或帳密外洩風險，本
系統不會臆測其登入 API。目前的處理方式：

1. 設定環境變數 `MGTASSET_USERNAME` / `MGTASSET_PASSWORD`（絕不寫入程式碼或
   版控）；`AssetAllocationProvider.fetch_defensive_pct()` 預留介面，待取得
   該站台實際登入 API 規格後即可實作自動查詢。
2. 在此之前，可於再平衡窗口內手動寫入 `state/asset_snapshot.json`：
   `{"defensive_pct": 55}`，系統會讀取並比對目標比例。
3. 若都沒有資料，`check_rebalance()` 回傳 `needs_manual_check=True`，提示
   人工登入站台比對 —— 對應 Tom 的故障恢復機制「自動判斷失敗時回報需人工
   介入」。

## 部署

- `.github/workflows/daily-signal.yml`：美股收盤後排程執行測試 + 產生每日
  報告，上傳為 workflow artifact（需專案推送至 GitHub 後啟用 Actions）。
- 無第三方相依套件，亦可用任一具備 Python 3.8+ 的排程環境（cron、Cloud
  Scheduler、Cloudflare Cron Triggers via subprocess 等）直接執行 `main.py`。

## 限制

- 僅為訊號/建議工具，不連接券商帳戶、不自動下單；持倉狀態需使用者自行用
  `--mark-filled` / `--mark-closed` 標記。
- `mgtasset.clare8628.workers.dev` 現金比例查詢需人工或待 API 規格確認後補上（見上）。
- RSI 使用 Wilder 平滑法（業界標準 14 日 RSI 計算方式）。
