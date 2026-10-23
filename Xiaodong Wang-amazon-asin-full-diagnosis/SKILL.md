---
name: amazon-asin-full-diagnosis
description: 亚马逊ASIN综合诊断报告：产品竞争力+流量结构+广告活动诊断+可交互广告框架思维导图。当用户要求对某个ASIN做全面诊断、分析销售下滑原因、出广告优化方案时使用。
version: 1.2.0
---

# Amazon ASIN 综合诊断报告

## 触发条件

用户提供一个ASIN（或父ASIN），要求做以下一项或多项分析：
- 产品市场竞争力 / 竞品对比
- 流量结构 / 关键词排名分析
- 广告活动诊断 / ACOS过高 / CPC上升
- 广告框架搭建 / 思维导图
- 销售下滑原因排查

## 依赖与硬门禁（执行第一步，先判后做）

本 skill 的「广告活动诊断」与「广告框架思维导图」两大模块**只能**取自 **SparkX AI MCP**（服务器名形如 `sparkx-<tenant>`，暴露 `get_user_authorized_context` / `get_entity_metadata` / `get_ads_perf` 等工具）。产品/流量/市场数据用 sellersprite，但**广告数据不可替代、不可降级**。

**门禁检查（在做任何分析前先执行）：**

1. 调 `qwenwork_mcp_tool_list`（keyword=`sparkx`）确认是否存在可用的 `sparkx-*` 服务器及其广告工具。
2. **若不存在 SparkX AI MCP → 立即中止整个 skill**，不得继续输出报告，并明确提示用户接入，话术模板：

   > ⚠️ 无法完成诊断：本报告的「广告活动诊断」与「广告框架思维导图」必须调用 **SparkX AI MCP** 获取真实广告数据，当前未检测到该 MCP。请先接入（端点 `https://mcp.sparkx.cn/mcp`，请求头 `Authorization: Bearer <mcp_pat_...>`；每个租户一个 Token，建为独立的 `sparkx-<租户>` custom HTTP MCP），接入后重新运行。可参考 `sparkx-mcp-tenant-onboarding` 技能完成接入与验证。

3. 若 SparkX AI MCP 已接入但**目标租户的 `sparkx-<tenant>` 服务器缺失** → 中止并提示按上述方式接入该租户，**不得**错用其他租户数据顶替。
4. **严禁**用 sellersprite / sorftime / 历史记忆 / 估算 / 编造的任何数值替代广告数据；**严禁**在缺 MCP 时输出"看似完整"但广告部分为占位/假数的报告。**缺广告数据 = 报告不成立。**

**连接成功判定**：对目标 profile 调 `get_user_authorized_context` 能返回 `userId` / `profileIds` 才算真正连上（仅有服务器名不代表可用）。

## 前置信息收集

开始前确认：
1. **站点**（US/UK/DE/JP等）
2. **ASIN**（父ASIN或子ASIN均可）
3. **所属租户/Profile**（前提：SparkX AI MCP 已接入并通过「依赖与硬门禁」检查；如有多个 SparkX 租户需确认目标 `sparkx-<tenant>`，并按 Step 6.2 用 productAd+asin 数据验证归属）
4. **核心问题**（用户最关心什么：销售下滑？ACOS过高？新品推广？）

## 数据采集步骤

### Step 1: 产品基础数据

```
工具: sellersprite → asin_detail
参数: { asin, country }
获取: 价格、评分、评论数、BSR、类目、变体、徽章(AC/BS/EBC/Video)、上架时间、卖家数
```

### Step 2: 销量与价格趋势（价格/销量必须独立源交叉验证，asin_sales_trend 仅作趋势形态参考）

