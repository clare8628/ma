// 放進 ma 專案（例如 ma/worker/index.js）的範例 Worker。
// 瀏覽器呼叫 ma 的 /api/defensive，由此腳本在伺服器端帶 token 轉呼叫 mgtasset，token 不會外露。
//
// ma 專案目前沒有 wrangler.toml（Dashboard 提示 "Update wrangler.jsonc in your repo"，name 為 "ma"）。
// 請在 ma 專案根目錄新增 wrangler.jsonc（directory 填 ma 實際的建置輸出資料夾，例如 dist 或 public）：
//   {
//     "name": "ma",
//     "main": "worker/index.js",
//     "compatibility_date": "2026-10-15",
//     "assets": { "directory": "./dist", "binding": "ASSETS" },
//     "vars": { "MGTASSET_URL": "https://mgtasset.clare8628.workers.dev" }
//   }
// 推送部署後，到 ma 的 Settings 頁最上方「Runtime variables and secrets」新增 Secret：MA_API_TOKEN（與 mgtasset 相同的新值）。
// 注意：不要放在頁面下方 Builds 區塊的「Variables and secrets」（那是建置時變數）。

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/api/defensive' && request.method === 'GET') {
      const upstream = await fetch(`${env.MGTASSET_URL}/api/ma/defensive`, {
        headers: { Authorization: `Bearer ${env.MA_API_TOKEN}` },
      });
      // 只轉發 JSON 本體與狀態碼，不轉發其他標頭
      return new Response(upstream.body, {
        status: upstream.status,
        headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
      });
    }

    return env.ASSETS.fetch(request);
  },
};
