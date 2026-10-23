# 否定商品（ASIN / 品牌）否词规范

本文档说明「否定商品投放」的适用场景、数据来源、写入路由与限制。所有字段与取值均来自实际接口返回，非推测。

## 1. 能不能做

**能，但它和关键词否词是两套完全不同的机制。**

| 维度 | 关键词否词 | 否定商品（ASIN） |
|------|-----------|-----------------|
| 作用对象 | 顾客的**搜索词** | 广告可能出现的**商品详情页** |
| 写入路由 | `negativeKeyword` + `create` / `copy` | `negativeTarget` + `create` / `copy` |
| 层级 | 广告活动级 或 广告组级 | **仅广告组级** |
| 适用广告组 | 关键词投放、自动投放、商品投放均可 | **仅商品投放广告组** |
| 表达式 | `keywordText` + `matchType` | `expression: [{type, value}]` |
| 单批上限 | 活动级可远超 200 条（1 项含多条） | **≤ 200 条**（1 项 = 1 条） |

> 关键约束：`negativeTarget + create/copy` **拒绝关键词投放的广告组**。服务端会校验目标广告组的投放类型，任一目标位不合格则整批不提交。所以在关键词投放组里加 ASIN 否词是无效操作，必须先用元数据确认该组有商品投放目标。

## 2. 候选来源：投放目标报表，不是搜索词报表

这是最容易搞错的一点，已用真实数据验证：

**搜索词报表（`factEntity='searchTerm'`）里拿不到 ASIN。** 该表中 `matchType='ASIN'` 的行（示例账户 7 月共 51 行）表示「该搜索词由商品投放匹配而来」，但 `query` 字段仍然是**顾客输入的搜索词**（如 `shokz openrun pro 2`），不是 ASIN。实测 51 行中符合 10 位 ASIN 格式的为 **0 行**。

正确来源是**投放目标报表**：

```
get_ads_perf(
  factEntity='target',
  filters={'p.matchType_': {'in': ['asinSameAs', 'asinExpanded']}},
  select=['p.target_','p.matchType_','p.targetId_','p.campaignId_','p.adGroupId_',
          'campaign.campaignName_','adGroup.adGroupName_'],
  metrics=['Impressions','Clicks','Spend','Sales','Conversions'],
  orderBy=[{'field':'Spend','direction':'DESC'}],
  pageSize=500, profileIds=[...])
```

`p.target_` 即 ASIN（如 `B0D2XRXNGY`）。

### 2.1 target 维度的可用字段

`factEntity='target'` 的 `p.` 维度字段只有这些：

```
adGroupId_  campaignId_  campaignType_  matchType_  profileId_  targetId_  target_  targetingType_
```

不存在 `p.targeting_`（会报 `that fact table has no such column`）。

### 2.2 matchType 取值

| matchType | 中文 | target 内容 |
|-----------|------|------------|
| `asinSameAs` | 商品-精准 ASIN | ASIN |
| `asinExpanded` | 商品-扩展 ASIN | ASIN |
| `category` | 商品-品类 | 品类名（如 `Open-Ear Headphones`） |
| `exact` / `phrase` / `broad` | 关键词-精准/词组/广泛 | 关键词文本 |
| `closeMatch` / `looseMatch` / `substitutes` / `complements` | 自动-紧密/宽泛/同类/关联 | 空字符串 |
| `THEME` / `TARGETING_EXPRESSION` | SB 主题 / 表达式 | 主题标识或描述 |

### 2.3 `asinExpanded` 的语义

`asinExpanded` 表示「亚马逊把该投放扩展匹配到了这个 ASIN」。否定它等于**阻断该 ASIN 的详情页曝光**，但不影响原投放目标的其它扩展结果。

因此对 `asinExpanded` 加否词，效果是收窄流量面，而不是关闭投放。若某 `asinExpanded` 的 ASIN 花费高且零转化，加否定是合理的；若整体投放效率差，应优先降 bid 或暂停目标。

## 3. 写入 payload

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

- `id` 是**广告组内部 ID**（`get_entity_metadata` 返回值），不是 Amazon ID。
- `expression` **必须且只能有一个**元素。
- `profileId` 在 `target` 项内是**字符串**，在 `request.profileIds` 中是**整数**。
- 1 个 `target` 项 = 1 条否定商品，所以单批最多 200 条。
- `create` / `copy` **不需要 confirmToken**；只有 `negativeTarget + updateStatus` 且涉及 `archived` 时才需要两阶段确认。

### 3.1 表达式类型

| type | value | 说明 |
|------|-------|------|
| `asinSameAs` | 10 位字母数字 ASIN | 否定单个商品，最常用 |
| `asinBrandSameAs` | 品牌 ID 或品牌名 | 否定整个品牌。**value 不是 ASIN**，传 ASIN 会被拒 |

> `asinBrandSameAs` 影响面极大（屏蔽该品牌所有商品），必须单独提示用户并取得明确授权，不得与普通 ASIN 混在同一批里默认提交。

### 3.2 否定 ASIN 与否定品类的区别

品类否词（`category` 目标）**不能**通过 `negativeTarget` 的 `expression` 直接表达为 `asinSameAs`。若要屏蔽某品类，应使用 `negativeKeyword` 的品类否定或直接在活动层面调整投放策略。不得把品类名当作 ASIN 传入。

## 4. 执行前置核查（强制）

1. **确认广告组是商品投放组**：查 `get_entity_metadata(entity='target', filters={'adGroupId': {'in': [...]}})`，存在 `targetType='product'` 或 `expression` 含 `asinSameAs` / `asinBrandSameAs` / `asinCategorySameAs` 才能加否定商品。
2. **确认 ASIN 有效**：10 位字母数字，大写。扩展匹配出来的 ASIN 可能已下架，下架 ASIN 加否词无实际意义。
3. **确认未重复**：查 `get_entity_metadata(entity='negativeTarget', filters={'campaignId': {'in': [...]}})`，比对 `expression.value`。
4. **确认不是自家商品**：否定自家 ASIN 会导致该 ASIN 详情页不再出现自家广告，属于自伤。先核对商品库。

## 5. 常见错误

| 现象 | 原因 | 处理 |
|------|------|------|
| 整批被拒，提示目标位不合格 | 目标广告组是关键词投放 | 改用关键词否词，或确认投放类型 |
| `p.targeting_` 报无此列 | 字段名错 | 用 `p.target_` |
| 搜索词报表里筛不到 ASIN | 用错了报表 | 改用 `factType='target'` |
| `asinBrandSameAs` 被拒 | value 传了 ASIN | 改传品牌 ID 或品牌名 |
| 提交成功但流量没变 | 该 ASIN 本来就没有曝光，或广告组已暂停 | 先看该目标的 Impressions |

## 6. 决策建议

| 情形 | 建议 |
|------|------|
| `asinSameAs` 目标花费高、零转化、点击充足 | 否定该 ASIN（或降 bid / 暂停目标） |
| `asinExpanded` 的 ASIN 零转化高花费 | 否定该 ASIN，保留原目标 |
| 竞品品牌整体表现差 | 优先 `asinBrandSameAs`，但需用户明确授权 |
| 自家 ASIN 出现在目标里 | **禁止否定**，改为调整投放结构 |
| 广告组是关键词投放 | 不加 ASIN 否词，改用关键词否词或搜索词否词 |
