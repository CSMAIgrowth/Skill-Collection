---
name: sparkx-ai-diagnosis
description: >-
  Diagnose why an Amazon ads campaign or AI-managed group underperformed after SparkX AI takeover:
  orders/ACOS/CVR deterioration, spend anomalies, traffic collapse. Produces a concise customer-facing
  report with verdict (root cause), evidence with plain charts, and recommendations.
  Use when the user asks "为什么托管后转化掉了/ACOS飙了/花费异常", "分析托管组表现变差",
  "诊断 AI 托管", or wants to audit whether AI or manual operations caused a change.
  Requires the sparkx-ai-mcp skill (get_ads_perf / get_operation_log / get_entity_metadata) to be connected.
metadata:
  version: "1.2.0"
---

# SparkX AI 托管诊断（AI 算法归因）

## 定位

对「AI 托管后某指标变差」的问题，给出**经证伪检验的单一责任判定**，产出客户 1 分钟能看懂的报告：**结论 → 原因 → 论据（含图）→ 建议**。不写长篇分析，不做模糊归因——每个原因必须通过证伪测试，通不过的降级为"可能原因"，证据不足的直接排除。

## 核心方法：证伪测试（不可省略）

对**每一条**操作（AI 与人工同一标准），判定三条：

| 条件 | 检验 |
|---|---|
| ① 时序 | 操作时间在恶化开始**之前**且紧邻（恶化的第一天即为分界） |
| ② 方向 | 该操作按业务逻辑**应该**产生观测到的恶化方向 |
| ③ 量级 | 操作的影响量级能**解释**实际损失（差 1 个数量级则不成立） |

判定规则：**三条全过 = 导致因素**；过两条 = 可能原因（标注，不强行归因）；仅时序符合 = 时间相关（排除）；都不符 = 排除。**排除项也要在报告中列出**——"AI 无责"的结论必须有完整的排除清单支撑。

## 第 0 步：一次性取全数据（先取数，后分析）

诊断开始时**先并行调取以下 7 类数据**，再进入分析，避免中途反复往返：

| # | 数据 | 工具调用 | 要点 |
|---|---|---|---|
| 1 | 广告活动数据 | `get_ads_perf(factEntity='campaign', select=campaignName+date, groupBy同)` | 前两周 + 托管后逐日；含 Spend/Clicks/Conversions/Sales/ACOS/CPC |
| 2 | 搜索词数据 | `get_ads_perf(factEntity='searchTerm', select=query_)` | **必须循环分页至 hasNextPage=false**；按广告活动归属过滤用 `adGroup.adGroupId_`（amazon AdGroup ID，经 `get_entity_metadata(entity='adGroup')` 换取） |
| 3 | 投放定向数据 | `get_ads_perf(factEntity='target')` 或 `get_entity_metadata(entity='target'/'keyword')` | 看定向/关键词的竞价与状态变更 |
| 4 | 推广商品数据 | `get_ads_perf(factEntity='productAd')` | 商品维度花费与转化，判断是否单品拖累 |
| 5 | 广告位数据 | `get_ads_perf(factEntity='placement')` | 按 placement 拆订单/CVR；过滤用 `campaign.aiGroupId_` 或 campaign name 拆分，**不能** join adGroup |
| 6 | 广告活动小时数据 | `get_ads_perf(factEntity='campaign', timeGranularity='hourly')` | 限 7 天窗口；预算 pacing / OOB 影响的取证 |
| 7 | 操作日志 | `get_operation_log`（entities=campaign/target/placement 各查一次） | AI 与人工分开通查；resourceIds 用 **amazon** ID |

**ID 口径提醒**（取数前核对，空结果先查这里）：报表维度过滤里 `campaign.campaignId_`/`adGroup.adGroupId_` 用 **Amazon ID**；`get_entity_metadata` 的 filters 用 **internal ID**（`campaignId`/`adGroupId`）；操作日志 resourceIds 用 **Amazon ID**。传错 ID 空间不报错、只返回 0 行。部分报表过滤不支持某些维度组合（报 `query_shape_unsupported`），改用先查组内全量、再按名称拆行的方式。

数据齐了再做第 1–5 步。后续步骤中如发现某类数据缺失，回补即可，不必重跑全部。

## 工作流程（5 步）

### 第 1 步：锁定问题与时间分界

