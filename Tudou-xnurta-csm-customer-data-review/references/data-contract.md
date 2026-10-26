# 通用字段和替换路径
字段为逻辑约定，不声称任意连接器已有同名字段。CSV/JSON/授权报表均可，使用者负责映射；不用内部DMS、CRM、私有脚本也可分析。
- context：customer_key、account/profile_id、marketplace、timezone、currency、review_start/end、baseline_start/end、recent_start/end、business_goal、report_mode、audience。
- metrics：scope_id、date或period、campaign_id、ad_type、impressions、clicks、spend、ad_sales、orders、total_sales（可选）、source_id。
- ai_intervals：campaign_id、start/end、group_id、goal、target及有效时间。按每日生效成员拆分，不能把今天的托管状态套全年。
- actions：对象、时间、动作、操作者类型、旧值/新值、来源；没有日志不能捏造动作。
- customer_context：目标、合同阶段、已确认负责人、服务/会议事项和执行状态；只取必要信息。
- optional：ASIN映射、搜索词/定向、预算时段、市场样本、使用事件、功能权限。缺项限制对应章节。
- coverage：来源、提取时间、完整截止日、日期覆盖、归因窗口、零/缺失区别、去重键。
ACOS=Σspend/Σad_sales；ROAS=Σad_sales/Σspend；CPC=Σspend/Σclicks；CTR=Σclicks/Σimpressions；CVR=Σorders/Σclicks；TACOS仅在真实total_sales存在时=Σspend/Σtotal_sales。分母0为不可计算。货币不混加。增长率=(后−前)/前，前=0不输出普通增幅。比例变化可用百分点。
AI数量/花费/销售占比各用对应总量分母并明确资格范围。不同归因窗口或粒度不能强合。
