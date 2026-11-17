#!/usr/bin/env python3
"""AI 与非AI 广告数据拆分（按广告活动×日 / 按推广商品×日 两种口径）。

自包含：直连 SparkX 数据服务取数，明细写入文件，屏幕上只给汇总与自检结论。

用法示例
  python3 scripts/ai_split.py --token-env SPARKX_AI_TOKEN_X --start 2026-10-16 --end 2026-11-14
  python3 scripts/ai_split.py --token <PAT> --calibers campaign --profile-ids 123,456 --out ./out
参数
  --token-env NAME   从该环境变量或 ~/.zshrc 读取 PAT（单引号赋值会被剥掉引号）
  --token PAT        直接给 token（优先级高于 --token-env）
  --endpoint URL     默认 https://mcp.sparkx.cn/mcp
  --start/--end      YYYY-MM-DD，含端点，跨度上限 90 天
  --profile-ids      逗号分隔，默认取该 token 全部授权店
  --calibers         both(默认) / campaign / product
  --out              输出目录，默认 ./ai_split_out
  --resume           已缓存的店铺跳过（默认开启）

判定规则：某活动当天有 AI 花费 ⇒ 该活动当天全部数据算 AI；商品当天所在活动算 AI 则整行跟随；
品牌广告不按商品拆分 ⇒ 其全部指标计入「未归属」。
"""
import argparse
import json
import os
import re
import sys
import time
import http.client
import urllib.request
from collections import defaultdict

ENDPOINT_DEFAULT = "https://mcp.sparkx.cn/mcp"
PAGE = 500
BASE_M = ["Spend", "Impressions", "Clicks", "Sales", "Conversions", "Units",
          "SalesSameSKU", "UnitsSameSKU", "SalesOtherSKU"]
RATIO = {"CPC": ("Spend", "Clicks", 1.0), "CTR%": ("Clicks", "Impressions", 100.0),
         "CVR%": ("Conversions", "Clicks", 100.0), "ACOS%": ("Spend", "Sales", 100.0),
         "ROAS": ("Sales", "Spend", 1.0)}
TOG = ("turn on managed group ai", "turn off managed group ai")
TYPE_CN = {"sponsoredProducts": "商品广告", "sponsoredBrands": "品牌广告", "sponsoredDisplay": "展示广告"}


def tcn(t):
    return TYPE_CN.get(t, t or "")


class Api:
    def __init__(self, endpoint, token):
        self.endpoint, self.token = endpoint, token
        self.sid = None

    def _post(self, payload):
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "Authorization": "Bearer " + self.token}
        if self.sid:
            headers["mcp-session-id"] = self.sid
        req = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST")
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    body = resp.read().decode("utf-8", "replace")
                    self.sid = resp.headers.get("mcp-session-id") or self.sid
            except urllib.error.HTTPError as e:
                # 307/308/429/5xx 与网关抖动一律重试；urllib 默认不跟随 POST 重定向
                if e.code in (307, 308, 429, 500, 502, 503, 504) and attempt < 5:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise
            except (http.client.HTTPException, OSError) as e:
                # 传输中断、连接重置、超时：同一请求指数退避重试，不让整轮取数失败
                if attempt < 4:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise RuntimeError("网络连续 5 次失败（%s），请稍后重跑，已完成的店铺会自动跳过" % e)
            if body.lstrip().startswith("event:") or "\ndata: " in body:
                objs = []
                for line in body.splitlines():
                    if line.startswith("data:") and line[5:].strip():
                        try:
                            objs.append(json.loads(line[5:].strip()))
                        except json.JSONDecodeError:
                            pass
                return objs[-1] if objs else None
            return json.loads(body) if body.strip() else None
        raise RuntimeError("retry exhausted")

    def connect(self):
        self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "ai-split", "version": "1.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, )

    def tool(self, name, args):
        res = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": name, "arguments": args}})
        if "error" in (res or {}):
            raise RuntimeError("%s: %s" % (name, res["error"]))
        txt = res["result"]["content"][0]["text"]
        out = json.loads(txt)
        if out.get("isError"):
            raise RuntimeError("%s: %s" % (name, str(out.get("message"))[:200]))
        return out.get("data") or {}

    def paged(self, tool, args, key="rows", max_pages=10000):
        args = dict(args, pageSize=PAGE)
        rows, page = [], 1
        while page <= max_pages:
            data = self.tool(tool, dict(args, page=page))
            got = data.get(key) or []
            rows.extend(got)
            if len(got) < PAGE:
                return rows, page
            page += 1
        raise RuntimeError("超过 %d 页，需拆窗口" % max_pages)


