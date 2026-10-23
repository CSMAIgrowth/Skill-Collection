# SparkX MCP 字段与调用参考（否词场景）

本文档记录在否词分析中实测有效的调用方式与易错点。字段名随 MCP 版本可能变化，报错信息会给出可用字段清单，以报错为准。

## 1. 工具清单

| 用途 | 工具 |
|------|------|
| 授权账户 / profile 列表 | `get_user_authorized_context` |
| 实体元数据（商品、广告活动、广告组、关键词、否词等） | `get_entity_metadata` |
| 搜索词 / 广告活动表现 | `get_ads_perf` |
| 变更历史 | `get_operation_log` |
| 写操作 | 视 MCP 实际提供而定（如 `batch_update_ads`），不存在时不得虚构 |

## 2. ID 双轨制（最高频错误源）

同一实体存在两套 ID：

| 字段 | 出现位置 | 示例 |
|------|---------|------|
| `adGroupId` | 元数据接口 | `142596476`（平台内部，短整数） |
| `adGroupId` | `get_ads_perf` 返回行 | `517547567010529`（Amazon ID，长整数） |
| `amazonAdGroupId` | 元数据接口 | `517547567010529` |

同理存在 `campaignId`（内部）与 `amazonCampaignId`；`keywordId` 与 `amazonKeywordId`。

**规则**：`get_ads_perf` 的 `filters` 使用 **Amazon ID**；`get_entity_metadata` 的 `filters` 使用**内部 ID**。

映射方法：

```
get_entity_metadata(entity='adGroup', filters={'adGroupId': {'in': [<内部ID...>]}},
                    select 或全字段，取 amazonAdGroupId)
```

## 3. 搜索词查询不能 join 商品维度

`get_ads_perf(factEntity='searchTerm')` 若 `select` 或 `filters` 中出现 `productAd` / `asin` / `productLine`，会返回：

```
UNSUPPORTED_PERFORMANCE_JOIN: searchTerm performance cannot be joined to
productAd, ASIN or productLine metadata in one query.
```

正确路径：productAd → adGroup（内部 ID）→ amazonAdGroupId → 按 `adGroup.adGroupId_` 过滤搜索词。

> 注意：按广告组过滤得到的是**广告组级指标**，不是按商品归因的指标。一个广告组含多 ASIN 时，不能把花费拆到单个 ASIN。

## 4. 字段命名规则

### 4.1 当前实体用 `p.` 前缀

`select` 中描述 fact entity 自身字段时必须用 `p.`，不能用实体名：

| 错误写法 | 正确写法 |
|---------|---------|
| `searchTerm.searchTerm_` | `p.query_` |
| `p.searchTerm_` | `p.query_` |
| `target.targeting_` | （不存在，改用 `p.matchType_` / `p.targetId_`） |

`factEntity='searchTerm'` 可用的 `p.` 字段：
`adGroupId_`、`campaignId_`、`campaignType_`、`matchType_`、`profileId_`、`queryCategory_`、`query_`、`targetId_`。

### 4.2 关联实体用 `实体名.` 前缀

可用前缀（大小写敏感）：
`adGroup`、`aiGroup`、`asin`、`audience`、`automationRule`、`campaign`、`keywordPlacement`、`parentAsin`、`placement`、`portfolio`、`productAd`、`productLine`、`profile`、`sku`、`target`。

示例：`campaign.campaignName_`、`campaign.campaignState_`、`adGroup.adGroupName_`、`adGroup.adGroupState_`。

**不存在的字段**（会报 `unknown field`）：`adGroup.amazonAdGroupId_`、`target.targeting_`。

### 4.3 `queryType`

`factEntity='searchTerm'` **仅支持 `queryType='keyword'`**，传 `auto` 会报 `not supported`。

该 `keyword` 结果已包含全部匹配类型：`exact`、`phrase`、`broad`、`CLOSE-MATCH`、`LOOSE-MATCH`、`SUBSTITUTES`、`COMPLEMENTS`、`CATEGORY`、`ASIN`。不要因为「只看关键词投放」而漏掉自动投放跑出的搜索词。

