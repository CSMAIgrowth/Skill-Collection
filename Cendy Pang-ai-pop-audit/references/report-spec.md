# Mode A — Excel audit specification

Create the execution workbook only. Do not generate the companion analysis document in this mode.

## 1. Join and population

- Keep IDs as text and metrics as typed numeric/date values.
- Join by managed-group ID; otherwise use a unique normalized group-name + store/profile key.
- Validate row counts, unmatched campaigns, duplicate group keys, and multi-group matches before scoring.
- Apply the customer’s inclusion/exclusion and missing-value rules exactly. Do not treat blanks as zero unless specified.
- Keep all in-scope managed campaigns in Sheet 1. Mark non-eligible rows `不纳入评级` and exclude them from Sheet 3.

## 2. Three sheets only

### Sheet 1: `广告活动`

One row per in-scope managed campaign. Use the lean field rules in [field-selection.md](field-selection.md):

1. Campaign identity and essential performance.
2. Managed-group identity and settings.
3. Only the helper results required by the supplied success standard.
4. Final score and rating.

Do not preserve the full source export. Do not add aggregate analysis, managed-group ratings, issue labels, priority columns, strong-case flags, or hidden analysis tabs.

### Sheet 2: `AI成功标准`

Reproduce the customer’s supplied standard without editorial processing:

- Image input: insert the image in supplied order.
- Excel input: copy the relevant cells, merged regions, and useful formatting.
- Text input: paste it with basic wrapping only.

Do not rewrite, normalize, summarize, add methodology, or create a second rule table.

### Sheet 3: `评级为差的广告活动`

Copy only rows whose final rating is exactly `差`. Use the lean execution field set in [field-selection.md](field-selection.md), then append `AI托管建议及对应解决方案`.

Create one recommendation record per distinct original managed-group ID. Generate it once and join it back to every poor row in that group. If a split is recommended, the identical recommendation contains the complete split plan.

## 3. Scoring

Translate the customer’s rule into a small number of explicit helper formulas:

1. eligibility;
2. each required scoring condition;
3. score;
4. rating mapping.

Preserve operators and thresholds exactly. Do not add helpers that are not used by the final score.

## 4. Presentation

- Follow the confirmed Zhio/Jiniu workbook hierarchy: dark campaign header, teal managed-setting header, amber score block, green recommendation column.
- Keep Chinese UI text readable, wrap long headers/advice, freeze the header and identifying columns, and enable filters on Sheets 1 and 3.
- Use typed currency, percentage, count, and date formats.
- Keep rating colors consistent and restrained.
- Do not add a dashboard, fourth sheet, or analysis block.

## 5. Validation

Before delivery, verify:

- Sheet names/order are exact.
- Join row count is unchanged and every included campaign has exactly one group.
- Scores reproduce representative boundary cases from Sheet 2.
- Sheet 3 is an exact poor subset by campaign ID.
- Every poor row has advice; every original group has one and only one recommendation value.
- Excluded default fields and unused helpers are absent.
- No formula errors, clipped headers, or unreadable advice cells remain.

Name the file `{客户名}_AI托管审核_{YYYYMMDD}-{YYYYMMDD}.xlsx` and stop after delivery.
