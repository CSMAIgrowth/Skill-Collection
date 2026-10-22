"""
Skill Extraction SP 托管组推荐分析脚本 (独立版)
================================================
通过 JSON 输入读取店铺 SP (Sponsored Products) 托管组 / ASIN 数据, 加载 v9.1 引擎,
提取 Tier 0-3 特征, 运行推荐, 输出 JSON 报告。

Scope: SP only. SB/SD groups are filtered out.

Usage:
    python recommend.py --groups groups.json --asins asins.json --model pool_min.pkl.gz --marketplace US --output report.json

输入 JSON 格式见 references/feature_definitions.md。
"""

import sys, os, json, argparse, pickle, gzip
from datetime import datetime
import pandas as pd
import numpy as np

# Windows 终端 UTF-8 兼容
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 引擎导入 (同目录下的 query_engine.py)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from query_engine import (
    QueryEngine, bucket_campaign_budget, bucket_acos_bin,
    VALUE_ORDER, TIER_1_FEATURES, TIER_2_FEATURES, TIER_3_FEATURES,
    WHITELIST_PARAMS,
)

# ==================== 常量 ====================

TODAY = datetime.now()

# 价格分箱边界
PRICE_BINS = [
    (30, '高价'),
    (20, '中高价'),
    (13, '中价'),
    (8,  '中低价'),
    (0,  '低价'),
]

# 13 白名单参数的 On/Off 值映射
PARAM_VALUE_MAP = {0: 'Off', 1: 'On'}

# On/Off 参数列表
ON_OFF_PARAMS = {
    'bidAdPlaceStatus', 'bidPerformanceStatus', 'bidDaypartStatus',
    'budgetDaypartStatus', 'budgetDynamicStatus', 'budgetRedistributeStatus',
    'negativeTargetStatus', 'structPauseCampaignStatus', 'structPauseProductStatus',
    'targetHarvestStatus', 'targetPausedAddStatus',
}

# aiPersonality 映射
PERSONALITY_MAP = {1: 'Conservative', 2: 'Moderate', 3: 'Balanced', 4: 'Aggressive', 5: 'Very Aggressive'}

# negativeTargetStatus 特殊值映射
NEG_TARGET_MAP = {0: 'Off', 1: 'On', 3: '待确认'}


# ==================== 分箱函数 ====================

def assign_bsr_bucket(bsr):
    """BSR 排名分箱 (输入必须为百分位 0-100, 非绝对排名)
    如输入为绝对排名, 需先通过品类大小转换为百分位后再传入。
    """
    if bsr is None or bsr == 0:
        return '未知'
    # 百分位校验: 若输入 > 100 则可能是绝对排名而非百分位
    if bsr > 100:
        return '未知'  # 超出百分位范围, 需先转换
    if bsr <= 1:       return 'Best Seller'
    if bsr <= 10:      return '热销'
    if bsr <= 50:      return '中等'
    if bsr <= 80:      return '中下'
    if bsr <= 95:      return '长尾'
    return '极长尾'


def assign_inventory_status(asin_row):
    """从 ASIN 元数据推断库存状态"""
    if not asin_row:
        return None
    fba = asin_row.get('asinFbaQuantity') or 0
    fbm = asin_row.get('asinFbmQuantity') or 0
    total = fba + fbm
    if total == 0:
        return None  # 数据不足
    if total >= 100:  return '库存冗余'
    if total >= 50:   return '库存充足'
    if total >= 20:   return '库存适中'
    return '库存紧张'


def assign_lifecycle(open_date_str, today=None):
    """从 asinOpenDate 推断生命周期"""
    if not open_date_str:
        return None
    if today is None:
        today = datetime.now()
    try:
        # 解析 "2026-06-15 03:22:05 PDT" 或 "2026-06-15" 格式
        parts = open_date_str.split(' ')
        if len(parts) >= 2:
            clean = parts[0] + ' ' + parts[1]
            dt = datetime.strptime(clean, '%Y-%m-%d %H:%M:%S')
        else:
            dt = datetime.strptime(parts[0], '%Y-%m-%d')
        days = (today - dt).days
    except Exception:
        return None

    if days < 0:
        return None
    if days < 180:   return '新品冷启动'
    if days < 365:   return '新品成长'
    if days < 730:   return '成长期'
    if days < 1095:  return '成熟期'
    return '老品'