### 4.4 `factEntity='target'`（投放目标维度）

ASIN 级数据只能从这里取，搜索词报表里没有。

可用 `p.` 字段仅 8 个：

```
adGroupId_  campaignId_  campaignType_  matchType_  profileId_  targetId_  target_  targetingType_
```

不存在 `p.targeting_`（报 `that fact table has no such column`）。

`matchType` 取值与 `target` 内容：

| matchType | 中文 | target |
|-----------|------|--------|
| `asinSameAs` | 商品-精准 ASIN | ASIN |
| `asinExpanded` | 商品-扩展 ASIN | ASIN |
| `category` | 商品-品类 | 品类名 |
| `exact` / `phrase` / `broad` | 关键词-精准/词组/广泛 | 关键词文本 |
| `closeMatch` / `looseMatch` / `substitutes` / `complements` | 自动-紧密/宽泛/同类/关联 | 空字符串 |
| `THEME` / `TARGETING_EXPRESSION` | SB 主题 / 表达式 | 主题标识或描述 |

按 ASIN 筛选：

```
filters={'p.matchType_': {'in': ['asinSameAs', 'asinExpanded']}}
```

> 搜索词报表中 `matchType='ASIN'` 的行表示「该搜索词由商品投放匹配而来」，`query` 仍是顾客搜索词，**不是 ASIN**。实测 51 行中 0 行符合 10 位 ASIN 格式。

## 5. 分页与大结果

- `pageSize` 上限 500；用 `meta.hasNextPage` 判断是否取完。
- 单页结果过大时会被自动落盘为文本文件（JSON），用脚本读取。
- 增加 `select` 维度会**改变分组粒度**（例如加入 `targetId_` 后，同一搜索词会按投放目标拆成多行），行数会变。做总量校验时固定同一组 `select`。
- 未取完全部分页不得开始分析。

## 6. 数据校验方法

```
# 1. 聚合总量（不带 select）
get_ads_perf(factEntity='searchTerm', filters=<同范围>,
             metrics=['Impressions','Clicks','Spend','Sales','Conversions'],
             pageSize=10)
# 2. 分页明细逐页累加
# 3. 四项指标（Spend / Clicks / Sales / Conversions）必须完全相等
```

不相等说明分页遗漏、过滤条件不一致或维度拆分导致重复，必须排查。

## 7. 现有否词

```
get_entity_metadata(entity='negativeKeyword',
                    filters={'campaignId': {'in': [...]}},
                    pageSize=500)
```

关键字段：`keywordText`、`matchType`（`negativeExact` / `negativePhrase`）、`businessType`（`campaign` / `adgroup`）、`negativeKeywordState`（`enabled` / `paused` / `archived`）、`adGroupId`、`campaignId`。

`businessType='campaign'` 的否词作用于该活动下所有广告组，加否词前必须查清，避免把单组建议误扩到全活动。

## 8. 正向关键词

```
get_entity_metadata(entity='keyword', filters={'campaignId': {'in': [...]}})
```

关键字段：`keywordText`、`matchType`、`keywordState`、`keywordBid`、`keywordCurrentBid`、`adGroupId`。

否词前必须比对，见 SKILL.md Step 4.1。

## 9. 操作日志

```
get_operation_log(profileIds=[...], dateStart='YYYY-MM-DD', dateEnd='YYYY-MM-DD',
                  entities=['campaign'], resourceIds=[{'idEntity':'campaign','ids':[<内部ID>]}])
```

- 时间跨度上限 90 天。
- 关键词级暂停不一定出现在 `entities=['campaign']` / `['adGroup']` 的日志中；查不到不等于没发生，以元数据当前状态为准。

## 10. 写操作上限与路由（`batch_update_ads`）

三条路由，payload 结构不同，**不得混批**：

| 路由 | entity + action | 层级 | 数组 | 1 项 = 几条 | 单批上限 |
|------|----------------|------|------|-----------|---------|
| R1 | `negativeKeyword` + `create` | **仅 SP 广告活动级** | `data` | 多条 | 可远超 200 |
| R2 | `negativeKeyword` + `copy` | 广告组级 | `target` | 1 条 | 200 |
| R3 | `negativeTarget` + `create` | **仅广告组级** | `target` | 1 条 | 200 |

