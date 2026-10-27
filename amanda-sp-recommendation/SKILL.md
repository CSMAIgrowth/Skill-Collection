---
name: amanda-sp-recommendation
description: 'Analyze running SP (Sponsored Products) AI managed groups and recommend configuration adjustments using the Skill Extraction v9.1 engine. Reads store data via MCP (managed groups, ASINs, performance), extracts Tier 0-3 features, queries the recommendation engine, and outputs actionable parameter adjustments. SP only — not for SB/SD groups. Use when the user asks "托管组怎么调", "推荐配置", "skill recommendation", "managed group adjustment", "分析我的托管组", "帮我看看配置". Not for creating new managed groups (use sparkx-create-ai-group) or editing ads directly (use sparkx-edit-ai-group).'
metadata:
  version: 1.1.0
  model_version: v9.1
  scope: SP (Sponsored Products) only
---

# Skill Extraction SP 托管组推荐分析

## 概述

基于 v9.1 查询引擎 (case-based reasoning)，从店铺运行中的 **SP (Sponsored Products)** AI 托管组提取实时特征，对比历史最优配置，输出 13 个参数的可执行调整建议。

**适用范围: 仅 SP 广告**。SB (Sponsored Brands) 和 SD (Sponsored Display) 托管组不在本 skill 范围内。

## 前置条件

- Python 3.8+ 及依赖: `pip install pandas numpy`
- 训练样本池: `pool_min.pkl.gz` (4.6MB gzip pickle, 历史干净样本 DataFrame, 非元数据)
- MCP 工具: `get_user_authorized_context`, `get_entity_metadata`, `get_ads_perf`
- 引擎脚本: `scripts/query_engine.py` (v9.1 冻结版, 1453 行)

**pool_min.pkl.gz 是什么?**
它是引擎的"记忆"——一份历史清洗后的样本池 DataFrame。每行 = 一个历史托管组样本，包含 18 个 Tier 特征 + 13 个配置参数 + 性能指标 (sales/cost/impressions 等)。引擎通过特征匹配在池中找到相似样本，提取 top 30% 样本的配置分布来推荐最优参数。它不是实时元数据，而是离线训练产物。

## 完整工作流

### Step 1: 获取授权店铺

```
CallMcpTool: get_user_authorized_context
→ 获取 profileIds, countryCode, profileName
```

让用户选择要分析的店铺（或全部分析）。

### Step 2: 读取 SP 托管组列表

```
CallMcpTool: get_entity_metadata
  entity: "aiGroup"
  profileIds: [<选定的 profileId>]
  userContext: "读取SP托管组配置用于推荐分析"
```

**仅保留 `campaignType = "sponsoredProducts"` 的托管组**, 跳过 SD/SB 组。

提取每个 SP 托管组的关键信息:
- `aiGroupId`, `aiGroupName`, `targetType`
- `targetAcos`, `aiPersonality`, `totalDailyBudget`
- `aiStatus` (必须为 1, 脚本会过滤非运行中的组)
- `aiActionSettings` 内的全部 11 个 On/Off 参数 (0=Off, 1=On)

> SP 组拥有完整的 13 参数空间 (含 bid 相关 3 个参数)。

**⚠️ 组的 `asin` 字段必须额外反查** (aiGroup 元数据不返回组内 ASIN, 缺失时引擎的产品特征会全部退化为 None, 推荐将按 targetType+预算档一刀切)。

两步反查 (SparkX AI 托管组的活动命名形如 `SparkX AI <组名>`):

```
// Step A: 按 aiGroupId 取该组的广告活动 (campaign 实体支持 aiGroupId 过滤)
CallMcpTool: get_entity_metadata
  entity: "campaign"
  profileIds: [<选定的 profileId>]
  filters: { "aiGroupId": 893922 }
  select: ["campaignId", "campaignName", "aiGroupId"]
  userContext: "反查AI托管组的广告活动"

// Step B: 按活动取组内 ASIN (注意: productAd 不支持 aiGroupId 过滤, 必须走 campaignId)
CallMcpTool: get_entity_metadata
  entity: "productAd"
  profileIds: [<选定的 profileId>]
  filters: { "campaignId": { "in": [<Step A 返回的 campaignId 列表>] } }
  select: ["asin", "campaignId", "adGroupId"]
  userContext: "反查AI托管组内的ASIN"
```

将每组的主推/代表 ASIN 写入 groups.json 该组的 `asin` 字段, 并确保该 ASIN 也存在于 asins.json 中。多 ASIN 组选花费最高或销量最高的代表 ASIN, 引擎按单 ASIN 特征匹配。

> 已实测验证 (2026-10-27, Nakkaa US): aiGroupId=893922 → campaign "SparkX AI NAS01318-KT-QYG" (campaignId 47323422) → productAd 返回 ASIN B0C2V5NM2J, 链路两跳可达。

### Step 3: 读取 ASIN 产品数据

```
CallMcpTool: get_entity_metadata
  entity: "asin"
  profileIds: [<profileId>]
  userContext: "获取产品特征数据用于推荐分析"
```

提取每个 ASIN 的关键字段:
- `asinPrice` → `price_bucket_mode`
- `asinOpenDate` → `lifecycle_stage`
- `asinBsr` → `bsr_bucket`
- `asinFbaQuantity` + `asinFbmQuantity` → `inventory_status`
- `asinTitle` → `category_l1`

### Step 4: 运行推荐脚本

```bash
python scripts/recommend.py \
  --groups groups.json \
  --asins asins.json \
  --model /path/to/pool_min.pkl.gz \
  --marketplace US \
  --output report.json
```

输入 JSON 格式见 [references/feature_definitions.md](references/feature_definitions.md)。

