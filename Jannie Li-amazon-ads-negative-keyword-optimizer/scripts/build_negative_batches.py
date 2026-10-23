#!/usr/bin/env python3
"""否词 / 否定商品批量提交构建器。

把用户已确认的清单拆成可逐批提交的 payload，并生成执行清单（manifest）。

为什么需要分批：
  1. batch_update_ads 单次上限 200 个数组项（data / target 各自硬限）
  2. 整批 all-or-nothing —— 任一项校验失败，整批被拒、一条都不写入
  3. 同步写操作，批次越大越容易超时，超时后状态不明难以恢复
  4. 部分失败时只能重试失败项，批次越小影响面越小

三条路由（payload 结构不同，不得混在同一批）：

  R1 关键词 · 广告活动级 → negativeKeyword + create
     request.data = [{profileId, campaignType, campaignId, negativeKeywords:[{keywordText,matchType}...]}]
     1 个 data 项 = 1 个活动 + 该活动下多条否词 → 单批否词数可远超 200

  R2 关键词 · 广告组级 → negativeKeyword + copy
     request.businessType = "adgroup"
     request.target = [{id:<adGroupId>, profileId, campaignType, keywordText, matchType}]
     1 个 target 项 = 1 条否词 → 单批否词数 ≤ 200

  R3 否定商品(ASIN) → negativeTarget + create
     request.businessType = "adgroup"
     request.target = [{id:<adGroupId>, profileId, campaignType, expression:[{type,value}]}]
     1 个 target 项 = 1 条否定商品 → 单批 ≤ 200
     仅适用于「商品投放」广告组；关键词投放广告组会被整批拒绝

输入（JSON，可为数组或 {"items":[...]}）：
  # 关键词否词
  {"profileId":"2950993281269288","campaignType":"sponsoredProducts","campaignId":44400757,
   "adGroupId":133264344,"businessType":"adgroup",
   "keywordText":"ear buds","matchType":"negativeExact"}

  # 否定商品
  {"profileId":"2950993281269288","campaignType":"sponsoredProducts","campaignId":44400757,
   "adGroupId":133264344,"asin":"B0G2Q34L8H","expressionType":"asinSameAs"}

用法：
  python build_negative_batches.py --items approved.json --outdir batches \
      --batch-size 100 --max-negatives-per-item 20 --existing existing_negatives.json
"""

import argparse
import json
import os
import re
from collections import OrderedDict

HARD_LIMIT = 200          # 单次数组项硬上限（data / target）
MAX_TEXT_LEN = 80         # keywordText 长度上限
VALID_MATCH = {"negativeExact", "negativePhrase"}
VALID_EXPR = {"asinSameAs", "asinBrandSameAs"}

R1 = "keyword-campaign"   # negativeKeyword + create
R2 = "keyword-adgroup"    # negativeKeyword + copy
R3 = "target-asin"        # negativeTarget + create