def read_token(env_name=None, direct=None):
    if direct:
        return direct.strip()
    if not env_name:
        raise SystemExit("需要 --token 或 --token-env")
    if os.environ.get(env_name):
        return os.environ[env_name].strip()
    path = os.path.expanduser("~/.zshrc")
    if os.path.exists(path):
        m = re.search(r"export\s+%s=['\"]?([^'\"\n]+)['\"]?" % re.escape(env_name),
                      open(path, encoding="utf-8", errors="ignore").read())
        if m:
            return m.group(1).strip()
    raise SystemExit("找不到 %s 的 token" % env_name)


def day_key(d):
    return d if isinstance(d, str) and len(d) == 8 and d.isdigit() else d.replace("-", "")[:8]


def ratios(sums):
    out = {}
    for r, (num, den, mul) in RATIO.items():
        den_v = sums.get(den, 0.0)
        out[r] = round(mul * sums.get(num, 0.0) / den_v, 4) if den_v else None
    return out


def dedup(rows):
    seen, uniq = set(), []
    for r in rows:
        t = tuple(sorted((k, str(v)) for k, v in r.items() if k not in ("campaignTypeText", "campaignStateText")))
        if t in seen:
            continue
        seen.add(t)
        uniq.append(r)
    return uniq, len(rows) - len(uniq)


def pull_campaign(api, pid, d0, d1):
    """活动×日：确定性排序 + 引擎聚合校验。"""
    rows, pages = api.paged("get_ads_perf", dict(
        profileIds=[pid], factEntity="campaign", dateStart=d0, dateEnd=d1,
        metrics=BASE_M + ["AISpend", "AISales"],
        select=["date", "campaign.campaignId_", "campaign.campaignName_", "campaign.campaignType_",
                "campaign.campaignState_", "campaign.aiGroupId_", "profile.profileId_"],
        orderBy=[{"field": "date", "direction": "ASC"}, {"field": "campaign.campaignId_", "direction": "ASC"}],
        userContext="AI非AI拆分-活动口径"))
    uniq, dup = dedup(rows)
    eng = (api.tool("get_ads_perf", dict(profileIds=[pid], factEntity="campaign", dateStart=d0, dateEnd=d1,
                                         metrics=["Spend", "AISpend"], select=["profile.profileId_"],
                                         pageSize=10, userContext="AI非AI拆分-完整性校验")).get("rows") or [{}])[0]
    return uniq, dup, rows, eng


def pull_product(api, pid, d0, d1):
    rows, pages = api.paged("get_ads_perf", dict(
        profileIds=[pid], factEntity="productAd", dateStart=d0, dateEnd=d1,
        metrics=BASE_M,
        select=["date", "productAd.asin_", "productAd.adGroupId_", "campaign.campaignId_",
                "campaign.campaignType_", "asin.asinTitle_", "profile.profileId_"],
        orderBy=[{"field": "date", "direction": "ASC"}, {"field": "campaign.campaignId_", "direction": "ASC"},
                 {"field": "productAd.asin_", "direction": "ASC"}],
        userContext="AI非AI拆分-商品口径"))
    uniq, dup = dedup(rows)
    return uniq, dup, rows