脚本内部流程:
1. 加载引擎 (`pool_min.pkl.gz` → `QueryEngine`)
2. 计算 budget 三分位边界 (复用训练集标准)
3. 对每个托管组:
   - 提取可靠特征 (数据不足的设为 None, 不参与查询)
   - 提取当前 13 参数配置
   - 运行引擎查询 (target_type + 非 None 特征)
   - 对比当前 vs 推荐, 生成调整建议
4. 输出 JSON 报告

### Step 5: 解读与执行

报告结构:
```json
{
  "group_id": 864843,
  "group_name": "电脑支架 test",
  "status": "DEGRADED",
  "pool_n": 200,
  "recommendations": [
    {
      "param": "structPauseCampaignStatus",
      "current": "Off",
      "recommended": "On",
      "significance": "显著",
      "confidence": 0.437,
      "lift": 0.1949,
      "action": "Change structPauseCampaignStatus from Off to On"
    }
  ]
}
```

**解读规则:**
- `significance=显著` + `lift>0.1`: 强建议调整
- `significance=边缘` + `lift>0.05`: 建议调整, 但需结合业务判断
- `significance=弱证据` 或 `证据不足`: 仅供参考, 不建议直接执行
- `status=INSUFFICIENT`: 数据严重不足, 无法给出可靠建议

**执行调整:**
如果用户确认要执行, 使用 `sparkx-edit-ai-group` skill 的 MCP 工具写入修改:
- SP/SB 组 → `save_sp_sb_ai_managed_group` (edit mode)
- SD 组 → `edit_sd_ai_managed_group`

## 特征体系

### 可靠特征 (参与查询)

| 特征 | 数据来源 | 分箱规则 |
|------|---------|---------|
| `price_bucket_mode` | asinPrice | ≥30=高价, 20-30=中高价, 13-20=中价, 8-13=中低价, <8=低价 |
| `lifecycle_stage` | asinOpenDate | <180天=新品冷启动, 180-364=新品成长, 1-2年=成长期, 2-3年=成熟期, ≥3年=老品 |
| `category_l1` | asinTitle 关键词 | mount/bracket/holder→Home, pet/grooming→Pet Supplies, 其他→General |
| `inventory_status` | FBA+FBM库存 | ≥100=冗余, ≥50=充足, ≥20=适中, <20=紧张, 0=缺货 |
| `bsr_bucket` | asinBsr (百分位 0-100) | ≤1%=Best Seller, ≤10%=热销, ≤50%=中等, ≤80%=中下, ≤95%=长尾, >95%=极长尾 |
| `campaign_budget_bucket` | totalDailyBudget | log1p 三分位 (复用训练集边界) |
| `marketplace_id` | countryCode | 直接映射 |

### 不可靠特征 (设为 None, 不参与查询)

以下特征因缺少实时数据源, 默认不参与引擎查询:
- `promo_phase` — 需要大促日历
- `peak_seasons_std` — 需要历史季节性分析
- `variation_bin` — 需要完整变体数据
- `trend_sales/imp/click_bin` — 需要逐日趋势数据
- `b14_ACOS/CTR/CVR/CPC_bin` — 需要 ASIN 级别 14 天表现
- `peak_month` — 需要历史月度分析

当这些数据可通过其他 MCP 工具获取时, 可恢复参与查询。

## 13 参数白名单

引擎推荐的配置参数 (WHITELIST_PARAMS):

| 参数 | 含义 | 值域 |
|------|------|------|
| `acos_bin` | ACOS 分箱 | low/mid_low/mid_high/high |
| `aiPersonality` | AI 性格 | Conservative/Moderate/Balanced/Aggressive |
| `bidAdPlaceStatus` | 广告位竞价调整 | On/Off |
| `bidPerformanceStatus` | 基础竞价优化 | On/Off |
| `bidDaypartStatus` | 分时竞价 | On/Off |
| `budgetDaypartStatus` | 分时预算 | On/Off |
| `budgetDynamicStatus` | 动态预算提升 | On/Off |
| `budgetRedistributeStatus` | 预算重分配 | On/Off |
| `negativeTargetStatus` | 否定投放 | On/Off |
| `structPauseCampaignStatus` | 暂停广告活动 | On/Off |
| `structPauseProductStatus` | 暂停商品 | On/Off |
| `targetHarvestStatus` | 收割投放 | On/Off |
| `targetPausedAddStatus` | 暂停补充投放 | On/Off |

值映射详情见 [references/value-mapping.md](references/value-mapping.md)。

## 注意事项

1. **SP Only**: 本 skill 仅支持 Sponsored Products 托管组, SB/SD 不在范围内
2. **模型路径**: 脚本需要 `pool_min.pkl.gz` 文件, 通过 `--model` 参数指定
3. **引擎版本**: 本 skill 绑定 v9.1 冻结版引擎, 不可与旧版模型混用
4. **数据不足处理**: 特征值为 None 时不参与查询, 引擎自动走降级链
5. **算法详情**: 精简算法规格见 [references/algorithm_spec.md](references/algorithm_spec.md)

## 参考文件

| 文件 | 内容 |
|------|------|
| [REGISTRATION.md](REGISTRATION.md) | Skill 登记卡 (版本、依赖、限制、验收状态) |
| [references/feature_definitions.md](references/feature_definitions.md) | Tier 0-3 特征定义、分箱规则、输入 JSON 格式 |
| [references/algorithm_spec.md](references/algorithm_spec.md) | v9.1 引擎精简算法规格 |
| [references/value-mapping.md](references/value-mapping.md) | 原始值→可读值映射表 (On/Off, personality, bsr, etc.) |
| [scripts/recommend.py](scripts/recommend.py) | 独立推荐脚本 (CLI 入口) |
| [scripts/query_engine.py](scripts/query_engine.py) | v9.1 查询引擎源码 |
