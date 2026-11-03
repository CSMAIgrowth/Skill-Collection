#!/usr/bin/env node

import fs from "node:fs";

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith("--")) {
      args[key] = next;
      i += 1;
    } else {
      args[key] = true;
    }
  }
  return args;
}

function readFile(file, label) {
  if (!file) return "";
  if (!fs.existsSync(file)) throw new Error(`${label} 文件不存在: ${file}`);
  return fs.readFileSync(file, "utf8");
}

function readJson(file, label) {
  try {
    return JSON.parse(readFile(file, label));
  } catch (error) {
    throw new Error(`${label} 不是有效 JSON: ${error.message}`);
  }
}

function dateValue(value) {
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function inclusiveDays(start, end) {
  const first = dateValue(start);
  const last = dateValue(end);
  if (!first || !last || last < first) return null;
  return Math.round((last - first) / 86400000) + 1;
}

function previousDay(value) {
  const date = dateValue(value);
  if (!date) return null;
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function collectNames(value) {
  if (Array.isArray(value)) return value.filter(item => typeof item === "string");
  if (!value || typeof value !== "object") return [];
  return ["managedGroups", "campaigns", "adGroups", "targets", "searchTerms"]
    .flatMap(key => Array.isArray(value[key]) ? value[key] : [])
    .filter(item => typeof item === "string");
}

function fail(message) {
  failures.push(message);
}

const args = parseArgs(process.argv.slice(2));
const failures = [];

if (!args.report && !args.data && !args.names) {
  console.error("用法: node case_preflight.mjs --report report.md --data data.json --names names.json");
  process.exit(2);
}

try {
  const report = args.report ? readFile(args.report, "报告") : "";
  const data = args.data ? readJson(args.data, "数据") : {};

  if (args["current-start"] && args["current-end"] && args["comparison-start"] && args["comparison-end"]) {
    const currentDays = inclusiveDays(args["current-start"], args["current-end"]);
    const comparisonDays = inclusiveDays(args["comparison-start"], args["comparison-end"]);
    if (!currentDays || !comparisonDays || currentDays !== comparisonDays) {
      fail("当前窗口与环比窗口天数不一致");
    }
    if (previousDay(args["current-start"]) !== args["comparison-end"]) {
      fail("环比窗口不是当前窗口前紧邻的等长窗口");
    }
  }

  const period = data.period || {};
  const expectedPeriods = [
    ["currentStart", period.currentStart || period.start, args["current-start"]],
    ["currentEnd", period.currentEnd || period.end, args["current-end"]],
    ["comparisonStart", period.comparisonStart, args["comparison-start"]],
    ["comparisonEnd", period.comparisonEnd, args["comparison-end"]]
  ];
  for (const [field, actual, expected] of expectedPeriods) {
    if (expected && actual && actual !== expected) {
      fail(`数据 period.${field} 与命令行窗口不一致: ${actual} != ${expected}`);
    }
  }

  if (args.report && !args["skip-date-text"]) {
    for (const value of [args["current-start"], args["current-end"], args["comparison-start"], args["comparison-end"]]) {
      if (value && !report.includes(value)) fail(`报告缺少窗口日期: ${value}`);
    }
  }

  if (args.names) {
    const names = collectNames(readJson(args.names, "名称")).filter(Boolean);
    for (const name of names) {
      if (!report.includes(name)) fail(`报告缺少完整原始名称: ${name}`);
    }
  }

  if (args["require-tables"]) {
    for (const marker of ["表现环比", "设置-动作-结果", "影响最大广告活动", "下钻证据"]) {
      if (!report.includes(marker)) fail(`报告缺少必需表格标识: ${marker}`);
    }
  }

  if (args["require-mcp-checks"]) {
    const reconciliation = data.reconciliation || data.reconciliationChecks;
    if (!Array.isArray(reconciliation) || !reconciliation.length) {
      fail("缺少 MCP 汇总与明细差异校验结果");
    } else {
      const maxDiff = Number(args["max-diff-rate"] || 0.01);
      for (const check of reconciliation) {
        const differenceRate = Number(check.differenceRate ?? check.diffRate ?? 0);
        if (check.ok === false || check.status === "failed" || differenceRate > maxDiff) {
          fail(`MCP 指标差异未通过: ${check.metric || check.name || "未命名指标"}`);
        }
      }
    }
    if (data.membership?.historyAvailable !== true) {
      fail("缺少窗口内托管组历史成员完整性确认");
    }
    if (data.logs?.complete !== true) {
      fail("操作日志未确认完整或存在截断");
    }
  }

  if (args["allow-opening-compare"] !== true && args["allow-opening-compare"] !== "true" && report) {
    const forbidden = ["托管前周期", "开启前周期", "AI开启前作为默认基线"];
    for (const phrase of forbidden) {
      if (report.includes(phrase)) fail(`报告疑似把开启前窗口当作默认基线: ${phrase}`);
    }
  }
} catch (error) {
  console.error(`预检失败: ${error.message}`);
  process.exit(2);
}

if (failures.length) {
  console.error("Case 预检未通过:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("Case 预检通过");
