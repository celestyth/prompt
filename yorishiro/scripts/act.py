#!/usr/bin/env python3
"""即記道具 — 儀式・占いを1コマンドで acts/ に化石化する。

使い方:
  python scripts/act.py tarot -q "今日の指針は" -r "塔(逆)" -r "星" -c "頭が冴えている" -n "所感"
  python scripts/act.py 儀式名                # 最小記録(method と時刻だけ)でもよい

その瞬間に書けなかった分は --moment で遡って記録できる(例: --moment "2026-07-29T21:00")。
"""
import argparse
import datetime
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
JST = datetime.timezone(datetime.timedelta(hours=9))


def main():
    ap = argparse.ArgumentParser(description="儀式・占いの即記")
    ap.add_argument("method", help="占術・儀式の種類 (tarot, 易, 独自体系名など)")
    ap.add_argument("-q", "--question", default=None, help="問い")
    ap.add_argument("-r", "--result", action="append", default=[], help="出目(複数回指定可)")
    ap.add_argument("-c", "--condition", default=None, help="自分の状態")
    ap.add_argument("-n", "--note", default=None, help="所感・自由記述")
    ap.add_argument("--site", default=None, help="象徴名(省略時はsites.jsonのdefault)")
    ap.add_argument("--moment", default=None, help="遡り記録用の時刻 (例: 2026-07-29T21:00)")
    args = ap.parse_args()

    if args.site is None:
        sites = json.loads((ROOT / "definitions" / "sites.json").read_text())
        args.site = sites["default"]
    if args.moment:
        moment = datetime.datetime.fromisoformat(args.moment)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=JST)
    else:
        moment = datetime.datetime.now(JST).replace(microsecond=0)

    act = {
        "schema": "act/v1",
        "moment": moment.isoformat(),
        "site": args.site,
        "method": args.method,
        "question": args.question,
        "result": args.result or None,
        "self": {"condition": args.condition, "note": None} if args.condition else None,
        "note": args.note,
    }
    slug = re.sub(r"[^\w\-]", "_", args.method)[:20]
    out = ROOT / "acts" / f"{moment:%Y}" / f"{moment:%m%d}-{moment:%H%M}-{slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(act, ensure_ascii=False, indent=2) + "\n")
    print(f"fossilized: {out.relative_to(ROOT)}")
    print("忘れずに: git add acts && git commit -m 'act' && git push")


if __name__ == "__main__":
    main()
