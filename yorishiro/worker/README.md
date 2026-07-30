# yorishiro-gate 翻訳所 (Cloudflare Worker)

Overlandから届く生座標を象徴名に翻訳する受け口。**生座標はどこにも保存しない** —
KVに残るのは `{"site": "皇居", "time": "..."}` のみ。

## デプロイ (v2で位置追従を始めるとき)

```sh
cd worker
npx wrangler kv namespace create YORISHIRO_KV   # 出力されたidを wrangler.toml に転記
npx wrangler secret put OVERLAND_TOKEN       # 長いランダム文字列を設定
npx wrangler secret put SITES_JSON           # definitions/sites.json と同形式(私的な場所はこちらにだけ)
npx wrangler deploy
```

## Overland側の設定

- Server URL: `https://yorishiro-gate.<your>.workers.dev/overland`
- Access Token: `OVERLAND_TOKEN` と同じ値(OverlandがAuthorizationヘッダに付ける)

## 収集ジョブからの参照 (v2)

`GET /latest` (Bearer トークン必須) が現在の象徴を返す。
collect.py はこれを使って「現在地の象徴」で天気を引くように拡張する。