def assign_price_bucket(price):
    """价格分箱"""
    if price is None:
        return None
    for threshold, label in PRICE_BINS:
        if price >= threshold:
            return label
    return '低价'


def assign_category_l1(title):
    """从 ASIN title 关键词推断一级品类"""
    if not title:
        return None
    t = title.lower()
    if any(w in t for w in ['mount', 'bracket', 'holder', 'stand', 'desk']):
        return 'Home'
    elif any(w in t for w in ['pet', 'grooming', 'dog', 'cat']):
        return 'Pet Supplies'
    elif any(w in t for w in ['kitchen', 'cook', 'food']):
        return 'Kitchen'
    elif any(w in t for w in ['sport', 'fitness', 'yoga']):
        return 'Sports'
    else:
        return 'General'


def compute_budget_terciles(pool_df):
    """从引擎 pool 数据计算 budget 三分位边界 (复用训练集标准)"""
    col = 'campaign_budget_usd'
    if col not in pool_df.columns:
        return {'low_max': 5.0, 'mid_max': 11.74}
    pos = pool_df[col].dropna()
    pos = pos[pos > 0]
    if len(pos) == 0:
        return {'low_max': 5.0, 'mid_max': 11.74}
    log_vals = np.log1p(pos)
    terciles = log_vals.quantile([1/3, 2/3])
    return {
        'low_max': np.expm1(terciles.iloc[0]),
        'mid_max': np.expm1(terciles.iloc[1]),
    }


def assign_budget_bucket(budget, terciles):
    """用训练集三分位边界分桶"""
    if budget is None or budget == 0:
        return 'no_budget'
    log_val = np.log1p(budget)
    low_max_log = np.log1p(terciles['low_max'])
    mid_max_log = np.log1p(terciles['mid_max'])
    if log_val <= low_max_log:   return 'low'
    elif log_val <= mid_max_log: return 'mid'
    else:                        return 'high'


# ==================== 特征提取 ====================

def extract_features_for_group(group, asin_info, marketplace_id, budget_terciles):
    """
    为单个托管组提取 Tier 0-3 特征。

    原则: 数据不足或不确定的特征设为 None, 不参与引擎查询。

    Returns: dict of feature_name -> value (None = 数据不足)
    """
    features = {}

    # ---- Tier 0 (查询前提, 始终可靠) ----
    features['targetType'] = str(group.get('targetType', ''))
    features['marketplace_id'] = marketplace_id

    # ---- Tier 1 特征 ----
    price = asin_info.get('asinPrice') if asin_info else None
    features['price_bucket_mode'] = assign_price_bucket(price) if price else None

    open_date = asin_info.get('asinOpenDate', '') if asin_info else ''
    features['lifecycle_stage'] = assign_lifecycle(open_date) if open_date else None

    # promo_phase: 无实时大促日历 → None
    features['promo_phase'] = None

    title = asin_info.get('asinTitle', '') if asin_info else ''
    features['category_l1'] = assign_category_l1(title)

    # ---- Tier 2 特征 ----
    features['peak_seasons_std'] = None   # 需历史季节性
    features['variation_bin'] = None      # 需完整变体数据
    features['trend_sales_bin'] = None    # 需逐日趋势
    features['trend_imp_bin'] = None
    features['trend_click_bin'] = None

    features['inventory_status'] = assign_inventory_status(asin_info) if asin_info else None

    bsr = asin_info.get('asinBsr') if asin_info else 0
    features['bsr_bucket'] = assign_bsr_bucket(bsr) if bsr else None

    budget = group.get('totalDailyBudget', 0)
    features['campaign_budget_bucket'] = assign_budget_bucket(budget, budget_terciles) if budget else None

    # b14 性能分箱: 需要 ASIN 级 14 天表现, 通常数据不足
    features['b14_ACOS_bin'] = None
    features['b14_CTR_bin'] = None
    features['b14_CVR_bin'] = None
    features['b14_CPC_bin'] = None

    # ---- Tier 3 ----
    features['peak_month'] = None

    return features


# ==================== 参数映射 ====================

def acos_to_bin(acos):
    if acos < 15:   return 'low'
    if acos < 25:   return 'mid_low'
    if acos < 35:   return 'mid_high'
    return 'high'


