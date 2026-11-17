# 数据坑清单

公开版本保留作者提供的排查方法，移除了原客户的精确经营数字和事件日期；上传环节未独立复跑。

## 1. 托管组维度不能做逐日判定（最贵的一课）
`campaign.aiGroupId_` 和 `aiGroup.aiStatus_` 都是**当前绑定的回填**，不是按天历史。

验证方法：选取报表窗口早于托管组创建日的活动，检查历史报表是否回填当前绑定；不要用当前绑定当逐日历史。成员加入、移出日志也可能缺少活动标识，应先验证字段完整性再使用。

曾经误判过：只看新建组与短窗口可能显示「零违规」，不能据此认定字段保存了按天历史归属。要证伪必须用**窗口早于组创建日**的样本。

## 2. 多页取数必须给确定性 orderBy
不给 `orderBy` 时服务端排序不稳定，翻页会**同时**发生两件事：部分行重复返回、另一部分行被挤掉。所以行级求和与行数都不可信，而且**不能靠整行元组去重补救**（去重后仍可能缺行）。

验证方式：同一店、同一窗口分别检查无排序与确定性排序的分页结果，用引擎店级聚合独立核对行级求和，不以去重成功代替完整性校验。

规范：任何 pageSize=500 的分页都要带 `date + 主键` 排序，取完立刻做双校验（整行去重零副本、行级求和等于引擎聚合，容差 0.5%）。允许极少量（<0.5%）整行完全重复的副本存在，那是数据源噪声不是翻页问题。

## 3. 日期格式不统一，比较前必须归一
报表返回的 `date` 是 `20261108`（无横线），入参是 `YYYY-MM-DD`。直接把两者字符串比较会出错：`'-'` 的 ASCII 小于数字，导致 `2026-11-12 < 20261108` 恒成立，所有事件都被判成「早于任何一天」，逐日状态被最后一次切换全覆盖。

## 4. 时区有三套
托管组操作日志 `createdDate` 是 UTC；元数据里的 `createTime`/`statusOnDate`/`lastStatusOnDate` 是店铺时区；报表 `date` 也是店铺时区。换算后再比较（实测换算后日志与元数据的 `lastStatusOffDate` 逐条吻合）。同一响应里混查多类实体等于混用多套时钟。

## 5. AI 指标只有四件套，且只在活动层有真值
`AISpend` / `AISales` / `AIACOS` / `AIROAS`。**没有** `AIImpressions`、`AIClicks`、`AIConversions`、`AISalesSameSKU`（直接报 `unknown field`）。`asin` 事实表完全不含 AI 列（要 `AISpend` 会报 `unknown field 'totalAICost'`）。小时级与 keywordPlacement 的 AI 指标是占位的 0/null。

所以「AI 的曝光/点击/订单/CPC/CTR/CVR」只能靠**分组求和重算**得到，不能指望取字段。

## 6. 分页与截断字段不可信
`hasNextPage`、`total` 常为空，按它们判断会把首页当全量。必须按「返回行数 < pageSize」继续翻页。长 ID 过滤列表会被服务端截断或报错，需分批。`get_operation_log` 的 `operationType IN [...]` 过滤服务端不生效（仍返回 addCampaigns、acos、optimizeType 等），必须本地二次筛；筛开关事件要用**精确匹配** `Turn on Managed group AI` / `Turn off Managed group AI`，用 `"managed group ai" in` 子串会把 `Set the objective of managed group AI`、`Set the target value of managed group AI` 误判成开关事件。

## 7. 粒度与重复副本
`productAd`（推广商品）的真实粒度是 店×日×子体×活动×**广告组**，漏掉 `adGroupId` 会把同一活动内不同广告组的钱折叠掉。结果集中字段完全相同的重复副本要**取一而非相加**。

## 8. 币种不能跨店相加
单店返回本币（US=USD、CA=CAD、JP=JPY、UK=GBP、DE=EUR、AU=AUD）。逐店本币直接相加会严重虚高。跨店或账号级金额必须用一次多店调用的折美元聚合口径；本币金额只做店内结构与占比。

## 9. 品牌广告落不到商品
`sponsoredBrands` 在 `productAd` 层返回 0 行，SD 与 SP 正常。未归属列要覆盖**所有指标**（花费、曝光、点击、订单），不能只处理花费。

## 10. 其他会静默出错的点
- `OrderCount` 是全店订单，不能当广告 CVR 的分子；广告订单用 `Conversions`。
- Vendor 店铺同一（店,日,子体）在 `asin` 事实表最多 4 行（不同观察角度），相加会虚高到 4 倍。
- 窗口硬上限 90 天；超窗口要拆成不重叠区间分别取。
- 单次 sandbox 命令约 600 秒上限，全账号级任务要放后台并按实体断点续跑。
- 明细绝不能回读进对话上下文：一页 500 行约 2.9 万 token。脚本内部消化、只打印聚合。
