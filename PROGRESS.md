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
  - [MAM-3 追加指示] 修復前端 JavaScript 語法錯誤與互動引擎 (v1.5.3)：
    - 修正前端模板字串拼接處之 `SyntaxError`，解決導致整個頁面 JavaScript 無法載入的根本原因
    - 確保滑鼠在圖表（主圖或副圖）滑動時，游標旁即刻浮現精緻的半透明資訊卡 (Tooltip) 與十字導引線
    - 確保切換「對數座標 (Log Scale)」或在「1M / 1Y / ALL」不同時間區間跳轉時，動態重繪引擎毫秒級流暢反應
    - 於單元測試中正式加入 Node.js 語法驗證（`node --check`）防護機制，徹底防範前端語法漏網之魚
  - 單元測試全面擴充 (41/41 通過，包含 Crosshair 游標導引、各指標高亮點、Tooltip 前端互動斷言與 JS 語法檢查)

- [x] [MAM-5] 研究：買賣TQQQ訊號基礎 TQQQ自身均線 vs QQQ均線，何者較優
  - 新增 `src/lrs/backtest.py`（雙基礎回測引擎）+ `scripts/compare_signal_basis.py`（可重現比較腳本）
  - 用全歷史快取資料(2010-2026, 4203日)實測：勝率相近(33.8% vs 35.1%)，但QQQ基礎均勝幅度(+24.6% vs +16.9%)、總回報(5899% vs 1387%)、假交叉率(19% vs 27%)明顯優於TQQQ自身基礎
  - 結論與限制詳見 `docs/research-qqq-vs-tqqq-signal-basis.md`；**僅研究評估，未變更 config/rules.json 正式邏輯**，待使用者決定是否採用

- [x] [MAM-5 追加指示] 正式採用 QQQ 訊號基礎，TQQQ 實際價格虛線參考呈現 (v1.6.0)
  - `signals.py`：EMA10/20、SMA200框架、RSI(14) 全改算於 QQQ 收盤價；`tqqq.close` 僅保留實際成交價
  - `config/rules.json`：R2~R6 條件欄位改為 `qqq.*`，訊息文字同步更新（買賣標的仍是 TQQQ）
  - `chart.py`：主圖改以 QQQ 為主線，TQQQ 實際價格以虛線呈現於右側獨立次軸（線性/對數雙模式皆支援），新增專屬圖層開關、Price Pill、Crosshair 圓點與 Tooltip 欄位
  - Playwright 截圖驗證圖表渲染與滑鼠懸浮互動正常、無 console 錯誤；單元測試 45/45 通過

- [x] [MAM-6] 搭配現金、QQQ平衡TQQQ融合進本專案（移植財富種植園逐字稿量化策略，v1.7.0）
  - 新增 `src/lrs/allocation.py`：
    - 依逐字稿實作 10% 底倉現金 + 90% 機動倉（QQQ/TQQQ/現金依訊號切換）
    - 每日檢查 QQQ 200MA、高點回落幅度（牛市回落>10%全倉TQQQ、回落<=10%維持45/45；空頭回落>30%黃金坑全倉TQQQ；跌破200MA危險防守換全現金；半山腰拉扯區以20MA站上/跌破判定）
    - 納入「高位巨量黑K出貨避險」邏輯（距高點<=5%且爆量2倍收黑K時，機動倉轉全QQQ）
    - 嚴格落實「鐵律一（今日賣、明日買）」與「鐵律二（防假反彈：防守滿2天且20MA向上方可轉進攻）」狀態機，狀態累進持久化於 `state/wealth_farm_state.json`
  - 持倉金額多管道調整（CLI + 網頁即時互動試算）：
    - 網頁介面（`public/index.html` / `state/report.html`）：三資產卡片加入即時金額輸入框（現金/QQQ/TQQQ），修改後前端立即重新計算百分比、長條圖與買賣美金差額明細，支援 LocalStorage 記住與重設
    - CLI 參數支援：`--set-amounts CASH QQQ TQQQ`（更新快照）、`--cash-amount` / `--qqq-amount` / `--tqqq-amount`（即時比對），終端直接印出各資產具體調倉美金金額
    - 快照檔案相容性：`state/allocation_snapshot.json` 同時支援美金金額或百分比輸入
  - `config/settings.json` 新增 `allocation` 區塊（含各門檻參數 thresholds）
  - CLI (`main.py`) 與 HTML 報告（`chart.py`）同步呈現財富種植園策略目標權重、當日狀態/註記與實際持倉對比
  - 完整策略架構與參數說明更新於 `docs/allocation-strategy.md`
  - 單元測試 63/63 通過（新增金額解析、金額快照儲存、前端 JS 語法驗證）

測試覆蓋率：indicators / rules_engine / signals / rebalance / chart / backtest / allocation 七大模組皆有測試 (63/63 通過)。
部署狀態：本機可執行；支援 Cloudflare Workers Static Assets 與 GitHub Actions 排程。
