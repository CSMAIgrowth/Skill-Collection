#!/usr/bin/env python3
"""30 / 60 / 90 天递进验证器。

解决的问题：只看最近 30 天就否词，误杀率很高。一个词可能在上个月出过 3 单，
只是最近 30 天碰上流量波动。正确做法是先看 30 天是否触发，再回看 60 天和 90 天
累计表现，确认它是「长期无效」还是「短期波动」。

为什么用三个不重叠窗口而不是三次累计查询：
  - 累计查询（0-30 / 0-60 / 0-90）需要做减法才能得到边际表现，减法会引入误差，
    且某个词只在一个窗口出现时无法拆分。
  - 三个不重叠窗口相加即得累计值，且能直接看出「最近 30 天 vs 之前 30 天」的趋势。

窗口定义（以 end 为基准向前推）：
  W1 = 最近 30 天      → 累计 30 天
  W2 = 第 31~60 天     → 累计 60 天 = W1 + W2
  W3 = 第 61~90 天     → 累计 90 天 = W1 + W2 + W3

输入：三份 get_ads_perf 的原始返回（或 {"data":{"rows":[...]}}，或直接数组）
用法：
  python verify_term_windows.py --w30 w1.json --w60 w2.json --w90 w3.json \
      --min-clicks 10 --min-spend 15 --target-acos 40 --acos-tolerance 2.0 \
      --protected "cleer" "cleer arc 4" --out-json verify.json --report verify.md
"""

import argparse
import json
import re
from collections import OrderedDict

# ---------- 载入 ----------

