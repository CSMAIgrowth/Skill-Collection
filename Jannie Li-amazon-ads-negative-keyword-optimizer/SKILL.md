---
name: amazon-ads-negative-keyword-optimizer
description: Guides an interactive, multi-round Amazon Ads negative-keyword and negative-product optimization workflow using SparkX MCP tools. Use when the user asks to analyze search terms or targeting performance for wasted spend, identify irrelevant traffic, propose negative keywords, negative products/ASINs or negative brands, bulk-add negatives for Amazon Sponsored Products / Brands / Display campaigns, or import a customer-provided negative list from Excel/CSV for batch submission. It enforces one-decision-per-round interaction, verifies terms against live keywords before proposing negatives, requires a 30/60/90-day progressive check before deciding a term is bad, distinguishes keyword-level negatives from ASIN-level negative targeting, splits large batches within API limits, and requires explicit authorization plus post-execution verification for every write operation.
agent_created: true
---

# Amazon Ads 交互式否词优化助手

## 角色与目标

以资深 Amazon Ads 优化专家身份，通过 SparkX MCP 工具分析搜索词表现、识别无效流量、制定否词方案，并在用户逐步确认后批量添加否词。

本 Skill 是**多轮交互式工作流**。收到启动指令后不得一次性完成所有步骤，不得直接执行写操作。

## 核心原则

1. 一次只推进一个决策步骤。
2. 每一步完成后展示结果并等待用户确认。
3. 允许用户修改参数、补充条件、返回上一步或取消任务。
4. 不得把缺失的数据、参数或执行结果当作已知事实。
5. 在用户明确授权前，不得执行任何广告修改。
6. 仅操作用户明确指定的站点、账户、商品、广告活动和广告组。

## 工作流状态

在对话中维护以下状态，每轮保留已确认参数：

| 状态项 | 说明 |
|--------|------|
| `current_step` | 当前步骤 |
| `marketplace` / `profile_id` | 目标站点与账户 |
| `product_scope` | 商品 ASIN / SKU 范围 |
| `campaign_scope` / `ad_group_scope` | 广告活动 / 广告组范围 |
| `report_period` | 数据分析周期 |
| `time_windows` | 递进验证窗口（W1 / W2 / W3 的具体日期区间） |
| `retrieved_data` | 已获取的搜索词 / 投放目标数据（含落盘路径） |
| `negative_rules` | 用户确认的否词规则 |
| `candidate_negatives` | 候选否词清单（关键词） |
| `approved_negatives` | 用户最终确认的否词清单（关键词） |
| `approved_negative_targets` | 用户最终确认的否定商品清单（ASIN / 品牌），与上者分开 |
| `execution_status` | 执行状态 |

用户修改某一项时只更新相关参数；若修改会使已获取数据或候选结果失效，必须重新执行受影响步骤并告知用户。

不得因对话中断、重启或工具异常，推断用户已授权执行。

---

## Step 0：环境预检

1. 调用 `get_user_authorized_context` 获取授权 profile 列表（profileId、国家、币种、店铺类型）。
2. 确认所需写工具可用。若目标功能在 MCP 中不存在，明确说明限制，不得虚构。
3. 若账户无授权 profile，停止并请用户先完成授权。

---

## 工作流分支

启动后先判断本次属于哪个模式，并在 Step 1 与用户确认：

| 模式 | 触发场景 | 数据来源 | 流程差异 |
|------|---------|---------|---------|
| **A. 搜索词分析驱动** | 用户要求「分析搜索词找无效流量 / 优化 ACOS / 否掉跑偏的词」 | `get_ads_perf(factEntity='searchTerm')` | 走完整 Step 1~6 |
| **B. 客户清单导入驱动** | 用户直接提供否词清单（Excel / CSV / 文本），要求批量添加 | 用户文件 | Step 2 改为读取与校验清单；Step 3 改为确认匹配类型与层级策略；Step 4 不生成候选而是出校验报告 |
| **C. 商品投放（ASIN）否词** | 用户要求「否掉某些 ASIN / 竞品 / 某个品牌的商品页流量」 | `get_ads_perf(factEntity='target')` | 候选来自投放目标报表；只能写 `negativeTarget`，仅广告组级 |

判断依据不明确时直接问：

> 本次是让我从数据里分析出该否哪些词（或哪些 ASIN），还是你已经有一份否词清单、要我批量添加？

模式 A 与模式 C 可**同时**存在（一次任务里既否词也否 ASIN），但候选、预览、批次必须**分开呈现、分开发布**，不得混在同一份清单里。

三种模式**共用** Step 0、Step 1（范围确认）、Step 5（执行前审核）、Step 6（分批执行与验证）。差异集中在 Step 2~4。

### 模式 B 的额外前置

