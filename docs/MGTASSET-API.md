# 資產站 ↔ MA 串接指南

資產站原始碼不在本專案內，所以端點要在「資產站專案」裡新增。MA 端已完成，只等該端點上線。

## 步驟

1. 在資產站專案目錄開啟 Claude Code，貼上下方「給資產站的指令」。
2. 讓它 commit 並 push 到 GitHub，Cloudflare 會自動部署（不要用 `wrangler deploy`）。
3. 產生 token 並設定到兩邊：
   ```
   openssl rand -hex 32
   # 資產站（Cloudflare 後台 Workers → Settings → Variables and Secrets，或 `wrangler secret put MA_API_TOKEN`）
   MA_API_TOKEN=<token>
   # MA 端（shell 或 GitHub Actions secret）
   export MGTASSET_API_TOKEN=<同一組 token>
   ```
4. 驗證：
   ```
   curl -H "Authorization: Bearer $MGTASSET_API_TOKEN" https://mgtasset.clare8628.workers.dev/api/ma/defensive
   python3 main.py
   ```
   再平衡窗口（11/1 ±3 天）內，輸出會顯示防禦性資產比例。

## 契約

`GET /api/ma/defensive`
- Header：`Authorization: Bearer <MA_API_TOKEN>`；缺少或錯誤回 401。
- 200 回應：`{"defensive_pct": 52.3, "as_of": "2026-10-15"}`
  - `defensive_pct`：現金 + 國債(SHY/BIL 等)佔總資產的百分比（0–100）。
- 唯讀、只回傳此比例，不回傳持倉明細。

## 給資產站的指令（貼給 Claude）

> 請在本專案新增唯讀 API：`GET /api/ma/defensive`。
> - 以 Bearer token 驗證，token 存在 secret `MA_API_TOKEN`，用常數時間比對；失敗回 401。此路徑不走帳密登入流程。
> - 回傳 JSON `{"defensive_pct": <現金+國債佔總資產百分比, 0-100>, "as_of": "YYYY-MM-DD"}`，不要回傳其他持倉資料。
> - 加上對應測試。
> - 完成後 commit 並 push 到 GitHub，由 Cloudflare 既有 Git 連接自動部署，不要直接 wrangler deploy。
> - 不要把 token 寫進程式碼或版控。

## 設計說明

用 token 而非帳密：帳密是完整權限，外洩風險大；token 僅能讀這一個數值，可隨時更換。