```
工具: sellersprite → asin_sales_trend
参数: { asin, country }
获取: 近12个月月销量/销售额趋势 —— ⚠️ 仅作"趋势形态参考"，其 price/averagePrice 与 parentSalesRevenue 可能与真实严重不符（见反例），禁止直接入报告表格或推导根因
交叉验证（必做）:
  价格历史: sellersprite → keepa_info { asin: 旗舰子ASIN, country } 取 buyBox/price 逐日序列为准
  销量/销售额: sparkx-{tenant} → get_ads_perf factEntity=asin metrics [TotalSalesAmount, OrderCount]（后台口径）为准
  需求形态: keepa_info subSalesRank 月均作辅证
判定: asin_sales_trend 月均价 vs keepa buyBox 月均偏差 >10% → 弃用其价格与销售额列;
      parentUnitSales vs 后台 OrderCount 偏差 >20% → 弃用其销量列
价格口径层级（报告必须出"成交价口径解释"表，逐行注明来源与采用状态）:
  页面成交价(采用): keepa buyBox 逐日 = SIF buyboxPrice/dealPrice 交叉验证; 含卖家直降, 不含结账促销/秒杀/会员价/税运
  实付价: 页面价×(1-结账促销率); 结账促销必查 SIF ops_get_asin_traffic_trend 日粒度 promotion 字段
          (如全期挂"Save 5% at checkout"=实付≈×0.95; 算促销弹性/毛利必须用实付口径)
  额面券实付: sellersprite asin_coupon_trend finalPrice (页面价-额面券; 比例型促销不捕捉)
  秒杀/会员价: SIF ldPrice / primePrice (全空=不存在)
  现点价: asin_detail / SIF chars[].price (仅快照, 不可作历史)
  GMV隐含每套价: SparkX GMV÷订单÷套/单 (仅交叉验证)
AOV口径(硬约束): asin级 TotalSalesAmount÷OrderCount = **每单金额**, 含一单多套
  (窗帘类约1.7套/单, 用广告 Units÷Conversions 作件数代理并标注) 与跨变体价格mix,
  **不是每套单价**; 报告表格必须标注口径; 需每套单价用 keepa 成交价或 GMV÷订单÷套/单
```

反例（实战教训 · B0FQHS2P6C · 2026-09-23）：asin_sales_trend 声称父ASIN月均价 $65.49/68.99↔$39.99 隔月振荡，据此推出"促销依赖/促销摧毁收入-34.4%"等根因；但 keepa buyBox 真实成交为 $35.98-$49.99 区间高频切换（6个月13个改价点），$65+ 价位根本不存在，且两个广告对比窗口主体价格相同($39.98)——整条根因链错误、报告被迫重建。错误根源：信了 asin_sales_trend 单源价格/销售额，未与 keepa/后台交叉验证。

### Step 3: Review评论分析

```
工具: sellersprite → review
参数: { marketplace, asin, starList: [1,2,3], page: 1, size: 20 }  // 差评
再调: { marketplace, asin, starList: [4,5], page: 1, size: 20 }    // 好评
注意: 参数是 marketplace 不是 country；需对子ASIN分别查询
提炼: 产品痛点、用户好评关键词、隐性需求
⚠️ 变体归属硬约束（前置，不可跳过）: review 返回的每条评论含 skus 字段（如 "Size: 10A"/"Size: 25A"/"Size: 4A(2A*2Banks)"）标明该评论属于哪个变体。
  多变体父ASIN共享同一评论池，详情页展示全部变体评论。诊断单个子ASIN（如25A）时，
  必须按 skus 字段逐条过滤差评/好评归属，严禁把其他变体（4A/10A）的差评扣到目标变体头上推导根因。
  正确做法: ① 分别统计"目标变体自身评论"与"父体全变体评论"；② 目标变体自身差评才是产品力问题；
  ③ 其他变体的差评归为"父ASIN差评污染"（影响目标变体CVR的隐性外因，解法是差评隔离/拆分变体/A+区隔，而非整改目标变体本身）。
  反例（B0F3C4FR8K · 2026-10-10）: 诊断25A变体，却把4条差评（实为10A/4A变体的"实际输出仅2A/充电18h/用几次就坏"）
  当成"25A虚标"根因，推出错误的"Listing整改解决25A虚标"P0建议；实际25A变体自身8条评论全4-5★、0差评，
  且差评抱怨的"2A慢充"恰是25A大电流的卖点。CVR低的真因是社会证明不足(8评论vs竞品21278)+父体差评污染+大词流量泛，与产品虚标无关。
```

### Step 4: 市场竞争格局

