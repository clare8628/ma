# STATE

目前狀態：程式完成（28/28 測試通過），部署與資產站串接尚有未完成設定。

## 待辦（需人工）
1. **資產站端點**：mgtasset 專案新增 `GET /api/ma/defensive`（Bearer 驗證），步驟見 `docs/MGTASSET-API.md`。mgtasset 目前只有 `APP_TOKEN` secret，尚無 `MA_API_TOKEN`，代表端點還沒做。
2. ~~Token 設定~~ 已完成：GitHub repo secret `MGTASSET_API_TOKEN`、Cloudflare Worker `ma` 的 secret `MA_API_TOKEN` 已用同一組新 token 設定完成（2026-10-15）。mgtasset 那邊仍需設定同一組 token 的 `MA_API_TOKEN` secret。
3. **前端未呼叫 Worker**：`worker/index.js` 提供 `/api/defensive`，但 `public/index.html` 未使用；現金 50% 檢核目前只在 Python CLI 再平衡窗口（11/1 ±3 天）內執行。
4. **public/index.html 為靜態快照**：需執行 `npm run build`（`python3 main.py --output public/index.html`）更新後 push；GitHub Actions 尚未自動 build/commit。
5. **持倉**：`state/position.json` 為 holding=false，實際買進後以 `--mark-filled` 更新（已 gitignore，雲端部署看不到）。
6. ~~`package.json` deploy script~~ 已移除 `wrangler deploy` script。本次為清除先前意外以明文 var 部署到正式環境的 token，手動執行了一次 `wrangler deploy`（已改用 `wrangler secret put` 設回正確做法），之後部署請回到只用 git push。