通用限制：

| 项目 | 限制 |
|------|------|
| 单次同步写操作 | **最多 200 个数组项**（`data` / `target` 各自上限） |
| `keywordText` | ≤ 80 字符，不含 `/`，空白字符会被保留 |
| 否词 `matchType` | 仅 `negativeExact` / `negativePhrase` |
| ASIN `expression` | 只能 1 个元素；`asinSameAs` 为 10 位字母数字 |
| 校验模型 | all-or-nothing：任一项失败整批被拒，无任何写入 |
| SB 否词 | 不支持 `state=paused`，传入会整批被拒 |
| 确认流程 | create / copy 均无需 confirmToken；`updateStatus` 涉及 `archived` 时才需两阶段确认 |

> ⚠️ `negativeKeyword + create` **只支持 SP 广告活动级**。广告组级否词必须走 `copy`（`businessType='adgroup'` + `target` 数组）。把 `businessType='adgroup'` 放进 `data` 项不会生效。

### R1：关键词否词 · 广告活动级

```json
{
  "entity": "negativeKeyword",
  "action": "create",
  "request": {
    "profileIds": [2950993281269288],
    "data": [
      {
        "profileId": "2950993281269288",
        "campaignType": "sponsoredProducts",
        "campaignId": 44400757,
        "negativeKeywords": [
          {"keywordText": "ear buds", "matchType": "negativeExact"}
        ]
      }
    ]
  }
}
```

### R2：关键词否词 · 广告组级

```json
{
  "entity": "negativeKeyword",
  "action": "copy",
  "request": {
    "profileIds": [2950993281269288],
    "businessType": "adgroup",
    "target": [
      {
        "id": 133264344,
        "profileId": "2950993281269288",
        "campaignType": "sponsoredProducts",
        "keywordText": "ear buds",
        "matchType": "negativeExact"
      }
    ]
  }
}
```

### R3：否定商品（ASIN / 品牌）

```json
{
  "entity": "negativeTarget",
  "action": "create",
  "request": {
    "profileIds": [2950993281269288],
    "businessType": "adgroup",
    "target": [
      {
        "id": 444796523073589,
        "profileId": "2950993281269288",
        "campaignType": "sponsoredProducts",
        "expression": [{"type": "asinSameAs", "value": "B0D2XRXNGY"}]
      }
    ]
  }
}
```

要点：

- `profileId` 在数组项内是**字符串**，在 `request.profileIds` 中是**整数**。
- `campaignId` / `adGroupId` / `target.id` 用 `get_entity_metadata` 返回的**内部 ID**，不是 Amazon ID（与查询接口相反）。
- R2 / R3 首次使用时先提交 1 条试跑，验证路由可用后再放大整批。

### 分批建议

- 硬上限 200 项，但**不要用满**：同步写耗时、超时后状态难恢复、all-or-nothing 放大失败面。
- 建议 ≤50 条用 1 批；51~300 条按 50~100/批；>300 条按 100/批。
- R1 按广告活动归组，同一活动不得跨批；R2 / R3 按 200 上限切批。
- 用 `scripts/build_negative_batches.py` 生成批次，脚本会自动判定路由并分别输出 payload。

## 11. 常见报错速查

| 报错 | 原因 | 处理 |
|------|------|------|
| `UNSUPPORTED_PERFORMANCE_JOIN` | searchTerm 与 productAd/asin 混查 | 改为 adGroup 过滤 |
| `Unknown field prefix 'searchTerm'` | 用了实体名作前缀 | 改用 `p.` |
| `that fact table has no such column` | `p.` 字段名猜错 | 按报错给出的可用字段清单改 |
| `unknown field 'xxx_'` | 关联实体字段不存在 | 去掉该字段 |
| `queryType=auto is not supported` | searchTerm 只支持 keyword | 改用 keyword |
| `Date range cannot exceed 90 days` | 跨度超限 | 拆分区间 |
| 过滤后 `rowCount: 0` | 多因 ID 体系用错 | 检查是否用了内部 ID |
