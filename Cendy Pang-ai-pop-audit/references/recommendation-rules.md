# Group-level recommendation rules

Use only in Mode A and only for managed groups containing campaigns rated `差`.

## Fast protocol

1. Aggregate poor rows by original managed-group ID with current/comparison spend, sales, orders, CPC, CVR, actual ACOS/ROAS, target, objective, persona, member-campaign dispersion, budget state, and action space.
2. Create one compact fact record per poor group. Do not send all campaign rows or unused export fields into recommendation generation.
3. Generate one recommendation per group, then mechanically join it to Sheet 3. Never generate advice in a campaign-row loop.
4. Validate that each original group has one recommendation hash/value.

## Diagnose in this order

1. Objective fit with lifecycle/business intent.
2. Target fit with recent achievable efficiency and profit limits when supplied.
3. Group composition and actual-efficiency dispersion.
4. Persona fit with conversion reliability and cost risk.
5. Only the action-space controls relevant to the diagnosed problem.
6. Data sufficiency under the customer’s standard.

Do not diagnose from ACOS alone. Use spend concentration, orders/sales, CPC/CVR, duration, budget status, and group dispersion.

## Core decisions

- `推动增长`: suitable for new/seasonal products or any explicit growth task. Poor performance alone does not make the objective wrong.
- `活动冲量`: suitable for a defined promotion window; include rollback timing.
- `保持订单稳定`: suitable for mature/off-season products or stable-order/cost-control phases.
- Keep the existing target/persona when performance is near target and the business task is being met.
- If different strategy, lifecycle, targeting function, or persistent actual-ACOS bands make one target unsuitable, recommend a split. Do not split merely because a group has several campaigns.

## Action space

Action spaces are functional controls, not a completeness checklist.

- Growth/exploration: use relevant bid optimization, harvesting, negatives, and conditional budget expansion. Expand budget only near target or with explicit cost tolerance.
- Stable/cost control: prioritize performance bidding, negatives, and pausing persistent low-efficiency targets; hold budget expansion until efficiency recovers.
- Exact core/brand defense: harvesting may be unnecessary; protect critical terms with a do-not-negate list.
- Low-data campaigns: avoid aggressive structural pauses without sufficient evidence.
- Do not recommend opening a closed action unless it directly addresses the diagnosed constraint.

## Keep or split

For each poor group choose one path:

- **Keep:** state the problem, target/objective/persona decision, only necessary action changes, budget treatment, and review trigger.
- **Split:** state deterministic membership rules plus objective, target, persona, action changes, budget treatment, and review trigger for every proposed group. The full split plan is one shared recommendation value for the original group.

## Compact writing format

Normally use four short parts:

1. `问题解析：` measurable mismatch and likely driver.
2. `托管组处理：` keep or split, with membership rule if split.
3. `建议设置：` exact objective, target/range, persona, necessary actions, and budget treatment.
4. `观察标准：` review window and pass/fail trigger.

Avoid `持续优化`, `适当调整`, or `建议多开行动空间`. Do not manufacture advice for a reasonable setting.
