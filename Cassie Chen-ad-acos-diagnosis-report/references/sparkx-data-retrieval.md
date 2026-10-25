# SparkX 数据拉取与完整性规则

> 公开版说明：案例标识、经营数据及操作轨迹已移除；数值示例为独立构造的虚构演示或字段占位，不代表真实客户结果。诊断时须使用当前授权数据，不能套用示例结论。


本文件用于 Amazon Ads + SparkX MCP 场景。先读对应官方 skill 的最新字段说明，再以本文件防止常见归因错误。

## 1. 操作日志 `get_operation_log`

### 必须拉全，不得只取第一页

**Mode A（首选）：** `entities` 恰好设置为一个非 `aiGroup` 实体，例如 `["target"]` 或 `["campaign"]`。

- 使用 `page` + `pageSize`。
- 循环到 `meta.hasNextPage=false`。
- 保存每次响应的页码、行数和结束标志。
- `aiGroup` 或多数实体查询属于 limit-only，不能用同样方式翻页。

**Mode B：** 多实体、未指定 `entities` 或仅 `aiGroup` 时，检查 `meta.truncated`。若为 true，优先改单实体查询；否则拆分日期窗口。不能把单页结果当作全量历史。

### `resourceIds` 使用平台实体 ID

- 过滤 Amazon 广告实体时使用 Amazon ID，例如 Amazon campaign ID。
- 不要把 SparkX 内部数字 ID 与 Amazon ID 混用。
- 过滤返回 0 行时，先换用已确认的 Amazon ID 和 `idEntity` 组合做小样验证，再判断“无操作”。

### 完整性门禁

每次归因前输出或内部确认：

```text
实体类型 / 查询日期范围 / 实际返回日期范围 / 总行数 / 分页是否完成 / truncated
基准期操作数 / 分析期操作数 / 每日操作数
```

若返回行数恰好接近页大小上限，或最早日期只覆盖最近几天，默认存在截断风险，继续翻页或拆窗。

### 操作来源与时区

- `changedBy=AI` 才计为 AI 操作。
- `Campaign Out of Budget` 是平台状态事件，不是人工调预算。
- `Amazon Console` 可能包含后台操作或系统记录，结合 `operationType` 判断，不能整批算作人工。
- `createdDate` 时区受实体和 `profileIds` 数量影响；单 profile 通常为店铺本地时间。跨实体拼接前核对时钟，aiGroup 配置日志可能与 campaign/target 日志不同钟。

## 2. 广告表现 `get_ads_perf`

### 通用参数

- `profileIds` 必须是已授权的整数 ID。
- 使用 `dateStart` / `dateEnd`、`metrics`、`select`、`filters`、`userContext`。
- `pageSize` 不超过 500；有下一页时继续拉取。
- 从响应 `data.rows` 读取数据，分页信息在 `meta`。
- 请求字段与响应字段可能不同名，不要把响应键直接回填为请求字段。

### Campaign 日级与小时级

- 日级：`factEntity="campaign"`，`timeGranularity="daily"`（默认）。
- 小时级：`factEntity="campaign"` + `timeGranularity="hourly"`，并在 `select` 中显式包含 `date` 和 `hour`。
- 小时级窗口最多 7 天；做两期对比时选择等长、可比的 7 天窗口并注明抽样范围。
- 小时级没有可靠 AI 指标；AI 花费/销售拆分使用日级数据。

### SearchTerm

- `factEntity="searchTerm"`，手动关键词流量可用 `queryType="keyword"`。
- 自有字段不带实体前缀：`query_`、`matchType_`、`targetId_`、`adGroupId_`、`campaignId_`。
- 需要日级词池变化时使用 `timeGranularity="daily"`。
- 自动流量不要误用手动关键词过滤；Auto 与手动行需按 `matchType_` 分开。
- `SUBSTITUTES` / `COMPLEMENTS` 的 `query_` 可能是 ASIN，不要当作搜索文本。
- 不要选择该实体不支持的 `matchTypeText` 或 `keywordText_` 字段。

### KeywordPlacement / AMS

- 用于关键词 × 位置的小时级分析，SP only，窗口最多 7 天，不传 `timeGranularity`。
- `placement` 过滤值必须匹配原始流值；更稳妥的做法是先读取返回行中的位置值。
- 数据可能因店铺接入时间而为空。返回 0 行时写明“该期间无可用位置数据”，不得编造位置占比。
- 无 placement 数据时，可同词 CVR + 竞价操作 + 分小时表现作间接证据，但位置结论标 B/C 级。

## 3. 实体元数据 `get_entity_metadata`

- 元数据实体 ID、广告表现过滤 ID 和操作日志 ID 可能属于不同 ID 空间。
- 用 campaign 元数据确认 Amazon campaign ID，再用于日志和表现查询。
- 某实体按名称/ID 过滤返回 0 行时，换用官方示例的字段名和 ID 类型排查，不要直接认定实体不存在。

## 4. 最小完整性记录

在分析工作底稿中保存：

```json
{
  "campaign_daily": {"rows": 0, "date_min": "", "date_max": ""},
  "campaign_hourly": {"rows": 0, "window": "", "baseline_window": ""},
  "search_terms": {"baseline_rows": 0, "analysis_rows": 0},
  "placement": {"rows": 0, "available": false},
  "target_ops": {"rows": 0, "pagination_complete": false, "date_min": "", "date_max": ""},
  "campaign_ops": {"rows": 0, "pagination_complete": false, "date_min": "", "date_max": ""}
}
```

任何“全部操作”“0 次人工操作”“AI 只在某天行动”的结论，都必须能追溯到完整记录。
