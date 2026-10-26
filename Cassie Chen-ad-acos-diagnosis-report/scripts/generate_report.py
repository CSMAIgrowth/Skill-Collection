#!/usr/bin/env python3
"""
ACOS Diagnosis Report Generator
Generates a professional HTML report for AI-managed campaign ACOS deterioration.
"""

from datetime import datetime
from typing import Dict, List, Optional


def generate_html_report(data: Dict) -> str:
    """
    Generate complete HTML report from structured data.

    Args:
        data: Dictionary containing all report data

    Returns:
        HTML string
    """

    # Helper to safely get values
    def gv(key, default=""):
        return data.get(key, default)

    def kpi(key):
        return data.get('kpis', {}).get(key, {})

    # Build HTML
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{gv('campaign_name')} 流量质量恶化责任归因报告</title>
<style>
@page{{size:A4;margin:13mm}}
*{{box-sizing:border-box}}
body{{margin:0;background:#e9edf1;color:#24272b;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}}
main{{max-width:1040px;margin:24px auto;background:white;padding:48px 56px;box-shadow:0 5px 24px #1f29371c}}
h1{{font-size:30px;margin:0 0 8px;border-bottom:4px solid #c94035;padding-bottom:13px}}
.meta{{font-size:13px;color:#667085;margin:0 0 20px}}
.verdict{{border:2px solid #c94035;padding:19px 21px;background:#fff8f7}}
.verdict h2{{border:0;margin:0 0 10px;padding:0;font-size:21px;color:#c94035}}
.verdict p{{margin:8px 0}}
.kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#dfe3e7;margin:18px 0}}
.kpi{{background:#f5f6f7;padding:15px}}
.kpi b{{font-size:24px;display:block;color:#c94035}}
.background{{background:#f5f7f9;border:1px solid #dde2e7;padding:16px 18px;margin:18px 0}}
.background h3{{margin:0 0 10px;font-size:16px;color:#c94035}}
.background p{{margin:6px 0;font-size:13px}}
.background table{{width:100%;font-size:12px;border-collapse:collapse;margin:10px 0}}
.background th,.background td{{border:1px solid #d8dde2;padding:6px 8px;text-align:left}}
.background th{{background:#eef0f2}}
.chain{{display:flex;align-items:stretch;margin:18px 0;gap:4px}}
.chain .node{{flex:1;border:1px solid #d8dde2;background:#f8f9fa;padding:12px;text-align:center;min-height:78px;display:flex;align-items:center;justify-content:center;font-size:13px}}
.chain .arrow{{text-align:center;color:#c94035;font-size:24px;font-weight:700}}
h2{{font-size:21px;border-left:5px solid #c94035;padding-left:11px;margin:42px 0 14px}}
.rank{{display:inline-flex;width:34px;height:34px;border-radius:50%;background:#c94035;color:white;align-items:center;justify-content:center;margin-right:8px}}
.formula{{background:#f5f7f9;border:1px solid #dde2e7;padding:12px 15px;font-size:13px;margin:14px 0}}
.formula b{{color:#c94035}}
figure{{position:relative;margin:18px 0 26px;break-inside:avoid}}
figure img{{width:100%;display:block;border:1px solid #dfe3e7}}
figcaption{{font-size:12px;color:#667085;margin:6px 0}}
.grade{{position:absolute;right:10px;top:10px;background:#24272b;color:white;padding:4px 9px;border-radius:3px;font-size:12px;z-index:2}}
.result{{font-size:16px;font-weight:700;border:1px solid #c94035;padding:12px 15px;background:#fff8f7;margin:12px 0}}
.insights{{margin:14px 0}}
.insight{{padding:10px 14px;background:#f8f9fa;border-left:3px solid #3498db;margin:8px 0;font-size:13px}}
.insight b{{color:#3498db}}
.transition{{margin:22px 0;padding:12px 15px;background:#f5f7f9;border-top:1px solid #d8dde2;border-bottom:1px solid #d8dde2;font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:12px;margin:12px 0}}
th,td{{border:1px solid #d8dde2;padding:7px;vertical-align:top}}
th{{background:#eef0f2;text-align:left}}
.callout{{padding:12px 15px;border-left:4px solid #b96717;background:#fff0e0;margin:16px 0;font-size:13px}}
.callout b{{color:#b96717}}
footer{{font-size:11px;color:#667085;text-align:center;margin-top:32px;padding-top:16px;border-top:1px solid #dfe3e7}}
</style>
</head>
<body><main>

<h1>{gv('campaign_name')}｜流量质量恶化责任归因报告</h1>
<p class="meta">{gv('platform')} · {gv('campaign_type')} · 基准期 {gv('baseline_start')}至{gv('baseline_end')} · 托管期 {gv('analysis_start')}至{gv('analysis_end')} · 目标ACOS {gv('target_acos')}% · 时区 {gv('timezone')} · 币种 {gv('currency')}</p>
'''

    # Background
    if gv('background'):
        bg = gv('background')
        html += f'''
<div class="background">
<h3>背景信息</h3>
<p><b>托管组目标设置：</b>AI托管启动时间 {bg.get('ai_start_time', '')}，目标ACOS {bg.get('target_acos', '')}%，初始日预算 ${bg.get('initial_budget', '')}，初始竞价策略 {bg.get('initial_bid_strategy', '')}。</p>
<p><b>数据表现：</b>基准期（{bg.get('baseline_start', '')}至{bg.get('baseline_end', '')}）总花费 ${bg.get('baseline_total_spend', '')}，总订单 {bg.get('baseline_total_orders', '')}，CVR {bg.get('baseline_cvr', '')}%，ACOS {bg.get('baseline_acos', '')}%。托管期（{bg.get('analysis_start', '')}至{bg.get('analysis_end', '')}）总花费 ${bg.get('analysis_total_spend', '')}，总订单 {bg.get('analysis_total_orders', '')}，CVR {bg.get('analysis_cvr', '')}%，ACOS {bg.get('analysis_acos', '')}%。</p>
<p><b>不达目标体现在：</b>ACOS从{bg.get('baseline_acos', '')}%升至{bg.get('analysis_acos', '')}%（目标{bg.get('target_acos', '')}%），超标{bg.get('acos_excess_pp', '')}pp；订单下降{bg.get('orders_decline_pct', '')}%；CVR下降{bg.get('cvr_decline_pp', '')}pp。</p>
</div>
'''

    # Verdict: prioritize traffic-quality mechanisms over ACOS arithmetic.
    verdict = gv('verdict', {})
    html += f'''
<section class="verdict">
<h2>结论：{verdict.get('one_sentence', '')}</h2>
'''
    mechanisms = verdict.get('mechanisms', [])
    if mechanisms:
        for mechanism in mechanisms:
            html += f'<p><b>{mechanism.get("name", "机制")}：</b>{mechanism.get("conclusion", "")}</p>\n'
    else:
        traffic_quality = verdict.get('why_traffic_quality', verdict.get('why_acos_up', ''))
        html += f'<p><b>流量质量为什么变差：</b>{traffic_quality}</p>\n'
        if verdict.get('ai_failures'):
            html += f'<p><b>AI哪里没做好：</b>{verdict.get("ai_failures", "")}</p>\n'
    html += f'''<p><b>责任：</b>{verdict.get('human_responsibility', '')}</p>
</section>
'''

    # KPIs
    kpis = gv('kpis', {})
    acos = kpis.get('acos', {})
    cvr = kpis.get('cvr', {})
    orders = kpis.get('orders', {})
    cpc = kpis.get('cpc', {})
    spend = kpis.get('spend', {})
    sales = kpis.get('sales', {})

    html += f'''
<div class="kpis">
<div class="kpi"><b>{acos.get('baseline', '')}%→{acos.get('analysis', '')}%</b>ACOS {'+' if acos.get('change_pp', 0) > 0 else ''}{acos.get('change_pp', '')}pp（目标{gv('target_acos')}%）</div>
<div class="kpi"><b>{cvr.get('baseline', '')}%→{cvr.get('analysis', '')}%</b>CVR {cvr.get('change_pct', '')}%</div>
<div class="kpi"><b>{orders.get('baseline', '')}→{orders.get('analysis', '')}</b>订单 {orders.get('change_pct', '')}%</div>
<div class="kpi"><b>{cpc.get('baseline', '')}→{cpc.get('analysis', '')}</b>CPC {cpc.get('change_pct', '')}%</div>
<div class="kpi"><b>{spend.get('baseline', '')}→{spend.get('analysis', '')}</b>总花费 {spend.get('change_pct', '')}%</div>
<div class="kpi"><b>{sales.get('baseline', '')}→{sales.get('analysis', '')}</b>总销售额 {sales.get('change_pct', '')}%</div>
</div>

<div class="formula"><b>数据说明：</b>ACOS/CVR/CPC均从<b>总量</b>重算（不平均每日百分比）。基准期共{gv('baseline_days', '')}天，托管期共{gv('analysis_days', '')}天。花费为<b>期间总计</b>，日均花费=总花费÷天数。</div>
'''

    # Optional causal chain: action -> traffic change -> conversion result.
    mechanism_chain = gv('mechanism_chain', [])
    if mechanism_chain:
        html += '<div class="chain">'
        for i, node in enumerate(mechanism_chain):
            html += f'<div class="node">{node}</div>'
            if i < len(mechanism_chain) - 1:
                html += '<div class="arrow">→</div>'
        html += '</div>'

    # Problems
    for p in gv('problems', []):
        html += f'''
<h2><span class="rank">{p.get('rank', '')}</span>{p.get('title', '')}</h2>
'''
        if p.get('chain'):
            html += '<div class="chain">'
            for i, node in enumerate(p.get('chain', [])):
                html += f'<div class="node">{node}</div>'
                if i < len(p.get('chain', [])) - 1:
                    html += '<div class="arrow">→</div>'
            html += '</div>'

        if p.get('chart_b64'):
            html += f'''
<figure><div class="grade">{p.get('grade', '')} {p.get('grade_type', '')}</div>
<img src="data:image/png;base64,{p.get('chart_b64', '')}" alt="">
<figcaption>{p.get('chart_caption', '')}</figcaption></figure>
'''

        if p.get('formula'):
            html += f'<div class="formula">{p.get("formula", "")}</div>'

        if p.get('analysis'):
            html += f'<p>{p.get("analysis", "")}</p>'

        if p.get('insights'):
            html += '<div class="insights">'
            for idx, insight in enumerate(p.get('insights', []), 1):
                html += f'<div class="insight"><b>Insight {idx}｜{insight.get("title", "")}</b> {insight.get("content", "")}</div>'
            html += '</div>'

        if p.get('result'):
            html += f'<p class="result">结论：{p.get("result", "")}</p>'

        if p.get('transition'):
            html += f'<div class="transition">{p.get("transition", "")}</div>'

    # AI vs Human
    ai_human = gv('ai_human_table', [])
    if ai_human:
        html += '<h2>AI还是人工</h2><table><thead><tr><th>检查项</th><th>证据</th><th>结论</th></tr></thead><tbody>'
        for row in ai_human:
            html += f'<tr><td>{row.get("item", "")}</td><td>{row.get("evidence", "")}</td><td><b>{row.get("conclusion", "")}</b></td></tr>'
        html += '</tbody></table>'

    # Recommendations
    recs = gv('recommendations', [])
    if recs:
        html += '<h2>动作建议</h2><table><thead><tr><th>动作</th><th>触发条件</th><th>验证与回滚</th></tr></thead><tbody>'
        for rec in recs:
            html += f'<tr><td>{rec.get("action", "")}</td><td>{rec.get("trigger", "")}</td><td>{rec.get("verify", "")}</td></tr>'
        html += '</tbody></table>'

    # Data boundary
    if gv('data_boundary'):
        html += f'<div class="callout"><b>数据边界：</b>{gv("data_boundary", "")}</div>'

    if gv('plain_conclusion'):
        html += f'<div class="callout"><b>最终通俗结论：</b>{gv("plain_conclusion", "")}</div>'

    # Footer
    html += f'''
<footer>数据截止 {gv('data_cutoff', '')} · 报告重构 {datetime.now().strftime("%Y-%m-%d")} · 数据源：{gv('data_sources', '')}</footer>

</main></body></html>
'''

    return html


def save_report(html: str, filepath: str):
    """Save HTML report to file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)


# Example usage: synthetic demonstration only; no real customer records.
if __name__ == '__main__':
    sample_data = {
        "campaign_name": "虚构演示活动 A（非真实客户数据）",
        "platform": "Amazon（演示）",
        "campaign_type": "SP手动广告",
        "baseline_start": "2000-01-01",
        "baseline_end": "2000-01-14",
        "analysis_start": "2000-01-15",
        "analysis_end": "2000-01-28",
        "target_acos": 30,
        "timezone": "UTC",
        "currency": "USD",
        "baseline_days": 14,
        "analysis_days": 14,
        "background": {
            "ai_start_time": "2000-01-15 00:00（虚构）",
            "target_acos": 30,
            "initial_budget": 30,
            "initial_bid_strategy": "虚构设置，不是建议参数",
            "baseline_start": "2000-01-01",
            "baseline_end": "2000-01-14",
            "baseline_total_spend": 300,
            "baseline_total_orders": 40,
            "baseline_cvr": 20,
            "baseline_acos": 25,
            "analysis_start": "2000-01-15",
            "analysis_end": "2000-01-28",
            "analysis_total_spend": 300,
            "analysis_total_orders": 20,
            "analysis_cvr": 8,
            "analysis_acos": 50,
            "acos_excess_pp": 20,
            "orders_decline_pct": 50,
            "cvr_decline_pp": 12
        },
        "verdict": {
            "one_sentence": "虚构演示：总花费相同时订单减少，需要核查时段、词池与商品因素",
            "mechanisms": [
                {
                    "name": "演示假设：时段错配",
                    "conclusion": "若实际日志与窗口表现一致，可进一步检验竞价和预算的影响；这里没有真实日志，不构成客户归因。"
                }
            ],
            "human_responsibility": "仅演示字段，不对任何真实客户的AI、人工或系统责任作判断。"
        },
        "mechanism_chain": [
            "构造的操作假设",
            "待核实的流量变化机制",
            "虚构指标对比，不证明因果"
        ],
        "kpis": {
            "acos": {
                "baseline": 25,
                "analysis": 50,
                "change_pp": 25
            },
            "cvr": {
                "baseline": 20,
                "analysis": 8,
                "change_pct": -60
            },
            "orders": {
                "baseline": 40,
                "analysis": 20,
                "change_pct": -50
            },
            "cpc": {
                "baseline": 1.5,
                "analysis": 1.2,
                "change_pct": -20
            },
            "spend": {
                "baseline": 300,
                "analysis": 300,
                "change_pct": 0
            },
            "sales": {
                "baseline": 1200,
                "analysis": 600,
                "change_pct": -50
            }
        },
        "problems": [
            {
                "rank": 1,
                "title": "演示：如何核查时段错配假设",
                "grade": "示例",
                "grade_type": "非真实证据",
                "formula": "窗口订单保留率＝托管期窗口日均订单÷基准期窗口日均订单。",
                "analysis": "先核实两期可比窗口，再对齐操作、预算可用性和表现；本示例不提供客户级原始记录。",
                "insights": [
                    {
                        "title": "不能从汇总指标直接归因",
                        "content": "还需检查操作来源、位置与搜索词数据，以及售价和库存等替代解释。"
                    }
                ],
                "result": "仅展示报告结构，不支持任何真实责任结论。"
            }
        ],
        "ai_human_table": [
            {
                "item": "日志完整性",
                "evidence": "未接入真实日志",
                "conclusion": "仅演示，不判定完整性"
            },
            {
                "item": "定向及预算操作来源",
                "evidence": "待实际授权查询",
                "conclusion": "不预设AI责任"
            },
            {
                "item": "人工操作",
                "evidence": "待实际授权查询",
                "conclusion": "不预设人工责任"
            }
        ],
        "recommendations": [
            {
                "action": "建议在核实后设计单变量分时对照，尚未实施",
                "trigger": "实际证据支持时段错配，且具备操作授权",
                "verify": "事先确定观察窗口、订单/CVR目标和回滚条件"
            }
        ],
        "data_boundary": "全部案例数值、日期和名称均为独立构造的虚构演示，不是客户实测结果。基准期点击200、订单40、花费300、销售1200；分析期点击250、订单20、花费300、销售600；各14天，币种USD。ACOS、CVR、CPC从这些总量重算。未拉取真实日志或位置数据，不能据此认定责任或执行广告变更。",
        "plain_conclusion": "此示例只演示报告结构和指标计算，不披露客户经营数据，也不代表已验证的改善成效。",
        "data_cutoff": "2000-01-28（虚构）",
        "data_sources": "独立构造的虚构演示数据"
    }

    report_html = generate_html_report(sample_data)
    save_report(report_html, 'sample_traffic_quality_report.html')
    print('Synthetic sample report generated: sample_traffic_quality_report.html')