```
工具: sellersprite → competitor_lookup
参数: { request: { marketplace, nodeIdPath: "类目路径", order: {desc:true, field:"total_units"}, size: 15, variation: "Y" } }
获取: 类目Top15竞品的价格/评分/评论数/月销量/BSR/徽章
必做: 从每个竞品标题解析**套装数量配置**（单机/2-Pack/4-Pack/4-Cam/KIT/有线vs无线），与本品配置一并记下，供分析框架一.0 分层对标与单台价折算使用

工具: sellersprite → market_research_statistics
参数: { marketplace, nodeIdPath }
获取: 类目均价、平均评分、平均评论数、头部产品数据、新品占比

工具: sellersprite → market_price_distribution
参数: { request: { marketplace, nodeIdPath } }
获取: 各价格带的产品数/销量/占比，定位本品所在价格带竞争力

工具: sellersprite → market_rating_distribution
参数: { request: { marketplace, nodeIdPath } }
获取: 各评分带的销量占比，判断评分门槛
```

### Step 5: 流量结构与关键词

```
工具: sellersprite → traffic_source
参数: { request: { marketplace, q: "子ASIN" } }
获取: 总流量词数、自然搜索词/广告词/品牌词/视频词分布

工具: sellersprite → traffic_keyword
参数: { request: { asin: "子ASIN", marketplace, order: {desc:true, field:"trafficPercentage"}, size: 30 } }
获取: Top30流量词的搜索量、自然排名、广告排名、PPC竞价、购买率、供需比、流量占比
关键: 用子ASIN查询（非父ASIN），父ASIN通常无数据
```

### Step 6: 广告数据（SparkX AI MCP · 强制数据源，不可降级）

> ⚠️ 前置门禁：以下所有 `sparkx-{tenant} → ...` 工具必须来自已接入的 SparkX AI MCP。执行前先 `qwenwork_mcp_tool_list`（keyword=`sparkx`）确认；若查不到 `sparkx-*` 服务器或 `get_user_authorized_context` 无法返回 profileIds，**立即中止本 skill** 并按「依赖与硬门禁」提示用户接入，**禁止**用 sellersprite/sorftime/估算/历史数据替代广告数据，**禁止**输出广告部分为占位的报告。

```
// 6.1 确认Profile
工具: sparkx-{tenant} → get_user_authorized_context
获取: 所有授权profile，匹配站点确定profileId

// 6.2 ⚠️ Profile 归属验证（硬约束，不可跳过）
// 当同站点有多个 profile 时（如 Popvil / Popvil-Fashion / Huining），
// 必须对每个候选 profile 跑 productAd+asin 过滤，只有返回 >0 行的才是正确 profile。
// 返回 0 行 = 该 ASIN 不在此 profile，这是铁证，不可用 campaignName like 绕过。
工具: sparkx-{tenant} → get_entity_metadata
参数: { entity: "productAd", filters: { asin: ["子ASIN1","子ASIN2",...] }, profileIds: [候选profileId], userContext: "..." }
验证规则:
  - 返回 rowCount > 0 → 确认为正确 profile，提取 campaignId 列表
  - 返回 rowCount = 0 → 立即排除该 profile，切换下一个候选
  - 所有候选 profile 均返回 0 → 停止，向用户确认 ASIN 所属店铺/profileId
  - 严禁在 0 行 profile 上用 campaignName like 拉数据替代（会拉到同品牌其他产品线）
  - 严禁按类目名/profileName 直觉匹配（如"服装→Fashion"），必须用数据验证

// 6.3 定位ASIN所在广告活动（在已验证的正确 profile 上执行）
工具: sparkx-{tenant} → get_entity_metadata
参数: { entity: "productAd", filters: { asin: ["子ASIN1","子ASIN2"] }, profileIds: [已验证profileId], userContext: "..." }
获取: 所有包含该ASIN的campaignId列表和profileId
注意: userContext必填(string≤100字符)；filters用asin数组

// 6.3 ASIN整体广告表现（近30天 vs 前30天）
工具: sparkx-{tenant} → get_ads_perf
参数: { factEntity: "asin", filters: { "asin.asin_": ["子ASIN"] }, dateStart, dateEnd, metrics: [...], profileIds, select: ["asin.asin_"], userContext }
获取: Impressions/Clicks/Spend/Sales/Conversions/Units/CTR/CVR/CPC/ACOS/ROAS/TotalSalesAmount/OrderCount/Sessions/TACOS
对比: 分两个时间段调用，计算环比变化

// 6.4 广告活动清单（按campaign名称过滤）
工具: sparkx-{tenant} → get_entity_metadata
参数: { entity: "campaign", filters: { campaignName: { like: "产品关键词" } }, profileIds, pageSize: 50, userContext }
获取: 活动名称、状态、日预算、竞价策略、targeting类型、AI组

// 6.5 全Profile活动表现排名
工具: sparkx-{tenant} → get_ads_perf
参数: { factEntity: "campaign", metrics: [...], orderBy: [{field:"Spend",direction:"DESC"}], pageSize: 50, profileIds, select: ["campaign.campaignId_","campaign.campaignName_","campaign.campaignState_","campaign.dailyBudget_"], userContext }
获取: 按花费排序的活动表现，从中筛选与目标ASIN相关的活动
注意: campaign级不支持productAd.asin_过滤(CTE断连)，需先拿全量再按名称筛选
```

