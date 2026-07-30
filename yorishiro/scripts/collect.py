#!/usr/bin/env python3
"""yorishiro field collector — 場のスナップショットを1つ生成して field/ に追記する。

取れなかった項目は null + エラーメモで残し、化石化自体は決して止めない。
"""
import datetime
import json
import os
import pathlib
import sys

import requests
import astronomy

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = {"User-Agent": "yorishiro-field-collector (github actions)"}
TIMEOUT = 30

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
SEKKI = [  # 太陽黄経0°=春分から15°刻み
    "春分", "清明", "穀雨", "立夏", "小満", "芒種", "夏至", "小暑",
    "大暑", "立秋", "処暑", "白露", "秋分", "寒露", "霜降", "立冬",
    "小雪", "大雪", "冬至", "小寒", "大寒", "立春", "雨水", "啓蟄",
]
SIGNS = [
    "牡羊", "牡牛", "双子", "蟹", "獅子", "乙女",
    "天秤", "蠍", "射手", "山羊", "水瓶", "魚",
]
DAY_PLANETS = ["月", "火星", "水星", "木星", "金星", "土星", "太陽"]  # weekday() 0=月曜
PLANETS = [
    ("sun", astronomy.Body.Sun), ("moon", astronomy.Body.Moon),
    ("mercury", astronomy.Body.Mercury), ("venus", astronomy.Body.Venus),
    ("mars", astronomy.Body.Mars), ("jupiter", astronomy.Body.Jupiter),
    ("saturn", astronomy.Body.Saturn), ("uranus", astronomy.Body.Uranus),
    ("neptune", astronomy.Body.Neptune), ("pluto", astronomy.Body.Pluto),
]


def load_sites():
    """公開辞書と私的辞書(SITES_JSON)をマージ。名前が重複したらシークレット側が勝つ。"""
    data = json.loads((ROOT / "definitions" / "sites.json").read_text())
    sites = {s["name"]: s for s in data["sites"]}
    default = data["default"]
    raw = os.environ.get("SITES_JSON")
    if raw:
        private = json.loads(raw)
        for s in private.get("sites", []):
            sites[s["name"]] = s
        default = private.get("default", default)
    return default, list(sites.values())


def fetch_json(url):
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def normalize_rows(data):
    """NOAAの2形式(ヘッダ行つき配列 / 辞書のリスト)を辞書のリストに揃える。"""
    if not isinstance(data, list) or not data:
        return []
    if isinstance(data[0], dict):
        return data
    header = data[0]
    return [dict(zip(header, r)) for r in data[1:]]


def pick(row, *keys):
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


def last_valid_row(data, *key_groups):
    """各キー群から1つずつ値が取れる、最後(最新)の行を返す。"""
    for row in reversed(normalize_rows(data)):
        if all(pick(row, *ks) is not None for ks in key_groups):
            return row
    return None


def collect_space_weather(errors):
    out = {"kp": None, "kp_time": None, "solar_wind": None, "imf": None}
    t_keys = ("time_tag", "time-tag")
    try:
        data = fetch_json("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json")
        row = last_valid_row(data, t_keys, ("Kp", "kp_index", "estimated_kp", "kp"))
        if row:
            out["kp_time"] = str(pick(row, *t_keys))
            out["kp"] = float(pick(row, "Kp", "kp_index", "estimated_kp", "kp"))
    except Exception as e:
        errors.append(f"kp: {e!r}")
    density_keys = ("density", "proton_density")
    speed_keys = ("speed", "proton_speed")
    bz_keys = ("bz_gsm", "bz")
    out["solar_wind"] = collect_first(
        [
            "https://services.swpc.noaa.gov/products/geospace/propagated-solar-wind-1-hour.json",
            "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json",
            "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json",
        ],
        (t_keys, density_keys, speed_keys),
        lambda row: {
            "time": str(pick(row, *t_keys)),
            "density_p_cm3": float(pick(row, *density_keys)),
            "speed_km_s": float(pick(row, *speed_keys)),
        },
        errors, "solar_wind",
    )
    out["imf"] = collect_first(
        [
            "https://services.swpc.noaa.gov/products/geospace/propagated-solar-wind-1-hour.json",
            "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json",
            "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json",
        ],
        (t_keys, bz_keys, ("bt",)),
        lambda row: {
            "time": str(pick(row, *t_keys)),
            "bz_nT": float(pick(row, *bz_keys)),
            "bt_nT": float(pick(row, "bt")),
        },
        errors, "imf",
    )
    return out


