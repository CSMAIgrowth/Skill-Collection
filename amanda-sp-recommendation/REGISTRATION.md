# Skill 登记卡

## 基本信息

| 字段 | 值 |
|------|-----|
| **名称** | Amanda-托管组参数优化 |
| **英文标识** | `amanda-sp-recommendation` |
| **版本** | 1.1.0 |
| **引擎版本** | v9.1 (冻结) |
| **作者/维护人** | Amanda |
| **类别** | 推荐分析 / 托管组配置优化 |
| **适用范围** | SP (Sponsored Products) AI 托管组 |

## 价值

基于 v9.1 case-based reasoning 引擎，从店铺运行中的 SP 托管组提取实时特征，对比历史最优配置样本池，输出 13 个参数的可执行调整建议。帮助运营快速定位配置优化方向，减少人工试错成本。

## 触发条件

**适用场景:**
- 用户问"托管组怎么调"、"推荐配置"、"skill recommendation"
- 用户问"分析我的托管组"、"帮我看看配置"
- 需要批量分析 SP 托管组配置优化方向

**不适用场景:**
- 创建新托管组 → 使用 `sparkx-create-ai-group`
- 直接修改广告配置 → 使用 `sparkx-edit-ai-group`
- SB/SD 托管组分析 → 本 skill 仅支持 SP
- 广告效果查询 → 使用 `sparkx-query-ads-performance`

## 输入/输出

**输入:**
- SP 托管组列表 (JSON, 来自 MCP `get_entity_metadata(entity="aiGroup")`)
- ASIN 产品数据 (JSON, 来自 MCP `get_entity_metadata(entity="asin")`)
- 训练样本池 (`pool_min.pkl.gz`, 4.6MB)

**输出:**
- 推荐报告 (JSON), 包含每个托管组的:
  - 状态 (OK / DEGRADED / INSUFFICIENT 等)
  - 13 参数当前值 vs 推荐值
  - 显著性、置信度、lift 值
  - 可执行的调整建议

## 运行依赖

| 依赖 | 版本/说明 |
|------|----------|
| Python | 3.8+ |
| pandas | 2.x (实测 2.3.3) |
| numpy | 2.x (实测 2.5.4) |
| 引擎脚本 | `scripts/query_engine.py` (v9.1 冻结版) |
| 训练样本池 | `scripts/pool_min.pkl.gz` (SP 历史干净样本) |
| MCP 工具 | `get_user_authorized_context`, `get_entity_metadata`, `get_ads_perf` |
| 写入工具 | `sparkx-edit-ai-group` (执行调整时使用) |

## 读写及数据边界

- **读取**: MCP 托管组配置、ASIN 元数据、广告性能数据
- **写入**: 仅输出 JSON 报告; 不直接修改广告配置
- **数据边界**: 仅分析 `aiStatus=1` (运行中) 且 `campaignType=sponsoredProducts` 的托管组
- **模型池**: 历史清洗后的 SP 托管组样本 DataFrame, 每行 = 一个历史样本 (18 特征 + 13 参数 + 性能指标)

## 限制

1. **仅 SP 广告**: SB/SD 托管组会被自动过滤
2. **BSR 口径**: `asinBsr` 必须为百分位 (0-100), 非绝对排名
3. **部分特征依赖外部数据**: 趋势、季节性、促销阶段等特征当前数据不足, 自动设为 None 不参与查询
4. **targetType 映射**: 1=imitation (跟卖型), 2=differentiation (差异型); tt=3 为活动冲量
5. **建议门槛**: 显著需 lift>0.1, 边缘需 lift>0.05, 才纳入可执行建议
6. **数据不足时**: status=INSUFFICIENT 时不提供可靠建议, 不等同于"无需调整"

## 交付与验收

| 项目 | 状态 |
|------|------|
| SKILL.md | ✅ 完成 |
| 推荐脚本 | ✅ `scripts/recommend.py` |
| 查询引擎 | ✅ `scripts/query_engine.py` (v9.1 冻结) |
| 特征定义 | ✅ `references/feature_definitions.md` |
| 算法规格 | ✅ `references/algorithm_spec.md` |
| 值映射表 | ✅ `references/value-mapping.md` |
| 训练样本池 | ✅ `scripts/pool_min.pkl.gz` |
| 登记卡 | ✅ 本文档 |
| 实测验收 | ⏳ 待提供脱敏真实输入-输出验收记录 |

## 模型池说明

`pool_min.pkl.gz` 是引擎的离线训练产物:
- **来源**: 历史 SP 托管组清洗后的干净样本
- **内容**: DataFrame, 每行 = 一个历史托管组样本 (18 Tier 特征 + 13 配置参数 + sales/cost/impressions 等性能指标)
- **大小**: ~4.6MB (gzip 压缩 pickle)
- **用途**: 引擎通过特征匹配在池中找到相似样本, 提取 top 30% 的配置分布来推荐最优参数
- **非实时元数据**: 不包含任何当前运行中的客户数据