def normalize_recommended_value(param, raw_val):
    """将引擎推荐的原始值 (0/1/2/3/4) 映射为可读格式 (On/Off/Balanced 等)"""
    if param == 'acos_bin':
        return str(raw_val)
    if param == 'aiPersonality':
        try:
            n = int(float(raw_val))
            return PERSONALITY_MAP.get(n, str(raw_val))
        except (ValueError, TypeError):
            return str(raw_val)
    if param == 'negativeTargetStatus':
        try:
            n = int(float(raw_val))
            return NEG_TARGET_MAP.get(n, str(raw_val))
        except (ValueError, TypeError):
            return str(raw_val)
    if param in ON_OFF_PARAMS:
        try:
            n = int(float(raw_val))
            return PARAM_VALUE_MAP.get(n, str(raw_val))
        except (ValueError, TypeError):
            return str(raw_val)
    return str(raw_val)


def extract_current_params(group):
    """
    从托管组配置中提取 13 个推荐参数的当前值。

    返回: (params_dict, missing_fields_list)
    - params_dict: 参数名 -> 当前值 (None 表示该参数缺失)
    - missing_fields: 缺失的关键字段列表
    """
    params = {}
    missing_fields = []
    settings = group.get('aiActionSettings', {})

    # targetAcos: 缺失时不默认, 标记为缺失
    raw_acos = group.get('targetAcos')
    if raw_acos is not None and raw_acos != 0:
        params['acos_bin'] = acos_to_bin(raw_acos)
    else:
        params['acos_bin'] = None
        missing_fields.append('targetAcos')

    # aiPersonality: 缺失时不默认, 标记为缺失
    raw_personality = group.get('aiPersonality')
    if raw_personality is not None and raw_personality != 0:
        params['aiPersonality'] = PERSONALITY_MAP.get(raw_personality, str(raw_personality))
    else:
        params['aiPersonality'] = None
        missing_fields.append('aiPersonality')

    for param_name in WHITELIST_PARAMS:
        if param_name in ('acos_bin', 'aiPersonality'):
            continue
        val = settings.get(param_name)
        if val is not None:
            if param_name == 'negativeTargetStatus':
                params[param_name] = NEG_TARGET_MAP.get(val, 'Off')
            else:
                params[param_name] = PARAM_VALUE_MAP.get(val, 'Off')
        else:
            params[param_name] = None
        # 参数不存在于 settings 中 → 值为 None (SP 组通常拥有全部 13 参数)

    return params, missing_fields


# ==================== 主分析 ====================

def load_engine(model_path):
    """加载 v9.1 引擎"""
    print(f"Loading model from {model_path}...")
    with gzip.open(model_path, 'rb') as f:
        df = pickle.load(f)
    print(f"  Loaded {len(df):,} rows x {len(df.columns)} cols")

    df = bucket_campaign_budget(df)
    df = bucket_acos_bin(df)
    engine = QueryEngine(df)
    terciles = compute_budget_terciles(df)
    print(f"  Budget terciles: low_max={terciles['low_max']:.2f}, mid_max={terciles['mid_max']:.2f}")

    return engine, df, terciles