def collect_first(urls, key_groups, build, errors, label):
    """候補URLを順に試し、最初に取れたものを返す。全滅したときだけ欠測メモを残す。"""
    attempts = []
    for url in urls:
        try:
            row = last_valid_row(fetch_json(url), *key_groups)
            if row:
                return build(row)
            attempts.append(f"{url.rsplit('/', 1)[-1]}: no valid row")
        except Exception as e:
            attempts.append(f"{url.rsplit('/', 1)[-1]}: {e!r}")
    errors.append(f"{label}: " + " | ".join(attempts))
    return None


def collect_weather(site, errors):
    try:
        data = fetch_json(
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={site['lat']}&longitude={site['lon']}"
            "&current=temperature_2m,relative_humidity_2m,surface_pressure,pressure_msl,"
            "cloud_cover,wind_speed_10m,wind_direction_10m,precipitation,weather_code"
            "&timezone=UTC"
        )
        cur = data["current"]
        return {
            "time": cur["time"] + "Z",
            "temperature_c": cur["temperature_2m"],
            "humidity_pct": cur["relative_humidity_2m"],
            "pressure_surface_hpa": cur["surface_pressure"],
            "pressure_msl_hpa": cur["pressure_msl"],
            "cloud_cover_pct": cur["cloud_cover"],
            "wind_speed_kmh": cur["wind_speed_10m"],
            "wind_direction_deg": cur["wind_direction_10m"],
            "precipitation_mm": cur["precipitation"],
            "weather_code": cur["weather_code"],
        }
    except Exception as e:
        errors.append(f"weather[{site['name']}]: {e}")
        return None


def collect_celestial(now, errors):
    try:
        t = astronomy.Time.Make(now.year, now.month, now.day, now.hour, now.minute, now.second)
        longitudes = {}
        for key, body in PLANETS:
            if body == astronomy.Body.Sun:
                lon = astronomy.SunPosition(t).elon
            elif body == astronomy.Body.Moon:
                lon = astronomy.EclipticGeoMoon(t).lon
            else:
                vec = astronomy.GeoVector(body, t, True)
                lon = astronomy.Ecliptic(vec).elon
            longitudes[key] = {"lon_deg": round(lon, 4), "sign": SIGNS[int(lon // 30) % 12]}
        phase_deg = astronomy.MoonPhase(t)  # 0=新月, 180=満月
        illum = astronomy.Illumination(astronomy.Body.Moon, t).phase_fraction
        return {
            "longitudes": longitudes,
            "moon_phase_deg": round(phase_deg, 2),
            "moon_illumination": round(illum, 4),
            "moon_age_days": round(phase_deg / 360.0 * 29.530589, 2),
        }
    except Exception as e:
        errors.append(f"celestial: {e}")
        return None


def collect_calendar(now, celestial):
    jst_date = (now + datetime.timedelta(hours=9)).date()
    # 1949-10-01 は甲子日。日の干支はJSTの日付で数える
    anchor = datetime.date(1949, 10, 1)
    idx = (jst_date.toordinal() - anchor.toordinal()) % 60
    ganzhi = STEMS[idx % 10] + BRANCHES[idx % 12]
    sekki = None
    if celestial:
        sun_lon = celestial["longitudes"]["sun"]["lon_deg"]
        sekki = SEKKI[int(sun_lon // 15) % 24]
    return {
        "date_jst": jst_date.isoformat(),
        "day_ganzhi": ganzhi,
        "sekki": sekki,
        "day_planet": DAY_PLANETS[jst_date.weekday()],
    }


def main():
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    errors = []
    default, sites = load_sites()
    celestial = collect_celestial(now, errors)
    snapshot = {
        "schema": "field/v1",
        "moment": now.isoformat(),
        "site": default,
        "celestial": celestial,
        "terrestrial": {
            "space_weather": collect_space_weather(errors),
            "weather": {s["name"]: collect_weather(s, errors) for s in sites},
        },
        "calendar": collect_calendar(now, celestial),
        "errors": errors or None,
    }
    out = ROOT / "field" / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}" / f"{now:%H%M}Z.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    print(f"fossilized: {out.relative_to(ROOT)}")
    if errors:
        print("partial (recorded with nulls):", *errors, sep="\n  ", file=sys.stderr)


if __name__ == "__main__":
    main()