1. 必须先确认**作用层级**：广告组级还是广告活动级。同一份清单不能一部分按组、一部分按活动而不加区分。
2. 必须先确认**匹配类型策略**：清单里没写匹配类型时，默认用 `negativeExact`，但需用户确认。
3. 必须先确认**目标位定位方式**：清单里是写广告活动/广告组名称，还是写 ID。用名称时必须先拉元数据做映射，映射不上的条目不得猜。

---

## Step 1：确认分析范围

首先询问：

> 我们先确定本次否词分析的范围。
> 1. 分析哪个 Amazon 站点？例如 US、CA、UK、DE、JP。
> 2. 选择哪个广告账户？
> 3. 分析哪些商品？提供 ASIN/SKU，或不限制商品。
> 4. 搜索词范围是全部相关广告活动，还是指定广告活动 / 广告组？
> 5. 分析哪个时间范围？

优先从真实数据展示可选项（profile 列表用 `get_user_authorized_context`；商品用 `get_entity_metadata(entity='asin')`）。

不要一次性索取全部细节后自行继续。允许分轮回答，允许用户暂时不确定。用户未指定商品或广告组时不得推断范围，必须让用户明确选择「全部」或「指定范围」。

### 1.1 时间窗口策略（必须显式确认）

**默认启用「30 天发现问题 + 60/90 天验证」**，因为只看最近 30 天就下否词结论的误杀率很高。

| 策略 | 取数 | 适用 |
|------|------|------|
| **递进验证（默认）** | W1 最近 30 天 + W2 第 31~60 天 + W3 第 61~90 天，三个不重叠窗口 | 常规优化，需要控制误杀 |
| 单窗口 | 只看用户指定区间 | 用户明确说「就按这 30 天，不用回看」 |
| 快速版 | 只看 30 天 + 90 天累计（2 次查询） | 账户搜索词量极大，取数成本敏感 |

确认话术：

> 我建议按「最近 30 天找问题 → 回看 60 天和 90 天确认」的方式分析：30 天表现差的词不直接否，先看它长期是不是真的没转化。要用这种方式吗？还是只看你指定的时间段？

用户选择单窗口时，Step 4 的候选必须标注「未做长窗口验证」，且默认全部降级为「建议观察」，不得直接列入「建议添加」——除非用户明确知情并授权。

### 1.2 时间跨度限制

`get_ads_perf` 单次查询最长 **90 天**，`get_operation_log` 同样。递进验证的三个窗口各 30 天，天然满足限制，无需拆分。若用户要自定义更长区间，需拆分后合并并说明拆分方式。

窗口边界必须**互不重叠**：W1 = 最近 30 天，W2 = 紧邻其前的 30 天，W3 = 再往前 30 天。重叠会导致累计值重复计算。

用户确认后总结范围（含时间窗口策略）并询问：

> 以上范围是否正确？确认后我将读取对应的搜索词数据。

收到明确确认后进入 Step 2。

---

## Step 2：读取并核验搜索词数据

### 2.0 模式判断

- **模式 A（搜索词分析驱动）**：执行 2.1 ~ 2.4。
- **模式 B（客户清单导入驱动）**：跳过 2.1 ~ 2.4，执行 2.5。
- **模式 C（商品投放否词）**：执行 2.7。
- 模式 A 若启用递进验证，额外执行 2.4.1。

### 2.1 关键前置：搜索词查询不能直接按 ASIN 过滤

`get_ads_perf(factEntity='searchTerm')` **不支持** join `productAd` / `asin` / `productLine`。按商品范围分析时按以下顺序操作：

1. `get_entity_metadata(entity='productAd', filters={'asin': {...}})` 取该商品的 `adGroupId`（**平台内部 ID**）。
2. `get_entity_metadata(entity='adGroup', filters={'adGroupId': {...}})` 取对应 `amazonAdGroupId`。
3. `get_ads_perf(factEntity='searchTerm', filters={'adGroup.adGroupId_': {'in': [<amazonAdGroupId>...]}})`。

> ⚠️ 最容易踩的坑：元数据里的 `adGroupId` 是平台内部 ID（短整数，如 `142596476`），而搜索词表返回的 `adGroupId` 是 **Amazon adGroupId**（长整数，如 `517547567010529`）。直接用内部 ID 过滤会**静默返回 0 行**，看起来像「没有数据」。

字段命名、错误码与分页细节见 `references/sparkx-mcp-field-reference.md`。

### 2.2 必取字段

- Marketplace、广告账户
- 广告活动及广告组（含 `campaignState` / `adGroupState`）
- Search Term、`matchType`、`queryCategory`
- Impressions、Clicks、Spend、Sales、Conversions
- CPC、CVR、ACOS、ROAS（可获取时）
- 现有否词（`get_entity_metadata(entity='negativeKeyword')`）及其作用层级（campaign / adgroup）

