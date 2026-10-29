# SparkX MCP 字段与调用实测笔记（动作复盘场景）

本文档记录 2026-10-29 在 SparkX AI MCP（真实客户只读账号）上实测验证的调用规则，用于补齐「字段名称和分页规则以该连接实际文档为准」缺本地参考的问题。字段名随 MCP 版本可能变化；平台报错信息会给出可用字段清单，以报错为准。同仓库 `Jannie Li-amazon-ads-negative-keyword-optimizer/references/sparkx-mcp-field-reference.md` 有更完整的否词场景字段参考，可交叉核对。

## 1. ID 双轨制

同一实体两套 ID：元数据接口用平台内部短 ID，`get_ads_perf` 返回行与 filters 用 Amazon 长 ID。跨接口对齐时先经 `get_entity_metadata` 换算（如 campaign 的 `amazonCampaignId`、target 的 `amazonEntityId`）。操作日志的 `resourceIds` 中 campaign/adGroup 必须传 Amazon ID，aiGroup 传内部托管组 ID。

## 2. `get_ads_perf` 维度字段命名

- fact entity 自身维度用 `p.` 前缀（如 `p.aiGroupId_`、`p.targetId_`、`p.matchType_`）；关联实体用 `实体名.` 前缀（如 `campaign.campaignName_`）。
- `p.date_` / `campaign.date_` / `statDate` 等日期字段不存在。`factEntity='campaign'` 的 `p.` 维度仅有 `aiGroupId_ / campaignId_ / campaignType_ / portfolioId_ / profileId_` 五个。
- 聚合查询（不带日粒度展开）返回整窗合计；窗口对比用「分段日期区间多次查询」实现，不要指望一次查询拿到逐日行。

## 3. 日粒度的实际限制与降级路径

- `timeGranularity='daily'` 在该 MCP 上**不产出逐日行**（无日期维度列可 select），`'hourly'` 仅 keywordPlacement 固定支持。
- 降级路径（实测有效）：
  1. 按动作节点切分日期区间（如 AI 开启日、人工改价/改预算日），每段一次聚合查询，段内指标从分子分母重算；
  2. 逐日预算还原改用 `get_operation_log` 逐笔拼装（日初值=前一日最后一次变更结果值；每次变更记时间/操作者/原值/新值；OUT_OF_BUDGET 事件单独标出）；
  3. 日末值≠全天额度：剧本「日初→日末/日内最高」要求改为「日志链上当日最大值」口径，日志链断档时标注预算重建不完整。

## 4. 分页与截断检测

- 聚合查询的 meta 常为空（无 `hasNextPage`）；判断是否翻页的可靠信号是 **`rowCount == pageSize` 即续页**，翻到返回行数小于 pageSize 或 `hasNextPage=false` 为止。
- 大账户（实测单 profile ≥1500 个活动）必须逐页取全；无法穷尽时在报告「限制」中写明实际覆盖行数。
- 操作日志单实体可分页（`page` 参数仅单一非 aiGroup 实体时有效）；`pageSize` 上限 1000，aiGroup-only 查询上限 10000。

## 5. 其他实测确认

- 日志时区：单 profile 的广告日志用店铺当地时间，多 profile 混查不可靠；SP/SB aiGroup 日志 UTC。跨时区对齐先核对来源。
- `changedBy` 取值实测含 `AI`、`Amazon Console`、具体邮箱（人工）、`System`；`manual` 不被支持，查人工操作用具体操作者邮箱或省略 `changeBy` 后自行归类。
- 指标一律从返回的分子分母重算（CPC=花费÷点击、CVR=订单÷点击、ACOS=花费÷销售额），不平均日值；零分母标不可计算。
- 复算校验法：活动级汇总应等于定向级求和（实测误差 ≤ 舍入级 0.01），对不上先怀疑转录/翻页漏行。

---
来源：2026-10-29 Skill Store 质量测试（真实客户 US 站实跑，16 次只读调用含 7 次字段试错）。
