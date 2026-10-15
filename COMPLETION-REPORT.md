# COMPLETION REPORT — MAM-1 移動平均線系統 (LRS)

## 功能驗證結果
- CLI `python3 main.py` 以即時 Yahoo Finance 資料執行成功，輸出建議與
  `state/report.html` 圖表報告。
- 離線模式（自備 CSV）驗證通過。
- `--mark-filled` / `--mark-closed` 持倉狀態切換驗證通過。
- 規則引擎驗證：大盤空頭強制清倉、死亡交叉無條件出場、RSI<45避險減碼、
  RSI>70+偏離20EMA>15%止盈、黃金交叉+RSI 50~65進場、RSI>=65放棄進場，
  各情境皆有對應單元測試覆蓋並通過。
- 11/1 再平衡窗口判斷（含窗口邊界）驗證通過。

## 測試覆蓋率
`python3 -m unittest discover -s tests -v` → 25/25 通過（indicators、
rules_engine、signals、rebalance 四模組）。

## 部署狀態
本機可直接執行，無第三方相依套件。已附 `.github/workflows/daily-signal.yml`
排程範例（需使用者自行推送至 GitHub 並啟用 Actions 才會實際運行）。

## 已知限制
1. `mgtasset.clare8628.workers.dev` 現金比例自動查詢未串接（缺登入API規格），
   見 `STATE.md`，不影響其他功能，有明確手動替代方案。
2. 僅為訊號建議工具，不連接券商、不自動下單。
3. RSI(14) 採 Wilder 平滑法（業界標準）。

## 如何落實最新指示
Taskboard 最新回報的「缺少工作目錄」訊息已透過本次任務指派提供的
`工作目錄: .../cowork/develop/ma` 解除——該路徑原為空目錄，本次已在其中
建立完整專案並驗證可執行，不再缺少工作目錄。
