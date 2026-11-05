# SparkX MCP 取数要点（作者经验，客户信息已移除）

执行第 0、4、5、6 步取数前先读本文。以下为作者提交的接口使用经验；本次发布未独立复跑，具体接口行为以当次返回与授权环境为准。

## 分页规则

- productAd、campaign、adGroup、automationRule 等 get_entity_metadata 类接口：返回中的 hasNextPage 字段**可能为空**，不代表没有下一页。
- 正确做法：循环翻页直到「本页返回行数 < pageSize」；每批过滤列表控制在约 40 个 ASIN / 50-200 个活动 ID（批次过大：ASIN 列表会被服务端截断只匹配部分，campaign ID 列表过长直接 business_error）。
- 分页风险：只取首批结果会低估活动和商品广告数量，必须核对分页完整性。

## 各实体查询要点

- get_operation_log：参数格式为 entities（如 ["campaign","target","productAd"]）+ resourceIds（[{"idEntity":"campaign","ids":[...]}]）。**活动级日志不包含目标级/商品级动作**，审计 AI 行动空间时三个层级都要取。
- get_ads_perf：campaign.campaignId_ 用的是 Amazon 长 ID（字符串），campaign 元数据接口返回的 amazonCampaignId 与 campaignId（短 ID）是两套 ID；跨源 join 前统一转字符串再比。
- automationRule：只返回活动「启用了哪些规则」的清单（enabledRuleNames/enabledRuleTypes），不含规则模板参数；活动级规则为空 ≠ 全部层级无规则，托管组级规则模式要看 aiGroup 实体的规则配置字段（有值 = 人工规则 RBA 模式，缺失 = 纯 AI 模式）。
- asin 级效果数据（factEntity=asin）是子体直接归因；活动级是整活动口径（含少量其他产品线），报告需注明占比。

## 归属验证

- 同租户同站点多 profile：对每个候选跑 productAd + asin 过滤，行数 >0 才是正确 profile；全 0 则停下问用户。
- 禁止用 campaignName like 代替（会拉到同品牌其他产品线，曾导致「AI 节流致死」的错误结论案例）。
