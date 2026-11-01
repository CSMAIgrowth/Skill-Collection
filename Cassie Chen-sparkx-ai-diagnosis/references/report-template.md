# 报告 HTML 模板与图表实现

本页数字均为虚构的排版示例，不代表客户实际经营数据；实际使用须替换为已核验数据。

单文件 HTML，无外部依赖。图表全部用纯 CSS div 条形或内联 SVG。下面是可直接复用的骨架。

**报告结构顺序**：⓪ 目标达成区（第一屏）→ 责任判定 → KPI 卡片 → 结论 → 论据图 → 证伪测试表 → 建议 → 方法说明。

## 页面骨架

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>诊断报告 · [活动名]</title>
<style>
  body{font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1a2233;padding:32px 20px;}
  .wrap{max-width:920px;margin:0 auto;}
  h1{font-size:20px;} .sub{color:#6b7280;font-size:13px;margin-bottom:20px;}
  h2{font-size:15px;margin:26px 0 10px;padding-left:8px;border-left:4px solid #1652f0;}
  .verdict{background:#fff;border-radius:10px;padding:16px 20px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:14px;font-size:14px;line-height:1.8;}
  .kpi-row{display:flex;gap:12px;flex-wrap:wrap;}
  .kpi{flex:1;min-width:130px;background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);}
  .kpi .label{font-size:12px;color:#6b7280;} .kpi .val{font-size:22px;font-weight:700;margin-top:2px;}
  .good{color:#0e9f6e;} .bad{color:#e02424;}
  table{width:100%;border-collapse:collapse;background:#fff;font-size:13px;box-shadow:0 1px 3px rgba(0,0,0,.06);}
  th{background:#eef1f6;padding:8px 10px;text-align:right;} td{padding:7px 10px;text-align:right;border-top:1px solid #eef0f4;}
  th:first-child,td:first-child{text-align:left;}
  .note{font-size:12px;color:#6b7280;margin-top:8px;line-height:1.6;}
  .maybe{background:#fff7e6;font-size:11px;padding:1px 8px;border-radius:10px;}
  .goal-card{background:#fff;border-radius:10px;padding:16px 20px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:14px;}
  .goal-line{display:flex;justify-content:space-between;font-size:13px;padding:4px 0;border-bottom:1px dashed #eef0f4;}
  .goal-line .k{color:#6b7280;}
  .bar-row{display:flex;align-items:center;gap:10px;margin:10px 0;}
  .bar-row .bl{width:170px;font-size:13px;}
  .bar-track{flex:1;height:14px;background:#eef1f6;border-radius:7px;overflow:hidden;position:relative;}
  .bar-fill{height:100%;border-radius:7px;}
  .bar-row .bv{width:150px;font-size:12px;text-align:right;}
  .goal-tag{font-size:11px;padding:1px 8px;border-radius:10px;white-space:nowrap;}
</style></head>
<body><div class="wrap">
  <h1>[活动名] · 诊断报告</h1>
  <div class="sub">[站点] · [类型] · 分析期 [X] ~ [Y] · AI 托管期 [A] ~ [B] · 数据截至 [D]（T+2 归因）</div>
  <h2>⓪ 托管目标与达成情况</h2>[目标设置清单 + 目标 vs 实际进度条，见下方"目标达成区"]
  <div class="verdict"><b>责任判定：[AI 导致 / 人工导致 / 非操作因素]</b><br>根因：[一句话机制解释，见 references/falsification.md 模板]</div>
  <div class="kpi-row">[4-5 个 KPI 卡片]</div>
  <h2>一、结论</h2>[3-4 句]
  <h2>二、论据</h2>[2-4 张图 + 每图 1-2 句解读]
  <h2>三、操作审查（证伪测试）</h2>[全表，含排除项]
  <h2>四、建议</h2>[P0/P1/P2]
  <div class="note">方法：证伪测试框架（时序/方向/量级三条件）· 数据：SparkX AI 平台 get_ads_perf / get_operation_log / get_entity_metadata · 归因延迟 T+2</div>
</div></body></html>
```

## 目标达成区（报告开头第一屏）

上半部分：目标设置清单（数据来自 get_entity_metadata(entity='aiGroup')）。下半部分：目标 vs 实际进度条。**只陈述，不判责**。

```html
<div class="goal-card">
  <div style="font-size:13px;font-weight:600;margin-bottom:8px;">托管组目标设置</div>
  <div class="goal-line"><span class="k">目标类型</span><span>保持订单稳定（Optimize ROAS）</span></div>
  <div class="goal-line"><span class="k">目标 ACOS</span><span>25%</span></div>
  <div class="goal-line"><span class="k">AI 人格</span><span>3</span></div>
  <div class="goal-line"><span class="k">开启的行动空间</span><span>竞价优化 · 预算分时 · 预算再分配 · 否定投放</span></div>
  <div class="goal-line"><span class="k">组日预算</span><span>$80</span></div>
</div>
<div class="goal-card">
  <div style="font-size:13px;font-weight:600;margin-bottom:4px;">目标 vs 实际（托管期均值）</div>
  <div class="bar-row">
    <span class="bl">ACOS（目标 25%，越低越好）</span>
    <div class="bar-track"><div class="bar-fill" style="width:62.5%;background:#e02424;"></div></div>
    <span class="bv">实际 40% <span class="goal-tag" style="background:#fee2e2;color:#b91c1c;">达成 62.5%</span></span>
  </div>
  <div class="bar-row">
    <span class="bl">日预算利用（目标 $80）</span>
    <div class="bar-track"><div class="bar-fill" style="width:75%;background:#f59e0b;"></div></div>
    <span class="bv">实际 $60 <span class="goal-tag" style="background:#fff7e6;color:#b45309;">达成 75%</span></span>
  </div>
  <div class="bar-row">
    <span class="bl">订单稳定（基线 35 单/周）</span>
    <div class="bar-track"><div class="bar-fill" style="width:102.9%;background:#0e9f6e;"></div></div>
    <span class="bv">实际 36 单/周 <span class="goal-tag" style="background:#e8f7f0;color:#0e9f6e;">达成 102.9%</span></span>
  </div>
  <div class="note">达成率算法：ACOS 等越低越好的指标 = 目标÷实际；预算利用、订单等越高越好 = 实际÷目标。≥100% 绿 / 70–99% 黄 / <70% 红。目标类型不可量化时用代理指标并注明（如"保持订单稳定"用订单达成为代理）。</div>
</div>
```

## 图 1：前后对比双序列（默认必有）

横向排布两组条形（托管前蓝 / 托管后红），或日期轴上柱+线。托管时刻画黄色竖虚线。

```html
<div style="display:flex;align-items:flex-end;gap:4px;height:160px;background:#fff;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,.06);">
  <!-- 每日一根柱：蓝色=托管前，红色=托管后；height = 花费归一化 -->
  <div style="flex:1;background:#3b82f6;height:80%;"></div>
  <div style="flex:1;background:#3b82f6;height:75%;"></div>
  <!-- AI 开启分界 -->
  <div style="width:2px;background:#f59e0b;height:100%;"></div>
  <div style="flex:1;background:#ef4444;height:40%;"></div>
  ...
</div>
```

图注写法（说明"看什么"）：*"AI 开启后（红线右侧）日花费未降，但订单（图中圆点线）下台阶。"*

## 图 2：错位对比分布图（损失集中点）

分组柱状，横轴小时/广告位/词分层；关键区间加半透明背景高亮。

```html
<div style="position:relative;background:#fff;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,.06);">
  <!-- 高亮区间：绝对定位半透明底色 -->
  <div style="position:absolute;left:40%;width:20%;top:0;bottom:0;background:#fde68a55;"></div>
  <div style="display:flex;align-items:flex-end;gap:6px;height:140px;position:relative;">
    <!-- 每个时段两根柱：8月蓝 / 9月红 -->
  </div>
  <div style="display:flex;gap:12px;font-size:12px;color:#6b7280;margin-top:8px;">
    <span><span style="color:#3b82f6;">■</span> 托管前</span>
    <span><span style="color:#ef4444;">■</span> 托管后</span>
    <span><span style="color:#f59e0b;">▮</span> 高峰时段</span>
  </div>
</div>
```

## 图 3：订单变化瀑布拆解

正负双色横条，每行一个流向：

```html
<div style="background:#fff;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,.06);">
  <!-- 每行：label + 条(宽度=单量) + 数值 -->
  <div style="display:flex;align-items:center;gap:8px;margin:6px 0;">
    <span style="width:220px;font-size:13px;">长尾词自然消退（45→18 个）</span>
    <div style="width:60%;"><div style="width:82%;background:#ef4444;height:16px;border-radius:3px;"></div></div>
    <span class="bad" style="font-size:13px;">-18</span>
  </div>
  <div style="display:flex;align-items:center;gap:8px;margin:6px 0;">
    <span style="width:220px;font-size:13px;">头部词轻度缩水</span>
    <div style="width:60%;"><div style="width:32%;background:#ef4444;height:16px;border-radius:3px;"></div></div>
    <span class="bad">-7</span>
  </div>
  <div style="display:flex;align-items:center;gap:8px;margin:6px 0;">
    <span style="width:220px;font-size:13px;">新增出单词补进</span>
    <div style="width:60%;"><div style="width:14%;background:#0e9f6e;height:16px;border-radius:3px;"></div></div>
    <span class="good">+3</span>
  </div>
  <div style="display:flex;align-items:center;gap:8px;margin:10px 0 2px;border-top:1px solid #e5e7eb;padding-top:8px;">
    <span style="width:220px;font-weight:600;">净变化</span>
    <span class="bad" style="font-weight:700;">-22</span>
  </div>
</div>
```

## 图 4：操作时间轴

横向时间轴，指标曲线（SVG polyline）+ 操作标记（色点：AI=红、人工=蓝、系统=灰）。

```html
<svg viewBox="0 0 900 200">
  <polyline points="..." stroke="#1a2233" fill="none"/>
  <line x1="300" y1="0" x2="300" y2="180" stroke="#f59e0b" stroke-dasharray="4"/>
  <circle cx="360" cy="120" r="6" fill="#ef4444"/><text x="360" y="105" font-size="11" text-anchor="middle">否词 7 条</text>
</svg>
```

## 用词规范

| 场景 | 用词 |
|---|---|
| 三条件全过 | 导致因素 / 是 X 造成的 |
| 过两条 | 可能原因（配 .maybe 黄标） |
| 仅时序 | 时间相关，已排除 |
| 数据回填不完整 | 末段数据未回填完整，按保守口径 |
| 量级不匹配的操作 | 无害噪音（列出但明确标注无影响） |
