# PROGRESS

- [x] 指標模組 SMA/EMA/RSI(Wilder)，純標準庫
- [x] Yahoo chart API 資料擷取 + 快取 + CSV 離線模式
- [x] 資料驅動規則引擎（可編輯 rules.json）
- [x] 訊號整合：QQQ大盤過濾 + TQQQ EMA交叉 + RSI過濾
- [x] 年度11/1再平衡檢核（mgtasset站台串接：介面已留，待API規格，見STATE.md）
- [x] 零相依 SVG 圖表報告 (SMA200框架+EMA20觸發+RSI參考線)
- [x] 單元測試 25/25 通過 (unittest, 無需安裝套件)
- [x] CLI 端對端驗證：離線CSV + 即時Yahoo資料皆通過
- [x] README / GitHub Actions 排程範例

測試覆蓋率：indicators/rules_engine/signals/rebalance 四大核心模組皆有測試。
部署狀態：本機可執行；GH Actions workflow 已備妥，需推送至 GitHub 後啟用。
