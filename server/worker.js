/**
 * SensorLog 受信サーバーのサンプル (Cloudflare Worker + D1)
 *
 * デプロイ手順:
 *   1. npm i -g wrangler && wrangler login
 *   2. wrangler d1 create sensorlog   → 出力された database_id を wrangler.toml に記入
 *   3. wrangler d1 execute sensorlog --remote --file=./schema.sql
 *   4. wrangler deploy
 *   5. 発行された URL + /api/readings をアプリの設定画面に入力
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS });
    }

    if (url.pathname === "/api/readings" && request.method === "POST") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "invalid JSON" }, 400);
      }
      const { device_id, session_id, samples } = body ?? {};
      if (!device_id || !Array.isArray(samples)) {
        return json({ error: "device_id and samples[] required" }, 400);
      }
      if (samples.length > 10000) {
        return json({ error: "batch too large" }, 413);
      }

      if (env.DB) {
        const stmt = env.DB.prepare(
          "INSERT INTO readings (device_id, session_id, t, sensor, v1, v2, v3, v4, v5) VALUES (?,?,?,?,?,?,?,?,?)"
        );
        const rows = samples.map((s) =>
          stmt.bind(
            device_id,
            session_id ?? null,
            s.t ?? Date.now(),
            String(s.sensor ?? "unknown"),
            num(s.v?.[0]), num(s.v?.[1]), num(s.v?.[2]), num(s.v?.[3]), num(s.v?.[4])
          )
        );
        await env.DB.batch(rows);
      }
      return json({ ok: true, stored: samples.length });
    }

    if (url.pathname === "/api/readings" && request.method === "GET") {
      if (!env.DB) return json({ error: "no DB bound" }, 501);
      const device = url.searchParams.get("device_id");
      const limit = Math.min(Number(url.searchParams.get("limit") ?? 100), 1000);
      const q = device
        ? env.DB.prepare("SELECT * FROM readings WHERE device_id = ? ORDER BY t DESC LIMIT ?").bind(device, limit)
        : env.DB.prepare("SELECT * FROM readings ORDER BY t DESC LIMIT ?").bind(limit);
      const { results } = await q.all();
      return json({ results });
    }

    return json({ service: "sensorlog-ingest", endpoints: ["POST /api/readings", "GET /api/readings"] });
  },
};

function num(v) {
  return typeof v === "number" && isFinite(v) ? v : null;
}
function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}