### Step 7: 补充数据（按需）

```
// 关键词反查（了解竞品在投什么词）
工具: sellersprite → traffic_keyword
参数: { request: { asin: "竞品ASIN", marketplace, size: 20 } }

// ABA排名趋势
工具: sellersprite → aba_research_weekly / keyword_research_trends

// Keepa价格历史
工具: sellersprite → keepa_info

// SIF 交叉验证与流量拆解（第二独立源）
工具: sif → ops_get_listing_traffic_overview { asin, country, timePieceType: month, timePieceValue: 月首日 }
获取: 月度自然/广告流量分绝对值与渠道拆解(SP/推荐/SB/SBV)，用于渠道塌方环比
工具: sif → market_get_keyword_history { keywords, country, granularity: week }
获取: 核心词ABA周搜索量，用于类目季节性检验（泛词 vs niche词趋势对照）
工具: sif → ops_get_asin_sales_trend { asin, country }
获取: 各变体月销量(50/100粗档)+前台档位文本，仅作变体结构参考（无销售额字段、方向可能与后台订单相反）
注意: ops_get_asin_traffic_trend 周粒度对部分ASIN全null(insufficient_data)，改用 listing_traffic_overview 月粒度；
      日粒度可取 buyboxPrice/dealPrice/ldPrice/couponInfo/promotion，用于价格交叉验证与结账促销检测
```

## 分析框架

### 一、产品市场竞争力分析

0. **套装配置对齐（前置硬约束，先做再谈定价）**: 多件装产品（N-Pack / N-Cam / KIT / bundle）严禁与不同配置的产品直接对标。步骤：
   - 从标题 + asin_detail 识别本品与每个竞品的**配置档位**（单机 / 2-Pack / 4-Pack / 4-Cam / KIT / 有线 vs 无线 / 含配件 bundle）
   - **一切价格比较先折算单台价**（单台价 = 售价 ÷ 台数），绝不拿不同台数的绝对售价直接比高低
   - 竞品集按配置档位**分层**：只有**同档位（同台数）**产品才是「直接对标」；单机/2-Pack 对 4-Pack 属「邻接/升级替代层」，只做升级迁移分析，不做头对头对标
   - 「直接对标」「最大威胁」「比我方便宜」等判断**必须取自同档位竞品**；跨档位时一律用单台价表述并注明配置差异
   - 竞品拦截目标、对比图/创意同样受此约束：只对同档位竞品做「规格/价格对比图」，对邻接层改用「升级到 N-Pack」的加购叙事
   - 若同类目**无同档位竞品**，明确说明，改用单台经济性对比并把"配置不同"列为 caveat
   - 反例（本 skill 实战教训 · B0H1VZY7W2）：本品是 FAMVIVA 太阳能 PTZ **4-Pack** $149.99（单台 $37.5），报告却把**单机** Tapo C660 KIT（B0F5LPQZPT）$115.99 标为「← 直接对标 · 比我方便宜」——$115.99 是单台价，论单台本品反而便宜约 3 倍；真正的直接对标应是 SOLIOM 4-Cam $349 / Carltec 4-Pack $249.99 / eufy 4-cam $349.99 等同为 4 机的产品。该错还传导到广告拦截（把单机 C660 当 #1 拦截目标）与 Week3「对标 C660 做规格/价格对比图」（4 台 vs 1 台，苹果比橘子）。根因：数据已折算单台价，却没把「配置对齐」当成前置硬约束，导致分层与结论串档。

