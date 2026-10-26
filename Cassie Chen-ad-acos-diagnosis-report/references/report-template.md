# 报告模板

> 公开版说明：案例标识、经营数据及操作轨迹已移除；数值示例为独立构造的虚构演示或字段占位，不代表真实客户结果。诊断时须使用当前授权数据，不能套用示例结论。


## HTML 完整模板

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{campaign_name} 流量质量恶化责任归因报告</title>
<style>
@page{size:A4;margin:13mm}
*{box-sizing:border-box}
body{margin:0;background:#e9edf1;color:#24272b;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}
main{max-width:1040px;margin:24px auto;background:white;padding:48px 56px;box-shadow:0 5px 24px #1f29371c}

/* 标题 */
h1{font-size:30px;margin:0 0 8px;border-bottom:4px solid #c94035;padding-bottom:13px}
.meta{font-size:13px;color:#667085;margin:0 0 20px}

/* 一句话结论 */
.verdict{border:2px solid #c94035;padding:19px 21px;background:#fff8f7}
.verdict h2{border:0;margin:0 0 10px;padding:0;font-size:21px;color:#c94035}
.verdict p{margin:8px 0}

/* KPI 概览 */
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#dfe3e7;margin:18px 0}
.kpi{background:#f5f6f7;padding:15px}
.kpi b{font-size:24px;display:block;color:#c94035}

/* 背景信息 */
.background{background:#f5f7f9;border:1px solid #dde2e7;padding:16px 18px;margin:18px 0}
.background h3{margin:0 0 10px;font-size:16px;color:#c94035}
.background p{margin:6px 0;font-size:13px}
.background table{width:100%;font-size:12px;border-collapse:collapse;margin:10px 0}
.background th,.background td{border:1px solid #d8dde2;padding:6px 8px;text-align:left}
.background th{background:#eef0f2}

/* 流程链 */
.chain{display:grid;grid-template-columns:1fr 32px 1fr 32px 1fr;align-items:center;margin:18px 0}
.chain .node{border:1px solid #d8dde2;background:#f8f9fa;padding:12px;text-align:center;min-height:78px;display:flex;align-items:center;justify-content:center;font-size:13px}
.chain .arrow{text-align:center;color:#c94035;font-size:24px;font-weight:700}

/* 章节标题 */
h2{font-size:21px;border-left:5px solid #c94035;padding-left:11px;margin:42px 0 14px}
.rank{display:inline-flex;width:34px;height:34px;border-radius:50%;background:#c94035;color:white;align-items:center;justify-content:center;margin-right:8px}

/* 公式框 */
.formula{background:#f5f7f9;border:1px solid #dde2e7;padding:12px 15px;font-size:13px;margin:14px 0}
.formula b{color:#c94035}

/* 图表 */
figure{position:relative;margin:18px 0 26px;break-inside:avoid}
figure img{width:100%;display:block;border:1px solid #dfe3e7}
figcaption{font-size:12px;color:#667085;margin:6px 0}
.grade{position:absolute;right:10px;top:10px;background:#24272b;color:white;padding:4px 9px;border-radius:3px;font-size:12px;z-index:2}

/* 结论框 */
.result{font-size:16px;font-weight:700;border:1px solid #c94035;padding:12px 15px;background:#fff8f7;margin:12px 0}

/* 洞察框 */
.insights{margin:14px 0}
.insight{padding:10px 14px;background:#f8f9fa;border-left:3px solid #3498db;margin:8px 0;font-size:13px}
.insight b{color:#3498db}

/* 过渡框 */
.transition{margin:22px 0;padding:12px 15px;background:#f5f7f9;border-top:1px solid #d8dde2;border-bottom:1px solid #d8dde2;font-size:13px}

/* 表格 */
table{border-collapse:collapse;width:100%;font-size:12px;margin:12px 0}
th,td{border:1px solid #d8dde2;padding:7px;vertical-align:top}
th{background:#eef0f2;text-align:left}

/* 数据边界 */
.callout{padding:12px 15px;border-left:4px solid #b96717;background:#fff0e0;margin:16px 0;font-size:13px}
.callout b{color:#b96717}

/* 页脚 */
footer{font-size:11px;color:#667085;text-align:center;margin-top:32px;padding-top:16px;border-top:1px solid #dfe3e7}
</style>
</head>
<body><main>

<!-- 1. 标题 -->
<h1>{campaign_name}｜流量质量恶化责任归因报告</h1>
<p class="meta">{platform} · {campaign_type} · 基准期 {baseline_start}至{baseline_end} · 托管期 {analysis_start}至{analysis_end} · 目标ACOS {target_acos}% · 时区 {timezone} · 币种 {currency}</p>

<!-- 2. 背景：保持简短 -->
<div class="background">
<h3>背景与分析视角</h3>
<p><b>托管组目标设置：</b>AI托管启动时间 {ai_start_time}，目标ACOS {target_acos}%，初始日预算 ${initial_budget}，初始竞价策略 {initial_bid_strategy}。启用动作：{ai_action_space}。</p>
<p><b>分析视角：</b>ACOS/CVR变化是结果。本报告重点回答“{traffic_quality_question}”，证据链为异常日期/时段 × 完整操作日志 × 竞价预算 × 广告数据。</p>
<p><b>结果差距：</b>ACOS {baseline_acos}%→{analysis_acos}%；CVR {baseline_cvr}%→{analysis_cvr}%；订单 {baseline_total_orders}→{analysis_total_orders}。两期总花费分别为 ${baseline_total_spend} / ${analysis_total_spend}。</p>
</div>

<!-- 3. 结论：先机制，后责任 -->
<section class="verdict">
<h2>结论：{main_conclusion}</h2>
<p><b>机制一（{mechanism_1_name}）：</b>{mechanism_1_conclusion}</p>
<p><b>机制二（{mechanism_2_name}）：</b>{mechanism_2_conclusion}</p>
<p><b>机制三（{mechanism_3_name}）：</b>{mechanism_3_conclusion}</p>
<p><b>责任：</b>{responsibility_conclusion}</p>
</section>

<!-- 4. KPI概览 -->
<div class="kpis">
<div class="kpi"><b>{baseline_acos}%→{analysis_acos}%</b>ACOS +{acos_change_pp}pp（目标{target_acos}%）</div>
<div class="kpi"><b>{baseline_cvr}%→{analysis_cvr}%</b>CVR {cvr_change_pct}%</div>
<div class="kpi"><b>{baseline_orders}→{analysis_orders}</b>订单 {orders_change_pct}%</div>
<div class="kpi"><b>{baseline_cpc}→{analysis_cpc}</b>CPC {cpc_change_pct}%</div>
<div class="kpi"><b>{baseline_spend}→{analysis_spend}</b>总花费 {spend_change_pct}%</div>
<div class="kpi"><b>{baseline_sales}→{analysis_sales}</b>总销售额 {sales_change_pct}%</div>
</div>

<div class="formula"><b>数据说明：</b>ACOS/CVR/CPC均从<b>总量</b>重算（不平均每日百分比）。基准期共{baseline_days}天，托管期共{analysis_days}天。机制KPI须单独注明可比窗口，例如“基准7天 vs 托管7天，两期花费分别为$X/$Y”。</div>

<!-- 可选：机制因果链，不重复结果算术 -->
<div class="chain">
<div class="node">{chain_1_action}</div><div class="arrow">→</div>
<div class="node">{chain_2_traffic}</div><div class="arrow">→</div>
<div class="node">{chain_3_conversion}</div>
</div>

<!-- 5. Top N机制问题：按因果贡献排序 -->
<h2><span class="rank">1</span>{problem_1_title}</h2>
<figure><div class="grade">{grade_1} {grade_type_1}</div><img src="{chart_1}" alt=""><figcaption>{caption_1}</figcaption></figure>
<p>{problem_1_analysis}</p>

<div class="insights">
<div class="insight"><b>Insight 1｜{insight_1_title}</b>{insight_1_content}</div>
<div class="insight"><b>Insight 2｜{insight_2_title}</b>{insight_2_content}</div>
</div>

<p class="result">结论：{problem_1_conclusion}</p>

<!-- 重复问题2-N -->

<!-- 6. AI还是人工 -->
<h2>AI还是人工</h2>
<table>
<thead><tr><th>检查项</th><th>证据</th><th>结论</th></tr></thead>
<tbody>
<tr><td>{check_1_item}</td><td>{check_1_evidence}</td><td><b>{check_1_conclusion}</b></td></tr>
<tr><td>{check_2_item}</td><td>{check_2_evidence}</td><td><b>{check_2_conclusion}</b></td></tr>
<tr><td>{check_3_item}</td><td>{check_3_evidence}</td><td><b>{check_3_conclusion}</b></td></tr>
</tbody>
</table>

<!-- 7. 动作建议 -->
<h2>动作建议</h2>
<table>
<thead><tr><th>动作</th><th>触发条件</th><th>验证与回滚</th></tr></thead>
<tbody>
<tr><td>{action_1}</td><td>{trigger_1}</td><td>{verify_1}</td></tr>
<tr><td>{action_2}</td><td>{trigger_2}</td><td>{verify_2}</td></tr>
<tr><td>{action_3}</td><td>{trigger_3}</td><td>{verify_3}</td></tr>
</tbody>
</table>

<!-- 8. 数据边界 + 页脚 -->
<div class="callout"><b>数据边界：</b>{data_boundary}</div>
<div class="callout"><b>最终通俗结论：</b>{plain_conclusion}</div>

<footer>数据截止 {data_cutoff} · 报告重构 {report_date} · 数据源：{data_sources}</footer>

</main></body></html>
```

## 各部分编写规范

### 背景信息

保持紧凑：
1. **托管组目标设置** — 时间、目标ACOS、初始预算、竞价策略、AI动作空间
2. **分析视角** — 明确本报告回答的是流量质量机制，而非重复ACOS算术
3. **结果差距** — 用一小段交代两期核心指标，不展开逐日解释

### 结论

按因果顺序：
1. **机制一/二/三** — 具体操作如何改变时段、位置、词池和转化
2. **责任** — AI、人工、系统分别做了什么
3. **可选因果链** — 操作 → 流量变化 → 转化结果；每条链只出现一次

### KPI概览

- 6个指标：ACOS、CVR、订单、CPC、总花费、总销售额
- 格式：`基准值→分析值` + `指标名` + `变化幅度`
- **必须紧跟数据说明框**，明确是总量还是日均

### 机制问题章节

每个问题：
1. **标题** — 直接写机制，如“高转化时段被降到底价”，不写“CVR下降是ACOS上升原因”
2. **证据等级** — 按具体论断分级；操作事实与位置推断分别标注
3. **图表** — 优先：操作小时分布×基准转化曲线、预算阶梯×OOB、同词CVR、词池结构
4. **分析段落** — 操作事实 → 机制解释 → 数据结果 → 替代解释排除
5. **Insight框** — 2-4个关键发现，包含反向验证或干扰项排除
6. **结论框** — 明确该机制是根因、放大器还是下游结果

### AI还是人工表格

至少3行：
- 定向竞价操作来源
- 预算/模式切换操作来源
- 人工操作是否存在

### 动作建议表格

三列：动作、触发条件、验证与回滚

### 数据边界

必须说明：
- 日志是否完整分页、实际日期覆盖范围
- 小时级/搜索词/placement 数据窗口和缺失情况
- 无 placement 时，位置结论属于间接推断
- 否定词匹配类型不可见时，误伤排查采用潜在影响上限
- 小样本搜索词和小时数据的随机性
- 缺少什么数据，因此未做什么分析，不做伪精确归因
