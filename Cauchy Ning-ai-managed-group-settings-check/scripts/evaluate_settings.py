"""Read-only settings evaluator.
Input JSON: scope, groups[{aiGroupId,targetType,targetAcos,rank,
rollupAccepted,groupDateCoverage}], members[{aiGroupId,amazonCampaignId,...}],
daily[{campaignId,date,Spend,Sales,Conversions}],
rollups[{aiGroupId,Spend,Sales,Conversions}].
rollupAccepted must be established by the authorized caller under SKILL.md.
Usage: python evaluate_settings.py input.json ; emits result JSON to stdout.
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

HIT, MISS, UNKNOWN = "命中待复核", "未命中", "无法判断"

def dec(value):
    if value is None:
        return None
    try:
        x = Decimal(str(value))
        return x if x.is_finite() and x >= 0 else None
    except Exception:
        return None

def target_rules(spend, sales, target, goal, accepted=True):
    s, v, t = dec(spend), dec(sales), dec(target)
    if not accepted or s is None or v is None or v == 0:
        return None, UNKNOWN, UNKNOWN
    a = s / v * 100
    if t is None:
        return float(a), UNKNOWN, UNKNOWN
    r2 = UNKNOWN if goal not in (1, 2, 3) else (
        HIT if (a - t > 15 if goal == 2 else a > t) else MISS)
    r3 = HIT if abs(a - t) > 25 else MISS
    return float(a), r2, r3

def r1_rule(acoses, total_members, full_members):
    if total_members == 1:
        return MISS
    xs = [Decimal(str(x)) for x in acoses]
    if len(xs) >= 2 and max(xs) - min(xs) > 10:
        return HIT
    if total_members >= 2 and full_members == total_members == len(xs):
        return MISS
    return UNKNOWN

def evaluate(src):
    daily = {}
    seen = set()
    for row in src["daily"]:
        key = (str(row["campaignId"]), row["date"])
        if key in seen:
            raise ValueError("Duplicate campaign/day: " + repr(key))
        seen.add(key)
        if any(dec(row.get(k)) is None for k in ("Spend", "Sales", "Conversions")):
            raise ValueError("Invalid campaign metrics: " + repr(key))
        daily.setdefault(key[0], []).append(row)
    campaigns = []
    for c in src["members"]:
        rs = daily.get(str(c["amazonCampaignId"]), [])
        sums = {k: sum((dec(r[k]) for r in rs), Decimal(0))
                for k in ("Spend", "Sales", "Conversions")}
        days = sorted({r["date"] for r in rs})
        a = sums["Spend"] / sums["Sales"] * 100 if sums["Sales"] > 0 else None
        campaigns.append(dict(c, days=len(days), dates=days,
            spend=float(sums["Spend"]) if rs else None,
            sales=float(sums["Sales"]) if rs else None,
            orders=float(sums["Conversions"]) if rs else None,
            acos=float(a) if a is not None else None,
            _exact_acos=a))
    rolls = {r["aiGroupId"]: r for r in src["rollups"]}
    groups = []
    for g in sorted(src["groups"], key=lambda x: x["rank"]):
        cs = [c for c in campaigns if c["aiGroupId"] == g["aiGroupId"]]
        if len(cs) != g["numCampaign"]:
            raise ValueError("Current membership count mismatch: " + str(g["aiGroupId"]))
        full = sum(c["days"] == 14 for c in cs)
        eligible = [c for c in cs if c.get("campaignState") != "paused"
                    and c["days"] > 0 and c["_exact_acos"] is not None]
        eligible_full = len(eligible)
        valid = sorted((c for c in eligible),
                       key=lambda c: c["_exact_acos"])
        r = rolls.get(g["aiGroupId"], {})
        skip_reasons = []
        if cs and all(c.get("campaignState") == "paused" for c in cs):
            skip_reasons.append("全部当前成员暂停")
        if dec(r.get("Sales")) == Decimal(0):
            skip_reasons.append("组广告归因销售额为0")
        a, r2, r3 = target_rules(r.get("Spend"), r.get("Sales"),
            g.get("targetAcos"), g.get("targetType"),
            g.get("rollupAccepted") is True)
        r1 = MISS if len(cs) == 1 else r1_rule(
            [c["_exact_acos"] for c in valid], len(eligible), eligible_full)
        if skip_reasons:
            r1 = r2 = r3 = "不执行判定"
        clean = lambda c: {k: v for k, v in c.items() if k != "_exact_acos"}
        observed_spend = sum((dec(c["spend"]) or Decimal(0) for c in cs), Decimal(0))
        observed_sales = sum((dec(c["sales"]) or Decimal(0) for c in cs), Decimal(0))
        if r and (abs(Decimal(str(r["Spend"])) - observed_spend) > Decimal("0.01")
                  or abs(Decimal(str(r["Sales"])) - observed_sales) > Decimal("0.01")):
            raise ValueError("Rollup/member totals mismatch: " + str(g["aiGroupId"]))
        groups.append(dict(g, members=len(cs), full=full,
            excluded=bool(skip_reasons), exclusion_reasons=skip_reasons,
            r1_eligible=len(eligible), r1_eligible_full=eligible_full,
            r1_excluded_paused=sum(c.get("campaignState") == "paused" for c in cs),
            r1_excluded_no_records=sum(c.get("campaignState") != "paused" and c["days"] == 0 for c in cs),
            complete=len(cs) > 0 and full == len(cs),
            partial=sum(0 < c["days"] < 14 for c in cs),
            none=sum(c["days"] == 0 for c in cs),
            spend=r.get("Spend"), sales=r.get("Sales"), orders=r.get("Conversions"),
            acos=a, range=float(valid[-1]["_exact_acos"] - valid[0]["_exact_acos"])
                if len(valid) >= 2 else None,
            low=clean(valid[0]) if valid else None,
            high=clean(valid[-1]) if valid else None,
            r1=r1, r2=r2, r3=r3,
            hit=HIT in (r1, r2, r3), unknown=UNKNOWN in (r1, r2, r3)))
    n = len(groups)
    stats = dict(scan=n, hit=sum(g["hit"] for g in groups),
        excluded=sum(g["excluded"] for g in groups),
        evaluated=sum(not g["excluded"] for g in groups),
        excluded_paused=sum("全部当前成员暂停" in g["exclusion_reasons"] for g in groups),
        excluded_zero_sales=sum("组广告归因销售额为0" in g["exclusion_reasons"] for g in groups),
        r1=sum(g["r1"] == HIT for g in groups),
        r2=sum(g["r2"] == HIT for g in groups),
        r3=sum(g["r3"] == HIT for g in groups),
        unknown=sum(g["unknown"] for g in groups),
        overlap=sum(g["hit"] and g["unknown"] for g in groups))
    return dict(scope=src["scope"], groups=groups,
                campaigns=[{k:v for k,v in c.items() if k != "_exact_acos"}
                           for c in campaigns], stats=stats)

if __name__ == "__main__":
    source = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(evaluate(source), ensure_ascii=False))