1. **定价定位**: 本品**单台价** vs 同档位竞品单台价 vs 类目均价 → 判断价格带竞争力（跨档位绝不比绝对售价）
2. **评分门槛**: 类目销量按评分带分布 → 本品是否跨过4.5★门槛
3. **评论量差距**: 本品评论数 vs Top5竞品 → 社会证明差距
4. **Review痛点**: 差评提炼产品问题 + 好评中的隐性痛点（4星评论最有价值）
5. **Listing完整度**: 视频/A+/EBC/变体 是否齐全
6. **同品牌内耗**: 是否有同品牌其他ASIN抢流量

输出: 改进建议表（优先级P0/P1/P2 + 具体措施 + 预期效果）

### 二、流量结构分析

1. **流量来源占比**: 自然搜索 vs 广告 vs 品牌推荐 → 判断广告依赖度
2. **核心词排名**: Top10流量词的自然排名+广告排名 → 是否进入首页前列
3. **机会词筛选**: 购买率>10% + 广告竞品<50 + 供需比>1 → 高转化低竞争词
4. **竞品ASIN定向**: 类目Top竞品中哪些值得拦截（价格/评分/销量维度）
5. **词群归类**: 按语义将关键词分组（核心大词/长尾精准词/场景词/竞品词）

输出: 重点投放关键词表（含当前排名、目标排名、建议竞价、匹配方式）

### 三、广告活动诊断

1. **架构评估**: 活动总数是否过多（>20个即碎片化）、预算是否分散
2. **效率对比**: 近30天 vs 前30天的CPC/ACOS/TACOS/CVR环比
3. **花费集中度**: Top3活动占总花费比例，是否过度依赖单一活动
4. **竞价策略**: 各活动的bidding strategy是否合理
5. **问题活动标记**: ACOS>目标值的、CPC异常高的、长期无出单的

输出: 活动诊断表 + 具体优化措施（降竞价/加否定/合并/归档）

### 四、广告框架思维导图

层级结构: **广告意图 → 广告活动 → 定向类型 → 具体关键词/ASIN**

预算分配方法：**意图框架固定，占比浮动**。5 大意图是稳定结构，但每格占比必须由该 ASIN 当前的生命周期/流量结构/竞争格局反推得出，禁止直接套中值。先取下方「默认锚点区间」，再按「数据信号 → 占比漂移」表调整，并**逐条写明每个数字的取数依据**。

默认锚点区间（仅作起手/兜底，不可直接作为结论）:
- 精准转化 30-40%（Exact核心词 + Exact高转化长尾 + Phrase词群）
- 广泛拓词 20-30%（Broad大词 + AMC受众再营销）
- 竞品拦截 15-25%（Product ASIN定向 + Category类目定向）
- 自动捡漏 8-12%（Auto低竞价 + Auto中竞价探词）
- 品牌推广 8-12%（SBV视频 + SB品牌旗舰店）

数据信号 → 占比漂移（每条标注取数步骤，方向由"该 ASIN 现在缺什么"决定）:
- **生命周期**（Step 2 asin_sales_trend + 上架时间）
  - 新品/冷启动、无稳定出单词 → 广泛拓词↑ 自动捡漏↑，精准转化↓（暂无数据可收）
  - 成熟守成款 → 精准转化↑（核心词 Exact 收割），拓词↓
  - 衰退/清货 → 全压精准转化 ROI，砍拓词与品牌推广
- **广告依赖度**（Step 5 traffic_source 自然 vs 广告占比）
  - 自然流量占比过低 → 增品牌词沉淀 + 精准，逐步降 Broad/AMC 依赖
- **竞争强度**（Step 4 头部集中度 + traffic_keyword CPC）
  - 红海、大词 CPC 畸高 → 减 Broad 大词，加长尾精准 + 定点竞品拦截（打弱势竞品）
  - 蓝海、机会词多（购买率>10% + 广告竞品<50 + 供需比>1） → Broad↑ Auto↑ 快速抢量占位
- **Listing 素材**（Step 1 是否有视频/A+）
  - 无视频素材 → 品牌推广预算先压低，不硬投 SBV
- **客单价/决策链**
  - 高价、多触点 → AMC 受众再营销 + SB 品牌↑

示例（反面）：若某 ASIN 根因是 AMC 广泛匹配 CPC 畸高占花费过半，则其正确配比应砍广泛、挪预算去精准转化与长尾机会词，**恰与默认中值相反**——这即是"固定占比不科学、必须自适应"的实证。

每个节点标注: 日预算、竞价策略、建议Bid、目标ACOS、广告位加价

