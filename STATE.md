# STATE

目前狀態：程式完成（28/28 測試通過）。mgtasset 資產站串接**已打通並驗證成功**（2026-10-15）。

## 本次修復（2026-10-15）
- mgtasset 已新增 `GET /api/ma/defensive` 並設定 `MA_API_TOKEN` secret，但發現 ma 的 `worker/index.js` 用 `fetch()` 直接打 mgtasset 的 workers.dev 網址時，被 Cloudflare 擋下（邊緣回 404 + `error code: 1042`，與 token 是否正確無關——這是 Cloudflare 對「Worker 內部對另一個 workers.dev 網址發出子請求」的限制）。已改用 Service Binding（`wrangler.jsonc` 新增 `services`，`worker/index.js` 改呼叫 `env.MGTASSET.fetch(...)`），繞過此限制，commit 83f0f37 push 後 Cloudflare 自動部署，已驗證生效。
- 同時發現 ma 與 mgtasset 雙方各自產生的 `MA_API_TOKEN` 值不一致（兩邊都各自設過，但不是同一組），造成即使路由修好仍回 401。已重新產生一組 token，同步設定到三處：GitHub repo secret `MGTASSET_API_TOKEN`（ma）、Cloudflare Worker `ma` 的 secret `MA_API_TOKEN`、Cloudflare Worker `mgtasset` 的 secret `MA_API_TOKEN`。
- 驗證：`curl https://ma.clare8628.workers.dev/api/defensive` → `200 {"defensive_pct":37.5,"as_of":"2026-10-14"}`。端到端成功。

## 待辦（需人工，非阻斷）
1. **前端未呼叫 Worker**：`worker/index.js` 的 `/api/defensive` 現已可正常運作，但 `public/index.html` 還沒加 JS 去呼叫它顯示防禦性資產比例。Python CLI 的再平衡檢核（11/1 ±3 天窗口）已可用同一組 token 直接呼叫 mgtasset（不經過 ma Worker，不受 1042 限制影響）。
2. **public/index.html 為靜態快照**：需執行 `npm run build`（`python3 main.py --output public/index.html`）更新後 push；GitHub Actions 尚未自動 build/commit。
3. **持倉**：`state/position.json` 為 holding=false，實際買進後以 `--mark-filled` 更新（已 gitignore，雲端部署看不到）。