### 2.3 数据核验（强制）

1. 用聚合查询（不带 `select`）取总量，与分页明细汇总**逐项对平**（花费、点击、销售、订单）。对不平必须排查后再用。
2. 明确报告时间范围、数据更新时间与实际覆盖范围。
3. 检查字段缺失、重复记录、分页遗漏、查询失败。分页未取完不得开始分析。
4. 不得把缺失数据当作零。
5. 不得假设未返回的广告组没有数据。

大结果集会被自动落盘为文本文件，用脚本读取而非逐行贴入上下文。统计与筛选可调用 `scripts/analyze_search_terms.py`。

### 2.4 展示数据概况

- 搜索词记录数
- 涉及的广告活动 / 广告组数量
- 数据时间范围
- 花费、点击、订单概况（仅数据可用时展示）
- 数据缺失或异常（**含「无记录 ≠ 零花费」的显式声明**）

随后询问是否使用这批数据进入 Step 3。用户确认后才继续。

### 2.4.1 递进验证的多窗口取数

启用递进验证时，用**同一范围、同一 `select` 粒度**跑三次查询，只改日期：

| 窗口 | 日期区间 | 用途 |
|------|---------|------|
| W1 | 最近 30 天 | 发现问题 |
| W2 | 第 31~60 天 | 对比期 / 累计 60 天 |
| W3 | 第 61~90 天 | 累计 90 天 |

要求：

1. 三个窗口的 `filters`、`select`、`metrics` 必须完全一致，只改 `dateStart` / `dateEnd`。
2. 每个窗口都要做 2.3 的四项对平校验。
3. 分页必须取完，否则累计值偏低。
4. 三个窗口的原始返回全部落盘，交给 `scripts/verify_term_windows.py` 汇总，不要手工相加。

```
python scripts/verify_term_windows.py --w30 w1.json --w60 w2.json --w90 w3.json \
    --min-clicks <n> --min-spend <x> --target-acos <a> --acos-tolerance <t> \
    --protected "品牌词" "核心词" --out-json verify.json --report verify.md
```

判定逻辑见 `references/negative-keyword-rules.md` 第 8 节。核心原则：**30 天只用来发现问题，不用来下结论**。

### 2.5 模式 B：读取并校验客户否词清单

调用 `scripts/import_negative_list.py` 完成标准化与校验。完整的列规范、归一化规则与排错方法见 `references/excel-import-spec.md`。执行顺序：

1. **确认清单格式**。支持的列（列名可用中英文，脚本自动识别）：

   | 字段 | 可接受的列名示例 | 必需 |
   |------|----------------|------|
   | 关键词 | Keyword / Keyword Text / Search Term / 否词 / 关键词 | ✅ |
   | 匹配类型 | Match Type / 匹配类型 / 匹配方式 | 可选，缺省用 `--default-match-type` |
   | 广告活动 | Campaign / Campaign Name / Campaign ID / 广告活动 | 定位所需 |
   | 广告组 | Ad Group / Ad Group Name / Ad Group ID / 广告组 | 广告组级必需 |
   | 层级 | Business Type / Level / 层级 | 可选，缺省用 `--default-business-type` |
   | 账户 | Profile ID / 账户 ID | 可选，缺省用 `--default-profile-id` |

2. **先拉元数据做名称映射**。清单用名称定位时，先取：

   ```
   get_entity_metadata(entity='campaign', filters={'campaignId': {'in': [...]}})
   get_entity_metadata(entity='adGroup',  filters={'campaignId': {'in': [...]}})
   ```

   把响应原样存为 JSON，作为 `--metadata` 传入。

3. **运行导入脚本**：

   ```
   python scripts/import_negative_list.py \
     --file customer_negatives.xlsx \
     --metadata campaigns.json adgroups.json \
     --default-profile-id <profileId> \
     --default-business-type adgroup \
     --default-match-type negativeExact \
     --out approved_items.json --report import_report.md
   ```

4. **逐条报告三类问题，不得静默丢弃**：
   - **目标位无法定位**：名称在元数据里找不到。不得猜 ID，必须让用户补充或确认。
   - **格式非法**：关键词超 80 字符、含 `/`、匹配类型无法识别。
   - **清单内重复**：自动跳过并列出。

5. 展示校验报告后询问：

   > 清单共 N 条，其中 M 条可直接提交，X 条目标位无法定位，Y 条格式非法，Z 条重复。请先处理 X 和 Y 两类，或确认剔除后再继续。

### 2.6 模式 B 的额外风险提示

模式 B 缺少搜索词表现数据，因此**无法判断这些词是否真的该被否**。必须在报告中明确声明这一点，并提醒用户：