def analyze_group(engine, group, asin_info, marketplace_id, budget_terciles):
    """分析单个托管组: 特征提取 -> 引擎查询 -> 对比推荐"""
    group_name = group.get('aiGroupName', f'Group {group.get("aiGroupId", "?")}')
    group_id = group.get('aiGroupId', 0)

    print(f"\n{'='*70}")
    print(f"  Group: {group_name} (ID: {group_id})")
    print(f"  ASIN: {group.get('asin', 'N/A')} | Type: {group.get('campaignType', '?')} | TT: {group.get('targetType', '?')} | ACOS: {group.get('targetAcos', '?')}%")
    print(f"{'='*70}")

    # 1. 提取特征
    features = extract_features_for_group(group, asin_info, marketplace_id, budget_terciles)
    print(f"\n  Tier 0-3 features:")
    for tier_name, tier_feats in [('Tier 1', TIER_1_FEATURES), ('Tier 2', TIER_2_FEATURES), ('Tier 3', TIER_3_FEATURES)]:
        print(f"    [{tier_name}]")
        for f in tier_feats:
            v = features.get(f)
            display = v if v is not None else '(insufficient data)'
            print(f"      {f} = {display}")

    # 2. 提取当前参数
    current_params, missing_fields = extract_current_params(group)
    if missing_fields:
        print(f"\n  ⚠ Missing config fields: {missing_fields}")
        print(f"    Recommendations for params with missing current values will be skipped.")
    print(f"\n  Current 13 params:")
    for p, v in current_params.items():
        display = v if v is not None else '(missing)'
        print(f"      {p} = {display}")

    # 3. 运行引擎
    query_features = {k: v for k, v in features.items()
                      if v is not None and k not in ('targetType',)}
    target_type = str(group.get('targetType', ''))

    active_feats = [k for k, v in features.items() if v is not None and k != 'targetType']
    skip_feats = [k for k, v in features.items() if v is None]

    print(f"\n  Engine query:")
    print(f"    Active features ({len(active_feats)}): {active_feats}")
    if skip_feats:
        print(f"    Skipped ({len(skip_feats)}): {skip_feats}")
    print(f"    target_type: {target_type}")

    result = engine.query(query_features, target_type=target_type)

    print(f"\n  Engine result:")
    print(f"    Status: {result.status}")
    print(f"    Pool size: {result.pool.get('n', 0)}")
    print(f"    Skills found: {len(result.skills)}")

    # 4. 对比推荐
    recommendations = []
    sig_order = {'显著': 0, '边缘': 1, '弱证据': 2, '不显著': 3, '证据不足': 4}

    param_top = {}
    for skill in result.skills:
        p = skill.get('param', '')
        if p not in param_top:
            param_top[p] = skill
        else:
            if sig_order.get(skill.get('significance', ''), 9) < sig_order.get(param_top[p].get('significance', ''), 9):
                param_top[p] = skill

    print(f"\n  Recommendation comparison:")
    print(f"    {'Param':<30} {'Current':<15} {'Recommended':<15} {'Sig':<10} {'Conf':<8} {'Lift':<8}")
    print(f"    {'-'*86}")

    for param in WHITELIST_PARAMS:
        current_val = current_params.get(param)
        skill = param_top.get(param)

        if skill:
            raw_rec_val = skill.get('recommended_value', 'N/A')
            rec_val = normalize_recommended_value(param, raw_rec_val)
            sig = skill.get('significance', 'N/A')
            conf = skill.get('confidence', 0)
            lift = skill.get('lift', 0)

            if current_val is None:
                display_current = '(N/A)'
            else:
                display_current = str(current_val)

            if current_val is None:
                match = '--'
            elif str(current_val) == str(rec_val):
                match = 'OK'
            else:
                match = '!!'

            print(f"    {param:<30} {display_current:<15} {rec_val:<15} {sig:<10} {conf:<8.3f} {lift:<8.4f} {match}")

            # Fix #5: enforce lift thresholds per SKILL.md spec
            # 显著: lift > 0.1; 边缘: lift > 0.05
            lift_pass = (sig == '显著' and lift > 0.1) or (sig == '边缘' and lift > 0.05)
            if current_val is not None and str(current_val) != str(rec_val) and lift_pass:
                recommendations.append({
                    'param': param,
                    'current': current_val,
                    'recommended': rec_val,
                    'significance': sig,
                    'confidence': conf,
                    'lift': lift,
                    'action': f"Change {param} from {current_val} to {rec_val}",
                })
        else:
            display_current = str(current_val) if current_val is not None else '(N/A)'
            print(f"    {param:<30} {display_current:<15} {'N/A':<15} {'N/A':<10} {'N/A':<8} {'N/A':<8}")

    return {
        'group_id': group_id,
        'group_name': group_name,
        'asin': group.get('asin', ''),
        'target_type': target_type,
        'campaign_type': group.get('campaignType', ''),
        'status': result.status,
        'pool_n': result.pool.get('n', 0),
        'n_skills': len(result.skills),
        'current_params': current_params,
        'features': features,
        'recommendations': recommendations,
        'all_skills': result.skills[:20],
    }


