#!/usr/bin/env python3
"""yorishiro field collector — 場のスナップショットを1つ生成して field/ に追記する。

取れなかった項目は null + エラーメモで残し、化石化自体は決して止めない。
"""
import datetime
import json
import math
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
ROKUYO = ["大安", "赤口", "先勝", "友引", "先負", "仏滅"]  # (旧暦月+旧暦日) % 6
KYUSEI = ["一白水星", "二黒土星", "三碧木星", "四緑木星", "五黄土星",
          "六白金星", "七赤金星", "八白土星", "九紫火星"]
JST = datetime.timezone(datetime.timedelta(hours=9))
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
    try:
        data = fetch_json("https://services.swpc.noaa.gov/json/goes/primary/xrays-6-hour.json")
        rows = [r for r in normalize_rows(data) if r.get("energy") == "0.1-0.8nm" and r.get("flux") not in (None, "")]
        if rows:
            row = rows[-1]
            flux = float(row["flux"])
            out["xray"] = {
                "time": str(pick(row, *t_keys)),
                "flux_w_m2": flux,
                "flare_class": flare_class(flux),
            }
        else:
            out["xray"] = None
    except Exception as e:
        out["xray"] = None
        errors.append(f"xray: {e!r}")
    try:
        data = fetch_json("https://services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json")
        row = last_valid_row(data, t_keys, ("ssn",))
        out["solar_cycle"] = {
            "month": str(pick(row, *t_keys)),
            "ssn": float(pick(row, "ssn")),
            "f10_7": float(pick(row, "f10.7", "f10_7")) if pick(row, "f10.7", "f10_7") is not None else None,
        } if row else None
    except Exception as e:
        out["solar_cycle"] = None
        errors.append(f"solar_cycle: {e!r}")
    return out