def load_items(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return raw
    for k in ("items", "rows", "data", "results"):
        if k in raw:
            v = raw[k]
            if isinstance(v, dict) and "rows" in v:
                return v["rows"]
            return v
    raise ValueError(f"无法从 {path} 解析条目")


def norm(text):
    t = str(text or "").lower().replace("+", " plus ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def route_of(it):
    """判定条目走哪条路由。"""
    if it.get("asin") or it.get("expression") or it.get("expressionType"):
        return R3
    bt = (it.get("businessType") or "adgroup").lower()
    return R1 if bt == "campaign" else R2


def target_id(it, route):
    if route == R1:
        return it.get("campaignId")
    return it.get("adGroupId")


def validate(it, route):
    errs = []
    if not it.get("profileId"):
        errs.append("缺少 profileId")
    if not it.get("campaignType"):
        errs.append("缺少 campaignType")

    if route == R3:
        if (it.get("businessType") or "adgroup").lower() != "adgroup":
            errs.append("否定商品仅支持广告组级（businessType 必须为 adgroup）")
        if not it.get("adGroupId"):
            errs.append("否定商品缺少 adGroupId")
        etype = it.get("expressionType") or "asinSameAs"
        if etype not in VALID_EXPR:
            errs.append(f"expressionType 非法({etype})")
        val = str(it.get("asin") or "")
        if etype == "asinSameAs":
            if not re.fullmatch(r"[A-Za-z0-9]{10}", val):
                errs.append(f"ASIN 格式非法({val})，需 10 位字母数字")
        elif etype == "asinBrandSameAs":
            if re.fullmatch(r"[A-Za-z0-9]{10}", val):
                errs.append(f"asinBrandSameAs 需要品牌 ID 或品牌名，不是 ASIN({val})")
            if not val.strip():
                errs.append("asinBrandSameAs 缺少品牌值")
        return errs

    text = str(it.get("keywordText") or "")
    if not text.strip():
        errs.append("keywordText 为空")
    if len(text) > MAX_TEXT_LEN:
        errs.append(f"keywordText 超长({len(text)}>{MAX_TEXT_LEN})")
    if "/" in text:
        errs.append("keywordText 含非法字符 '/'")
    if it.get("matchType") not in VALID_MATCH:
        errs.append(f"matchType 非法({it.get('matchType')})")

    if route == R1:
        if not it.get("campaignId"):
            errs.append("活动级否词缺少 campaignId")
        if (it.get("campaignType") or "").lower() not in ("sponsoredproducts",):
            errs.append("negativeKeyword+create 仅支持 sponsoredProducts")
    else:
        if not it.get("adGroupId"):
            errs.append("广告组级否词缺少 adGroupId")
        if it.get("campaignId") is None:
            errs.append("广告组级否词建议同时提供 campaignId 便于核对")
    return errs


def dedupe_key(it, route):
    base = (str(it.get("profileId")), route, str(target_id(it, route)))
    if route == R3:
        return base + (str(it.get("asin") or "").upper(),
                       it.get("expressionType") or "asinSameAs")
    return base + (norm(it.get("keywordText")), it.get("matchType"))


def build_data_items(items, max_per_item):
    """R1：按活动归组，1 个 data 项可含多条否词。"""
    groups = OrderedDict()
    for it in items:
        groups.setdefault((str(it["profileId"]), it["campaignType"], int(it["campaignId"])), []).append(it)
    out = []
    for (pid, ctype, cid), rows in groups.items():
        for i in range(0, len(rows), max_per_item):
            ch = rows[i:i + max_per_item]
            out.append({
                "profileId": pid,
                "campaignType": ctype,
                "campaignId": cid,
                "negativeKeywords": [{"keywordText": x["keywordText"], "matchType": x["matchType"]}
                                     for x in ch],
            })
    return out


def build_target_items(items, route):
    """R2 / R3：1 个 target 项 = 1 条否定。"""
    out = []
    for it in items:
        t = {
            "id": int(it["adGroupId"]),
            "profileId": str(it["profileId"]),
            "campaignType": it["campaignType"],
        }
        if route == R2:
            t["keywordText"] = it["keywordText"]
            t["matchType"] = it["matchType"]
        else:
            t["expression"] = [{
                "type": it.get("expressionType") or "asinSameAs",
                "value": str(it.get("asin") or "").upper() if (it.get("expressionType") or "asinSameAs") == "asinSameAs" else str(it.get("asin")),
            }]
        out.append(t)
    return out


def payload_for(route, items):
    profile_ids = sorted({int(x["profileId"]) for x in items})
    if route == R1:
        return {"entity": "negativeKeyword", "action": "create",
                "request": {"profileIds": profile_ids, "data": items}}
    if route == R2:
        return {"entity": "negativeKeyword", "action": "copy",
                "request": {"profileIds": profile_ids, "businessType": "adgroup", "target": items}}
    return {"entity": "negativeTarget", "action": "create",
            "request": {"profileIds": profile_ids, "businessType": "adgroup", "target": items}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True, help="已确认清单 JSON")
    ap.add_argument("--outdir", default="batches")
    ap.add_argument("--batch-size", type=int, default=100,
                    help=f"每批数组项数，默认 100，硬上限 {HARD_LIMIT}")
    ap.add_argument("--max-negatives-per-item", type=int, default=20,
                    help="R1 单个 data 项内最多合并的否词数")
    ap.add_argument("--existing", default=None, help="现有否词 JSON，用于跳过已存在条目")
    args = ap.parse_args()

    if args.batch_size > HARD_LIMIT:
        print(f"⚠️  batch-size {args.batch_size} 超过硬上限 {HARD_LIMIT}，已收敛为 {HARD_LIMIT}")
        args.batch_size = HARD_LIMIT

    raw = load_items(args.items)

    existing = set()
    if args.existing:
        for r in load_items(args.existing):
            if r.get("asin") or r.get("expression"):
                existing.add(dedupe_key(r, R3))
            else:
                bt = (r.get("businessType") or "adgroup").lower()
                existing.add(dedupe_key(r, R1 if bt == "campaign" else R2))

    invalid, skipped_dup, seen = [], [], set()
    valid = OrderedDict((r, []) for r in (R1, R2, R3))
    for it in raw:
        route = route_of(it)
        errs = validate(it, route)
        if errs:
            invalid.append({"item": it, "route": route, "errors": errs})
            continue
        key = dedupe_key(it, route)
        if key in existing:
            skipped_dup.append({**it, "_route": route, "reason": "已存在相同否定"})
            continue
        if key in seen:
            skipped_dup.append({**it, "_route": route, "reason": "清单内重复"})
            continue
        seen.add(key)
        valid[route].append(it)

    os.makedirs(args.outdir, exist_ok=True)
    manifest = {
        "totalInput": len(raw),
        "valid": sum(len(v) for v in valid.values()),
        "invalid": len(invalid),
        "skippedDuplicate": len(skipped_dup),
        "byRoute": {r: len(v) for r, v in valid.items()},
        "batchSize": args.batch_size,
        "batchCount": 0,
        "batches": [],
    }

    idx = 0
    for route in (R1, R2, R3):
        items = valid[route]
        if not items:
            continue
        if route == R1:
            units = build_data_items(items, args.max_negatives_per_item)
        else:
            units = build_target_items(items, route)
        for i in range(0, len(units), args.batch_size):
            chunk = units[i:i + args.batch_size]
            idx += 1
            name = f"batch_{idx:03d}.json"
            with open(os.path.join(args.outdir, name), "w", encoding="utf-8") as f:
                json.dump(payload_for(route, chunk), f, ensure_ascii=False, indent=2)
            if route == R1:
                neg = sum(len(d["negativeKeywords"]) for d in chunk)
            else:
                neg = len(chunk)
            manifest["batches"].append({
                "file": name, "route": route, "units": len(chunk), "negatives": neg,
            })

    manifest["batchCount"] = len(manifest["batches"])
    with open(os.path.join(args.outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    if invalid:
        with open(os.path.join(args.outdir, "invalid.json"), "w", encoding="utf-8") as f:
            json.dump(invalid, f, ensure_ascii=False, indent=2)
    if skipped_dup:
        with open(os.path.join(args.outdir, "skipped.json"), "w", encoding="utf-8") as f:
            json.dump(skipped_dup, f, ensure_ascii=False, indent=2)

    print("# 否词分批构建结果\n")
    print(f"- 输入条目：{manifest['totalInput']}")
    print(f"- 通过校验：{manifest['valid']}")
    print(f"- 校验失败：{manifest['invalid']}")
    print(f"- 跳过重复：{manifest['skippedDuplicate']}")
    for r in (R1, R2, R3):
        if manifest["byRoute"][r]:
            print(f"  - {r}：{manifest['byRoute'][r]} 条")
    print(f"- 分批：{manifest['batchCount']} 批（每批 ≤{args.batch_size} 个数组项）\n")
    if manifest["batches"]:
        print("| 批次 | 路由 | 数组项 | 否定条数 |")
        print("|---|---|---|---|")
        for b in manifest["batches"]:
            print(f"| {b['file']} | {b['route']} | {b['units']} | {b['negatives']} |")
    if invalid:
        print(f"\n⚠️  {len(invalid)} 条校验失败，详见 {args.outdir}/invalid.json（不得跳过，需先修正）")
    print("\n执行顺序：按 manifest.json 中 batches 顺序逐批提交，每批完成后重新读取验证，再执行下一批。")


if __name__ == "__main__":
    main()
