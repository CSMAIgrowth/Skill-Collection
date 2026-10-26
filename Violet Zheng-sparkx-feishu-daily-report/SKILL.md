---
name: sparkx-feishu-daily-report
description: This skill should be used when creating, updating, or running a customer-specific SparkX MCP powered advertising daily report that publishes to Feishu/Lark. It requires the customer's own SparkX MCP connection plus store scope, Feishu view/edit permission mode, target Feishu group or private chat, and daily delivery time before any automation is created or run.
agent_created: true
---

# SparkX Feishu Daily Report

## Overview

Create or update a scheduled, customer-specific SparkX MCP advertising daily report that fetches store-level Amazon Ads data from the customer's own SparkX MCP connection, writes a Feishu spreadsheet, and sends a concise Feishu message to a group or private chat.

Treat this skill as a reusable customer-facing workflow. Do not include or reuse any other customer's MCP server name, account identifier, chat identifier, spreadsheet link, report output, or operational data. Require the current customer to provide or authorize their own SparkX MCP and Feishu targets.

Require four user-provided parameters before running or creating the automation:

1. 店铺范围（store scope）
2. 飞书权限：可编辑或仅查看（Feishu permission mode）
3. 飞书发送目标：群组或私聊（target chat or user）
4. 每天几点发送（daily send time）

Do not create or update an automation until all four parameters are known.

## Required input gate

Before taking action, collect and confirm these fields:

| Field | Acceptable values | Validation notes |
| --- | --- | --- |
| SparkX MCP 连接 | Customer-provided MCP server name/connector, or an already connected SparkX MCP chosen by the customer | Use only the current customer's MCP. If no SparkX MCP is connected, ask the user to connect or authorize it first. |
| 店铺范围 | all authorized stores; countries/sites such as US/CA/DE/EU; profile names; profile IDs; brand/store groups | Resolve ambiguous names before scheduling. If the scope is partial, store the exact filter definition in the automation prompt. |
| 飞书权限 | `view` / `editable`; Chinese: `仅查看` / `可编辑` | Apply to the generated spreadsheet or shared Drive resource. If Feishu permission tooling is unavailable, state the blocker and leave a manual permission step. |
| 飞书发送目标 | Feishu group name, chat_id (`oc_...`), private user name, or open_id (`ou_...`) | Resolve names to exact IDs before saving the schedule. For groups, prefer `im +chat-search`; for private messages, prefer `contact +search-user`. |
| 每天几点发送 | HH:MM in the user's intended timezone; Chinese phrases such as `每天上午九点` | Convert to an automation RRULE. If timezone is not stated, assume the user's current timezone/北京时间 and state that assumption. |

Ask a short clarification question if any field is missing. Never use demo defaults, previous customer defaults, old local scripts, or historical chat IDs as runtime parameters.

## Workflow

### 1. Resolve Feishu connectivity first

Use the Feishu/Lark connector or official `lark-cli` flow before building the report. If Feishu is unavailable or authorization expired, reconnect or ask the user to reauthorize before scheduling.

Use `--as user` unless the user explicitly asks for bot/agent identity and a bot application is available.

### 2. Resolve the target chat or private recipient

For a group target:

- Search by group name and confirm the exact match.
- Store the resolved `chat_id` in the automation config or generated script.

For a private target:

- Search the person with Feishu contact lookup.
- Store the resolved `open_id`/`user_id` and use direct-message sending.

For @mentions in report messages, use:

```text
<at user_id="ou_xxx">Name</at>
```

For @all, use:

```text
<at user_id="all"></at>
```

Avoid @all unless the user explicitly requests it.

### 3. Resolve SparkX store scope from the customer's own MCP

Use `get_user_authorized_context` on the customer-selected SparkX MCP server to list authorized profiles. Filter profiles according to the user's store scope.

Supported filters:

- profile ID list
- profile name list or keyword list
- country/site list
- brand/store group names if the account metadata supports them
- `all` for all authorized stores

