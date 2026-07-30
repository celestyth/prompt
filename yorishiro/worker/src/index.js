// yorishiro-gate 翻訳所 — Overlandの生座標を受け取り、象徴名に翻訳して最新位置だけ保持する。
// 生座標はどこにも永続化しない。KVに残るのは象徴名と粗い時刻のみ。

function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function translate(lat, lon, sites) {
  for (const s of sites) {
    if (haversineM(lat, lon, s.lat, s.lon) <= (s.radius_m ?? 1000)) return s.name;
  }
  return "外";
}

function authorized(request, env) {
  const auth = request.headers.get("Authorization") ?? "";
  const token = auth.replace(/^Bearer\s+/i, "");
  return token.length > 0 && token === env.OVERLAND_TOKEN;
}

export default {
  async fetch(request, env) {
    if (!authorized(request, env)) {
      return new Response("unauthorized", { status: 401 });
    }
    const url = new URL(request.url);

    // Overland からのバッチ受信
    if (request.method === "POST" && url.pathname === "/overland") {
      const body = await request.json();
      const locations = body.locations ?? [];
      if (locations.length > 0) {
        const sites = JSON.parse(env.SITES_JSON).sites;
        const last = locations[locations.length - 1];
        const [lon, lat] = last.geometry.coordinates;
        const record = {
          site: translate(lat, lon, sites),
          time: last.properties?.timestamp ?? new Date().toISOString(),
        };
        await env.YORISHIRO_KV.put("latest_location", JSON.stringify(record));
      }
      // Overland は {"result": "ok"} を受け取ると送信済みバッチを端末から消す
      return Response.json({ result: "ok" });
    }

    // 収集ジョブが現在の象徴を問い合わせる
    if (request.method === "GET" && url.pathname === "/latest") {
      const raw = await env.YORISHIRO_KV.get("latest_location");
      return Response.json(raw ? JSON.parse(raw) : { site: null, time: null });
    }

    return new Response("not found", { status: 404 });
  },
};