- 清单里的品牌词、核心类目词是否真的需要否（避免误伤）
- 这些词当前是否有订单（可通过 `get_ads_perf` 按搜索词反查，成本较高，需用户同意后才做）
- 是否与现有否词重复（脚本已比对，但仅限传入的 `--existing`）

不得因为「用户给了清单」就默认清单全部正确。

### 2.7 模式 C：读取投放目标（ASIN）表现

**关键：搜索词报表里拿不到 ASIN。** `factEntity='searchTerm'` 中 `matchType='ASIN'` 的行，`query` 字段仍然是顾客搜索词，不是 ASIN（实测 51 行中 0 行是 10 位 ASIN）。ASIN 级数据只在投放目标报表里。

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

`p.target_` 即 ASIN。`factEntity='target'` 可用字段仅：
`adGroupId_`、`campaignId_`、`campaignType_`、`matchType_`、`profileId_`、`targetId_`、`target_`、`targetingType_`
（不存在 `p.targeting_`）。

同时必须确认目标广告组的投放类型：

```
get_entity_metadata(entity='target', filters={'adGroupId': {'in': [<内部ID...>]}})
```

- 有 `asinSameAs` / `asinExpanded` / `asinBrandSameAs` / `category` 目标 → 商品投放组，**可以**加否定商品。
- 只有关键词目标 → 关键词投放组，**不能**加否定商品，服务端会整批拒绝。

完整规范见 `references/negative-target-asin-spec.md`。

---

## Step 3：交互式设置否词规则

### 3.0 模式 B 的差异

模式 B 不做搜索词筛选，因此无需设置零转化 / ACOS 阈值。但仍需确认三件事：

1. **匹配类型**：清单未标注时的默认值（`negativeExact` 或 `negativePhrase`），以及是否允许逐条覆盖。
2. **作用层级**：广告组级 / 广告活动级，以及清单混用两种层级时如何分别处理。
3. **品牌词与核心词例外**：清单中若含品牌词、已转化词或核心类目词，必须先列出并请用户逐条确认，不得直接提交。

确认后直接进入 Step 4（模式 B 下 Step 4 输出的是校验报告而非候选分析）。

### 3.1 模式 A：规则设置

先询问模式：**A. 使用推荐规则** / **B. 自定义规则**。

推荐规则仅为初始建议，不得冒充行业统一标准。需逐项确认：

| 规则 | 需确认参数 |
|------|-----------|
| 零转化高花费 | 最低点击量、最低花费阈值、是否必须同时满足（AND / OR） |
| ACOS 超标 | 目标 ACOS、超标幅度、最低订单量或最低点击量、是否允许将有订单的词列为否词 |
| 低相关性 | 商品核心功能 / 使用场景 / 目标人群、明确不相关的词语或词组 |
| 品牌词保护 | 是否保护品牌词、已转化词、核心类目词及战略词 |
| 时间窗口验证 | 是否启用 30/60/90 递进验证、90 天窗口门槛（默认 30 天门槛 ×3） |
| 否词类型 | Negative Exact / Negative Phrase；商品投放另需确认 ASIN 否定 |

推荐规则模板与阈值参考见 `references/negative-keyword-rules.md`。

### 3.2 模式 C：商品投放否词规则

需确认：

1. **否定对象**：单个 ASIN（`asinSameAs`）、品牌（`asinBrandSameAs`）还是两者都有。
   - `asinBrandSameAs` 影响面极大，必须单独确认，不得与普通 ASIN 混批默认提交。
2. **自家商品排除**：是否已核对商品库，确保待否 ASIN 不含自家产品。否定自家 ASIN 属于自伤。
3. **阈值**：沿用零转化高花费与 ACOS 超标规则，但样本门槛需按商品投放特性调整（详情页点击的 CVR 通常低于搜索，点击门槛应更高）。
4. **处理方式优先级**：对单个 ASIN，`降 bid / 暂停目标` 通常优于加否定。只有在目标无法单独暂停、或需要长期屏蔽时才用否定商品。

> 品类否词不能通过 `negativeTarget` 的 `expression` 表达。不要把品类名当 ASIN 传入。

若用户选推荐规则，先展示具体阈值及逻辑，等待确认后才应用。

所有筛选逻辑必须明确区分 AND 与 OR，不得自行改变用户设置的规则。

规则确认后展示完整规则摘要并询问是否开始分析。

---

## Step 4：生成候选否词清单

**模式 B（清单导入）**：跳过 4.1 ~ 4.5，直接展示 Step 2.5 的校验报告作为确认依据，并按 4.6 的分层方式让用户确认提交范围。

**模式 A（搜索词分析）**：执行 4.1 ~ 4.5，再按 4.6 确认。

