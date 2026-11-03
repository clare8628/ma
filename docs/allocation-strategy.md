# 現金 / QQQ / TQQQ 三資產配置（簡化版）

[MAM-6] 任務：研究並融合「搭配現金、QQQ平衡TQQQ」的操作策略。

## 1. 研究來源與限制

來源影片：YouTube《TQQQ 長期持有策略：10年50倍策略詳解》（頻道「財富種植園」），
`https://www.youtube.com/watch?v=HkY2Rb99htY`。

**限制**：此影片無公開逐字稿、無官方 API，且 YouTube 頁面本身不提供結構化的
策略參數文字（僅標題可取得）。公開可查到的相關資訊顯示，該頻道的量化系統核心
思路是「在長期做多 TQQQ 的基礎上，搭配現金與 QQQ 做組合管理以平滑波動、
壓低最大回撤」（宣稱將 TQQQ 單押原本的回撤從 -79% 壓縮到更低），但並未取得
逐日進出場規則的完整原始程式碼或參數。因此本次整合**不逐字重現影片內部實作**，
而是依任務描述指定的範例比例（10% 現金 / 45% QQQ / 45% TQQQ），將「用現金與
QQQ 平衡 TQQQ」這個核心思路抽象成一套簡單、可驗證、可獨立於既有訊號引擎運作
的配置層，待使用者取得影片更完整的規則細節後，仍可調整本模組參數而不需改架構。

## 2. 簡化後的融合方式（本專案的實作）

新增模組 `src/lrs/allocation.py`，只做三件事：

1. **基礎目標權重**：預設 `現金10% / QQQ45% / TQQQ45%`
   （`config/settings.json` → `allocation.target_weights`，可直接調整）。
2. **依訊號動作縮放 TQQQ 曝險**：既有規則引擎（`config/rules.json`）仍負責
   判斷多空與買賣時機，本模組只是把訊號「翻譯」成配置權重：
   | 訊號動作 | 目標配置 |
   |---|---|
   | `SELL_ALL` / `FORCE_EXIT`（死亡交叉／大盤空頭） | 100% 現金 |
   | `REDUCE_50`（動能預警減碼50%） | TQQQ 目標砍半，差額併入現金 |
   | `TRIM_PARTIAL`（過熱止盈，賣1/3~1/2） | TQQQ 目標保留60%，差額併入現金 |
   | `BUY` / `BUY_DIP_PANIC` / `HOLD` / `SKIP_ENTRY_OVERBOUGHT` | 維持基礎目標權重 |
3. **偏離度再平衡提醒**：使用者可將實際持倉比例寫入
   `state/allocation_snapshot.json`（`cash_pct` / `qqq_pct` / `tqqq_pct`）。
   只要任一資產的「實際權重 − 目標權重」超過 `allocation.drift_threshold_pct`
   （預設 ±5 個百分點），系統就會提示賣出超重資產、買入低配資產拉回目標——
   這就是「用現金與 QQQ 平衡 TQQQ」的具體操作：TQQQ 大漲超配時賣出鎖定獲利
   （資金轉入現金/QQQ），TQQQ 大跌低配時用現金/QQQ 換回 TQQQ 逢低攤平。

此機制與既有的年度 11/1 防禦性資產再平衡（`src/lrs/rebalance.py`）是獨立的
兩套檢核，互不衝突：11/1 檢核針對「防禦性資產是否達標」，本模組針對「三資產
配置是否偏離目標」，兩者都只是輸出建議文字，不自動下單。

## 3. 使用方式

```bash
python3 main.py
# CLI 輸出新增一段：
# === 現金/QQQ/TQQQ 三資產配置檢核 ===
# 目標配置：現金10.0%/QQQ45.0%/TQQQ45.0%。尚無實際持倉快照，請於 state/allocation_snapshot.json ...
```

填入實際持倉後重新執行即可看到偏離度與再平衡建議：

```json
// state/allocation_snapshot.json
{"cash_pct": 8, "qqq_pct": 40, "tqqq_pct": 52}
```

HTML 報告（`state/report.html` / `public/index.html`）新增「現金 / QQQ / TQQQ
三資產配置」卡片，以長條圖呈現目標 vs 實際權重，並在偏離超過門檻時顯示橘色
再平衡提醒橫幅。

## 4. 後續注意事項

- 若未來取得該 YouTube 影片或頻道更完整的規則文字稿／官方資料，可依實際參數
  調整 `config/settings.json` 的 `target_weights` 與 `drift_threshold_pct`，
  或擴充 `_TQQQ_KEEP_FRACTION` 對應更多訊號動作，不需更動既有架構。
- 本模組不連接券商帳戶、不自動下單，`allocation_snapshot.json` 需使用者
  自行依實際持倉手動更新。