### 五、自然流量/Sessions 塌方排查 playbook（流量塌方类问题必逐条执行，禁止跳步归因）

排查顺序（每步记录数据源与结论）:
1. 价格因素: keepa buyBox 两对比窗口主体价格是否相同 → 相同=排除
2. 断货: sparkx get_entity_metadata entity=asin select [asinFbaQuantity, asinDayAvailability30] → 主力变体健康=排除（边缘变体断货需注明销量占比）
3. Listing压制: SIF 日粒度 buyboxSeller/promotion + keepa → buybox正常=排除
4. 类目季节性: sif market_get_keyword_history ABA周搜索量，**泛词 vs niche词对照** → 泛词跌而niche词平/涨=季节性成立（量化跌幅）
5. 自身排名螺旋: sif listing_traffic_overview 月自然分跌幅 vs 类目需求同期跌幅 → 自然分跌幅显著大于大盘=份额丢失(螺旋)；keepa BSR月均辅证
6. 广告掩盖: sif 月广告分 → 期中广告加投(广告分大涨+自然占比大跌)后回落=掩盖后塌方放大器
结论模板: 外因季节性 × 内因排名螺旋 × 广告掩盖 三层叠加；残余不确定性必须注明（如词级自然排名周序列未取到）
反例（B0FQHS2P6C · 2026-09-23）：Sessions -48.8% 初疑提价所致，查实两窗口主体价格相同；真因=泛遮光词ABA -36%季节回落(42.8%流量压该单词) × 自然分-59%排名螺旋 × 8月广告加投(+132%)掩盖后9月回落。若不做季节性对照（niche词+9.5%不跌），会误判为大盘衰退或活动做坏。

## 输出格式

生成单文件HTML报告，包含:
1. KPI卡片（环比变化用红/绿色标注）
2. 数据表格（竞品对比、关键词排名、活动表现）
3. 诊断Alert（danger/warning/success/info四级）
4. Review引用框（真实评论作为论据）
5. **可交互思维导图**（HTML/CSS/JS树形结构，支持收起/展开子节点）
6. 执行节奏表（按周排期的行动项）
7. **成交价口径解释表**（价格口径层级+采用来源+交叉验证结果，见 Step 2；含结账促销检测结论）

### 思维导图实现要点

- 不使用Mermaid（静态无交互），改用纯HTML嵌套`<ul>/<li>`树
- 每个有子节点的`<li>`动态注入toggle按钮（+/−）
- CSS: 左侧竖线+横线连接、节点圆角卡片、层级底色区分
- JS: click切换`.collapsed`类控制`display:none`
- 提供「全部展开」「全部收起」快捷按钮
- 布局从左往右缩进（padding-left递增）
- Alert框CSS: 仅标题加粗换行（`.alert>b:first-child{display:block}`）；**禁止**给所有`b`设`display:block`，否则正文每个加粗数据片段（如-46%、6.42%→5.19%）都被劈成独立行（2026-09-23 真实排版事故教训）

## 注意事项