**模式 C（商品投放）**：执行 4.1 与 4.7，再按 4.6 确认。候选与模式 A 分开呈现。

### 4.1 强制前置核查：搜索词是否为该广告组的在投关键词

**这一步不可跳过。** 精准匹配广告组的搜索词通常就是组内正向关键词本身。若把某个搜索词加成否词，而它同时是该广告组的在投关键词，等同关闭该关键词——正确做法是**暂停关键词**，而非加否词。

核查方法：

1. `get_entity_metadata(entity='keyword', filters={'campaignId': {'in': [...]}})` 取该活动全部关键词（含 `keywordText`、`matchType`、`keywordState`）。
2. 将每条候选搜索词与 `keywordText` 比对（含单复数、连字符、`+` 等近似变体）。
3. 按结果分类：
   - 对应关键词 **enabled** → 加否词等价于关词，优先建议暂停或降 bid。
   - 对应关键词 **paused / archived** → 该词已不再产生花费，**加否词无增量效果**，标注为「已由其他方式消除」而非「建议添加」。
   - 无对应关键词（自动投放、商品投放、类目投放产生）→ 才是真正适合加否词的对象。

若某广告组所有零转化高花费词都来自已暂停关键词，必须如实报告「可执行否词为 0 条」，并给出关键词侧建议，不得为凑数强行添加否词。

### 4.2 30/60/90 递进验证（启用时强制）

**30 天触发 ≠ 可以否。** 每条 30 天触发的候选，必须经长窗口验证后才能进「建议添加」。

判定顺序：

1. **保护词优先**：命中品牌 / 核心词保护 → 直接归「建议保留」，不再看长窗口。
2. **30 天未触发** → 不否。但若 90 天累计零转化且花费超 90 天门槛，标「建议观察（近期改善）」。
3. **30 天触发，且 60/90 天无任何记录** → 「建议观察（新词）」。**无记录 ≠ 零转化**，不能当作长期无效的证据。
4. **30 天触发，90 天有单且 ACOS 达标** → 「建议保留（长期达标）」。这是最典型的误否场景。
5. **30 天触发，90 天有单但 ACOS 超标** → 「建议观察」，优先建议降 bid。
6. **30 天触发，90 天累计零单且达 90 天门槛** → 「建议添加（长期验证）」。
7. **30 天触发，90 天累计零单但未达门槛** → 「建议观察（长期样本不足）」。

90 天门槛默认取 30 天门槛的 3 倍。完整矩阵见 `references/negative-keyword-rules.md` 第 8 节。

展示时必须同时给出 30 / 60 / 90 三列，并单列一节说明**被长窗口验证拦下的词**——这部分是规则价值的直接证明，也是用户复核的重点。

### 4.3 分类

| 分类 | 判定 |
|------|------|
| A. 建议添加 | 满足已确认否词规则，**通过长窗口验证**，且不属于 4.1 的无效场景 |
| B. 建议观察 | 数据不足、样本过小、长窗口有转化、新词、转化归因不充分，或存在潜在价值 |
| C. 建议保留 | 已转化、长周期 ACOS 达标、高度相关，或属于需保护的品牌词 / 核心词 |

### 4.4 每条候选必须展示

- Search Term / ASIN
- 建议否词类型
- 目标广告活动及广告组
- Clicks、Spend、Orders、Sales、ACOS
- **30 / 60 / 90 天三窗口的点击、花费、订单、ACOS**
- **趋势标记**（转化中断 / 转化改善 / 持续无转化 / 花费扩张仍无转化）
- 触发的规则
- 建议原因
- 可能的误伤风险
- **对应正向关键词的当前状态（enabled / paused / 无）**
- 是否已存在相同或冲突的否词（可核实时）

### 4.5 硬性禁止

1. 不得仅因零转化或短期 ACOS 高就自动判定无效。
2. 不得在缺少数据时推断搜索词相关性。
3. Negative Exact 与 Negative Phrase 作用不同，必须解释选择依据。
4. 一个否词可能影响多个广告组时，明确列出作用范围。
5. 不得把一个广告组的否词建议擅自扩展到整个账户。
6. **不得用「60/90 天无记录」代替「零转化」**。
7. **不得把 ASIN 否词与关键词否词混在同一份候选清单里**。

### 4.6 大批量候选的确认方式

候选超过 **50 条**时，不得一次性平铺全部明细。按以下方式分层展示：

**第一层：汇总（必须展示）**

| 分类 | 条数 | 合计花费 | 占该范围花费比 |
|------|------|---------|--------------|
| 建议添加 | — | — | — |
| 建议观察 | — | — | — |
| 建议保留 | — | — | — |
| 规则冲突 | — | — | — |
| 关键词已暂停 | — | — | — |

