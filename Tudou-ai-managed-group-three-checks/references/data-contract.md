# 可替换输入约定
CSV/JSON均可。百分比用小数（0.25=25%），金额保持原币；ID作为字符串。
- context：customer_id、account_id、D、timezone（IANA）、currency、source、extracted_at、complete_through、attribution_window。
- groups：group_id、run_start、run_end（空表示尚在运行）；本轮连续运行区间须覆盖D 00:00。
- members：group_id、campaign_id、valid_from、valid_to；采用[from,to)；D落在区间内才纳入。
- daily：campaign_id、date、currency、clicks、spend、ad_sales、orders。稳定键去重，明确零值与未返回日期的区别；缺行不能自动补零。
- targets：group_id、valid_from、valid_to、target_acos、source。后期末D+14日结束时的生效目标；可仅提供current_target但须标记代理、时间和不能严格核验。
输入亦可用经核验的窗口汇总，但必须附固定成员列表、日期覆盖证明及原始分子分母。不能只提供ACOS。