- sellersprite的`review`/`traffic_keyword`/`traffic_source`/`competitor_lookup`参数名是`marketplace`不是`country`
- `traffic_keyword`/`traffic_source`/`competitor_lookup`需要`request`包装对象
- **Profile 归属必须用 productAd+asin 验证，不可按名字/类目猜**：同租户同站点有多个 profile 时（如 Popvil / Popvil-Fashion），对每个候选跑 `get_entity_metadata(entity:"productAd", filters:{asin:[子ASIN列表]})`，返回 0 行即排除，>0 行才是正确 profile。严禁在 0 行 profile 上用 `campaignName like` 拉数据替代（会命中同品牌其他产品线的活动，导致根因判断完全错误）。教训源自 B0H36J3FFP：按"服装→Popvil-Fashion"猜错 profile，productAd 返回 0 行未当红灯，用 campaignName like %popvil% 拉到另一条产品线 24 个活动，得出"AI 节流致死"的错误结论（实际正确 profile 无 AI 托管，根因是人工暂停+预算清零）。
- SparkX `get_entity_metadata`必填`userContext`(string≤100字符)
- SparkX campaign级perf不支持按productAd.asin过滤，需先查全量再按名称筛选
- `get_ads_perf`中`campaign.campaignId_`是Amazon ID，非内部ID
- 流量关键词用**子ASIN**查询，父ASIN通常返回空
- **asin_sales_trend 的价格/销售额/销量均不可信**：price/averagePrice 可能与 keepa buyBox 真实成交价严重不符，parentSalesRevenue 系用该错误价格反推，parentUnitSales 与后台 OrderCount 差 1.3-2 倍；价格一律以 keepa_info buyBox 逐日序列为准、销量以 SparkX asin 口径 TotalSalesAmount/OrderCount 为准，asin_sales_trend 仅作趋势形态参考（反例 B0FQHS2P6C：凭空推出"$65↔$40隔月振荡"，实际为 $35.98-$49.99 高频切换）
- 对比期建议: 近30天 vs 前30天（环比），或近7天 vs 前7天（短期波动）
- **多件装(N-Pack/N-Cam/KIT/bundle)对标必须先折算单台价、按配置档位分层**：单机/2-Pack 不可作为 4-Pack 本品的「直接对标」，跨档位比绝对售价无效；直接对标只取同台数竞品，邻接层只做「升级到 N-Pack」叙事（详见分析框架一.0，教训源自 B0H1VZY7W2）
- **广告数据唯一来源 = SparkX AI MCP**：Step 6、活动诊断、思维导图全部依赖 `sparkx-*` 工具取数；未接入或 `get_user_authorized_context` 拿不到 profileIds，即按「依赖与硬门禁」中止并提示接入（参考 `sparkx-mcp-tenant-onboarding`），**绝不**用 sellersprite/sorftime/估算/历史/编造替代——缺广告数据 = 报告不成立
- 报告文件命名: `{ASIN}_综合诊断报告.html`

## 验证清单

- [ ] **SparkX AI MCP 门禁已通过**：Step 6 / 活动诊断 / 思维导图的广告数据全部实时取自 `sparkx-*` 工具（`get_user_authorized_context` 已返回 profileIds）；若该 MCP 缺失或目标租户未接入，skill 已按「依赖与硬门禁」中止并提示接入，**未**产出广告部分为占位/估算/假数的报告
- [ ] KPI环比数据计算正确（手动验算ACOS = Spend/Sales）
- [ ] 竞品列表与类目实际Top sellers一致
- [ ] 竞品对标已按套装配置分层：「直接对标」竞品与本品**同台数**；所有价格比较用**单台价**；未把单机/KIT/不同 Pack 当作多件装本品的直接对标（跨档位只做升级叙事）
- [ ] Review 已按 skus 字段做**变体归属核对**：目标子ASIN自身差评与其他变体差评已分开统计；未把其他变体（如4A/10A）的差评扣到目标变体（如25A）头上推导根因；其他变体差评已归类为"父ASIN差评污染"并给出隔离/拆分/A+区隔解法（反例 B0F3C4FR8K）
- [ ] 关键词排名数据为最新（检查updatedTime）
- [ ] 价格序列已与 keepa buyBox 逐日序列交叉验证（月均偏差<10%），否则该节作废重取；禁止用 asin_sales_trend 价格列推导促销/价格类根因
- [ ] 销量/销售额已与 SparkX 后台口径（TotalSalesAmount/OrderCount，偏差<20%）交叉验证；凡环比恶化结论涉及价格归因，必须先确认两窗口 keepa 价格确实不同
- [ ] 广告活动花费总和 ≈ ASIN级Spend（允许±10%误差，因含其他ASIN）
- [ ] 思维导图所有节点可正常收起/展开
- [ ] 思维导图每个策略节点含**广告位溢价**建议（TOS/商品页/其余搜索 或 SB顶部）；泛词活动明确溢价清零并附实证
- [ ] 报告含"成交价口径解释"表：页面成交价/实付价/额面券/秒杀会员价/现点价/GMV隐含 逐行注明来源与采用状态；结账促销已用 SIF 日粒度 promotion 字段检测
- [ ] AOV口径已标注：GMV÷OrderCount 为每单金额（含一单多套与跨变体mix），非每套单价
- [ ] 流量塌方类结论已按「框架五」playbook 逐条排查留痕，且含泛词 vs niche词季节性对照
- [ ] 广告框架预算分配为**该 ASIN 专属推导**：每个意图占比都附"为什么是这个数"的取数依据（引用生命周期/流量结构/竞争格局的具体数据），未直接套用默认中值
- [ ] HTML文件在浏览器中渲染正常（无JS报错）
