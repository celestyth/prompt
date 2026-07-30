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


def render_latest(s):
    c, cal = s.get("celestial"), s.get("calendar") or {}
    sw = (s.get("terrestrial") or {}).get("space_weather") or {}
    w = (s.get("terrestrial") or {}).get("weather")
    t = jst(s["moment"])
    lines = [f"## 最新の断面 — {t:%Y-%m-%d %H:%M} JST @{s['site']}", ""]
    if c:
        lon = c["longitudes"]
        lines.append(
            f"- 月: {moon_emoji(c['moon_phase_deg'])} 輝面 {c['moon_illumination']*100:.1f}%"
            f" / 月齢 {c['moon_age_days']} / {lon['moon']['sign']}座"
        )
        lines.append(
            f"- 太陽: {lon['sun']['sign']} {lon['sun']['lon_deg']:.1f}°"
            f" / {cal.get('sekki') or '—'} / {cal.get('day_ganzhi') or '—'}の日"
            f" / {cal.get('day_planet') or '—'}の日"
        )
    wind = sw.get("solar_wind") or {}
    imf = sw.get("imf") or {}
    lines.append(
        f"- 地磁気 Kp: {fmt(sw.get('kp'))} / 太陽風 {fmt(wind.get('speed_km_s'), ' km/s')}"
        f" / Bz {fmt(imf.get('bz_nT'), ' nT')}"
    )
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
        "| 時刻 (JST) | 場 | 月 | 月齢 | Kp | 気温 | 気圧 | 天気 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in reversed(snaps[-MAX_ROWS:]):
        c = s.get("celestial") or {}
        sw = (s.get("terrestrial") or {}).get("space_weather") or {}
        w = ((s.get("terrestrial") or {}).get("weather") or {}).get(s["site"]) or {}
        moon = moon_emoji(c["moon_phase_deg"]) if c else "—"
        lines.append(
            f"| {jst(s['moment']):%m-%d %H:%M} | {s['site']} | {moon}"
            f" | {fmt(c.get('moon_age_days'))} | {fmt(sw.get('kp'))}"
            f" | {fmt(w.get('temperature_c'), '℃')} | {fmt(w.get('pressure_msl_hpa'))}"
            f" | {weather_emoji(w.get('weather_code'))} |"
        )
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
