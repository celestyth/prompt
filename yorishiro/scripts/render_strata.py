#!/usr/bin/env python3
"""strata renderer — field/ の地層から STRATA.md (確認ページ) を再生成する。

収集のたびにbotが実行する。ネットワーク不要・決定論的。
"""
import datetime
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_ROWS = 40

MOON_EMOJI = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]  # phase_deg 45°刻み


def moon_emoji(phase_deg):
    return MOON_EMOJI[int(((phase_deg + 22.5) % 360) // 45)]


def weather_emoji(code):
    if code is None:
        return "—"
    table = [
        ((0,), "☀️"), ((1, 2), "🌤"), ((3,), "☁️"),
        (range(45, 49), "🌫"), (range(51, 58), "🌦"),
        (range(61, 68), "🌧"), (range(71, 78), "🌨"),
        (range(80, 83), "🌦"), (range(85, 87), "🌨"),
        (range(95, 100), "⛈"),
    ]
    for codes, emoji in table:
        if code in codes:
            return emoji
    return f"({code})"


def jst(moment_iso):
    t = datetime.datetime.fromisoformat(moment_iso)
    return t.astimezone(datetime.timezone(datetime.timedelta(hours=9)))


def fmt(value, suffix="", digits=None):
    if value is None:
        return "—"
    if digits is not None:
        value = round(value, digits)
    return f"{value}{suffix}"


def load_snapshots():
    field = ROOT / "field"
    if not field.exists():
        return []
    snaps = [json.loads(p.read_text()) for p in sorted(field.rglob("*.json"))]
    snaps.sort(key=lambda s: s["moment"])
    return snaps


PLANET_JA = {
    "mercury": "水星", "venus": "金星", "mars": "火星", "jupiter": "木星",
    "saturn": "土星", "uranus": "天王星", "neptune": "海王星", "pluto": "冥王星",
}


def render_latest(s):
    c, cal = s.get("celestial"), s.get("calendar") or {}
    terr = s.get("terrestrial") or {}
    sw = terr.get("space_weather") or {}
    w = terr.get("weather")
    seismic = terr.get("seismic")
    t = jst(s["moment"])
    lines = [f"## 最新の断面 — {t:%Y-%m-%d %H:%M} JST @{s['site']}", ""]
    if c:
        lon = c["longitudes"]
        lines.append(
            f"- 月: {moon_emoji(c['moon_phase_deg'])} 輝面 {c['moon_illumination']*100:.1f}%"
            f" / 月齢 {c['moon_age_days']} / {lon['moon']['sign']}座"
            f" / 距離 {fmt(c.get('moon_distance_km'), ' km')} / 潮汐 {fmt(c.get('tidal_index'))}"
        )
        lines.append(
            f"- 太陽: {lon['sun']['sign']} {lon['sun']['lon_deg']:.1f}°"
            f" / {cal.get('sekki') or '—'} / {cal.get('day_ganzhi') or '—'}の日"
            f" / {cal.get('day_planet') or '—'}の日"
        )
        k = cal.get("kyureki")
        if k:
            leap = "閏" if k.get("leap") else ""
            lines.append(
                f"- 暦: 旧暦{leap}{k['month']}月{k['day']}日 {cal.get('rokuyo') or ''}"
                f" / {cal.get('kyusei_year') or '—'}年・{cal.get('kyusei_month') or '—'}月"
            )
        if c.get("retrograde"):
            lines.append("- 逆行中: " + "・".join(PLANET_JA.get(p, p) for p in c["retrograde"]))
        rs = c.get("rise_set_jst") or {}
        if rs:
            sun_rs, moon_rs = rs.get("sun") or {}, rs.get("moon") or {}
            lines.append(
                f"- 出入り(JST): 日 {fmt(sun_rs.get('rise'))}〜{fmt(sun_rs.get('set'))}"
                f" / 月 {fmt(moon_rs.get('rise'))}〜{fmt(moon_rs.get('set'))}"
            )
    wind = sw.get("solar_wind") or {}
    imf = sw.get("imf") or {}
    xray = sw.get("xray") or {}
    cycle = sw.get("solar_cycle") or {}
    lines.append(
        f"- 地磁気 Kp: {fmt(sw.get('kp'))} / 太陽風 {fmt(wind.get('speed_km_s'), ' km/s')}"
        f" / Bz {fmt(imf.get('bz_nT'), ' nT')}"
    )
    lines.append(
        f"- 太陽活動: X線 {fmt(xray.get('flare_class'))} / 黒点数 {fmt(cycle.get('ssn'))}"
        f" / F10.7 {fmt(cycle.get('f10_7'))}"
    )
    if seismic:
        mx = seismic.get("max")
        if mx:
            lines.append(
                f"- 大地: 直近24h M4+ {seismic['count_24h_m4']}件"
                f" (最大 M{fmt(mx.get('mag'))} {mx.get('place') or ''})"
            )
        else:
            lines.append("- 大地: 直近24h M4+ なし (静穏)")
    else:
        lines.append("- 大地: —")
    for name, sw_ in sorted((w or {}).items(), key=lambda kv: kv[0] != s["site"]):
        if sw_:
            lines.append(
                f"- {name}: {weather_emoji(sw_.get('weather_code'))} {fmt(sw_.get('temperature_c'), '℃')}"
                f" / {fmt(sw_.get('pressure_msl_hpa'), ' hPa')} / 湿度 {fmt(sw_.get('humidity_pct'), '%')}"
                f" / 雲量 {fmt(sw_.get('cloud_cover_pct'), '%')}"
            )
        else:
            lines.append(f"- {name}: —")
    if s.get("errors"):
        lines.append(f"- ⚠ 欠測 {len(s['errors'])} 項目 (このスナップショットのerrors参照)")
    return lines


def render_table(snaps):
    lines = [
        "## 直近の地層 (新しい順)", "",
        "| 時刻 (JST) | 月 | 月齢 | 六曜 | Kp | 気温 | 気圧 | 五点の空 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    site_order = None
    for s in reversed(snaps[-MAX_ROWS:]):
        c = s.get("celestial") or {}
        cal = s.get("calendar") or {}
        sw = (s.get("terrestrial") or {}).get("space_weather") or {}
        weather = (s.get("terrestrial") or {}).get("weather") or {}
        w = weather.get(s["site"]) or {}
        if site_order is None and weather:
            site_order = list(weather.keys())
        skies = "".join(
            weather_emoji((weather.get(name) or {}).get("weather_code")) for name in (site_order or [])
        ) or "—"
        moon = moon_emoji(c["moon_phase_deg"]) if c else "—"
        lines.append(
            f"| {jst(s['moment']):%m-%d %H:%M} | {moon}"
            f" | {fmt(c.get('moon_age_days'))} | {fmt(cal.get('rokuyo'))} | {fmt(sw.get('kp'))}"
            f" | {fmt(w.get('temperature_c'), '℃')} | {fmt(w.get('pressure_msl_hpa'))}"
            f" | {skies} |"
        )
    if site_order:
        lines += ["", f"気温・気圧は錨点。五点の空は左から {('・'.join(site_order))}。"]
    return lines


def main():
    snaps = load_snapshots()
    lines = ["# 地層 — strata", ""]
    if not snaps:
        lines += ["まだ地層はない。最初の収集を待っている。", ""]
    else:
        first, last = jst(snaps[0]["moment"]), jst(snaps[-1]["moment"])
        days = (last.date() - first.date()).days + 1
        lines += [
            f"**深さ**: {len(snaps)} 断面 / {first:%Y-%m-%d} 〜 {last:%Y-%m-%d} ({days}日)",
            "",
            *render_latest(snaps[-1]),
            "",
            *render_table(snaps),
            "",
        ]
    lines.append("*このページは収集のたびに `scripts/render_strata.py` が自動再生成する。手で編集しない。*")
    (ROOT / "STRATA.md").write_text("\n".join(lines) + "\n")
    print(f"rendered: STRATA.md ({len(snaps)} snapshots)")


if __name__ == "__main__":
    main()
