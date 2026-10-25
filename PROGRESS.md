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

- [x] [MAM-3] VIX 指數超過 45 抄底綜合判斷整合 (版本升級至 v1.5.0 ~ v1.5.2)
  - 新增 VIX 恐慌指數全歷史日線資料擷取與快取 (`^VIX` -> `state/cache/VIX.json`)，支援 `--vix-csv` 離線模式
  - 規則庫新增 `R0_vix_panic_bottom`（VIX ≥ 45 觸發 `BUY_DIP_PANIC` 恐慌抄底買進，設定為最高優先級，打破常規空頭限制）
  - 核心訊號引擎加入 `evaluate_vix_regime` 綜合評估模型（極度恐慌、恐慌警戒、中度波動、低波動平穩四級分級與策略指引）
  - 前端與報告整合：指標速覽面板新增 VIX 即時狀態卡片，新增「VIX 恐慌指數綜合判斷與歷史抄底勝率分析」專區
  - [MAM-3 追加指示] VIX 指標曲線加入價格與均線圖中 (v1.5.1)：
    - 主圖（價格與均線圖）正式整合 VIX 恐慌指數曲線，映射至專屬波動率刻度 (10~80+)
    - 繪製 VIX 45 恐慌抄底水平警戒虛線與右側數值刻度，一眼看清歷史大底與 VIX 爆發點
    - 工具列新增「顯示 VIX 恐慌指標曲線」開關（支援 toggle 隨時隱藏/顯示）
    - 右側 Price Pills 加入最新 VIX 定位標籤，動態防重疊排列
    - 前端 JavaScript 重繪引擎全區間 (1M/3M/6M/1Y/2Y/5Y/10Y/ALL) 與線性/對數座標無縫即時連動
  - [MAM-3 追加指示] 滑鼠懸浮滑移即時檢視價格與 VIX 等精確數值 (v1.5.2)：
    - 主圖與副圖加入即時十字導引線 (Crosshair) 與高亮焦點圓點 (Highlight Dots)
    - 實作跟隨游標的浮動資訊卡 (Tooltip)：滑移時即時顯示日期、TQQQ收盤價(含漲跌幅)、VIX恐慌指數(含情緒分級標籤)、短期EMA10/20、長期SMA200、RSI(14)及重大金融事件
    - 主圖上方加入即時動態指示狀態列 (Interactive Status Bar)，同步反應用戶游標位置之精確量化數值
    - 完美支援全歷史區間切換、線性/對數座標模式、圖層開關過濾以及行動端觸控操作
  - 單元測試全面擴充 (41/41 通過，包含 Crosshair 游標導引、各指標高亮點與 Tooltip 前端互動斷言)

測試覆蓋率：indicators / rules_engine / signals / rebalance / chart 五大模組皆有測試 (41/41 通過)。
部署狀態：本機可執行；支援 Cloudflare Workers Static Assets 與 GitHub Actions 排程。
