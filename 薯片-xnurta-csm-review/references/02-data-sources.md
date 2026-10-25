# SparkX AI MCP 取数对照表（本技能的唯一广告数据源）

本表把报告需要的数据映射到 SparkX AI MCP 的只读工具。**具体参数格式、字段拼写、分页和报错以官方查询 Skill 为准**，本表只告诉你"取什么、去哪取、取不到怎么办"。

- 官方仓库：https://github.com/SparkXAI/SparkXAI-MCP
- 必装的官方查询 Skill：`sparkx-query-ads-performance`（`get_ads_perf`）、`sparkx-query-entity-metadata`（`get_entity_metadata`）、`sparkx-query-operation-log`（`get_operation_log`）。本对照表依据 2026-10-22 的 manifest（release v1.3.4，三个查询 Skill 分别为 1.4.7 / 1.4.7 / 1.3.6）。版本更新后以新版 Skill 为准。

## 0. 每次取数前

1. 调 `get_user_authorized_context`，拿到当前账号**已授权**的店铺 `profileId` 列表。只能查这些；任何一个未授权的 ID 会让整次调用失败。
2. 和用户确认本次要分析哪些店铺。用户没指定时用全部已授权店铺，并在报告里写明范围。
3. 日期：单次调用最多 90 天，最多回溯 15 个月；超过 90 天先拆成多段再合并。数据约 T+2，结束日默认取前天，近 2–3 天归因未回流，趋势判断以更早日期为准。
4. 比率不要平均：ACOS、CPC、CVR、ROAS、TACOS 一律用原始花费、销售、点击、订单重新算。MCP 返回的百分比已乘 100（`17.61` 表示 17.61%）。
5. 多店铺查询时金额自动换算成 USD；单店铺返回本币。报告里写明币种。

## 1. 广告表现（`get_ads_perf`）

| 报告要的数据 | factEntity | 指标 / 维度要点 |
|---|---|---|
| 大盘花费、销售、订单、点击、展示 | `campaign` | `Spend` `Sales` `Conversions`（订单）`Units` `Clicks` `Impressions`；SP / SB / SD 用 `campaign.campaignType_` 分开取，不要混算 |
| AI 与人工拆分 | `campaign`（只能日级） | `AISpend` `AISales` `AIACOS` `AIROAS`；人工侧 = 总量 − AI 侧。AI 指标**只在 campaign 实体、日粒度上有真实值**，小时级和 keywordPlacement 上是占位值，不能用 |
| 月度、周度趋势 | `campaign` | 在 `select` 里用官方 Skill 给的月/周聚合表达式；跨 90 天先分段 |
| 店铺 / 站点拆分 | `campaign` | 按 `profile` 维度分组（字段名见官方 Skill） |
| 托管组层面表现 | `campaign` | 加 `aiGroup.aiGroupId_` / `aiGroup.aiGroupName_` 维度，可同时取 `aiGroup.aiTargetType_`、`aiGroup.targetAcos_` |
| 商品（ASIN）广告表现 | `productAd` | 每行就是一个被推广商品；**不要**在 campaign 或 adGroup 上加 ASIN 维度，会重复计数 |
| 店铺总销售、TACOS、Sessions、Buy Box、自然销售 | `asin` | `TotalSalesAmount` `TACOS` `Sessions` `UnitSessionPercentage` `BuyBoxPercentage` `OrganicSales`；只在 asin 实体可用，不能和广告实体混合 |
| 关键词 / 定向 | `target` | 必须带 `queryType`：`keyword` / `product` / `auto` |
| 搜索词 | `searchTerm` | 不传 `queryType` 才能拿到自动广告的搜索词 |
| 广告位 | `placement` | 广告位层面的比较只看同层 CPC、CVR、ACOS 和占比 |
| 小时 / 分时 | `campaign` + `timeGranularity: hourly`，或 `keywordPlacement` | 单次最多 7 天；没有 AI 指标 |

同 ASIN 的 AI 与人工比较：`productAd` 实体没有 AI 指标，需要先在 `campaign` 实体按"活动 × 日"拿 AI 花费，再把 AI 标签挂到同一活动同一天的商品行上。只能挂"整条活动当天是否有 AI 花费"，挂不了更细；这个限制要写进数据说明。

## 2. 配置与托管组（`get_entity_metadata`）

| 报告要的数据 | entity | 说明 |
|---|---|---|
| 托管组清单、状态、目标、人格 | `aiGroup` | 返回的是**当前生效配置**；关闭的开关会连同下属字段一起被省略，"字段缺失"表示当前未生效，不代表没配置过 |
| 行动空间开关（竞价、预算、否定、收割、广告位、分时等） | `aiGroup` | 展示给客户前先读官方 Skill 的 `managed-group-display.md`，用客户界面的叫法 |
| 托管组排期 | `aiGroup_schedule` | 一次只能传一个 profileId |
| 活动预算、竞价策略、状态 | `campaign` | |
| 商品信息（标题、库存、可投放状态、产品线） | `asin` | |

配置是**查询当天的快照**，不能当成历史某天的配置，也不能单独作为"运营做错了"的证据。要看历史变化，用操作日志。

## 3. 操作日志（`get_operation_log`）

| 报告要的数据 | 用法 |
|---|---|
| AI 做了多少调价、调预算、启停 | `changeBy` 筛 AI，按 `operationType` / `changeField` 在本地计数 |
| 人工改了什么、什么时候改的 | `changeBy` 筛人工；按时间线排列 |
| 托管组的开关、目标、活动增删记录 | `entities: ["aiGroup"]` |

- 只有指定**一个**非 aiGroup 实体时才能翻页；否则单次有上限，`truncated=true` 时要拆日期段重查，或者在报告里写明"部分记录"。
- 返回时间的时区随传入店铺数变化，报告前先按官方 Skill 的规则换算。
- 日志次数只说明"发生过多少动作"，不能直接当成业绩提升或节省的工时。

## 4. MCP 取不到的数据（必须如实写缺口，不能编）

| 数据 | 处理方式 |
|---|---|
| 合同、版本、到期日、额度、服务记录、续约状态 | 请用户提供，或从公司已授权的客户系统里由 CSM 自己查后填入；不写就标"未提供" |
| 系统登录天数、各功能模块使用次数 | 平台前台的账号活跃页面截图或用户提供；取不到就写"未取得，不能据此认定无人使用" |
| 跨客户的同行对标、类目 benchmark | MCP 只能看本账号授权店铺，不能跨客户。可选外部来源：卖家精灵、SIF（需 CSM 自己的授权），使用时标日期、站点、样本和口径 |
| 关键词搜索量、市场 CPC、竞品排名 | 用外部市场工具（需 CSM 自己的授权）；搜索量是市场口径，不是本账户口径 |
| AI 否词 / 收割拦截了多少钱 | 日志能数动作次数，拦截金额需要反事实假设；只给次数和样例，金额标"情景估算"或不写 |
| 毛利、成本、库存计划、促销计划 | 请用户提供；缺失时只给有条件的建议 |
