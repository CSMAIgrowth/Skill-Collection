#!/usr/bin/env python3
"""客户自有否词清单导入器（Excel / CSV）。

把客户提供的否词表标准化为可直接提交的否词条目，并解析目标位。

流程：
  1. 读取 xlsx / xls / csv
  2. 自动识别列（关键词、匹配类型、广告活动、广告组、层级、profile）
  3. 归一化匹配类型与层级
  4. 用 get_entity_metadata 导出的元数据 JSON 把名称解析为内部 ID
  5. 校验（长度 ≤80、不含 '/'、matchType 合法、目标位存在）
  6. 输出去重后的条目 JSON + 校验报告

用法：
  python import_negative_list.py --file customer_negatives.xlsx \
      --metadata campaigns.json adgroups.json \
      --default-profile-id 2950993281269288 \
      --default-business-type adgroup \
      --default-match-type negativeExact \
      --out approved_items.json --report import_report.md
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, OrderedDict

MAX_TEXT_LEN = 80
VALID_MATCH = {"negativeExact", "negativePhrase"}

# ---------- 列名识别 ----------

COL_PATTERNS = {
    "keywordText": [r"keyword ?text", r"^keyword$", r"search ?term", r"negative ?keyword",
                    r"否词", r"关键词", r"^词$", r"否定词"],
    "matchType": [r"match ?type", r"匹配类型", r"匹配方式", r"^类型$"],
    "campaignName": [r"campaign ?name", r"^campaign$", r"广告活动", r"^活动$", r"活动名称"],
    "campaignId": [r"campaign ?id", r"活动 ?id"],
    "adGroupName": [r"ad ?group ?name", r"^ad ?group$", r"^adgroup$", r"广告组", r"广告组名称"],
    "adGroupId": [r"ad ?group ?id", r"adgroup ?id", r"广告组 ?id"],
    "businessType": [r"business ?type", r"^level$", r"层级", r"否词层级", r"作用层级"],
    "profileId": [r"profile ?id", r"账户 ?id", r"店铺 ?id"],
}

MATCH_ALIASES = {
    "negativeexact": "negativeExact", "negative exact": "negativeExact",
    "exact": "negativeExact", "精准否定": "negativeExact", "否定精准": "negativeExact",
    "精准": "negativeExact", "否定精准匹配": "negativeExact", "精准否定匹配": "negativeExact",
    "negativephrase": "negativePhrase", "negative phrase": "negativePhrase",
    "phrase": "negativePhrase", "词组否定": "negativePhrase", "否定词组": "negativePhrase",
    "词组": "negativePhrase", "否定词组匹配": "negativePhrase", "词组否定匹配": "negativePhrase",
}

LEVEL_ALIASES = {
    "adgroup": "adgroup", "ad group": "adgroup", "广告组": "adgroup", "组": "adgroup",
    "campaign": "campaign", "活动": "campaign", "广告活动": "campaign",
}


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(s or "").lower()).split())


def norm_key(s):
    return norm(s)


def detect_columns(header):
    """返回 {字段: 列索引}。"""
    mapping = {}
    normed = [norm_key(h) for h in header]
    for field, pats in COL_PATTERNS.items():
        for i, h in enumerate(normed):
            if i in mapping.values() or not h:
                continue
            for p in pats:
                if re.search(p, h):
                    mapping[field] = i
                    break
            if field in mapping:
                break
    return mapping


# ---------- 读取 ----------

def read_table(path, sheet=None):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return [list(r) for r in csv.reader(f)]
    if ext in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            sys.exit("需要 openpyxl 才能读取 xlsx；或另存为 CSV 后重试")
        wb = load_workbook(path, data_only=True, read_only=True)
        ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    sys.exit(f"不支持的文件类型：{ext}（支持 .xlsx / .xlsm / .csv；.xls 请先另存为 xlsx）")


def load_metadata(paths):
    """从 get_entity_metadata 响应构建 名称 -> 内部ID 映射。"""
    camp_by_name, camp_by_id = {}, {}
    ag_by_name, ag_by_id = {}, {}
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        rows = raw
        if isinstance(raw, dict):
            rows = raw.get("data", {}).get("rows") or raw.get("rows") or []
        for r in rows:
            if r.get("adGroupName") and r.get("adGroupId") is not None:
                ag_by_name[norm_key(r["adGroupName"])] = r
                ag_by_id[str(r["adGroupId"])] = r
            if r.get("campaignName") and r.get("campaignId") is not None:
                camp_by_name[norm_key(r["campaignName"])] = r
                camp_by_id[str(r["campaignId"])] = r
    return camp_by_name, camp_by_id, ag_by_name, ag_by_id


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="客户否词表（xlsx / csv）")
    ap.add_argument("--sheet", default=None, help="工作表名，默认第一个")
    ap.add_argument("--metadata", nargs="*", default=[], help="get_entity_metadata 导出的 JSON（campaign / adGroup）")
    ap.add_argument("--default-profile-id", default=None)
    ap.add_argument("--default-business-type", default="adgroup", choices=["adgroup", "campaign"])
    ap.add_argument("--default-match-type", default="negativeExact",
                    choices=["negativeExact", "negativePhrase"])
    ap.add_argument("--campaign-type", default="sponsoredProducts")
    ap.add_argument("--header-row", type=int, default=1, help="表头所在行（1-based），默认 1")
    ap.add_argument("--out", default="approved_items.json")
    ap.add_argument("--report", default="import_report.md")
    args = ap.parse_args()

    table = read_table(args.file, args.sheet)
    if len(table) < 2:
        sys.exit("表格为空或只有表头")

    hi = args.header_row - 1
    header = table[hi]
    cols = detect_columns(header)
    body = table[hi + 1:]

    if "keywordText" not in cols:
        sys.exit(f"未能识别「关键词」列。表头为：{header}\n请把关键词列命名为 Keyword / 否词 / 关键词 之一")

    camp_by_name, camp_by_id, ag_by_name, ag_by_id = load_metadata(args.metadata)

    def cell(row, field):
        i = cols.get(field)
        if i is None or i >= len(row):
            return None
        v = row[i]
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    valid, unresolved, invalid, skipped = [], [], [], []
    seen = set()

    for rn, row in enumerate(body, start=hi + 2):
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue

        text = cell(row, "keywordText")
        if not text:
            invalid.append({"row": rn, "keywordText": None, "errors": ["关键词为空"]})
            continue

        raw_match = cell(row, "matchType")
        match = MATCH_ALIASES.get(norm_key(raw_match)) if raw_match else None
        if raw_match and not match:
            invalid.append({"row": rn, "keywordText": text,
                            "errors": [f"无法识别匹配类型：{raw_match}"]})
            continue
        match = match or args.default_match_type

        raw_level = cell(row, "businessType")
        level = LEVEL_ALIASES.get(norm_key(raw_level)) if raw_level else None
        if raw_level and not level:
            invalid.append({"row": rn, "keywordText": text,
                            "errors": [f"无法识别层级：{raw_level}"]})
            continue
        level = level or args.default_business_type

        pid = cell(row, "profileId") or args.default_profile_id
        if not pid:
            invalid.append({"row": rn, "keywordText": text, "errors": ["缺少 profileId"]})
            continue

        # 目标位解析
        camp_id = cell(row, "campaignId")
        ag_id = cell(row, "adGroupId")
        camp_name = cell(row, "campaignName")
        ag_name = cell(row, "adGroupName")

        if ag_id:
            meta = ag_by_id.get(str(ag_id))
            if meta and not camp_id:
                camp_id = meta.get("campaignId")
        if not ag_id and ag_name and ag_by_name:
            meta = ag_by_name.get(norm_key(ag_name))
            if meta:
                ag_id = meta.get("adGroupId")
                camp_id = camp_id or meta.get("campaignId")
        if not camp_id and camp_name and camp_by_name:
            meta = camp_by_name.get(norm_key(camp_name))
            if meta:
                camp_id = meta.get("campaignId")

        errors = []
        if len(text) > MAX_TEXT_LEN:
            errors.append(f"关键词超长({len(text)}>{MAX_TEXT_LEN})")
        if "/" in text:
            errors.append("关键词含非法字符 '/'")
        if level == "adgroup" and not ag_id:
            errors.append("广告组级否词无法定位广告组（缺 adGroupId / adGroupName 或名称未匹配）")
        if level == "campaign" and not camp_id:
            errors.append("活动级否词无法定位广告活动（缺 campaignId / campaignName 或名称未匹配）")

        if errors:
            target = unresolved if any("无法定位" in e for e in errors) else invalid
            target.append({"row": rn, "keywordText": text, "matchType": match,
                           "level": level, "campaignName": camp_name,
                           "adGroupName": ag_name, "errors": errors})
            continue

        item = {
            "profileId": str(pid),
            "campaignType": args.campaign_type,
            "businessType": level,
            "keywordText": text,
            "matchType": match,
        }
        if camp_id:
            item["campaignId"] = int(camp_id)
        if level == "adgroup":
            item["adGroupId"] = int(ag_id)

        key = (str(pid), level,
               str(camp_id if level == "campaign" else ag_id),
               norm_key(text), match)
        if key in seen:
            skipped.append({"row": rn, "keywordText": text, "reason": "清单内重复"})
            continue
        seen.add(key)
        valid.append(item)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(valid, f, ensure_ascii=False, indent=2)

    # 报告
    lines = ["# 否词清单导入报告\n"]
    lines.append(f"- 源文件：`{args.file}`" + (f"（工作表 {args.sheet}）" if args.sheet else ""))
    lines.append(f"- 识别到的列：{', '.join(f'{k}→第{v + 1}列' for k, v in cols.items())}")
    lines.append(f"- 有效条目：**{len(valid)}**")
    lines.append(f"- 目标位无法定位：{len(unresolved)}")
    lines.append(f"- 格式非法：{len(invalid)}")
    lines.append(f"- 清单内重复跳过：{len(skipped)}")
    if valid:
        c = Counter(i["businessType"] for i in valid)
        m = Counter(i["matchType"] for i in valid)
        lines.append(f"- 层级分布：{dict(c)}")
        lines.append(f"- 匹配类型分布：{dict(m)}")
        lines.append(f"- 涉及广告活动：{len({i.get('campaignId') for i in valid})} 个")
        lines.append(f"- 涉及广告组：{len({i.get('adGroupId') for i in valid if i.get('adGroupId')})} 个")
    lines.append("")

    def block(title, rows, extra_cols):
        if not rows:
            return
        lines.append(f"## {title}（{len(rows)} 条）\n")
        if extra_cols:
            lines.append("| 行号 | 关键词 | " + " | ".join(extra_cols) + " | 问题 |")
            lines.append("|---|---|" + "---|" * len(extra_cols) + "---|")
        else:
            lines.append("| 行号 | 关键词 | 问题 |")
            lines.append("|---|---|---|")
        for x in rows[:200]:
            vals = " | ".join(str(x.get(k) or "—") for k in extra_cols)
            issue = "；".join(x["errors"]) if "errors" in x else x.get("reason", "")
            if extra_cols:
                lines.append(f"| {x['row']} | {x.get('keywordText') or '—'} | {vals} | {issue} |")
            else:
                lines.append(f"| {x['row']} | {x.get('keywordText') or '—'} | {issue} |")
        if len(rows) > 200:
            lines.append(f"\n> 仅显示前 200 条，共 {len(rows)} 条")
        lines.append("")

    block("目标位无法定位（需补充或修正）", unresolved, ["campaignName", "adGroupName"])
    block("格式非法（需修正）", invalid, ["matchType"])
    block("清单内重复（已跳过）", skipped, [])

    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))
    print(f"\n有效条目已写入 {args.out}")
    if unresolved or invalid:
        print(f"⚠️  {len(unresolved) + len(invalid)} 条需人工处理，未纳入提交清单。"
              f"不得静默丢弃，须向用户逐条列出。")


if __name__ == "__main__":
    main()
