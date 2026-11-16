# 界面与交付

用[案例 01](../examples/case-01/task.md)复跑包内的合成数据。打开示例 HTML 的「重点关注」页可核对本期数量和默认折叠的父 ASIN 卡片，点击「大盘总览」可回到首页。

- **大盘总览**展示本期结论、大盘结果和效率、国家站点变化、品线变化与「国家站点 × 产品线」筛选。大盘卡片展示本期数值和相对环比，按业务方向显示绿、红与中性。筛选为空时提供空态，结果表末按当前可见行各期求和，并重算比率。
- **国家页**列出该站点的店铺。每行一张品线卡片，折叠态突出花费、订单、转化率、ACOS 和两期变化，展开才显示对应投放类型表。读者可以直接看到两期的绝对值和变化。
- **重点关注**用明显的数字显示入选父体总数。折叠态仅展示优先级、父 ASIN、站点、店铺、品线和一句主因。展开后展示两期花费、广告销售额、订单、CPC、CVR、客单价、ACOS，以及入选依据与后续检查方向。名单为空时正常交付大盘，说明筛选结果。
- **验证**独立 HTML 可离线打开。点击首页、国家页和 `#focus`，检查默认折叠与跳转、切换筛选和清空筛选后的总计、移动宽度与金额格式。检查对客页面无凭据、授权标识、内部备注或未替换占位符。

## 渲染输入

调用 `python scripts/render_report.py 数据.json 输出.html`。JSON 用 UTF-8，金额先转换到报告币种。对象形状如下，数组顺序即显示顺序。每个 `metrics` 都是 `[上期, 本期]`，其中一期可以是 `null`。每期对象字段 `spend, sales, clicks, orders` 为广告基础量，`totalSales` 用于 TACOS；两期 TACOS 同范围的花费与销售可另外填 `tacosSpend`（此时 `totalSales` 与该覆盖范围一致）。空字段留空或填 `null`，仅确认有完整覆盖且无量时填 0。

```json
{
  "client": "客户名称",
  "title": "10月广告复盘",
  "prior": "2026-08-31 至 09-30",
  "current": "2026-10-01 至 10-31",
  "currency": "USD",
  "conclusions": ["花费变化和主要流向", "ACOS 变化和主要指标贡献"],
  "account": [{ "spend": 1270, "sales": 4100, "clicks": 2600, "orders": 100, "totalSales": 8900 }, { "spend": 1410, "sales": 4200, "clicks": 2700, "orders": 101, "totalSales": 9100 }],
  "sites": [{
    "id": "us", "name": "美国站", "metrics": [null, null],
    "stores": [{
      "name": "示例店铺", "metrics": [null, null],
      "lines": [{
        "name": "示例品线", "metrics": [null, null],
        "types": [{ "name": "SP-精准", "metrics": [null, null] }]
      }]
    }]
  }],
  "parents": [{
    "asin": "B000000001", "site": "us", "store": "示例店铺", "line": "示例品线",
    "metrics": [{ "spend": 100, "sales": 500, "clicks": 200, "orders": 25 }, { "spend": 180, "sales": 600, "clicks": 240, "orders": 27 }],
    "headline": "增投后 CPC 上升",
    "reason": "广告花费增加 $80，广告销售额增加 $100，ACOS 从 20% 上升到 30%。",
    "next": "核对增量流量来自哪些活动、定向及广告位。"
  }],
  "focusLimit": 6,
  "notes": ["说明报表覆盖、TACOS 共同范围，以及更新日期。"]
}
```

`parents` 输入所有符合覆盖要求的已核实候选，由模板据原始数值排序。缺口或零销售大额对象可用 `focusNote` 补充。国家页 ID 用小写字母、数字和连字符，避开 `overview`、`focus`。首页品线和交叉筛选基于各店铺的品线行复算；有未分类商品时以「未标记产品线」保留可核实数据。部分覆盖的合计须附口径。
