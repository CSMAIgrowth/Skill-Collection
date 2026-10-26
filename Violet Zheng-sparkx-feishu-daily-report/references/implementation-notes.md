# Implementation Notes

Use these notes when creating or modifying a customer-specific SparkX MCP → Feishu daily advertising report automation. Keep this reference generic. Do not add customer-specific identifiers, report output, chat IDs, spreadsheet links, profile lists, or credential material.

## SparkX MCP data retrieval

- Use `get_user_authorized_context` on the customer-selected SparkX MCP connection to identify the authorized profile list before querying ads performance.
- Filter the authorized profile list according to the user-provided store scope.
- Query each profile/store separately with `get_ads_perf` when account or connector behavior makes multi-profile aggregation unreliable.
- Fetch D-1 data according to each profile's own timezone, not the computer timezone.
- Fetch D-2 totals for comparison columns.
- Use activity-level details for campaign/ad type breakdowns, and also fetch store-level totals for reconciliation where supported.
- Keep currencies separate. Do not create a cross-currency spend/sales total unless the user explicitly provides exchange-rate rules.

## Feishu/Lark operating notes

Prefer the connected Feishu/Lark toolchain available in the current session. Use user identity for normal sends unless the user explicitly requests bot/agent identity and a bot application is available.

Useful operation families:

- Resolve a group by name before scheduling.
- Inspect group members and get open IDs when @mentions are needed.
- Resolve a private recipient before direct-message sending.
- Send text/markdown/post/media/interactive messages.
- Create a workbook or write typed tables to an existing spreadsheet.
- Verify workbook tabs after writes.
- Delete only accidental files created during the current task and only after explicit confirmation.

## Feishu table gotchas

- Typed table writes can create missing sheet tabs by name where the Feishu tool supports it.
- For large JSON payloads, use temp-file arguments where supported instead of sending multiple large JSON values through stdin.
- Keep style payloads limited to fields accepted by the active Feishu toolchain.
- Store percentage-like values as percentage points and use literal percent formats:
  - ACOS/CTR/CVR value: `45.73`, format: `0.00"%"`
  - Ring change value: `-8.7`, format: `0.0"%"`
  - Percentage-point delta: `-1.7`, format: `+0.0"pp";-0.0"pp";0.0"pp"`
- Using `0.00%` on a value like `45.73` displays `4573.00%`.

## Message formatting

Recommended Feishu message structure:

1. Bold title with report date.
2. Coverage line: store count, store scope, local-yesterday basis.
3. Overall D-1 vs D-2 comparison table.
4. Top 5 stores/campaigns by spend.
5. Attention points with severity levels.
6. Spreadsheet link.
7. Footnote: currency handling, attribution delay, no cross-currency total, data snapshot timing.

Mention syntax in text/post markdown:

```text
<at user_id="ou_xxx">Name</at>
```

Card/interactive messages may require card-native mention syntax, depending on the Feishu toolchain:

```text
<at id=ou_xxx></at>
```

## Report behavior to preserve where applicable

- Save run state under an output directory to support idempotency.
- Avoid sending duplicate Feishu messages for the same run.
- If a sent message is withdrawn and resent within one hour, use a new idempotency key.
- Keep warning rows for failed profiles rather than failing the whole report.
- Include reconciliation/delta columns when comparing campaign details to store totals.

## Automation prompt template

Use a self-contained prompt like this when creating a recurring automation:

```text
Generate the SparkX MCP advertising daily report for <store scope>. Use the customer-selected SparkX MCP connection <server or connector name>. For each included profile, compute local yesterday from the profile timezone, fetch D-1 ad performance and D-2 totals, keep currencies separate, build the Feishu spreadsheet with overview/store/ad-type/top-campaign tabs, apply <view/edit> permissions, and send the concise markdown summary to <target type> <target id>. Treat SparkX access as read-only and do not modify campaigns, budgets, bids, or managed groups.
```

Set the schedule using automation fields, for example:

```text
FREQ=DAILY;BYHOUR=9;BYMINUTE=0
```

Do not put the schedule inside the automation prompt.
