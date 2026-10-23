---
name: sparkx-ai-pop-audit
description: "Create a SparkX AI POP audit in two independent modes: a three-sheet Excel scoring and optimization workbook when the user asks ‘给我出份AI POP报告和优化建议’, or a concise POP/common-issue review document when the user asks ‘给我分析下POP和AI托管共性问题’. Do not automatically generate both artifacts."
metadata:
  short-description: "Build lean SparkX AI POP audits in two stages"
---

# SparkX AI POP Audit

This skill has two separate, user-triggered modes. Run only the requested mode. Do not automatically continue from Excel to the analysis document.

This is an audit and recommendation workflow. Do not modify live AI managed groups unless the user separately asks to apply changes.

## Route the request

### Mode A — Excel audit

Trigger examples: `给我出份AI POP报告和优化建议`, `POP评级`, `AI托管审核`.

Output only one three-sheet Excel workbook:

1. `广告活动`
2. `AI成功标准`
3. `评级为差的广告活动`

Read [references/field-selection.md](references/field-selection.md), [references/report-spec.md](references/report-spec.md), and [references/recommendation-rules.md](references/recommendation-rules.md). Stop after delivering the workbook. Do not also write a POP analysis document.

### Mode B — POP and common-issue review

Trigger examples: `给我分析下POP和AI托管共性问题`, `分析POP表现`, `总结AI托管共性问题`.

Use the latest validated Excel audit for the same customer and period as the source of truth. Read [references/review-document-spec.md](references/review-document-spec.md), produce only the concise Markdown review, and stop.

Do not re-fetch campaign/group data, repeat the join, re-score campaigns, or regenerate row-level advice when the completed workbook is available. If it is not available, ask the user to upload it or run Mode A first.

If the user explicitly requests both deliverables in one message, finish and validate Mode A first, then use that workbook for Mode B. This is the exception, not the default.

## Inputs

### Mode A

- Customer name and reporting window.
- Customer-specific AI success standard.
- Current/comparison campaign performance for AI-managed campaigns.
- Managed-group membership and the settings needed by the lean output field set.

Accept uploaded exports or SparkX MCP data. With MCP, request only the selected output/scoring fields; do not fetch every available metric. Account-wide data is not needed for Mode A.

### First-use success-standard gate

Never invent or reuse another customer’s standard. If the standard is missing, ask:

> 这是该客户首次生成AI POP审核，我还缺少客户专属的AI成功标准。请上传包含成功标准的Excel/图片，或直接提供纳入条件、评分规则、评级映射及空值处理方式。

For a repeat report, reuse the latest validated standard only when it is clearly tied to the same customer. Sheet 2 must reproduce the supplied standard without rewriting it.

### Mode B

Require the completed Mode A workbook. Account-wide data is optional and should be used only when supplied and requested for comparison.

## Fast execution rules

- Join by managed-group ID. Fall back to normalized group name plus profile/store only when unique. The join must not increase campaign rows.
- Normalize and calculate with deterministic code/formulas. Use the model only for ambiguous rule interpretation and group-level recommendation text.
- Score only the customer-defined eligible population. Keep excluded rows in Sheet 1 as `不纳入评级`; never copy them to Sheet 3.
- Generate advice exactly once per distinct poor managed-group ID, then mechanically fill the same advice into every poor row in that group.
- Do not generate recommendations for reasonable settings or for non-poor campaigns.
- Do not add dashboards, group-rating summaries, issue-analysis columns, helper tabs, or document-only analysis to Excel.
- Do not fetch or output fields excluded by [references/field-selection.md](references/field-selection.md), unless the customer’s scoring rule explicitly requires them as hidden working inputs.
- Keep temporary joins and aggregates outside the deliverable and discard them after validation.

## Quality rules

- Every included campaign maps to exactly one managed group.
- The visible score and rating reproduce the client’s rules and boundary conditions.
- Sheet 3 contains only campaigns rated `差` and one shared recommendation per original managed group.
- Action space is not “the more the better”. Recommend changes only when tied to campaign function and evidence.
- Different actual ACOS bands, lifecycle stages, or targeting functions should not share a target when the mismatch is material.
- Do not apply live changes, overwrite source exports, or publish externally without explicit authorization.

## Output names

- Mode A: `{客户名}_AI托管审核_{YYYYMMDD}-{YYYYMMDD}.xlsx`
- Mode B: `{客户名}_AI托管表现及托管组设置优化建议_{YYYYMMDD}-{YYYYMMDD}.md`