def run_recommendation(groups, asins, marketplace_id, model_path, output_path=None):
    """
    主入口: 运行完整推荐分析 (SP only)。

    Args:
        groups: list of dict, 托管组数据 (自动过滤非 SP 组)
        asins: dict, asin -> ASIN 产品数据
        marketplace_id: str, 店铺国家代码 (US/BR/MX/CA 等)
        model_path: str, pool_min.pkl.gz 路径
        output_path: str, 输出 JSON 路径 (可选)

    Returns:
        list of dict, 每个 SP 托管组的分析结果
    """
    # Filter: SP only — SB/SD not supported
    sp_groups = [g for g in groups if g.get('campaignType', '') == 'sponsoredProducts']
    skipped_type = len(groups) - len(sp_groups)
    if skipped_type > 0:
        print(f"  [Filter] Skipped {skipped_type} non-SP group(s) (SB/SD not supported)")

    # Fix #6: filter running status — only analyze aiStatus=1 (active) groups
    active_groups = [g for g in sp_groups if g.get('aiStatus') == 1]
    skipped_status = len(sp_groups) - len(active_groups)
    if skipped_status > 0:
        print(f"  [Filter] Skipped {skipped_status} inactive SP group(s) (aiStatus != 1)")

    if not active_groups:
        if not sp_groups:
            print("  [Error] No SP groups found. This skill only supports Sponsored Products.")
        else:
            print("  [Error] No active SP groups found (all have aiStatus != 1).")
        return []

    print("=" * 70)
    print("  Skill Extraction - SP Managed Group Recommendation Analysis")
    print(f"  Marketplace: {marketplace_id}")
    print(f"  SP Groups to analyze: {len(active_groups)}")
    print("=" * 70)

    # 1. 加载引擎
    engine, pool_df, budget_terciles = load_engine(model_path)

    # 2. 逐个分析
    all_results = []
    for group in active_groups:
        asin = group.get('asin', '')
        asin_info = asins.get(asin, {})
        result = analyze_group(engine, group, asin_info, marketplace_id, budget_terciles)
        all_results.append(result)

    # 3. 汇总
    total_recs = sum(len(r['recommendations']) for r in all_results)
    print(f"\n\n{'#'*70}")
    print(f"#  Summary Report")
    print(f"#  Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"#  Marketplace: {marketplace_id}")
    print(f"#  Groups analyzed: {len(all_results)}")
    print(f"#  Total recommendations: {total_recs}")
    print(f"{'#'*70}")

    for r in all_results:
        print(f"\n  Group: {r['group_name']} (ID: {r['group_id']})")
        print(f"  ASIN: {r['asin']} | TT: {r['target_type']} | Status: {r['status']} | Pool: {r['pool_n']}")

        # Fix #4: distinguish INSUFFICIENT / no-qualifying / config-match
        if r['status'] == 'INSUFFICIENT' or r['pool_n'] < 30:
            print(f"  ⚠ Insufficient data (pool_n={r['pool_n']}) — cannot provide reliable recommendations")
        elif r['recommendations']:
            print(f"  Recommendations ({len(r['recommendations'])}):")
            for rec in r['recommendations']:
                print(f"    - {rec['action']}")
                print(f"      sig={rec['significance']}, conf={rec['confidence']:.3f}, lift={rec['lift']:.4f}")
        else:
            print(f"  ✓ No qualifying recommendations (config aligns with top-performing peers, or lift below threshold)")

    # 4. 保存报告
    if output_path:
        report_data = []
        for r in all_results:
            report_data.append({
                'group_id': r['group_id'],
                'group_name': r['group_name'],
                'asin': r['asin'],
                'target_type': r['target_type'],
                'campaign_type': r['campaign_type'],
                'status': r['status'],
                'pool_n': r['pool_n'],
                'features': r['features'],
                'current_params': r['current_params'],
                'recommendations': r['recommendations'],
            })
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"\n  Report saved: {output_path}")

    print(f"\n  Done! Analyzed {len(all_results)} groups, found {total_recs} recommendations.")
    return all_results


# ==================== CLI 入口 ====================

def main():
    parser = argparse.ArgumentParser(description='Skill Extraction Recommendation Engine')
    parser.add_argument('--groups', required=True, help='Path to managed groups JSON')
    parser.add_argument('--asins', required=True, help='Path to ASIN data JSON')
    parser.add_argument('--perf', default=None, help='Path to performance data JSON (optional)')
    parser.add_argument('--model', required=True, help='Path to pool_min.pkl.gz')
    parser.add_argument('--marketplace', default='US', help='Marketplace ID (US/BR/MX/CA)')
    parser.add_argument('--output', default=None, help='Output report JSON path')
    args = parser.parse_args()

    # 读取输入
    with open(args.groups, 'r', encoding='utf-8') as f:
        groups = json.load(f)
    with open(args.asins, 'r', encoding='utf-8') as f:
        asins = json.load(f)

    run_recommendation(groups, asins, args.marketplace, args.model, args.output)


if __name__ == '__main__':
    main()