def flare_class(flux):
    for letter, threshold in [("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7)]:
        if flux >= threshold:
            return f"{letter}{flux / threshold:.1f}"
    return f"A{flux / 1e-8:.1f}"


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


def ecliptic_lon(body, t):
    if body == astronomy.Body.Sun:
        return astronomy.SunPosition(t).elon
    if body == astronomy.Body.Moon:
        return astronomy.EclipticGeoMoon(t).lon
    return astronomy.Ecliptic(astronomy.GeoVector(body, t, True)).elon


def vec_length_au(vec):
    return math.sqrt(vec.x ** 2 + vec.y ** 2 + vec.z ** 2)


def rise_set(body, observer, start, direction):
    found = astronomy.SearchRiseSet(body, observer, direction, start, 1.2)
    return found.Utc().replace(tzinfo=datetime.timezone.utc).astimezone(JST).strftime("%H:%M") if found else None


def collect_celestial(now, site, errors):
    try:
        t = astronomy.Time.Make(now.year, now.month, now.day, now.hour, now.minute, now.second)
        longitudes = {}
        retrograde = []
        for key, body in PLANETS:
            lon = ecliptic_lon(body, t)
            longitudes[key] = {"lon_deg": round(lon, 4), "sign": SIGNS[int(lon // 30) % 12]}
            if body not in (astronomy.Body.Sun, astronomy.Body.Moon):
                drift = (ecliptic_lon(body, t.AddDays(0.5)) - lon + 540) % 360 - 180
                if drift < 0:
                    retrograde.append(key)
        phase_deg = astronomy.MoonPhase(t)  # 0=新月, 180=満月
        illum = astronomy.Illumination(astronomy.Body.Moon, t).phase_fraction
        moon_km = vec_length_au(astronomy.GeoVector(astronomy.Body.Moon, t, True)) * 149597870.7
        sun_au = vec_length_au(astronomy.GeoVector(astronomy.Body.Sun, t, True))
        # 潮汐力指数: 月+太陽の起潮力(M/d^3)を月の平均距離=1.0で正規化。平均≈1.46、大きいほど強い
        tidal = (384400.0 / moon_km) ** 3 + 0.46 * (1.0 / sun_au) ** 3
        out = {
            "longitudes": longitudes,
            "retrograde": retrograde,
            "moon_phase_deg": round(phase_deg, 2),
            "moon_illumination": round(illum, 4),
            "moon_age_days": round(phase_deg / 360.0 * 29.530589, 2),
            "moon_distance_km": round(moon_km),
            "tidal_index": round(tidal, 3),
        }
        try:
            jst_now = now.astimezone(JST)
            midnight_utc = datetime.datetime(jst_now.year, jst_now.month, jst_now.day, tzinfo=JST).astimezone(datetime.timezone.utc)
            start = astronomy.Time.Make(midnight_utc.year, midnight_utc.month, midnight_utc.day, midnight_utc.hour, 0, 0)
            obs = astronomy.Observer(site["lat"], site["lon"], 0.0)
            out["rise_set_jst"] = {
                "sun": {"rise": rise_set(astronomy.Body.Sun, obs, start, astronomy.Direction.Rise),
                        "set": rise_set(astronomy.Body.Sun, obs, start, astronomy.Direction.Set)},
                "moon": {"rise": rise_set(astronomy.Body.Moon, obs, start, astronomy.Direction.Rise),
                         "set": rise_set(astronomy.Body.Moon, obs, start, astronomy.Direction.Set)},
            }
        except Exception as e:
            errors.append(f"rise_set: {e!r}")
        return out
    except Exception as e:
        errors.append(f"celestial: {e!r}")
        return None


def kyureki(now):
    """旧暦の月日を朔望月+中気法で求める。返り値: (月, 日, 閏月か)"""
    t = astronomy.Time.Make(now.year, now.month, now.day, now.hour, now.minute, now.second)

    def prev_new_moon(t_ref):
        nm = astronomy.SearchMoonPhase(0, t_ref.AddDays(-31), 32)
        while True:
            nxt = astronomy.SearchMoonPhase(0, nm.AddDays(1), 32)
            if nxt is None or nxt.ut > t_ref.ut:
                return nm
            nm = nxt

    def month_of_lunation(start, end):
        """朔望月[start, end)に含まれる中気(黄経30°の倍数)から旧暦月を返す。無ければNone=閏月。"""
        for k in range(12):
            found = astronomy.SearchSunLongitude(k * 30.0, start, end.ut - start.ut)
            if found is not None and found.ut < end.ut:
                return ((k + 1) % 12) + 1  # 330°雨水=1月, 0°春分=2月, ...
        return None

    start = prev_new_moon(t)
    end = astronomy.SearchMoonPhase(0, start.AddDays(1), 35)
    month = month_of_lunation(start, end)
    leap = month is None
    if leap:  # 中気を含まない月は閏月 — 前の朔望月の月名を継ぐ
        prev_start = prev_new_moon(start.AddDays(-1))
        month = month_of_lunation(prev_start, start)
    start_jst = start.Utc().replace(tzinfo=datetime.timezone.utc).astimezone(JST).date()
    day = (now.astimezone(JST).date() - start_jst).days + 1
    return month, day, leap


def kyusei_year_month(jst_date, sun_lon):
    """九星(年家・月家)。年は立春、月は節切り。"""
    m = int(((sun_lon - 315) % 360) // 30)  # 0=寅月(立春〜)
    year = jst_date.year
    if jst_date.month <= 2 and m >= 10:  # 立春前は前年扱い
        year -= 1
    n = year
    while n > 9:
        n = sum(int(c) for c in str(n))
    ystar = 11 - n
    if ystar > 9:
        ystar -= 9
    anchor = [8, 2, 5][(ystar - 1) % 3]  # 年星1,4,7→寅月八白 / 2,5,8→二黒 / 3,6,9→五黄
    mstar = ((anchor - m - 1) % 9) + 1
    return KYUSEI[ystar - 1], KYUSEI[mstar - 1]


def collect_calendar(now, celestial, errors):
    jst_date = now.astimezone(JST).date()
    # 1949-10-01 は甲子日。日の干支はJSTの日付で数える
    anchor = datetime.date(1949, 10, 1)
    idx = (jst_date.toordinal() - anchor.toordinal()) % 60
    ganzhi = STEMS[idx % 10] + BRANCHES[idx % 12]
    out = {
        "date_jst": jst_date.isoformat(),
        "day_ganzhi": ganzhi,
        "sekki": None,
        "day_planet": DAY_PLANETS[jst_date.weekday()],
        "kyureki": None,
        "rokuyo": None,
        "kyusei_year": None,
        "kyusei_month": None,
    }
    if celestial:
        sun_lon = celestial["longitudes"]["sun"]["lon_deg"]
        out["sekki"] = SEKKI[int(sun_lon // 15) % 24]
        try:
            month, day, leap = kyureki(now)
            out["kyureki"] = {"month": month, "day": day, "leap": leap}
            out["rokuyo"] = ROKUYO[(month + day) % 6]
        except Exception as e:
            errors.append(f"kyureki: {e!r}")
        try:
            out["kyusei_year"], out["kyusei_month"] = kyusei_year_month(jst_date, sun_lon)
        except Exception as e:
            errors.append(f"kyusei: {e!r}")
    return out


def collect_seismic(errors):
    """日本周辺(緯度24-46, 経度122-148)の直近24時間・M4以上。"""
    try:
        since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24))
        data = fetch_json(
            "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
            f"&starttime={since:%Y-%m-%dT%H:%M:%S}"
            "&minmagnitude=4&minlatitude=24&maxlatitude=46&minlongitude=122&maxlongitude=148"
            "&orderby=magnitude&limit=50"
        )
        feats = data.get("features", [])
        out = {"count_24h_m4": len(feats), "max": None}
        if feats:
            p = feats[0]["properties"]
            geo = feats[0]["geometry"]["coordinates"]
            out["max"] = {
                "mag": p.get("mag"),
                "place": p.get("place"),
                "time": datetime.datetime.fromtimestamp(p["time"] / 1000, datetime.timezone.utc).isoformat(),
                "depth_km": geo[2] if len(geo) > 2 else None,
            }
        return out
    except Exception as e:
        errors.append(f"seismic: {e!r}")
        return None


def main():
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    errors = []
    default, sites = load_sites()
    anchor_site = next(s for s in sites if s["name"] == default)
    celestial = collect_celestial(now, anchor_site, errors)
    snapshot = {
        "schema": "field/v1",
        "moment": now.isoformat(),
        "site": default,
        "celestial": celestial,
        "terrestrial": {
            "space_weather": collect_space_weather(errors),
            "weather": {s["name"]: collect_weather(s, errors) for s in sites},
            "seismic": collect_seismic(errors),
        },
        "calendar": collect_calendar(now, celestial, errors),
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