def load_rows(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "data" in raw:
            d = raw["data"]
            if isinstance(d, dict) and "rows" in d:
                return d["rows"]
            if isinstance(d, list):
                return d
        for k in ("rows", "items", "data"):
            if k in raw and isinstance(raw[k], list):
                return raw[k]
    raise ValueError(f"无法从 {path} 解析行数据")


def num(row, *names):
    for n in names:
        if n in row and row[n] is not None:
            try:
                return float(row[n])
            except (TypeError, ValueError):
                pass
    return 0.0


def norm(text):
    t = str(text or "").lower().replace("+", " plus ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def term_key(row, key_mode):
    q = row.get("query") or row.get("searchTerm") or row.get("keywordText") or ""
    if key_mode == "query":
        return norm(q)
    ag = row.get("adGroupId") or row.get("amazonAdGroupId")
    return f"{norm(q)}||{ag}"


# ---------- 聚合 ----------

class Acc:
    __slots__ = ("clicks", "spend", "orders", "sales", "imp", "present")

    def __init__(self):
        self.clicks = self.spend = self.orders = self.sales = self.imp = 0.0
        self.present = False

    def add(self, row):
        self.present = True
        self.clicks += num(row, "Clicks", "clicks")
        self.spend += num(row, "Spend", "spend", "Cost")
        self.orders += num(row, "Conversions", "conversions", "Orders", "orders")
        self.sales += num(row, "Sales", "sales")
        self.imp += num(row, "Impressions", "impressions")

    def merge(self, other):
        a = Acc()
        a.present = self.present or other.present
        a.clicks = self.clicks + other.clicks
        a.spend = self.spend + other.spend
        a.orders = self.orders + other.orders
        a.sales = self.sales + other.sales
        a.imp = self.imp + other.imp
        return a

    @property
    def acos(self):
        return (self.spend / self.sales * 100.0) if self.sales > 0 else None

    @property
    def cvr(self):
        return (self.orders / self.clicks * 100.0) if self.clicks > 0 else None

    @property
    def cpc(self):
        return (self.spend / self.clicks) if self.clicks > 0 else None


def build(path, key_mode):
    out = OrderedDict()
    for row in load_rows(path):
        k = term_key(row, key_mode)
        if not k.strip("|"):
            continue
        out.setdefault(k, {"term": row.get("query") or row.get("searchTerm") or "",
                           "adGroupId": row.get("adGroupId"),
                           "campaignId": row.get("campaignId"),
                           "campaignName": row.get("campaignName"),
                           "adGroupName": row.get("adGroupName"),
                           "acc": Acc()})
        out[k]["acc"].add(row)
    return out


# ---------- 判定 ----------

def trend_label(w1, w2):
    """最近 30 天 vs 之前 30 天的转化趋势。"""
    if not w2.present:
        return "无对比期"
    if w1.orders > 0 and w2.orders == 0:
        return "转化改善"
    if w1.orders == 0 and w2.orders > 0:
        return "转化中断"
    if w1.orders > 0 and w2.orders > 0:
        a1, a2 = w1.acos, w2.acos
        if a1 is not None and a2 is not None:
            if a1 < a2 * 0.8:
                return "ACOS 改善"
            if a1 > a2 * 1.25:
                return "ACOS 恶化"
        return "持平"
    # 两期都无单
    if w1.clicks > w2.clicks * 1.3:
        return "花费扩张仍无转化"
    if w1.clicks < w2.clicks * 0.7:
        return "花费收缩仍无转化"
    return "持续无转化"


def decide(term, w1, w2, w3, cfg):
    """返回 (code, label, reason, confidence)"""
    c30 = w1
    c60 = w1.merge(w2)
    c90 = c60.merge(w3)
    present_windows = [n for n, a in (("30d", w1), ("31-60d", w2), ("61-90d", w3)) if a.present]

    # 品牌 / 核心词保护最高优先
    nt = norm(term)
    for p in cfg.protected:
        pn = norm(p)
        if pn and (nt == pn or nt.startswith(pn + " ") or (" " + pn + " ") in (" " + nt + " ")):
            return ("PROTECTED", "建议保留（保护词）",
                    f"命中保护清单「{p}」，即使 30 天表现差也不自动否", "high")

    trig_zero = (c30.orders == 0 and c30.clicks >= cfg.min_clicks and c30.spend >= cfg.min_spend)
    trig_acos = (c30.orders > 0 and c30.acos is not None
                 and c30.acos > cfg.target_acos * cfg.acos_tolerance)
    triggered = trig_zero or trig_acos

    if not triggered:
        # 30 天没触发，但长周期累计很差 → 说明近期在改善，标记观察而不是否
        if c90.orders == 0 and c90.clicks >= cfg.min_clicks_90 and c90.spend >= cfg.min_spend_90:
            return ("WATCH", "建议观察（近期改善）",
                    f"30 天未触发，但 90 天累计零转化且花费 {c90.spend:.2f}；"
                    f"近期表现已好转，暂不否", "medium")
        return ("NOT_TRIGGERED", "未触发", "30 天未达到否词阈值", "high")

    # 30 天触发，进入长窗口验证
    if len(present_windows) == 1 and present_windows[0] == "30d":
        return ("NEW_TERM", "建议观察（新词）",
                f"仅最近 30 天有数据，60/90 天无记录，无法证明长期无效；"
                f"30 天 {c30.clicks:.0f} 点击 / {c30.spend:.2f} 花费 / {c30.orders:.0f} 单", "low")

    if c90.orders > 0:
        a90 = c90.acos
        if a90 is not None and a90 <= cfg.target_acos:
            return ("KEEP", "建议保留（长期达标）",
                    f"90 天累计 {c90.orders:.0f} 单、ACOS {a90:.1f}% 达标，"
                    f"30 天只是短期波动", "high")
        if a90 is not None and a90 <= cfg.target_acos * cfg.acos_tolerance:
            return ("WATCH", "建议观察（长期略超标）",
                    f"90 天累计 {c90.orders:.0f} 单、ACOS {a90:.1f}%，"
                    f"未超容忍线 {cfg.target_acos * cfg.acos_tolerance:.0f}%，"
                    f"有转化不宜否", "medium")
        return ("WATCH", "建议观察（长期超标但有转化）",
                f"90 天累计 {c90.orders:.0f} 单但 ACOS {a90:.1f}% 明显超标；"
                f"建议先降 bid 而非否词", "medium")

    # 90 天累计零订单
    if c90.clicks >= cfg.min_clicks_90 and c90.spend >= cfg.min_spend_90:
        extra = ""
        if c30.orders == 0 and c60.orders == 0:
            extra = "；60 天窗口同样零转化"
        return ("ADD", "建议添加（长期验证）",
                f"30/60/90 天累计 {c90.clicks:.0f} 点击、{c90.spend:.2f} 花费、"
                f"{c90.orders:.0f} 单{extra}", "high")

    return ("WATCH", "建议观察（长期样本不足）",
            f"90 天累计仅 {c90.clicks:.0f} 点击 / {c90.spend:.2f} 花费，"
            f"未达 90 天阈值（{cfg.min_clicks_90} 点击 / {cfg.min_spend_90} 花费）", "low")


# ---------- 主流程 ----------

def fmt(v, nd=2):
    return "—" if v is None else f"{v:.{nd}f}"


def as_pct(v, nd=1):
    return "—" if v is None else f"{v:.{nd}f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w30", required=True, help="最近 30 天数据")
    ap.add_argument("--w60", required=True, help="第 31~60 天数据")
    ap.add_argument("--w90", required=True, help="第 61~90 天数据")
    ap.add_argument("--key", choices=["auto", "query"], default="auto",
                    help="auto=按 搜索词+广告组 归集；query=只按搜索词归集")
    ap.add_argument("--min-clicks", type=float, default=10)
    ap.add_argument("--min-spend", type=float, default=15)
    ap.add_argument("--target-acos", type=float, default=40)
    ap.add_argument("--acos-tolerance", type=float, default=2.0)
    ap.add_argument("--min-clicks-90", type=float, default=None,
                    help="90 天窗口最低点击，缺省 = min-clicks × 3")
    ap.add_argument("--min-spend-90", type=float, default=None,
                    help="90 天窗口最低花费，缺省 = min-spend × 3")
    ap.add_argument("--protected", nargs="*", default=[], help="品牌 / 核心词保护清单")
    ap.add_argument("--only-triggered", action="store_true",
                    help="只输出 30 天触发了的搜索词")
    ap.add_argument("--out-json", default="verify.json")
    ap.add_argument("--report", default="verify.md")
    args = ap.parse_args()

    if args.min_clicks_90 is None:
        args.min_clicks_90 = args.min_clicks * 3
    if args.min_spend_90 is None:
        args.min_spend_90 = args.min_spend * 3

    key_mode = "query" if args.key == "query" else "auto"
    w1map, w2map, w3map = build(args.w30, key_mode), build(args.w60, key_mode), build(args.w90, key_mode)

    keys = list(w1map.keys())
    if key_mode != "query":
        # 只验证最近 30 天出现过的词；长窗口独有的词不进入候选
        keys = list(w1map.keys())

    results = []
    for k in keys:
        meta = w1map[k]
        w1 = meta["acc"]
        w2 = w2map[k]["acc"] if k in w2map else Acc()
        w3 = w3map[k]["acc"] if k in w3map else Acc()
        code, label, reason, conf = decide(meta["term"], w1, w2, w3, args)
        c60, c90 = w1.merge(w2), w1.merge(w2).merge(w3)
        trig30 = (w1.orders == 0 and w1.clicks >= args.min_clicks and w1.spend >= args.min_spend) or \
                 (w1.orders > 0 and w1.acos is not None and w1.acos > args.target_acos * args.acos_tolerance)
        results.append({
            "term": meta["term"],
            "adGroupId": meta.get("adGroupId"),
            "campaignId": meta.get("campaignId"),
            "campaignName": meta.get("campaignName"),
            "adGroupName": meta.get("adGroupName"),
            "verdict": code, "label": label, "reason": reason, "confidence": conf,
            "triggered_30d": trig30,
            "windows_present": [n for n, a in (("30d", w1), ("31-60d", w2), ("61-90d", w3)) if a.present],
            "trend": trend_label(w1, w2),
            "w30": {"clicks": w1.clicks, "spend": w1.spend, "orders": w1.orders,
                    "sales": w1.sales, "acos": w1.acos},
            "w60": {"clicks": c60.clicks, "spend": c60.spend, "orders": c60.orders,
                    "sales": c60.sales, "acos": c60.acos},
            "w90": {"clicks": c90.clicks, "spend": c90.spend, "orders": c90.orders,
                    "sales": c90.sales, "acos": c90.acos},
            "prev30": {"clicks": w2.clicks, "spend": w2.spend, "orders": w2.orders,
                       "sales": w2.sales, "acos": w2.acos},
        })

    order = {"ADD": 0, "WATCH": 1, "KEEP": 2, "PROTECTED": 3, "NEW_TERM": 4, "NOT_TRIGGERED": 5}
    results.sort(key=lambda r: (order.get(r["verdict"], 9), -r["w30"]["spend"]))

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump({"config": vars(args), "results": results}, f, ensure_ascii=False, indent=2)

    # ---- 报告 ----
    total30 = sum(r["w30"]["spend"] for r in results)
    groups = OrderedDict()
    for r in results:
        groups.setdefault(r["verdict"], []).append(r)

    L = []
    L.append("# 30 / 60 / 90 天递进验证报告\n")
    L.append(f"- 规则：30 天窗口 {args.min_clicks:.0f} 点击 / {args.min_spend:.2f} 花费；"
             f"目标 ACOS {args.target_acos:.0f}%、容忍 {args.acos_tolerance:.1f} 倍")
    L.append(f"- 90 天窗口门槛：{args.min_clicks_90:.0f} 点击 / {args.min_spend_90:.2f} 花费")
    L.append(f"- 归集方式：{'搜索词' if key_mode == 'query' else '搜索词 + 广告组'}")
    L.append(f"- 最近 30 天有记录的搜索词：{len(results)} 条，花费合计 {total30:.2f}\n")

    L.append("## 结论汇总\n")
    L.append("| 判定 | 条数 | 30 天花费 | 占最近 30 天花费 |")
    L.append("|---|---|---|---|")
    for code, label in (("ADD", "建议添加"), ("WATCH", "建议观察"), ("KEEP", "建议保留"),
                        ("PROTECTED", "保护词"), ("NEW_TERM", "新词/样本不足"),
                        ("NOT_TRIGGERED", "未触发")):
        rows = groups.get(code, [])
        if not rows:
            continue
        sp = sum(r["w30"]["spend"] for r in rows)
        pct = f"{sp / total30 * 100:.1f}%" if total30 else "—"
        L.append(f"| {label} | {len(rows)} | {sp:.2f} | {pct} |")
    L.append("")

    show = [r for r in results if (r["verdict"] != "NOT_TRIGGERED" or not args.only_triggered)]

    L.append("## 明细\n")
    L.append("| 搜索词 | 判定 | 趋势 | 30天 点击/花费/单/ACOS | 60天 单/ACOS | 90天 单/ACOS | 依据 |")
    L.append("|---|---|---|---|---|---|---|")
    for r in show:
        L.append(
            f"| {r['term']} | {r['label']} | {r['trend']} | "
            f"{r['w30']['clicks']:.0f} / {r['w30']['spend']:.2f} / {r['w30']['orders']:.0f} / "
            f"{as_pct(r['w30']['acos'])} | "
            f"{r['w60']['orders']:.0f} / {as_pct(r['w60']['acos'])} | "
            f"{r['w90']['orders']:.0f} / {as_pct(r['w90']['acos'])} | {r['reason']} |"
        )
    L.append("")

    add = groups.get("ADD", [])
    if add:
        L.append("## 建议添加（已通过 60/90 天验证）\n")
        for r in add:
            L.append(f"- **{r['term']}** — 90 天累计 {r['w90']['clicks']:.0f} 点击 / "
                     f"{r['w90']['spend']:.2f} 花费 / 0 单；30 天可节省 {r['w30']['spend']:.2f}")
        L.append("")

    saved = [r for r in results if r["triggered_30d"] and r["verdict"] in ("KEEP", "WATCH", "NEW_TERM", "PROTECTED")]
    if saved:
        L.append("## 被长窗口验证拦下的词（只看 30 天会误否）\n")
        for r in saved[:20]:
            L.append(f"- {r['term']} — {r['label']}；{r['reason']}")
        if len(saved) > 20:
            L.append(f"- 其余 {len(saved) - 20} 条见 {args.out_json}")
        L.append("")

    report = "\n".join(L)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