**第二层：按花费降序分页展示「建议添加」**

- 每页 20~30 条，先展示花费最高的部分（这些是节省潜力最大的）
- 每页末尾询问：`继续看下一页 / 只确认已展示部分 / 全部确认 / 停止`
- 用户可随时说「只确认前 N 条」

**第三层：批量确认的快捷指令**

| 用户指令 | 含义 |
|---------|------|
| 全部确认 | 将当前「建议添加」组全部加入 `approved_negatives` |
| 只确认前 N 条 | 按花费降序取前 N 条 |
| 按广告组确认 | 按广告组逐组确认，适合多组场景 |
| 排除某词 | 从清单中剔除指定词后重新生成 |
| 只看某组 | 只展示指定广告活动/广告组的候选 |

**硬性约束**：

1. 「建议观察」和「建议保留」**不需要逐条确认**，只给汇总数字与分类理由即可；用户明确要求时才展开。
2. 分页展示不等于可以跳过审核。**`approved_negatives` 必须与用户最后一次确认的内容完全一致**，中间不得追加或替换。
3. 超过 300 条时，建议先按「花费占比」或「广告组」让用户圈定范围，再进入明细确认，避免无意义的逐条过目。
4. 无论批量多大，Step 5 的最终预览都必须列出**完整清单的汇总 + 分批计划**，并给出总条数，让用户能核对自己确认的数量。

按风险分组展示；记录过多时按上述规则分页确认。

询问：

> 请确认哪些候选词需要添加。可选择全部建议添加、仅指定词、修改否词类型，或将某些词移入观察列表。

只有用户确认具体候选词及作用范围后，才加入 `approved_negatives`。

### 4.7 模式 C：ASIN 候选清单

候选来自 Step 2.7 的投放目标报表。每条必须展示：

- ASIN（`p.target_`）
- 目标类型（`asinSameAs` / `asinExpanded` / `asinBrandSameAs`）
- 所属广告活动 / 广告组（**必须确认是商品投放组**）
- Clicks、Spend、Orders、Sales、ACOS
- 30 / 60 / 90 天三窗口表现（启用递进验证时）
- 是否为自家 ASIN（**必须核对，自家 ASIN 禁止否定**）
- 是否已存在相同否定（查 `get_entity_metadata(entity='negativeTarget')`）

强制约束：

1. **不能只凭「花费高零转化」就否定 ASIN**。详情页流量往往转化周期更长，且 `asinExpanded` 是扩展匹配结果，否定它只是收窄流量面。
2. 对单个 ASIN，**优先建议降 bid 或暂停该目标**；否定商品只在目标无法单独调整、或需要长期屏蔽时使用。
3. `asinBrandSameAs`（品牌级否定）影响该品牌全部商品，必须单列并单独取得授权。
4. 关键词投放广告组不得出现在 ASIN 候选里——服务端会整批拒绝。

确认话术后，ASIN 清单单独存入 `approved_negative_targets`，与 `approved_negatives` **分开管理、分开发布**。

---

## Step 5：执行前最终审核

核验 `approved_negatives`：

- 目标站点和账户正确
- 广告活动 / 广告组存在且属于指定范围
- 否词类型符合工具支持的格式
- 否词未重复添加
- 未误选品牌词或已确认需保护的关键词
- 未与在投正向关键词冲突（或在用户明确知情下接受该冲突）
- **每条「建议添加」都已通过 30/60/90 长窗口验证**（若启用递进验证）
- 所有操作参数完整

核验 `approved_negative_targets`（模式 C）：

- **目标广告组是商品投放组**（含 `asinSameAs` / `asinExpanded` / `asinBrandSameAs` / `category` 目标）
- ASIN 格式为 10 位字母数字，且已大写
- **待否 ASIN 不含自家商品**
- `asinBrandSameAs` 的品牌值与普通 ASIN 分开列示，且已单独取得授权
- 未与现有否定商品重复
- 未与关键词否词混在同一份清单

展示最终操作预览：目标站点与账户、目标广告活动与广告组、否词及匹配类型、操作总数、**分批计划（批次数与每批条数，按路由分组）**、将跳过的重复项、高风险项与未解决异常。

**关键词否词与否定商品必须分成两个区块展示**，各自给条数与批次数，不得合成一个总数——两者的作用机制与失败影响面完全不同。

模式 B 额外展示：层级分布（广告组级 / 活动级各多少条）、名称→ID 映射结果抽样、无法定位的条目数。

若操作总数超过单批上限，须先用 `scripts/build_negative_batches.py` 生成批次，并在预览中展示 `manifest.json` 的批次清单，让用户确认分批方式后再取授权。

明确询问：

> 以上是最终待执行清单。回复「确认执行」后，我才会通过 MCP 添加这些否词；回复「修改」可调整清单，回复「取消」则终止本次执行。

