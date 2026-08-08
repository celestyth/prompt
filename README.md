# StellaLog — スマホセンシングアプリ

スマホのセンサーをリアルタイム計測・記録する PWA(+ 将来のネイティブ iOS 版)。

> 開発・デプロイは専用リポジトリ https://github.com/celestyth/stellalog に移行しました。

**アプリ URL: https://celestyth.github.io/stellalog/**

iPhone / Android の Safari・Chrome で開いて、共有メニューから「ホーム画面に追加」するとアプリとして使えます。

## 機能

| センサー | 取得値 | 記録レート |
|---|---|---|
| 加速度 | X/Y/Z (m/s²) | 端末依存 (~60 Hz) |
| ジャイロ | X/Y/Z 角速度 (deg/s) | 端末依存 (~60 Hz) |
| 方位・姿勢 | コンパス方位、前後・左右の傾き (°) | 端末依存 |
| GPS | 緯度・経度・高度・速度・精度 | ~1 Hz |
| マイク | 音量レベル (dBFS) | 20 Hz |

- **リアルタイム表示**: スクロールする波形チャート(タッチでその時点の値を表示)
- **記録 & CSV エクスポート**: 記録開始/停止 → センサーごとの CSV を共有シートから保存
- **サーバー送信**(任意): 設定画面でエンドポイント URL を指定すると 2 秒ごとに JSON バッチを POST

> iOS の制約: 気圧・磁気の生値はブラウザから取得不可(ネイティブ版で対応予定)。センサー許可は HTTPS + タップ操作が必要です。バックグラウンド計測は PWA では不可。

## 構成

```
web/       PWA 本体(ビルド不要の素の HTML/JS)→ GitHub Pages に自動デプロイ
ios/       ネイティブ iOS 版(次フェーズで追加予定 — 気圧・磁気・バックグラウンド計測対応)
server/    データ受信サーバーのサンプル(Cloudflare Worker + D1)
```

デプロイは `.github/workflows/deploy-pages.yml` が行います。`web/` 配下を変更してプッシュすると自動で反映されます。

## サーバー送信のデータ形式

```json
POST <endpoint>
{
  "device_id": "uuid",
  "session_id": "uuid",
  "samples": [
    { "t": 1754660000000, "sensor": "accel", "v": [0.01, -0.2, 9.8] }
  ]
}
```

`v` の並びは CSV と同じ: accel=[x,y,z], gyro=[x,y,z], orientation=[alpha,beta,gamma,compass], gps=[lat,lon,alt,speed,accuracy], mic=[dbfs]。受信側の実装例は `server/` を参照。
