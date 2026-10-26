# 登记卡
1. 名称：大促复盘；标识：tudou-promotion-review；版本：0.1.0；登记编号：由收集方分配。
2. 作者/维护：土豆负责改造；原素材归属保留，见references/provenance.md，公开分发许可尚需核实。
3. 使用对象与场景：CSM在本客户授权范围内执行大促复盘。
4. 输入：见正文输入；客户/日期/目标等不写死；合成案例见examples/acceptance.md。
5. 输出：正文规定的报告或表格；关键数字可复算，缺口不得虚构。
6. 依赖与环境：SparkX MCP只读工具实际schema；卖家精灵/SIF可选；条件材料缺失按正文降级，无内部数据库依赖。
7. 权限与安全：不携带凭证/客户数据，不改广告或自动发送；越权scope停止。
8. 文件与运行：SKILL主体由Workshop提案承载；references与examples随包；本卡正式导出映射包根REGISTRATION.md；仓库外层建议Tudou-promotion-review，标准包内部目录保持tudou-promotion-review。
9. 测试与证据：只有合成测试设计，真实客户/独立新案例/缺权限实跑/不适用实跑均未执行。静态检查另附回执，不用预期当actual-output。
10. 状态与下一步：改造草稿pending，未安装、未提交PR。土豆先完成静态审查，再在获授权且工具可用的客户环境补正常、独立案例、缺数/权限和不适用验证；凭证/内部地址/客户信息全包扫描后再提审。