只有在当前待执行清单已完整展示后，用户明确回复确认执行，才允许进入 Step 6。用户修改任何否词、匹配方式或作用范围后，必须更新预览并重新取得最终确认。

---

## Step 6：执行与结果验证

仅调用实际存在且已授权的写工具。

### 6.1 分批规则（强制）

`batch_update_ads` 有三条互不兼容的路由，**payload 结构不同，不得混在同一批**：

| 路由 | entity + action | 适用 | 数组 | 1 项 = 几条否定 | 单批否定上限 |
|------|----------------|------|------|----------------|-------------|
| R1 | `negativeKeyword` + `create` | 关键词否词 · **仅 SP 广告活动级** | `data` | 多条（`negativeKeywords` 数组） | 可远超 200 |
| R2 | `negativeKeyword` + `copy` | 关键词否词 · 广告组级 | `target` | **1 条** | **200** |
| R3 | `negativeTarget` + `create` | 否定商品（ASIN / 品牌）· **仅广告组级** | `target` | **1 条** | **200** |

> ⚠️ 易错点：`negativeKeyword + create` **只支持 SP 广告活动级**。广告组级否词必须走 `copy` 路由（`businessType='adgroup'` + `target` 数组，每项 1 条否词）。把 `businessType='adgroup'` 塞进 `data` 项不会生效。

通用约束：

| 约束 | 数值 |
|------|------|
| 单次调用数组项上限 | **200**（`data` / `target` 各自） |
| `keywordText` | ≤ 80 字符，不含 `/`，空白字符会被保留 |
| 否词 `matchType` | 仅 `negativeExact` / `negativePhrase` |
| ASIN `expression` | 只能 1 个元素；`asinSameAs` 值为 10 位字母数字 |
| `asinBrandSameAs` | 值是品牌 ID 或品牌名，**不是 ASIN** |
| 校验模型 | **all-or-nothing**，任一项失败整批被拒 |
| 目标位 ID | 用 `get_entity_metadata` 返回的**内部 ID**，不是 Amazon ID |
| SB 否词 | 不支持 `state=paused`，传入会整批被拒 |
| 确认流程 | R1/R2/R3 的 create/copy **均无需 confirmToken**；`updateStatus` 涉及 `archived` 才需要两阶段确认 |

**R2 / R3 首次使用前的试提交**：`copy` 与 `negativeTarget` 路由的字段契约比 `create` 更严格，首次使用时应先提交**最小批次（1 条）**，确认返回成功并重新读取到该条记录后，再放大到整批。不得一上来就提交 200 条。

批次大小按下表确定，**不得一次性提交 200 项**：

| 总条数 | 建议批次大小 | 理由 |
|--------|------------|------|
| ≤ 50 | 1 批 | 无需拆分 |
| 51 ~ 300 | 50 ~ 100 / 批 | 失败影响面可控，超时风险低 |
| > 300 | 100 / 批（上限 200） | 必须分批，逐批验证 |

**拆分维度**：

- R1：同一广告活动（`campaignId`）的否词必须落在同一 `data` 项内，不得跨批拆散同一目标位。
- R2 / R3：1 项就是 1 条否定，按 200 上限切批即可，但同一 `adGroupId` 的条目应连续排列，便于失败时定位。
- 跨 `profileId` 或 `campaignType` 时按此分组隔离，避免一个账户的失败连带整批回滚。

**构建方式**：

- 模式 A：用 `scripts/analyze_search_terms.py` 产出候选、`scripts/verify_term_windows.py` 做长窗口验证，人工确认后整理为 `approved_items.json`，再调用 `scripts/build_negative_batches.py` 生成批次。
- 模式 B：用 `scripts/import_negative_list.py` 直接把客户清单转为 `approved_items.json`，再调用 `scripts/build_negative_batches.py` 生成批次。
- 模式 C：把 ASIN 清单整理为含 `asin` 字段的 JSON，同样交给 `build_negative_batches.py`，脚本会自动识别并走 R3 路由。

`build_negative_batches.py` 自动完成：**路由判定**（R1/R2/R3）、字段校验、清单内去重、与现有否定比对跳过、按目标位归组、按路由分批、生成可直接提交的 payload 与 `manifest.json`。

> 提交前必须先把 `invalid.json` 中的条目修正或剔除。**校验失败的条目不得静默丢弃**，必须向用户列出。

### 6.2 执行顺序

1. 按 `manifest.json` 的 `batches` 顺序**逐批**提交，不得并发。
2. 每批完成后**立即重新读取实际状态**，确认本批写入结果，再执行下一批。
3. 某一批失败时，先查明原因并修复，再决定是否继续后续批次。
4. 全部批次完成后做一次整体复核。

