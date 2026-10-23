#!/usr/bin/env python3
"""否词候选分析器。

输入：
  - 搜索词数据（get_ads_perf 原始响应文件，或行数组 JSON；可传多个，自动去重合并）
  - 可选：关键词元数据（get_entity_metadata entity='keyword' 原始响应）
  - 可选：现有否词（get_entity_metadata entity='negativeKeyword' 原始响应）
  - 可选：聚合值（用于对平校验）

输出：
  - 终端 Markdown 摘要
  - --out-json 指定路径时写出结构化结果

用法：
  python analyze_search_terms.py --terms p1.txt p2.txt \
      --keywords kw.txt --negatives neg.txt \
      --min-clicks 10 --min-spend 15 \
      --target-acos 40 --acos-tolerance 2.0 --min-orders 1 --min-clicks-acos 20 \
      --out-json result.json
"""

import argparse
import json
import re
import sys
from collections import defaultdict


# ---------- 读取 ----------

def load_rows(path):
    """从 MCP 原始响应或行数组 JSON 中取出 rows。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "data" in raw and isinstance(raw["data"], dict) and "rows" in raw["data"]:
            return raw["data"]["rows"]
        if "rows" in raw:
            return raw["rows"]
    raise ValueError(f"无法从 {path} 解析 rows")


def pick(row, *names, default=None):
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    return default


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------- 归一化 ----------

_PUNCT = re.compile(r"[^a-z0-9]+")


def norm(text):
    """统一大小写、符号、+ 号，便于搜索词与关键词比对。"""
    if not text:
        return ""
    t = str(text).lower()
    t = t.replace("+", " plus ")
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


def build_keyword_index(keyword_rows):
    """norm(keywordText) -> 最佳状态（enabled 优先于 paused/archived）。"""
    rank = {"enabled": 3, "paused": 2, "archived": 1}
    idx = {}
    for r in keyword_rows:
        text = norm(pick(r, "keywordText", "keyword", default=""))
        if not text:
            continue
        state = str(pick(r, "keywordState", "state", default="unknown")).lower()
        prev = idx.get(text)
        if prev is None or rank.get(state, 0) > rank.get(prev, 0):
            idx[text] = state
    return idx


def match_keyword(term, kw_index):
    """返回 (匹配到的关键词文本, 状态) 或 (None, None)。

    先精确匹配归一化文本，再退化为包含匹配（处理连字符、单复数等变体）。
    """
    n = norm(term)
    if not n:
        return None, None
    if n in kw_index:
        return n, kw_index[n]
    # 包含匹配：取最长候选，避免短词误配
    best = None
    for k, state in kw_index.items():
        if len(k) < 4:
            continue
        if n == k or n in k or k in n:
            if best is None or len(k) > len(best[0]):
                best = (k, state)
    if best:
        return best
    return None, None


# ---------- 规则引擎 ----------

def classify(row, kw_index, args, protected):
    clicks = num(pick(row, "Clicks", "clicks"))
    spend = num(pick(row, "Spend", "spend"))
    sales = num(pick(row, "Sales", "sales"))
    orders = num(pick(row, "Conversions", "conversions", "Orders", "orders"))
    term = pick(row, "query", "searchTerm", "SearchTerm", default="")

    acos = (spend / sales * 100.0) if sales > 0 else None

    kw_text, kw_state = match_keyword(term, kw_index)

    rules = []
    zero_conv = (
        clicks >= args.min_clicks
        and spend >= args.min_spend
        and orders == 0
    )
    if zero_conv:
        rules.append(f"零转化高花费(点击{clicks:g}>={args.min_clicks:g} AND 花费{spend:.2f}>={args.min_spend:g} AND 订单=0)")

    acos_hit = False
    if acos is not None and acos > args.target_acos * args.acos_tolerance:
        if orders >= args.min_orders or clicks >= args.min_clicks_acos:
            acos_hit = True
            rules.append(f"ACOS超标({acos:.1f}%>{args.target_acos * args.acos_tolerance:.0f}%)")

    is_protected = norm(term) in protected

    # 分类
    if zero_conv or acos_hit:
        if is_protected:
            bucket = "conflict"
        elif orders > 0:
            # 有订单不自动否
            bucket = "watch"
        elif kw_state in ("paused", "archived"):
            # 关键词已暂停：加否词无增量效果
            bucket = "moot"
        elif kw_state == "enabled":
            # 加否词等同关词，应先考虑暂停关键词
            bucket = "keyword_conflict"
        else:
            bucket = "add"
    else:
        if orders > 0 or is_protected:
            bucket = "keep"
        elif clicks < args.min_clicks:
            bucket = "watch"
        else:
            bucket = "keep"

    return {
        "searchTerm": term,
        "matchType": pick(row, "matchType", default=""),
        "campaignName": pick(row, "campaignName", default=""),
        "campaignId": pick(row, "campaignId", default=""),
        "adGroupName": pick(row, "adGroupName", default=""),
        "adGroupId": pick(row, "adGroupId", default=""),
        "clicks": clicks,
        "spend": round(spend, 2),
        "orders": orders,
        "sales": round(sales, 2),
        "acos": round(acos, 2) if acos is not None else None,
        "keywordMatched": kw_text,
        "keywordState": kw_state,
        "protected": is_protected,
        "rules": rules,
        "bucket": bucket,
    }


BUCKET_TITLE = {
    "add": "A. 建议添加（可执行否词）",
    "keyword_conflict": "B. 与在投关键词冲突（建议暂停/降 bid，而非加否词）",
    "moot": "C. 关键词已暂停（加否词无增量效果）",
    "conflict": "D. 规则冲突（需用户决策）",
    "watch": "E. 建议观察",
    "keep": "F. 建议保留",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terms", nargs="+", required=True, help="搜索词数据文件，可多个")
    ap.add_argument("--keywords", nargs="*", default=[], help="关键词元数据文件")
    ap.add_argument("--negatives", nargs="*", default=[], help="现有否词文件")
    ap.add_argument("--protected", nargs="*", default=[], help="需保护的词（品牌词/核心词）")
    ap.add_argument("--min-clicks", type=float, default=10)
    ap.add_argument("--min-spend", type=float, default=15)
    ap.add_argument("--target-acos", type=float, default=40)
    ap.add_argument("--acos-tolerance", type=float, default=2.0)
    ap.add_argument("--min-orders", type=float, default=1)
    ap.add_argument("--min-clicks-acos", type=float, default=20)
    ap.add_argument("--aggregate", default=None, help="聚合值 JSON，用于对平校验")
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    # 合并搜索词，按 (query, matchType, campaignId, adGroupId) 去重
    seen = {}
    for path in args.terms:
        for r in load_rows(path):
            k = (
                str(pick(r, "query", "searchTerm", default="")),
                str(pick(r, "matchType", default="")),
                str(pick(r, "campaignId", default="")),
                str(pick(r, "adGroupId", default="")),
            )
            if k not in seen:
                seen[k] = r
    rows = list(seen.values())

    kw_rows = []
    for p in args.keywords:
        kw_rows.extend(load_rows(p))
    kw_index = build_keyword_index(kw_rows)

    neg_rows = []
    for p in args.negatives:
        neg_rows.extend(load_rows(p))
    neg_set = {norm(pick(r, "keywordText", default="")) for r in neg_rows}

    protected = {norm(t) for t in args.protected}

    results = [classify(r, kw_index, args, protected) for r in rows]
    for r in results:
        r["alreadyNegative"] = norm(r["searchTerm"]) in neg_set

    # 对平校验
    tot = {
        "rows": len(results),
        "impressions": sum(num(pick(r, "Impressions", "impressions")) for r in results),
        "clicks": sum(r["clicks"] for r in results),
        "spend": round(sum(r["spend"] for r in results), 2),
        "sales": round(sum(r["sales"] for r in results), 2),
        "orders": sum(r["orders"] for r in results),
    }
    check = ""
    if args.aggregate:
        agg = load_rows(args.aggregate)
        if agg:
            a = agg[0]
            pairs = [
                ("clicks", num(pick(a, "Clicks", "clicks")), tot["clicks"]),
                ("spend", num(pick(a, "Spend", "spend")), tot["spend"]),
                ("sales", num(pick(a, "Sales", "sales")), tot["sales"]),
                ("orders", num(pick(a, "Conversions", "conversions")), tot["orders"]),
            ]
            bad = [n for n, exp, got in pairs if abs(exp - got) > 0.05]
            check = "✅ 与聚合值对平" if not bad else f"❌ 对平失败：{', '.join(bad)}"

    # 输出
    grouped = defaultdict(list)
    for r in results:
        grouped[r["bucket"]].append(r)

    print("# 否词候选分析结果\n")
    print(f"- 搜索词记录：{tot['rows']} 条")
    print(f"- 曝光 {tot['impressions']:.0f} / 点击 {tot['clicks']:.0f} / 花费 ${tot['spend']:.2f} / 销售 ${tot['sales']:.2f} / 订单 {tot['orders']:.0f}")
    if tot["sales"] > 0:
        print(f"- ACOS {tot['spend'] / tot['sales'] * 100:.2f}%")
    if check:
        print(f"- 数据校验：{check}")
    print(f"- 规则：点击>={args.min_clicks:g} AND 花费>=${args.min_spend:g} AND 订单=0；ACOS>{args.target_acos * args.acos_tolerance:.0f}%")
    print()

    for key in ("add", "keyword_conflict", "moot", "conflict", "watch", "keep"):
        items = grouped.get(key, [])
        if not items:
            continue
        print(f"## {BUCKET_TITLE[key]}（{len(items)} 条）\n")
        print("| 搜索词 | 关键词状态 | 点击 | 花费 | 订单 | 销售 | ACOS | 命中规则 | 已是否词 |")
        print("|---|---|---|---|---|---|---|---|---|")
        for r in sorted(items, key=lambda x: -x["spend"]):
            acos = f"{r['acos']:.1f}%" if r["acos"] is not None else "—"
            rules = "；".join(r["rules"]) if r["rules"] else "—"
            print(
                f"| {r['searchTerm']} | {r['keywordState'] or '无对应'} | {r['clicks']:g} | "
                f"${r['spend']:.2f} | {r['orders']:g} | ${r['sales']:.2f} | {acos} | {rules} | "
                f"{'是' if r['alreadyNegative'] else '否'} |"
            )
        print()

    if not grouped.get("add"):
        print("> ⚠️ 可执行否词为 0 条。若 B/C/D 组有内容，说明问题应通过关键词状态或出价解决，"
              "不得为凑数强行添加否词。\n")

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump({"summary": tot, "check": check, "results": results}, f,
                      ensure_ascii=False, indent=2)
        print(f"结构化结果已写入 {args.out_json}")


if __name__ == "__main__":
    sys.exit(main())
