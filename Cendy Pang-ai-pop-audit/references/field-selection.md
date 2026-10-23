# Lean output field selection

Use this reference only for Mode A.

## Selection order

1. Follow a customer-specific `要/不要` field row when the user supplies one.
2. Keep fields required to join, score, filter, or execute a recommendation even if they are not displayed. Working-only fields stay outside the visible workbook when possible.
3. Without a customer-specific field row, use the cross-client default below. It is based on the confirmed Zhio and Jiniu templates.
4. Do not append available export fields merely because they exist.

## Cross-client default exclusions

Do not fetch or display these fields by default:

- `SP站外广告策略`
- Duplicate `当前预算` when `日预算` or the managed-group budget is already present
- `订单成本(环比增长率)`
- `点击率(环比增长率)`
- `曝光量(环比增长率)`
- `点击量(环比增长率)`
- `销量(环比增长率)`
- `搜索结果顶部展示份额` current/comparison/change fields
- `推广商品订单数/销量/销售额` current/comparison/change fields
- `其他商品订单数/销量/销售额` current/comparison/change fields

These fields were marked `不要` in both templates, or were omitted by one template and marked `不要` by the other.

## Sheet 1 default shape

Keep only fields used for campaign identity, group matching, customer scoring, and practical filtering:

- Campaign identity/status: switch, ad type, campaign name/ID, delivery status, country, store/profile, targeting type, bidding strategy, start date, daily budget.
- Managed context: group name/ID, objective, target ACOS/ROAS, actual-to-target gap, persona, creator and enablement dates/duration when available.
- Core performance: current and comparison CPC, CTR, CVR, ACOS/ROAS, spend, impressions, clicks, orders/units, and sales. Keep a change field only when either the customer’s standard or one confirmed template needs it.
- Managed settings: group switch, group budget, campaign/product counts when useful, 12 action-space fields, target type/value, bid range, and campaign-name marker.
- Scoring: only the helper conditions required by the customer’s supplied standard, final score, and final rating.

Do not add document-only fields such as managed-group rating, issue category, priority, case flags, or common-problem summaries.

## Sheet 3 default shape

Sheet 3 is an execution view, not a duplicate of Sheet 1. Start from the same poor rows, then keep only:

- Campaign identification and current status.
- The current/comparison metrics or changes actually used to explain the poor rating.
- Original managed-group identity, objective, target, persona, latest enabled duration, budget/bid range, and all 12 action-space fields.
- Required scoring helpers, score, and rating.
- `AI托管建议及对应解决方案`.

Remove duplicate campaign-level copies when the same authoritative value appears in the managed-group block. By default also remove these Sheet 3 fields because both confirmed templates marked them `不要` in this context:

- Campaign-level target ACOS, ACOS gap, persona, creator, first enable time, recent enable duration, current budget, and SP offsite strategy when duplicated in the managed-group block
- CPC comparison; order-cost current/comparison/change; CTR comparison/change; CVR comparison; ACOS comparison; ROAS comparison; spend comparison; impressions comparison/change; clicks comparison/change; orders comparison; units current/comparison/change; sales comparison
- AI recent close time, label, managed-group first enable time
- Search-top-share, promoted-product, and other-product metric families

When a customer-specific template marks one of these as `要`, follow that template. Never delete a field required to understand or apply the recommendation.

## Source-query minimization

For MCP retrieval, translate the selected visible fields plus required scoring/join inputs into one campaign query and one managed-group query. Avoid exploratory wide queries. If an uploaded export contains extra columns, ignore them rather than copying them into the output.
