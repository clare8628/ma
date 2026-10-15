# PROGRESS

- [x] 指標模組 SMA/EMA/RSI(Wilder)，純標準庫
- [x] Yahoo chart API 資料擷取 + 快取 + CSV 離線模式
- [x] 資料驅動規則引擎（可編輯 rules.json）
- [x] 訊號整合：QQQ大盤過濾 + TQQQ EMA交叉 + RSI過濾
- [x] 年度11/1再平衡檢核（mgtasset站台串接：介面已留，待API規格，見STATE.md）
- [x] 零相依 SVG 圖表報告 (SMA200框架+EMA10/20雙觸發線+RSI參考線)，雙圖皆加縱橫軸刻度，RSI放大3倍，EMA可圖上開關隱藏
- [x] daily-signal.yml 每日自動 rebuild + commit + push public/index.html，網頁日期/股價不再是靜態快照
- [x] 單元測試 25/25 通過 (unittest, 無需安裝套件)
- [x] CLI 端對端驗證：離線CSV + 即時Yahoo資料皆通過
- [x] README / GitHub Actions 排程範例
- [x] Cloudflare 部署適配：新增 wrangler.jsonc、package.json 與 public/ 靜態資源發布

- [x] MA平台微調加入版本時間戳記（頁首標籤組與頁尾時間戳記，版本 v1.3.0）
- [x] 圖表右側空間延伸利用：擴充畫布寬度、雙側價格刻度、右側 Price Pills 即時均線/收盤定位標籤與即時指標速覽面板
- [x] 標記重大金融事件時間點（config/events.json 驅動、圖上垂直標記線與圖釘標籤、可開關切換、時序表紀錄）
- [x] 「建議動作」與「價格與均線」中間新增目前遵守的「買入與賣出規則」區塊（支援條件翻譯、動作說明與今日符合狀態）
- [x] 時間軸延長追溯回 TQQQ 2010 年成立開始（全歷史日線資料、年份自適應刻度、對數 Log Scale 與線性座標切換、擴充 2010~2026 重大金融事件 28 項）
- [x] 觀察時間區間方便可調（新增快捷按鈕組 1M/3M/6M/1Y/2Y/5Y/10Y/ALL 與經典歷史情境下拉選單，前端毫秒級無延遲重繪，Y軸自動適應縮放，避免全時間長度過於擁擠）
- [x] 版面左右兩側閒置空間充分利用（頁面最大寬度擴充至 1760px，SVG 畫布拓寬至 1600px，指標面板與表格自適應延展）
- [x] 單元測試 35/35 通過 (含 indicators, rules_engine, signals, rebalance, chart 全面覆蓋，版本升級至 v1.4.0)

測試覆蓋率：indicators / rules_engine / signals / rebalance / chart 五大模組皆有測試 (35/35 通過)。
部署狀態：本機可執行；支援 Cloudflare Workers Static Assets 與 GitHub Actions 排程。