1. 从用户描述提取：哪个组/campaign、什么指标变差、什么时间开始托管。
2. `get_user_authorized_context` → `get_entity_metadata(entity='aiGroup')`（按名字模糊匹配）拿 aiGroupId、profileId、目标 ACOS、AI 开启时间、行动空间开关。
3. `get_entity_metadata(entity='campaign', filters={"aiGroupId":...})` 拿组内 campaign 清单（注意记录 internal campaignId 与 amazonCampaignId 两套 ID——操作日志的 resourceIds 用 **amazon** ID）。
4. 定义三个对比窗口：**托管前一周 vs 托管后一周**；若托管前一周可能是异常高/低基数，再往前取一周做基线校验。

### 第 2 步：量化恶化（先分清"掉的是什么"）

`get_ads_perf(factEntity='campaign')` 按周对比：Spend / Impressions / Clicks / Conversions / Sales / ACOS / CPC。关键分流：

- **点击没掉、订单掉** → 流量质量/转化问题 → 走第 3 步 a+b+d；
- **点击掉了** → 流量供给问题 → 走第 3 步 b+c；
- CPC 持平 → 直接排除竞价因素（写进报告）。

数据有 T+2 归因延迟：托管后窗口的**末尾 1–2 天转化未回填完整**，对比时要么剔除，要么在报告里明确标注，不可静默使用。

### 第 3 步：四方取证

a. **搜索词对比**（前后各一周，`factEntity='searchTerm'`，注意分页取全量——默认只回第一页会漏长尾词）：
   - 分层：头部出单词（≥2 单）vs 长尾 1 单词；
   - 逐词标注：保留 / 缩水 / 消失 / 新增，消失词再标注"是否被否定"；
   - 订单变化 = Σ缩水 + Σ消失 − Σ新增，拆出各层贡献占比。

b. **操作日志审计**（`get_operation_log`，AI 与人工分开通查）：
   - 按操作类型汇总（否词 / 竞价 / 预算 / 状态 / 广告位），看**量级**：调价幅度百分比、调价后实际 CPC 是否变化、预算总量是否变化、否定是 campaign 级还是组级；
   - 被否词要交叉验证：去搜索词报告确认该词（及同词根词族）在其他 campaign 是否继续出单、60 天维度是否本就低效。**只看"被否"不看"否对了没有"是最常见误判**；
   - 人工操作（changedBy 非 ai/automation）单独列出，同样过证伪测试。

c. **时段与广告位切片**（流量供给问题时）：
   - `factEntity='campaign' + timeGranularity='hourly'`（限 7 天窗口）看分时预算/花费是否掐断高峰；
   - `get_operation_log(entities='campaign')` 中 DailyBudget 序列还原 pacing 行为（凌晨清零+逐级释放）；
   - `factEntity='placement'` 看广告位订单分布是否单渠道塌陷（全渠道同步下滑 → 指向大盘因素而非单一操作）。

d. **环境因素**：季节切换（品类需求 Google 趋势逻辑）、基线异常（前一周 vs 再前一周）、促销/竞品——凡是不能用数据排除的，列为"可能原因"并标注不确定性。

### 第 4 步：出判定

**判定前读取 [references/falsification.md](references/falsification.md)**：三条件（时序/方向/量级）的操作化定义、逐操作类型的默认检验要点、量级判定的 50%/10% 阈值、机制解释模板，以及"非操作因素"结论的论证义务清单。

把第 3 步结果填进证伪测试表（每条操作一行：操作者/时间/内容/三条件/判定）。汇总后只允许三种结论：

1. **AI 导致**（有通过三条件的操作）→ 给机制解释（如"匀速 pacing 撞脉冲需求"）；
2. **人工导致**（同上）；
3. **非操作因素**（所有操作被排除）→ 给大盘解释（季节/基数/归因延迟），此时必须附完整排除清单。

最强证据是**反向验证**：托管关闭/配置回退后当天恢复 → 直接锁定责任；反之若恶化在操作之前已开始（如广告位 CVR 从托管首日即下滑、且早于该操作），该操作排除。

### 第 5 步：写报告（结构固定，勿自由发挥）

**写报告前读取 [references/report-template.md](references/report-template.md)**：页面骨架、目标达成卡片、4 种图表的现成 HTML/SVG 代码、用词规范表，直接复用，不重新发明样式。

输出为单文件 HTML（存到 output/ 后用 show 展示），结构照抄：

```
⓪ 目标达成区（开头第一屏）：托管组目标设置 + 广告活动目标 vs 实际对比
① 头部：活动名 / 站点 / 分析期 / 一句话判定 + 根因
② KPI 卡片行：4-5 个核心数字的前后对比（大数字 + 涨跌%），一眼看完
③ 结论段：3-4 句话讲清"谁的责任、为什么"，每句都必须有下文图表支撑
④ 论据区：2-4 个图表（见可视化规范）+ 每图 1-2 句解读
⑤ 操作审查表：证伪测试全表（含被排除项）
⑥ 建议：P0/P1/P2 分级，每条一句话
```