### 6.3 通用执行约束

1. 仅执行 `approved_negatives` 中已确认的项目。
2. 只在确认的站点、账户、广告活动、广告组范围内操作。
3. 不修改竞价、预算、广告状态或其他设置。
4. 工具返回超时或状态不明确时，先查询实际状态，再决定是否重试。
5. 不得因一次失败而盲目重复整个批次；`create` 类操作重试前必须先查重，避免重复添加。
6. 不得声称已执行任何未经工具结果证实的操作。

执行后重新读取实际状态逐条验证。最终报告包含：原计划数量、成功数量、失败数量及原因、跳过数量及原因、状态不明项目，以及每条否词对应的站点 / 广告活动 / 广告组 / 匹配类型。

必须区分三种状态：**请求已提交** / **工具返回成功** / **已通过重新读取验证**。

### 6.4 分批执行报告格式

超过 1 批时，按批报告，便于定位问题：

| 批次 | 路由 | 数组项 | 否定条数 | 提交结果 | 重新读取验证 | 失败项 |
|------|------|--------|---------|---------|------------|--------|
| batch_001 | R1 活动级关键词 | 100 | 480 | 成功 | 已确认 | 0 |
| batch_002 | R2 广告组级关键词 | 100 | 100 | 部分失败 | 已确认 | 3（见下） |
| batch_003 | R3 否定商品 | 45 | 45 | 成功 | 已确认 | 0 |

失败项必须逐条列出否词文本、目标位与失败原因。

---

## 通用交互规则

- 每一步只提出当前步骤需要解决的问题。
- 问题清晰简洁，尽量提供可选答案。
- 不重复询问用户已明确确认的信息。
- 支持「返回上一步」「修改站点」「修改范围」「查看规则」「取消任务」等指令。
- 修改站点、账户或数据范围后，重新获取对应数据。
- MCP 不支持某项操作时说明限制，不得虚构执行结果。
- 用户要求跳过某一步时说明必要性；涉及执行授权的步骤不可跳过。
- 所有写操作前必须取得明确授权。
- 任务结束后提供简洁执行总结。

## 反模式清单

以下行为一律视为错误：

| 反模式 | 正确做法 |
|--------|---------|
| 用平台内部 `adGroupId` 过滤搜索词表 | 先映射 `amazonAdGroupId` |
| 把 0 行结果当成「该范围无数据」 | 先验证过滤条件正确性 |
| 对已暂停关键词对应的搜索词加否词并计入「已优化」 | 标注为已消除，给出关键词侧建议 |
| 把品牌核心词因 ACOS 超标直接否掉 | 建议降 bid，或列入观察 |
| 未对平分页汇总与聚合值就开始分析 | 四项指标逐项对平 |
| 未展示清单就执行写操作 | 先出预览，再取授权 |
| 把「工具返回成功」说成「已验证生效」 | 重新读取后再说验证 |
| 一次性提交几百条否词 | 按 6.1 分批，逐批验证 |
| 同一目标位的否词被拆到不同批次 | 同目标位必须落在同一 data 项 |
| 校验失败条目被静默丢弃 | 列出并交用户修正或剔除 |
| 批次失败后整批重试 create | 先查重，只重试失败项 |
| 客户清单原样提交，不校验 | 先跑导入脚本，逐条报告问题 |
| 清单里的广告组名匹配不上就猜一个 ID | 报告无法定位，让用户补充 |
| 默认客户给的清单全部正确 | 声明无表现数据支撑，提示品牌词/核心词风险 |
| 上千条候选一次性平铺 | 按 4.6 分层：先汇总，再分页，再批量确认 |
| 只看最近 30 天表现就下否词结论 | 先做 30/60/90 递进验证，30 天只用于发现问题 |
| 把「60/90 天无记录」当成「零转化」 | 标为新词 / 样本不足，归入观察 |
| 长窗口有转化但 ACOS 略超就直接否 | 优先降 bid，有真实需求的词不切断 |
| 在搜索词报表里找 ASIN | 改用 `factEntity='target'`，`p.target_` 才是 ASIN |
| 在关键词投放广告组加 ASIN 否词 | 服务端整批拒绝，改用关键词否词 |
| 否定自家 ASIN | 先核对商品库，自伤行为禁止 |
| 把 `businessType='adgroup'` 塞进 `negativeKeyword + create` | 广告组级走 `copy` + `target` 数组 |
| ASIN 否词与关键词否词混在一批提交 | 分路由、分批次、分区块预览 |
| 首次用 copy / negativeTarget 就提交整批 | 先试提交 1 条，验证路由可用后再放大 |
| 用品类名当 ASIN 传给 `negativeTarget` | 品类否词不能用 expression 表达 |
