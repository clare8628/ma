// ma 專案的 Worker。瀏覽器呼叫 ma 的 /api/defensive，由此腳本在伺服器端帶 token 轉呼叫 mgtasset，token 不會外露。
//
// 原本用 `fetch("https://mgtasset.clare8628.workers.dev/...")` 直接打 workers.dev URL，
// 但 Cloudflare 會擋掉從 Worker 內部對另一個 workers.dev 網址發出的子請求
// （邊緣回應 404 + body "error code: 1042"，與 token 是否正確無關）。
// 改用 Service Binding（wrangler.jsonc 的 services）直接呼叫 mgtasset 這個 Worker，
// 不經過 workers.dev 的邊緣路由，不會被擋，也不需要 MGTASSET_URL 這個 var。
// 到 ma 的 Settings →「Runtime variables and secrets」新增 Secret：MA_API_TOKEN（與 mgtasset 相同的值）。

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/api/defensive' && request.method === 'GET') {
      const upstream = await env.MGTASSET.fetch('https://mgtasset/api/ma/defensive', {
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