**⓪ 目标达成区写法**（数据来自第 1 步的 `get_entity_metadata(entity='aiGroup')` 与第 2 步的实际表现）：

- 上半部分为**托管组目标设置清单**：目标类型（targetTypeText，如"保持订单稳定/优化 ROAS/促进增长"）、目标 ACOS（targetAcos）、AI 人格（aiPersonality，只显示数字等级）、行动空间开关（预算分时/预算再分配/否定投放/竞价优化等，只列开启项）、组日预算（totalBudget）。每项一行，纯文字标签样式。
- 下半部分为**目标 vs 实际进度条**：每个可量化目标一条进度条——实际值/目标值换算完成率，进度条按完成率填充，颜色规则：≥100% 绿（达成）、70–99% 黄（接近）、<70% 红（未达成）。典型条目：ACOS（实际/目标，注意方向——ACOS 是越低越好，完成率=目标÷实际）、日预算利用（日均花费/组日预算）、订单稳定性（托管后日均订单/托管前基线日均）。目标类型不可量化的（如"保持订单稳定"），以订单达成为代理指标并注明。
- 该区只陈述"目标是什么、完成到哪"，**不下责任结论**——责任判定仍在下方 verdict 区，避免读者把"未达目标"直接误解为"AI 有责"。

语言规范：短句；数字带单位；"可能导致"和"导致"必须区分；每个结论句都能指向一张图表或一行日志；全文客户 1 分钟读完主干。

## 可视化规范（论据图必须遵守）

**每张图只回答一个问题，且该问题必须是理解"原因"的必经环节。** 图表类型限定：

1. **前后对比双序列图**（柱+线，黄虚线分隔托管前后）——回答"什么时候开始恶化、恶化了多少"。两个时期用蓝/红两色，虚线标注 AI 开启时刻。这是默认第一张图。
2. **错位对比分布图**（分组柱状，横轴为小时/广告位/搜索词分层，关键区间加背景高亮）——回答"损失集中在哪"。例如 OOB 次数按小时分布、午高峰高亮，一眼看出"AI 在最需要钱的时候没钱"。
3. **瀑布式拆解条**（订单变化的逐项加减条，正负双色横条）——回答"订单去哪了"（长尾消退 X + 头部缩水 Y − 新增补进 Z = 净变化）。
4. **操作时间轴**（时间轴上一条条标注 AI/人工操作 + 指标曲线叠加）——回答"操作与恶化的时序关系"。

**禁止**：热力图、雷达图、3D 图、双 Y 轴超过 2 序列、与结论无直接关系的装饰性图表。单页图数 ≤4；图注说明"看什么"而不描述数据。用纯 HTML/CSS（div 条形）或内联 SVG 实现，不依赖外部图表库，保证单文件可离线打开。

## 陷阱清单（来自实战，违反会产生错误归因）

- **搜索词默认只回第一页** → 长尾词全漏，结论偏向"头部异常"。必须循环分页到 hasNextPage=false。
- **被否 ≠ 有害**：否定是 campaign 级的；被否词可能恰是在别的 campaign 出单的"分流"操作。先查同词根在其他 campaign 的表现再下结论。
- **T+2 归因延迟**：托管后末段日期数据不完整，直接对比会放大跌幅。
- **异常基线**：托管前一周可能是超常周（先对比再前一周校验）。
- **小时数据时区**：hourly 数据是店铺当地时间还是 UTC 要先验证（用"深夜时段是否近零花费"校验），错一个时区,"凌晨清零预算"会被误读成"白天掐流量"。
- **internal vs amazon ID**：操作日志 resourceIds 用 amazon ID；传 internal ID 不报错但返回 0 行——空结果先查 ID 空间再下"无日志"结论。
- **"AI 调了很多次"≠"AI 造成影响"**：调价 100 次但幅度 ±5% 且 CPC 持平 = 无害噪音，判定为排除（量级不匹配）。
- **同时段多因素**：季节切换与托管同时发生时，用"分时段/分广告位是否同步下滑"区分：操作伤害是局部的，大盘因素是全面同步的。

## 报告产出要求

- 文件：`output/<diagnosis-name>/index.html`，单文件，无外部依赖，中文。
- 报告末尾附数据来源与方法说明（3 行以内：证伪测试框架 + 数据工具 + 归因延迟说明）。
- 若判定为"可能原因"（未通过全部三条件），在报告中用明显标识（如黄色标签）标注，不与"导致因素"混排。
