# 自然用户请求与复跑输入

用 `$sparkx-store-review` 做示例品牌 4 月广告复盘，上期按 3 月自然月。给我可离线打开的 HTML，能看店铺和品线的投入与效率变化，首页能按国家和品线筛选，并列出客户该优先分析的父 ASIN 及下一步检查方向。

本案例使用合成的两期汇总输入，直接用 [input.json](input.json) 复跑。示例金额均为模拟 USD，客户名称、店铺和商品标识均为虚构。

```text
python scripts/render_report.py examples/case-01/input.json examples/case-01/report.html
```

从 Skill 根目录运行。浏览器打开 [示例成品](report.html)，用导航进入「重点关注」。
