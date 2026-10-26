# SparkX Feishu Daily Report Reference

This file is the general reference entry point for the reusable customer-facing workflow. For implementation details, read `implementation-notes.md` first.

## Core external systems

- Customer's own SparkX MCP connection for Amazon Ads data retrieval.
- Customer-authorized Feishu/Lark connector for spreadsheets, messages, permissions, chats, users, and optional bot events.
- WorkBuddy automations for recurring schedules.

## Minimum user inputs before running

1. Customer SparkX MCP connection/server to use.
2. Store scope.
3. Feishu permission mode: editable or view-only.
4. Feishu target group/private chat.
5. Daily send time.

## Reusability rule

Do not store or reuse any previous customer's MCP server name, credential material, account ID, profile list, chat ID, spreadsheet URL, message ID, report output, or business data in this skill. Resolve all such values from the current customer's own connected systems at runtime.