If a profile name maps to multiple profile IDs, show the matches and ask the user to choose.

### 4. Generate or update the report script

Implement a customer-specific script or update the customer's existing report script. Parameterize all customer-specific values:

- SparkX MCP server/connector selected by the customer
- profile/store filter
- Feishu target type and ID
- Feishu spreadsheet permission mode
- daily schedule time
- workbook reuse policy

Preserve these reporting rules:

- Fetch each profile separately with `get_ads_perf`; do not query many profiles in one call if the connector or account shows multi-profile aggregation anomalies.
- Calculate each profile's “local yesterday” from its own timezone.
- Fetch D-1 activity detail and D-2 total metrics for comparison.
- Keep currencies separate; do not sum values across currencies.
- Keep ACOS/CTR/CVR as percentage-point values in spreadsheet cells, e.g. `45.73`, and format them as `0.00"%"` rather than `0.00%`.
- Include at least these report sections: overall comparison, store summary, ad type summary, top-spend campaigns, and attention points.
- Save run state so retries are idempotent and do not spam Feishu.

### 5. Write to Feishu

Prefer a fixed Feishu spreadsheet if the user wants a stable historical view:

- Use one workbook with a daily sheet tab, or a summary/history tab appended over time.
- Use typed table writes where available.
- Use temporary file arguments for large sheet/style JSON payloads where the CLI supports `@file`.
- Keep table styles portable and do not rely on undocumented fields.

If the user wants a fresh workbook each day, create a new workbook and include the new link in the message.

Apply the requested permission mode:

- `仅查看`: share/view-only where supported.
- `可编辑`: share/edit where supported.

If the current Feishu tooling cannot modify permissions, clearly report that the table was created and that permissions need manual adjustment.

### 6. Send the Feishu message

Send a concise message containing:

1. Report title and covered store count
2. Overall D-1 vs D-2 comparison by currency/date
3. Top 5 stores or campaigns by spend
4. Attention points with severity labels
5. Spreadsheet link
6. Data口径 footnote: timezone, currency, delayed attribution, no cross-currency total

Use a unique idempotency key per message run. If an old message is withdrawn and resent within one hour, generate a new key; Feishu may otherwise return the withdrawn message ID.

### 7. Create or update the automation

Use one recurring automation per logical report. Do not create one automation per store, country, or day.

The automation prompt must be self-contained and include:

- customer-selected SparkX MCP server/connector name
- exact store scope filter
- Feishu target type and resolved target ID
- Feishu permission mode
- workbook reuse policy
- report content expectations
- safety rules: read-only SparkX data retrieval unless explicitly authorized otherwise

Put the schedule in the automation fields, not inside the prompt. For a daily schedule, use an RRULE like:

```text
FREQ=DAILY;BYHOUR=9;BYMINUTE=0
```

Adjust `BYHOUR` and `BYMINUTE` to the user-provided send time.

## Safety and reliability rules

- Use only the current customer's authorized SparkX MCP connection and Feishu target.
- Treat SparkX advertising actions as read-only unless the user explicitly asks for write operations and the connection has write permission.
- Never modify budgets, bids, campaigns, or AI managed groups as part of this reporting skill.
- Do not expose SparkX credentials, Feishu credentials, raw Authorization headers, customer IDs, chat IDs, spreadsheet links, or historical report outputs in user-facing reusable materials.
- Do not ship customer-specific scripts, state files, report JSON, spreadsheet links, chat IDs, or message IDs inside the skill.
- Confirm the target group/private chat before the first send.
- When Feishu connector status is unavailable, stop before sending and ask for reconnection or authorization.
- Keep a local run log and state file for troubleshooting, but do not store secrets or customer-sensitive identifiers in reusable skill files.

## When to read bundled references

Read `references/implementation-notes.md` when implementing or modifying the actual scripts, Feishu table write flow, or automation prompt. It contains reusable implementation gotchas only and must stay free of customer-specific identifiers or report data.