def sums(rows, group_field=None):
    agg = defaultdict(lambda: defaultdict(float))
    for r in rows:
        g = "ALL" if group_field is None else r.get(group_field) or "?"
        s = agg[g]
        for m in BASE_M + ["AISpend", "AISales"]:
            s[m] += r.get(m) or 0.0
        s["n"] += 1
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-env")
    ap.add_argument("--token")
    ap.add_argument("--endpoint", default=ENDPOINT_DEFAULT)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--profile-ids")
    ap.add_argument("--calibers", default="both", choices=["both", "campaign", "product"])
    ap.add_argument("--out", default="ai_split_out")
    a = ap.parse_args()

    d0, d1 = a.start, a.end
    span = (time.mktime(time.strptime(d1, "%Y-%m-%d")) - time.mktime(time.strptime(d0, "%Y-%m-%d"))) // 86400 + 1
    if span > 90:
        raise SystemExit("窗口 %d 天，超过 get_ads_perf 的 90 天硬上限，请拆成多个不重叠窗口分别跑" % span)
    os.makedirs(a.out, exist_ok=True)

    api = Api(a.endpoint, read_token(a.token_env, a.token))
    api.connect()
    ctx = api.tool("get_user_authorized_context", {})
    profs = ctx.get("profiles") or []
    want = {int(x) for x in a.profile_ids.split(",")} if a.profile_ids else None
    sel = [p for p in profs if (want is None or p["profileId"] in want)]
    nm = {str(p["profileId"]): "%s %s" % (p["profileName"], p["countryCode"]) for p in profs}
    print("已连接账户：授权店铺 %d 家，本次覆盖 %d 家 / 区间 %s~%s 共 %d 天" % (
        len(profs), len(sel), d0, d1, span))

    camp, prod, checks = {}, {}, []
    for p in sel:
        pid = str(p["profileId"])
        cf = os.path.join(a.out, "campaign_%s.json" % pid)
        pf = os.path.join(a.out, "product_%s.json" % pid)
        try:
            if os.path.exists(cf):
                camp[pid] = json.load(open(cf))
            else:
                uniq, dup, raw, eng = pull_campaign(api, p["profileId"], d0, d1)
                rs = sum(r.get("Spend") or 0 for r in uniq)
                es = eng.get("Spend") or 0.0
                ok = dup == 0 and abs(rs - es) <= max(1.0, 0.005 * es)
                checks.append(["活动口径 %s" % nm[pid], "重复 %d 行 / 取到 %.0f / 平台汇总 %.0f" % (dup, rs, es),
                               "通过" if ok else "不通过"])
                if not ok:
                    print("  ! 跳过 %s：取数完整性校验未通过（重复 %d 行，%.0f vs 平台 %.0f）" % (nm[pid], dup, rs, es))
                    continue
                camp[pid] = uniq
                json.dump(uniq, open(cf, "w"), ensure_ascii=False)
            if a.calibers in ("both", "product") and not os.path.exists(pf):
                u2, d2, _ = pull_product(api, p["profileId"], d0, d1)
                cs = sum((r.get("Spend") or 0) for r in camp[pid])
                ps = sum((r.get("Spend") or 0) for r in u2)
                ok2 = (d2 / len(u2) if u2 else 0) <= 0.005 and ps <= cs * 1.005 + 1
                checks.append(["商品口径 %s" % nm[pid], "重复 %d 行 / 商品层 %.0f / 活动层 %.0f" % (d2, ps, cs),
                               "通过" if ok2 else "不通过"])
                if ok2:
                    prod[pid] = u2
                    json.dump(u2, open(pf, "w"), ensure_ascii=False)
                else:
                    print("  ! %s 商品口径校验未通过（重复 %d 行，%.0f vs %.0f）" % (nm[pid], d2, ps, cs))
            elif a.calibers in ("both", "product"):
                prod[pid] = json.load(open(pf))
        except Exception as e:  # 单店失败不终止整轮，其余店铺继续
            checks.append(["店铺 %s" % nm[pid], str(e)[:120], "未完成"])
            print("  ! %s 本轮未完成：%s（可重跑，已完成的店铺会跳过）" % (nm[pid], str(e)[:90]))
            continue

    # 口径 A
    ai_cd = {(p, day_key(r["date"]), r["campaignId"]) for p, rows in camp.items() for r in rows
             if (r.get("AISpend") or 0) > 0}
    gA = defaultdict(lambda: defaultdict(float))
    dayA = defaultdict(lambda: defaultdict(float))
    for p, rows in camp.items():
        for r in rows:
            g = "AI" if (r.get("AISpend") or 0) > 0 else "非AI"
            for m in BASE_M + ["AISpend"]:
                gA[g][m] += r.get(m) or 0.0
            gA[g]["n"] += 1
            k = (p, day_key(r["date"]))
            dayA[k][g] += r.get("Spend") or 0.0
            dayA[k]["Spend"] += r.get("Spend") or 0.0
            dayA[k]["AISpend"] += r.get("AISpend") or 0.0
    ai_spend_field = sum(r.get("AISpend") or 0 for rows in camp.values() for r in rows)

    # 口径 B：整行继承；未归属 = 活动层 − 商品层 的残差（SB 在商品层无行，不能靠打标）
    gB = defaultdict(lambda: defaultdict(float))
    unatt = defaultdict(lambda: defaultdict(float))
    unatt_type = defaultdict(float)
    psum = defaultdict(lambda: defaultdict(float))
    for p, rows in prod.items():
        for r in rows:
            g = "AI" if (p, day_key(r["date"]), r["campaignId"]) in ai_cd else "非AI"
            for m in BASE_M:
                gB[g][m] += r.get(m) or 0.0
            gB[g]["n"] += 1
            k = (p, day_key(r["date"]), r["campaignId"])
            for m in BASE_M:
                psum[k][m] += r.get(m) or 0.0
    for p, rows in camp.items():
        for r in rows:
            if (r.get("Spend") or 0) <= 0 and (r.get("Impressions") or 0) <= 0:
                continue
            g = "AI" if (r.get("AISpend") or 0) > 0 else "非AI"
            k = (p, day_key(r["date"]), r["campaignId"])
            for m in BASE_M:
                d = (r.get(m) or 0.0) - psum[k][m]
                if d > 0:
                    unatt[g][m] += d
                    if m == "Spend":
                        unatt_type[(g, r.get("campaignType") or "?")] += d
    mix = defaultdict(lambda: [0.0, 0.0])
    for p, rows in prod.items():
        for r in rows:
            if (r.get("campaignType") or "") == "sponsoredBrands":
                continue
            g = "AI" if (p, day_key(r["date"]), r["campaignId"]) in ai_cd else "非AI"
            if (r.get("Spend") or 0) > 0:
                k = (p, day_key(r["date"]), r["asin"])
                mix[k][0 if g == "AI" else 1] += r.get("Spend") or 0.0

    tiers = defaultdict(int)
    for (p, d, asin), (ai, non) in mix.items():
        tot = ai + non
        share = ai / tot if tot else 0
        if ai > 0 and non == 0:
            tiers["纯AI"] += 1
        elif non > 0 and ai == 0:
            tiers["纯非AI"] += 1
        elif share >= 0.8:
            tiers["以AI为主(>=80%)"] += 1
        elif share >= 0.2:
            tiers["混合(20-80%)"] += 1
        else:
            tiers["以非AI为主(<20%)"] += 1

    acct = (api.tool("get_ads_perf", dict(profileIds=[p["profileId"] for p in sel], factEntity="campaign",
                                          dateStart=d0, dateEnd=d1, metrics=["Spend", "AISpend", "Sales", "AISales"],
                                          select=["profile.profileId_"], pageSize=500,
                                          userContext="AI非AI拆分-账户级汇总")).get("rows") or [])
    us_s = sum(r.get("Spend") or 0 for r in acct)
    us_a = sum(r.get("AISpend") or 0 for r in acct)

    print("\n=== 活动口径 AI 与 非AI（金额为各店铺当地币种；跨店金额请看下方账户级汇总）===")
    print("%-6s %12s %10s %9s %12s %8s %8s %7s %7s %7s" % ("组", "花费", "曝光", "点击", "销售", "订单", "CPC", "CTR%", "CVR%", "ACOS%"))
    for g in ("AI", "非AI"):
        s = gA[g]
        r = ratios(s)
        print("%-6s %12.0f %10.0f %9.0f %12.0f %8.0f %8.2f %7.2f %7.2f %7.1f" % (
            g, s["Spend"], s["Impressions"], s["Clicks"], s["Sales"], s["Conversions"],
            r["CPC"] or 0, r["CTR%"] or 0, r["CVR%"] or 0, r["ACOS%"] or 0))
    print("\n=== 商品口径 AI / 非AI / 未归属 ===")
    for g in ("AI", "非AI"):
        s = gB[g]
        r = ratios(s)
        print("%-16s 花费 %10.0f 曝光 %10.0f 点击 %9.0f 销售 %11.0f 订单 %7.0f 本品销售 %11.0f CPC %5.2f CTR %5.2f%% ACOS %5.1f%%" % (
            g, s["Spend"], s["Impressions"], s["Clicks"], s["Sales"], s["Conversions"], s["SalesSameSKU"],
            r["CPC"] or 0, r["CTR%"] or 0, r["ACOS%"] or 0))
    for g in ("AI", "非AI"):
        s = unatt[g]
        if s["Spend"] or s["Impressions"]:
            print("%-16s 花费 %10.0f 曝光 %10.0f 点击 %9.0f 销售 %11.0f 订单 %7.0f" % (
                "未归属·" + g, s["Spend"], s["Impressions"], s["Clicks"], s["Sales"], s["Conversions"]))
    if unatt_type:
        print("   未归属构成：", ", ".join("%s/%s %.0f" % (g, tcn(t), v) for (g, t), v in
                                          sorted(unatt_type.items(), key=lambda x: -x[1])[:5]))
    print("\n=== 商品当天 AI 花费份额分档 ===")
    tot_mix = sum(tiers.values())
    for k, v in sorted(tiers.items(), key=lambda x: -x[1]):
        print("   %-18s %6d  %5.1f%%" % (k, v, 100.0 * v / tot_mix if tot_mix else 0))
    print("\n=== 账户级汇总（统一折算，跨店铺可比）===")
    print("   花费 %.0f  AI花费 %.0f  AI占比 %.1f%%" % (us_s, us_a, 100.0 * us_a / us_s if us_s else 0))
    print("\n=== 四项自检 ===")
    print("   自检2 AI组花费合计 %.0f vs 平台记录的 AI 花费 %.0f → 差 %.3f%%" % (
        gA["AI"]["Spend"], ai_spend_field,
        100.0 * (gA["AI"]["Spend"] - ai_spend_field) / ai_spend_field if ai_spend_field else 0))
    totA = gA["AI"]["Spend"] + gA["非AI"]["Spend"]
    totB = sum(gB[g]["Spend"] for g in ("AI", "非AI")) + sum(unatt[g]["Spend"] for g in ("AI", "非AI"))
    print("   自检3 口径对平：活动口径 %.0f vs 商品口径+未归属 %.0f → 差 %.3f%%" % (totA, totB, 100.0 * (totA - totB) / totA if totA else 0))
    bad = [c for c in checks if c[2] == "不过"]
    print("   自检1 逐店取数完整性：检查 %d 项，未通过 %d 项%s" % (
        len(checks), len(bad), ("：" + "; ".join(c[0] for c in bad[:5])) if bad else "（全部通过）"))

    # 明细导出（CSV；有 openpyxl 则再出一份 xlsx）
    import csv
    with open(os.path.join(a.out, "活动口径_明细.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "store", "currency", "campaignId", "campaignName", "type", "state", "is_ai_day", "aiGroupId_current_ref"] + BASE_M)
        for p, rows in camp.items():
            for r in rows:
                w.writerow([r["date"], nm[p], next(x["currencyCode"] for x in profs if str(x["profileId"]) == p),
                            r["campaignId"], r.get("campaignName"), tcn(r.get("campaignType")), r.get("campaignState"),
                            1 if (r.get("AISpend") or 0) > 0 else 0, r.get("aiGroupId")] + [r.get(m) for m in BASE_M])
    with open(os.path.join(a.out, "商品口径_明细.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "store", "asin", "asinTitle", "campaignId", "type", "adGroupId", "ai_share_bucket"] + BASE_M)
        share = {}
        for (p, d, asin), (ai, non) in mix.items():
            t = ai / (ai + non) if (ai + non) else 0
            share[(p, d, asin)] = ("纯AI" if ai > 0 and non == 0 else "纯非AI" if non > 0 and ai == 0 else
                                   "以AI为主" if t >= 0.8 else "混合" if t >= 0.2 else "以非AI为主")
        for p, rows in prod.items():
            for r in rows:
                w.writerow([r["date"], nm[p], r["asin"], r.get("asinTitle"), r["campaignId"], tcn(r.get("campaignType")),
                            r.get("adGroupId"), share.get((p, day_key(r["date"]), r["asin"]), "")] + [r.get(m) for m in BASE_M])
    with open(os.path.join(a.out, "商品口径_未归属构成.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["分组", "活动类型", "花费"])
        for (g, t), v in sorted(unatt_type.items(), key=lambda x: -x[1]):
            w.writerow([g, tcn(t), round(v, 2)])
    json.dump({"window": [d0, d1], "caliberA": {k: dict(v) for k, v in gA.items()},
               "caliberB": {k: dict(v) for k, v in gB.items()},
               "unattributed": {k: dict(v) for k, v in unatt.items()},
               "unattributed_by_type": {"%s/%s" % (g, tcn(t)): round(v, 2) for (g, t), v in unatt_type.items()},
               "tiers": dict(tiers),
               "usd": {"spend": us_s, "ai_spend": us_a}, "checks": checks,
               "ratioA": {k: ratios(v) for k, v in gA.items()},
               "ratioB": {k: ratios(v) for k, v in gB.items()}},
              open(os.path.join(a.out, "summary.json"), "w"), ensure_ascii=False)
    print("\n明细与汇总已写入 %s/（活动口径_明细.csv、商品口径_明细.csv、商品口径_未归属构成.csv、summary.json）" % a.out)
    print("同一目录内按店铺缓存了取数结果，中途中断后重跑会自动跳过已完成的店铺；要重新取数请换 --out 目录。")


if __name__ == "__main__":
    main()
