"""Render a standalone, customer-facing report from validated aggregates."""

import argparse
import json
from pathlib import Path
import re


ASSETS = Path(__file__).resolve().parents[1] / "assets"


def render(data):
    for key in ("client", "prior", "current", "currency"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"Missing required text field: {key}")
    if not re.fullmatch(r"[A-Z]{3}", data["currency"]):
        raise ValueError("currency must be a three-letter currency code")
    if not isinstance(data.get("account"), list) or len(data["account"]) != 2:
        raise ValueError("account requires [prior, current]")
    sites = data.get("sites", [])
    ids = [row["id"] for row in sites]
    if len(ids) != len(set(ids)) or any(
        key in {"overview", "focus"} or not re.fullmatch(r"[a-z][a-z0-9-]*", key)
        for key in ids
    ):
        raise ValueError("site IDs must be unique lowercase slugs; overview and focus are reserved")
    parents = data.get("parents", [])
    keys = [(row["site"], row["store"], row["asin"]) for row in parents]
    if len(keys) != len(set(keys)) or any(site not in ids for site, _, _ in keys):
        raise ValueError("Parent rows must have unique site/store/ASIN keys and a known site")
    limit = data.get("focusLimit", 6)
    if type(limit) is not int or limit < 0:
        raise ValueError("focusLimit must be a nonnegative integer")

    payload = json.dumps(data, ensure_ascii=False, allow_nan=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    parts = {
        "__REPORT_DATA__": payload,
        "__REPORT_SCRIPT__": (ASSETS / "report.js").read_text(encoding="utf-8"),
    }
    template = (ASSETS / "report.html").read_text(encoding="utf-8")
    return re.sub(r"__REPORT_(?:DATA|SCRIPT)__", lambda match: parts[match[0]], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("use a separate output file")
    result = render(json.loads(args.source.read_text(encoding="utf-8-sig")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")


if __name__ == "__main__":
    main()
