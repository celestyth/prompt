#!/usr/bin/env python3
"""yorishiro validator — field/ と acts/ の全レコードをスキーマ検証する。

壊れたデータが地層に混ざった瞬間にCIで気づくための門番。
"""
import json
import pathlib
import sys

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_schema(name):
    return json.loads((ROOT / "schemas" / name).read_text())


def validate_tree(directory, schema, errors):
    if not directory.exists():
        return 0
    count = 0
    for path in sorted(directory.rglob("*.json")):
        count += 1
        try:
            jsonschema.validate(json.loads(path.read_text()), schema)
        except Exception as e:
            errors.append(f"{path.relative_to(ROOT)}: {getattr(e, 'message', e)}")
    return count


def main():
    errors = []
    n_field = validate_tree(ROOT / "field", load_schema("field.schema.json"), errors)
    n_acts = validate_tree(ROOT / "acts", load_schema("act.schema.json"), errors)
    json.loads((ROOT / "definitions" / "sites.json").read_text())
    print(f"validated: {n_field} field snapshots, {n_acts} acts")
    if errors:
        print("INVALID:", *errors, sep="\n  ", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
