# Mode B — concise POP and common-issue review

Produce only the Markdown review after a validated Excel audit exists. Do not re-fetch source data, repeat matching/scoring, or regenerate the recommendation cells.

## Source and scope

Use the latest same-customer/same-period workbook as the source of truth:

- `广告活动` for population, metrics, ratings, and managed settings.
- `评级为差的广告活动` for poor groups and their final shared recommendations.
- `AI成功标准` only to state the rating scope briefly.

Exclude `不纳入评级`, `#VALUE!`, and other out-of-scope labels from rating shares and issue denominators. Use weighted totals and ratios; never average campaign-level ACOS/CPC/CTR/CVR.

Account-wide comparison is optional. Include it only when the user supplied account data and requested that comparison.

## Required structure

Keep the document short and avoid repeating the Excel rows.

### 一、核心结论与统计口径

In one compact section, state the report period, eligible/excluded populations, rating standard source, and three or four evidence-backed conclusions.

### 二、POP表现复盘

Include:

- Overall managed spend, sales, orders, and ACOS/ROAS with period movement.
- Each customer-defined rating level separately, with count/share and the most useful exposure metric.
- At most one additional breakdown by managed duration or objective, only when it materially explains the result.

Do not add creator/store breakdowns, multiple redundant pivots, or a long methodology section.

### 三、AI托管共性问题及解决方案

Select only the three to five highest-value issues, ranked by affected spend, sales loss, or execution risk. For each issue, use four compact parts:

1. scale and denominator;
2. diagnosis logic;
3. one or two named examples;
4. the same executable group-level solution used in Sheet 3.

Do not reproduce every poor campaign or include a generic checklist.

### 四、正向案例与可复用做法

Use two or three meaningful strong cases with sufficient spend/orders and valid comparison data. State the group, objective/persona/target, result, why the setting is reasonable, and the boundary for reuse. Do not imply causation from correlation.

### 五、执行优先级

Give three ranked actions:

- immediate high-impact poor groups;
- settings/structure changes that can be applied in batches by original group;
- strong groups eligible for continued observation or controlled expansion.

## What to omit

- Full account comparison unless explicitly requested.
- Long generic AI-setting principles already expressed in the recommendations.
- Separate chapters for every objective, duration band, creator, site, or store.
- Repeated campaign-level data, full action-space matrices, and recommendations copied verbatim for every row.
- More than five common issues or more than three strong cases unless the user asks.

## Consistency checks

- Rating counts sum to the eligible population.
- Poor groups/cases exist in Sheet 3.
- Named solutions match the one shared recommendation for that original group.
- Strong cases are eligible and not selected solely for trivial spend or a loose target.
- Every statistic recomputes from the workbook.

Name the file `{客户名}_AI托管表现及托管组设置优化建议_{YYYYMMDD}-{YYYYMMDD}.md` and stop after delivery.
