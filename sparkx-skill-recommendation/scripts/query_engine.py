"""
Phase 6: 查询引擎框架 (v7b)

核心架构: case-based reasoning（查询时动态分组）
三要素分工: 相似度(筛选) / 作用度(排序) / 置信度(标注)

输入: query(features: dict)
输出: {pool, skills, fairness, status}
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import warnings

# ==================== 常量定义 ====================

N_MIN = 200       # 最小池大小（噪声底校准后定）
N_FLOOR = 50      # 最低池阈值（低于则跳过 stratum L0 探测，直接走放宽）
STRATUM_N_MIN = 100  # 单个 stratum 最小样本量（top 30% ≥ 30 才稳）
ABSOLUTE_MIN = 30    # 绝对最低线：pool >= 此值仍可输出 DEGRADED_HEAVY
MAX_RELAX_STEPS = 2  # Tier 2 最大放宽步数
SHUFFLE_TIMES = 100  # 噪声资格检验打乱次数
CONFIDENCE_THRESHOLD = 0.80  # lift 基线 80 分位（临时放宽以获取更多 params）

# Stratum 降维层级定义
# 优先级: stratum 合并 > X 放宽 > L2 质心
# 原因: 合并保留原始样本（高相似度），放宽引入低相似度样本
STRATUM_MERGE_LEVELS = {
    0: 'full',        # tt × mkt（最精细）
    1: 'mkt_bin',     # tt × (US / non-US)
    2: 'tt_only',     # tt only（忽略 marketplace）
    3: 'none',        # 不分层（整个池作为一个 stratum）
}

# Tier 分级定义 (PLAN v4 §1.2, 2026-10-06)
# promo_phase 从 T2 移入 T1: 大促阶段是核心业务维度, 最后防线
#
# !! 列表顺序 = 轮转顺序 (round-robin 按此序遍历) !!
# 放宽总序: T3 → T2 → T1 (先让不重要的)
# Tier 内部序: PLAN §1.2 规定

TIER_1_FEATURES = [
    'price_bucket_mode',    # T1 第1道: price 相邻档
    'lifecycle_stage',      # T1 第2道: lifecycle 相邻档
    'promo_phase',          # T1 第3道: promo 相位链对称让步
    'category_l1',          # T1 最后: 名义, 一步放弃
]
TIER_2_FEATURES = [
    'peak_seasons_std',     # T2 第1道
    'variation_bin',        # T2 第2道: 稀疏无序, 一轮放弃
    'trend_sales_bin',      # T2 第3道
    'trend_imp_bin',        # T2 第4道
    'inventory_status',     # T2 第5道
    'bsr_bucket',           # T2 第6道
    'campaign_budget_bucket',  # T2 第7道
    'b14_ACOS_bin',         # T2 第8道
    'b14_CTR_bin',          # T2 第9道
]
TIER_3_FEATURES = [
    'peak_month',           # T3 第1道: ±月距离扩展
    'b14_CVR_bin',          # T3 第2道
    'b14_CPC_bin',          # T3 第3道
    'trend_click_bin',      # T3 第4道
    'marketplace_id',       # T3 最后: 名义, 一轮放弃
]

# [v9] 白名单 (用户裁决, 引擎不得自行增删)
# 13 参数 = 推荐池 = CONFIG_FULL_COLS
WHITELIST_PARAMS = [
    'acos_bin',  # v9: 分箱替代原始 acos
    'aiPersonality',
    'bidAdPlaceStatus', 'bidPerformanceStatus', 'bidDaypartStatus',
    'budgetDaypartStatus', 'budgetDynamicStatus', 'budgetRedistributeStatus',
    'negativeTargetStatus', 'structPauseCampaignStatus', 'structPauseProductStatus',
    'targetHarvestStatus', 'targetPausedAddStatus',
]

# ==================== 轮转放宽值序表 (PLAN v4 §1.2) ====================
# 放宽总序: T3 → T2 → T1 (先让不重要的)
# 每 Tier 内部序: 按特征重要性排列
#
# 放宽方式:
#   ordered: 有序链, 每轮向相邻值扩展一步
#   nominal: 名义特征, 一轮放弃 (T1 的 category_l1/lifecycle_stage)
#   chain_symmetric: 相位链对称让步 (promo_phase)
#   subset_expand: 子集大小扩展 (peak_seasons_std)
#   distance_expand: 距离扩展 (peak_month, ±月)
#
# 独立桶规则: no_baseline / no_budget = 所属特征的最后一个让步值

VALUE_ORDER = {
    # --- Tier 1 (最后防线) ---
    'price_bucket_mode': {
        'type': 'ordered',
        'order': ['高价', '中高价', '中价', '中低价', '低价'],
    },
    'lifecycle_stage': {
        'type': 'nominal',  # 一步放弃
    },
    'promo_phase': {
        'type': 'ordered',
        'order': ['大促中', '大促前', '大促后', '非大促'],  # 对称链
    },
    'category_l1': {
        'type': 'nominal',  # 一步放弃
    },

    # --- Tier 2 ---
    'peak_seasons_std': {
        'type': 'subset_expand',  # 按季度数扩展: 1Q→2Q→3Q→4Q
    },
    'variation_bin': {
        'type': 'nominal',  # 稀疏无序, 一轮放弃
    },
    'trend_sales_bin': {
        'type': 'ordered',
        'order': ['high', 'mid', 'low', 'no_baseline'],  # no_baseline 最后
    },
    'trend_imp_bin': {
        'type': 'ordered',
        'order': ['high', 'mid', 'low', 'no_baseline'],
    },
    'inventory_status': {
        'type': 'ordered',
        'order': ['库存充足', '库存冗余', '库存适中', '库存紧张', '缺货/无数据'],
    },
    'bsr_bucket': {
        'type': 'ordered',
        'order': ['Best Seller', '热销', '中等', '中下', '未知', '长尾', '极长尾'],
    },
    'campaign_budget_bucket': {
        'type': 'ordered',
        'order': ['high', 'mid', 'low', 'no_budget'],  # no_budget 最后
    },
    'b14_ACOS_bin': {
        'type': 'ordered',
        'order': ['low', 'mid', 'high', 'no_baseline'],
    },
    'b14_CTR_bin': {
        'type': 'ordered',
        'order': ['high', 'mid', 'low', 'no_baseline'],
    },

    # --- Tier 3 ---
    'peak_month': {
        'type': 'distance_expand',  # ±月, 环形距离
    },
    'b14_CVR_bin': {
        'type': 'ordered',
        'order': ['high', 'mid', 'low', 'no_baseline'],
    },
    'b14_CPC_bin': {
        'type': 'ordered',
        'order': ['high', 'mid', 'low', 'no_baseline'],
    },
    'trend_click_bin': {
        'type': 'ordered',
        'order': ['high', 'mid', 'low', 'no_baseline'],
    },
    'marketplace_id': {
        'type': 'nominal',  # 名义, 一轮放弃
    },
}

# ==================== NA 值映射 ====================
# 放宽阶段: NA(数据缺失) 等价于 no_* 桶, 只有 no_* ∈ accepted 时才纳入
# 过滤阶段: NA = "不知道", 无条件纳入 (语义不同, 见 _filter_exact)
NA_EQUIV = {
    'trend_sales_bin':  'no_baseline',
    'trend_imp_bin':    'no_baseline',
    'trend_click_bin':  'no_baseline',
    'b14_ACOS_bin':     'no_baseline',
    'b14_CTR_bin':      'no_baseline',
    'b14_CVR_bin':      'no_baseline',
    'b14_CPC_bin':      'no_baseline',
    'campaign_budget_bucket': 'no_budget',
    # inventory_status: '缺货/无数据' 已在 order 里, isin 自然命中
    # bsr_bucket: '未知'/'长尾'/'极长尾' 已在 order 里
}

# ==================== 分桶说明 ====================
# campaign_budget_bucket: 【输入过滤条件】
#   - 用户主动指定预算档位筛选样本池（如 query({'campaign_budget_bucket': 'low'})）
#   - 分桶逻辑: log1p(campaign_budget_usd) 三分位 + NULL/0 单独一档
#   - 作用: 管"进不进池"——用户说"我的预算是 X，给我看类似场景的历史案例"
#
# b14_ACOS_bin / b14_CTR_bin 等: 【rank 分层】
#   - 系统自动用于 stratum 分层，保证"和谁比排名"的公平性
#   - 作用: 管"和谁比排名"——同档位内比较 Y 分位秩
#
# 两者并行不冲突: budget 是用户输入，b14_* 是系统公平化机制

# [P2] 查值字典：枚举含义注释（从 _v7b_schema_v1.json 提取）
# negativeTargetStatus: 0=关闭, 1=开启, 3=待用户确认（schema 中无 3 的定义，但数据中存在）
# budgetDynamicStatus: 0=关闭, 1=开启, 3=待用户确认（schema 中无 3 的定义，但数据中存在）
# 注意：这些字段的枚举含义需要用户确认，当前标注为"待用户确认"


# ==================== 数据类定义 ====================

@dataclass
class QueryResult:
    """查询结果封装"""
    pool: Dict
    skills: List[Dict]
    fairness: Dict
    status: str  # OK / DEGRADED / INSUFFICIENT
    tt_distribution: Dict = None  # target_type 分布标注 (Tier 0 输出)
    target_type: str = None  # 实际使用的 target_type
    param_coverage: Dict = None  # [v9] 覆盖预检结果
    relax_final_state: str = None  # [v9.1] 放宽终态 (放宽后接受的值集合)
    
    def to_dict(self):
        return {
            'pool': self.pool,
            'skills': self.skills,
            'fairness': self.fairness,
            'status': self.status,
            'tt_distribution': self.tt_distribution,
            'target_type': self.target_type,
            'param_coverage': self.param_coverage,
            'relax_final_state': self.relax_final_state,
        }


@dataclass
class RelaxStep:
    """放宽步骤记录"""
    feature: str
    original_value: any
    relaxed_to: any
    step_num: int


# ==================== 核心引擎类 ====================

class QueryEngine:
    """
    Phase 6 查询引擎
    
    输入: 任意 X 子集（完整/部分/未见组合）
    输出: {pool, skills, fairness, status}
    """
    
    def __init__(self, sample_pool: pd.DataFrame):
        """
        初始化查询引擎
        
        Args:
            sample_pool: 清洗后的样本池 (_phase1_clean_sample_pool.pkl)
                        需包含: X 特征 + config_full (40 列) + Y 原料
                        注意: 必须先调用 bucket_campaign_budget() 创建 budget 桶列
        """
        self.pool_df = sample_pool.copy()
        self.tier1_features = TIER_1_FEATURES
        self.tier2_features = TIER_2_FEATURES
        self.tier3_features = TIER_3_FEATURES
        
        # [P1] 启动时一致性检查: VALUE_ORDER/Tier 特征必须全部在 pool 中
        all_configured = set(VALUE_ORDER.keys()) | set(TIER_1_FEATURES) | set(TIER_2_FEATURES) | set(TIER_3_FEATURES)
        missing = [f for f in all_configured if f not in self.pool_df.columns]
        if missing:
            raise ValueError(
                f"[QueryEngine] 配置与数据不一致! 以下特征在 pool 中缺失: {missing}\n"
                f"请确认 load_engine() 已调用 bucket_campaign_budget() 等预处理函数."
            )
        
        # 预计算高频 Tier1 组合统计（供快速判断）
        self._precompute_tier1_stats()
        
        print(f"[QueryEngine] Initialized with {len(self.pool_df):,} samples")
        print(f"  Tier 1 features: {self.tier1_features}")
        print(f"  Tier 2 features: {self.tier2_features[:5]}... ({len(self.tier2_features)} total)")
    
    def _precompute_tier1_stats(self):
        """预计算高频 Tier1 组合的 n 统计"""
        tier1_cols = [c for c in self.tier1_features if c in self.pool_df.columns]
        if tier1_cols:
            self.tier1_stats = self.pool_df.groupby(tier1_cols).size().reset_index(name='n')
            self.tier1_stats = self.tier1_stats.sort_values('n', ascending=False)
            print(f"  Precomputed {len(self.tier1_stats)} Tier 1 combinations")
        else:
            self.tier1_stats = pd.DataFrame()
            print("  Warning: No Tier 1 features found in pool")
    
    def query(self, features: Dict[str, any], target_type: str = None) -> QueryResult:
        """
        主查询接口 (v3: target_type 作为查询输入)
        
        决策流:
        0. target_type 处理 (Tier 0: 查询前提, 非让步对象)
           - 给定 → 池过滤 targetType == target_type
           - 未给定 → 众数默认 + 分布标注
        1. 精确过滤 → pool_p0
        2. n_p0 < N_FLOOR → L2 质心 / 拒绝
        3. stratum 分层 (level 0: tt × mkt)
        4. 检查最大 stratum ≥ STRATUM_N_MIN(100)?
           - YES → 正常挖掘
           - NO  → ① stratum 降维 (mkt→US/non-US → tt_only)
                   ② X 侧放宽链 (目标: 最大 stratum ≥ 100)
                   ③ 放宽耗尽 → INSUFFICIENT 或边缘输出
        
        Args:
            features: 任意 X 子集字典
            target_type: 可选, 业务目标类型 ('1'=扩大销量, '2'=控制成本, '3'=活动冲量)
                         给定 → 在该 tt 内挖掘; 未给定 → 众数默认
        Returns:
            QueryResult: {pool, skills, fairness, status}
        """
        print(f"\n{'='*80}")
        print(f"Query: {features}")
        if target_type:
            print(f"  target_type={target_type} (用户指定)")
        print(f"{'='*80}")
        
        # Step 0: target_type 处理 (Tier 0: 查询前提, 非让步对象)
        # targetType 不参与轮转放宽, 不在 VALUE_ORDER 中, 不在 active_features 中
        # [v9.1] 精确过滤后不因池空提前返回 — 进入放宽链
        pool_p0, relax_chain = self._filter_exact(features)
        
        if target_type is not None:
            # 用户指定 tt: 记录分布, 过滤
            if len(pool_p0) > 0:
                tt_counts = pool_p0['targetType'].astype(str).value_counts()
                tt_dist = (tt_counts / len(pool_p0)).to_dict()
            else:
                tt_dist = {}
            tt_distribution = tt_dist
            print(f"\n  [Tier 0] target_type={target_type} (用户指定)")
            print(f"  [Tier 0] tt 分布: {tt_dist}")
        else:
            # 未指定 tt: 确定众数 (精确池优先, 空池回退全量池)
            if len(pool_p0) > 0:
                tt_counts = pool_p0['targetType'].astype(str).value_counts()
            else:
                print(f"\n  [Tier 0] 精确过滤后池为空, 从全量池确定 tt 众数")
                tt_counts = self.pool_df['targetType'].astype(str).value_counts()
            tt_dist = (tt_counts / tt_counts.sum()).to_dict()
            mode_tt = tt_counts.index[0]
            mode_pct = tt_dist[mode_tt]
            tt_distribution = tt_dist
            print(f"\n  [Tier 0] target_type 未指定, tt 分布: {tt_dist}")
            print(f"  [Tier 0] 众数默认: tt={mode_tt} ({mode_pct:.0%})")
            print(f"  [Tier 0] 注意: 多数派选择是 imitation 参考, 非推荐. 可切换 target_type 参数重新查询.")
            target_type = mode_tt
        
        # tt 过滤 (精确池 → 放宽链的 tt 约束)
        pool_p0_tt = pool_p0[pool_p0['targetType'].astype(str) == str(target_type)]
        n_p0 = len(pool_p0_tt)
        print(f"\nPool P0 (tt-filtered): {n_p0:,} samples (tt={target_type})")
        
        # [v9.1] 统一处理路径: 所有场景走完整 stratum L0 探测 → 降维链 → 放宽链
        # N_FLOOR 常量保留仅作日志提示, 不再改变控制流
        if n_p0 < N_FLOOR:
            print(f"  [日志] 池小 ({n_p0} < {N_FLOOR}), 预期会触发降级")
        
        # Step 3: stratum 分层 (level 0: tt × mkt, 最精细)
        probe_pool = self._apply_stratum(pool_p0_tt, features, merge_level=0, verbose=False)
        largest_n = self._get_largest_stratum_n(probe_pool)
        total_n = self._get_stratum_total_n(pool_p0_tt, merge_level=0)
        print(f"\n  Stratum health check (level 0: tt×mkt): largest={largest_n}, total={total_n}")
        
        # Step 4: 判断是否需要降级
        stratum_merge_level = 0
        stratum_degraded = False
        stratum_pool = None
        
        if largest_n >= STRATUM_N_MIN:
            # 健康，正常挖掘——重新用 verbose 打印最终分层
            status = "OK"
            print(f"  → Largest stratum {largest_n} >= {STRATUM_N_MIN}, OK")
            stratum_pool = self._apply_stratum(pool_p0_tt, features, merge_level=0, verbose=True)
        else:
            # 不健康，尝试 stratum 降维
            print(f"  → Largest stratum {largest_n} < {STRATUM_N_MIN}, attempting stratum downgrade...")
            
            for merge_level in [1, 2, 3]:
                level_name = STRATUM_MERGE_LEVELS[merge_level]
                probe_pool = self._apply_stratum(pool_p0_tt, features, merge_level=merge_level, verbose=False)
                largest_n = self._get_largest_stratum_n(probe_pool)
                total_n = self._get_stratum_total_n(pool_p0_tt, merge_level=merge_level)
                print(f"    Level {merge_level} ({level_name}): largest={largest_n}, total={total_n}")
                
                if largest_n >= STRATUM_N_MIN:
                    stratum_merge_level = merge_level
                    stratum_degraded = True
                    status = "DEGRADED_STRATUM"
                    print(f"    → Stratum downgraded to level {merge_level} ({level_name})")
                    # 用 verbose 重新打印最终选定的分层
                    stratum_pool = self._apply_stratum(pool_p0_tt, features, merge_level=merge_level, verbose=True)
                    break
            
            if not stratum_degraded:
                # stratum 降维全部失败，进入 X 侧轮转放宽
                print(f"  → Stratum downgrade exhausted, entering X-side round-robin relaxation...")
                # 用 tt_only (level 2) 做 stratum 检查: 这是保留 Y 公式正确性的最粗粒度
                x_merge_level = 2
                pool_p0_tt, relax_chain, relax_status = self._relax_pool_roundrobin(
                    pool_p0_tt, features, relax_chain,
                    stratum_merge_level=x_merge_level,
                    target_type=target_type,
                )
                # 放宽后重新分层 (verbose 打印最终结果)
                stratum_pool = self._apply_stratum(
                    pool_p0_tt, features, merge_level=x_merge_level, verbose=True
                )
                largest_n = self._get_largest_stratum_n(stratum_pool)

                if largest_n >= STRATUM_N_MIN:
                    status = "DEGRADED"
                    stratum_merge_level = x_merge_level
                    print(f"  → X-side relaxation succeeded: largest stratum = {largest_n}")
                elif len(pool_p0_tt) >= ABSOLUTE_MIN:
                    # DEGRADED_HEAVY: 数据有但不达标，最低置信
                    status = "DEGRADED_HEAVY"
                    stratum_merge_level = x_merge_level
                    print(f"  → Pool {len(pool_p0_tt)} >= {ABSOLUTE_MIN}, outputting DEGRADED_HEAVY (lowest confidence)")
                else:
                    status = "INSUFFICIENT"
                    print(f"  → X-side relaxation exhausted: pool {len(pool_p0_tt)} < {ABSOLUTE_MIN}, truly INSUFFICIENT")
        
        # [v9.1] 放宽终态
        relax_final_state = self._get_relax_final_state(relax_chain)
        
        # [v9] 改动 2: 覆盖预检
        param_coverage = self._coverage_check(stratum_pool, relax_chain)
        
        # Step 5-7: 挖掘 + 输出
        return self._build_result(stratum_pool, relax_chain, status, features,
                                   stratum_merge_level=stratum_merge_level,
                                   tt_distribution=tt_distribution, target_type=target_type,
                                   param_coverage=param_coverage,
                                   relax_final_state=relax_final_state)
    
    def _filter_exact(self, features: Dict) -> Tuple[pd.DataFrame, List[RelaxStep]]:
        """
        Step 1: 精确过滤（Tier 1 + Tier 2 给定项）
        
        NA 处理策略 (语义 B, 与放宽体系一致):
          查询特征为实值时, NA 不匹配 (除非显式查 no_* 桶).
          NA 样本通过放宽体系的“独立桶最后让步”规则进入池,
          并在 relax_chain 中标注放宽程度.
          用户查 trend=up 就拿 up 的样本, 不混入无趋势数据.
        
        Returns:
            (filtered_pool, relax_chain)
        """
        mask = pd.Series(True, index=self.pool_df.index)
        relax_chain = []
        
        for feat, val in features.items():
            if feat not in self.pool_df.columns:
                # [P0] 静默跳过查询条件是危险的失败模式, 升级为报错
                raise KeyError(
                    f"[QueryEngine] 查询特征 '{feat}' 不在样本池中! "
                    f"可用列: {sorted(self.pool_df.columns.tolist())[:20]}... "
                    f"请检查特征名拼写或确认预处理已执行."
                )
            
            if pd.isna(val):
                # 用户指定 NA → 只匹配 NA (显式查"无数据"组)
                mask &= self.pool_df[feat].isna()
            else:
                # 语义 B: 精确匹配, NA 不进池
                # NA 样本通过放宽体系的独立桶规则最后进入
                mask &= (self.pool_df[feat] == val)
            
            # 记录是否为 Tier 1/2
            tier = self._get_tier(feat)
            n_match = mask.sum()
            n_na = self.pool_df[feat].isna().sum()
            print(f"  Filter: {feat}={val} (Tier {tier}, match={n_match}, NA_excluded={n_na})")
        
        filtered = self.pool_df[mask].copy()
        return filtered, relax_chain
    
    # ==================== 轮转放宽引擎 (PLAN v4 §1.2) ====================

    def _relax_pool_roundrobin(self, pool: pd.DataFrame, features: Dict,
                                relax_chain: List[RelaxStep],
                                stratum_merge_level: int = 0,
                                target_type: str = None,
                                ) -> Tuple[pd.DataFrame, List[RelaxStep], str]:
        """
        轮转式逐值让步放宽 (PLAN v4 §1.2)

        总序: T3 → T2 → T1 (先让不重要的)
        每轮: 每个活跃特征扩展一个 grade
        检查: 每步检查 max(tt_stratum) >= STRATUM_N_MIN(100)
        累积: 候选池从【当前累积让步后】重建, 修复旧版 bug
        独立桶: no_baseline/no_budget = 最后一个让步值
        """
        # 确定参与放宽的特征 (用户在 query 中指定的)
        # [Tier 0] targetType 永不参与放宽 (查询前提, 非让步对象)
        active_features = {}
        for tier_features in [TIER_3_FEATURES, TIER_2_FEATURES, TIER_1_FEATURES]:
            for feat in tier_features:
                if feat in features and feat in self.pool_df.columns and feat != 'targetType':
                    active_features[feat] = {
                        'original_value': features[feat],
                        'accepted': {features[feat]},
                        'done': False,
                        'round': 0,
                    }

        if not active_features:
            print("    No features to relax")
            return pool, relax_chain, "INSUFFICIENT"

        current_pool = pool.copy()
        step_num = 0
        max_rounds = 6  # 安全阀 (值最多特征 5 档 + no_* = 6 轮足够)

        for round_num in range(1, max_rounds + 1):
            any_expanded = False

            for tier_features in [TIER_3_FEATURES, TIER_2_FEATURES, TIER_1_FEATURES]:
                for feat in tier_features:
                    if feat not in active_features:
                        continue
                    info = active_features[feat]
                    if info['done']:
                        continue

                    # 扩展一步
                    new_accepted, is_done = self._expand_feature_value(
                        feat, info['original_value'], info['accepted'], round_num
                    )

                    if len(new_accepted) == len(info['accepted']) and not is_done:
                        # 没有新值可加
                        info['done'] = True
                        continue

                    info['accepted'] = new_accepted
                    info['round'] = round_num
                    any_expanded = True
                    step_num += 1

                    # 记录放宽步骤
                    relax_chain.append(RelaxStep(
                        feature=feat,
                        original_value=info['original_value'],
                        relaxed_to=f"accepted={new_accepted}",
                        step_num=step_num,
                    ))

                    # 从【当前累积让步】重建池 (修复旧版 bug)
                    candidate_pool = self._rebuild_pool_with_accepted(features, active_features)

                    # [v9.1] 放宽链中按 tt 过滤再检查 stratum
                    # tt 永不放宽 (不在 active_features 中), tt 池增长是放宽的副产品
                    if target_type is not None:
                        tt_pool = candidate_pool[candidate_pool['targetType'].astype(str) == str(target_type)]
                    else:
                        tt_pool = candidate_pool

                    # 检查最大 stratum
                    if len(tt_pool) > 0:
                        probe = self._apply_stratum(
                            tt_pool, features,
                            merge_level=stratum_merge_level, verbose=False
                        )
                        largest_n = self._get_largest_stratum_n(probe)
                    else:
                        largest_n = 0

                    print(f"    Step {step_num} (R{round_num}): {feat} "
                          f"accepted={new_accepted} → largest_stratum={largest_n}")

                    if largest_n >= STRATUM_N_MIN:
                        print(f"    → Target met: {largest_n} >= {STRATUM_N_MIN}")
                        return candidate_pool, relax_chain, "DEGRADED"

                    if is_done:
                        info['done'] = True

            if not any_expanded:
                print(f"    All features exhausted after {round_num - 1} rounds")
                break

        # 全部让完仍不足
        final_pool = self._rebuild_pool_with_accepted(features, active_features)
        # [v9.1] 最终池也按 tt 过滤
        if target_type is not None:
            final_pool = final_pool[final_pool['targetType'].astype(str) == str(target_type)]
        print(f"    All features fully relaxed, pool={len(final_pool)}, still INSUFFICIENT")
        return final_pool, relax_chain, "INSUFFICIENT"

    def _expand_feature_value(self, feat: str, original_val: any,
                               current_accepted: set, round_num: int
                               ) -> Tuple[set, bool]:
        """
        将一个特征的接受值集合扩展一步

        Returns:
            (new_accepted_set, is_done)
            is_done=True 表示该特征已全值覆盖, 移出轮转
        """
        if feat not in VALUE_ORDER:
            # 未知特征: 一轮放弃
            all_vals = set(self.pool_df[feat].dropna().unique())
            return all_vals, True

        spec = VALUE_ORDER[feat]
        ftype = spec['type']

        if ftype == 'nominal':
            # 名义特征: 第 1 轮全接受 (= 放弃该特征)
            all_vals = set(self.pool_df[feat].dropna().unique())
            return all_vals, True

        elif ftype == 'ordered':
            order = spec['order']
            all_vals_set = set(order)

            if original_val not in order:
                # 原值不在序表中, 放弃
                return set(self.pool_df[feat].dropna().unique()), True

            idx = order.index(original_val)
            # 扩展半径 = round_num
            lo = max(0, idx - round_num)
            hi = min(len(order) - 1, idx + round_num)
            new_accepted = set(order[lo:hi + 1])
            is_done = (new_accepted >= all_vals_set)
            return new_accepted, is_done

        elif ftype == 'subset_expand':
            # peak_seasons_std: 按季度数扩展
            all_quarters = {'Q1', 'Q2', 'Q3', 'Q4'}
            orig_parts = set(str(original_val).split(','))
            target_size = len(orig_parts) + round_num

            all_col_vals = self.pool_df[feat].dropna().unique()
            new_accepted = set()
            for v in all_col_vals:
                parts = set(str(v).split(','))
                if len(parts) <= target_size:
                    new_accepted.add(v)

            is_done = (len(new_accepted) >= len(set(all_col_vals)))
            return new_accepted, is_done

        elif ftype == 'distance_expand':
            # peak_month: ±月环形距离
            try:
                orig_month = int(original_val)
            except (ValueError, TypeError):
                return set(self.pool_df[feat].dropna().unique()), True

            all_col_vals = self.pool_df[feat].dropna().unique()
            new_accepted = set()
            for v in all_col_vals:
                try:
                    v_int = int(v)
                except (ValueError, TypeError):
                    continue
                dist = min(abs(v_int - orig_month), 12 - abs(v_int - orig_month))
                if dist <= round_num:
                    new_accepted.add(v)

            is_done = (len(new_accepted) >= len(set(all_col_vals)))
            return new_accepted, is_done

        else:
            return set(self.pool_df[feat].dropna().unique()), True

    def _rebuild_pool_with_accepted(self, query_features: Dict,
                                     active_features: Dict) -> pd.DataFrame:
        """
        从全量 pool_df 重建候选池 (累积式)

        NA 处理策略 (放宽阶段, 与过滤阶段语义不同):
          过滤阶段: NA = "不知道", 无条件纳入.
          放宽阶段: NA = no_* 桶, 只有 no_* ∈ accepted 时才纳入.
          这保证了 PLAN 的"独立桶规则": no_* 是最后一个让步值.

        对每个查询特征:
          - 在 active_features 中 → isin(accepted), NA 仅当 no_* ∈ accepted
          - 不在 active_features 中 → 精确匹配原值, NA 仅当 no_* ∈ accepted
        """
        mask = pd.Series(True, index=self.pool_df.index)

        for feat, val in query_features.items():
            if feat not in self.pool_df.columns:
                continue

            if feat in active_features:
                accepted = active_features[feat]['accepted']
                # NA 纳入条件: no_* 桶已进入 accepted
                na_equiv = NA_EQUIV.get(feat)
                if na_equiv and na_equiv in accepted:
                    mask &= self.pool_df[feat].isin(accepted) | self.pool_df[feat].isna()
                else:
                    mask &= self.pool_df[feat].isin(accepted)
            else:
                # 未放宽特征: 精确匹配, NA 仅当 no_* 在精确值中
                na_equiv = NA_EQUIV.get(feat)
                if pd.isna(val):
                    mask &= self.pool_df[feat].isna()
                elif na_equiv and val == na_equiv:
                    # 用户精确指定 no_* 值 → NA 也匹配
                    mask &= (self.pool_df[feat] == val) | self.pool_df[feat].isna()
                else:
                    # 普通值 → NA 不匹配
                    mask &= (self.pool_df[feat] == val)

        return self.pool_df[mask].copy()
    
    def _fallback_l2(self, pool: pd.DataFrame, features: Dict,
                     relax_chain: List[RelaxStep]) -> Tuple[pd.DataFrame, List[RelaxStep], str]:
        """
        Step 3: L2 质心匹配（最近 300 样本）
        
        TODO: 实现 Gower 距离计算
        当前简化版：返回空池 + INSUFFICIENT 状态
        """
        print("  L2 centroid matching not yet implemented")
        return pool, relax_chain, "INSUFFICIENT"
    
    def _apply_stratum(self, pool: pd.DataFrame, features: Dict, 
                        merge_level: int = 0, verbose: bool = True) -> pd.DataFrame:
        """
        Stratum 分层（公平化）
        
        merge_level:
          0 = tt × mkt（最精细，默认）
          1 = tt × mkt_bin (US / non-US)
          2 = tt only（忽略 marketplace）
          3 = none（整个池作为一个 stratum）
        verbose: 是否打印逐 stratum 详情（探测模式设为 False）
        
        关键修复：b7 是 before window，Y 必须用 a7（after window）派生指标
        """
        if len(pool) == 0:
            return pool
        
        # 新建 a7 系派生指标
        pool = pool.copy()
        
        # [v8.1] a7_ACOS: 守卫从 sales≥$50 放宽至 sales>0 (仅真零排除)
        # v8 守卫理由 "$50 以下 ACOS 方向不稳定" 被用户裁决撤销 (2026-10-09)
        # 放宽后 tt=2 的 y_rank 非空率从 ~35% 预期升至 90%+
        # NaN 仅在 sales=0 (真零) 时产生
        # [v8.1 正交性] a7_ACOS 是 Y 侧效果观测, 守卫宽严不得因 cf_acos 等 config 参数而调整
        if 'sum_a7_cost' in pool.columns and 'sum_a7_sales' in pool.columns:
            pool['a7_ACOS'] = np.where(
                pool['sum_a7_sales'] > 0,
                pool['sum_a7_cost'] / pool['sum_a7_sales'],
                np.nan
            )
        
        # [v8] a7_CTR: 撤销 imp≥20 守卫, 真零归零档
        # 理由: rank 对比率爆炸免疫 (百分位变换压缩极端值), 守卫已无保护对象
        # NaN 仅在分母真零时产生; imp=0 → click 必=0 → CTR=0 是数学事实
        # 注意: b14_CTR_bin (X 侧) 保留 click≥20 守卫 — 三分位桶化对极端值敏感
        if 'sum_a7_click' in pool.columns and 'sum_a7_imp' in pool.columns:
            imp = pool['sum_a7_imp'].fillna(0)
            click = pool['sum_a7_click'].fillna(0)
            pool['a7_CTR'] = np.where(imp > 0, click / imp, 0.0)
        
        # [v8] a7_CVR: 撤销 click≥20 守卫, 真零归零档
        # 理由同上; click=0 → conv 必=0 → CVR=0 是数学事实
        if 'sum_a7_conv' in pool.columns and 'sum_a7_click' in pool.columns:
            click = pool['sum_a7_click'].fillna(0)
            conv = pool['sum_a7_conv'].fillna(0)
            pool['a7_CVR'] = np.where(click > 0, conv / click, 0.0)
        
        level_name = STRATUM_MERGE_LEVELS.get(merge_level, 'unknown')
        if verbose:
            print(f"  Created a7 metrics. Stratum merge_level={merge_level} ({level_name})")
        
        # 根据 merge_level 计算 stratum 分组键
        if merge_level == 0:
            # tt × mkt（最精细）
            pool['_stratum_key'] = pool['marketplace_id'].astype(str)
            groupby_keys = ['targetType', '_stratum_key']
            key_label = 'mkt'
        elif merge_level == 1:
            # tt × mkt_bin (US / non-US)
            US_MKT = 'ATVPDKIKX0DER'
            pool['_stratum_key'] = pool['marketplace_id'].apply(
                lambda x: 'US' if x == US_MKT else 'non-US'
            )
            groupby_keys = ['targetType', '_stratum_key']
            key_label = 'mkt_bin'
        elif merge_level == 2:
            # tt only
            pool['_stratum_key'] = 'all'
            groupby_keys = ['targetType']
            key_label = 'tt_only'
        else:
            # merge_level >= 3: 等价于 tt_only (保留 targetType 分组)
            # 原因: 不分组会导致 _compute_y_rank_for_stratum 用 iloc[0] 的 tt 公式
            #        污染整个池的 Y 排名。保留 tt 分组确保 Y 公式正确性。
            pool['_stratum_key'] = 'all'
            groupby_keys = ['targetType']
            key_label = 'tt_only(=none)'
        
        # 分层 + 计算 Y 分位秩
        stratified_pools = []
        
        if not groupby_keys:
            # 理论上不会走到这里 (level 3 已改为按 tt 分组)
            grp = pool.copy()
            grp = self._compute_y_rank_for_stratum(grp)
            if len(grp) >= 30:
                if verbose:
                    print(f"    Stratum (all): n={len(grp)}")
                stratified_pools.append(grp)
        else:
            for group_vals, grp_raw in pool.groupby(groupby_keys):
                # 构造打印标签
                if merge_level == 0:
                    tt, mkt = group_vals
                    label = f"tt={tt}, {key_label}={mkt}"
                elif merge_level == 1:
                    tt, mkt_bin = group_vals
                    label = f"tt={tt}, {key_label}={mkt_bin}"
                elif merge_level == 2:
                    tt = group_vals
                    label = f"tt={tt}"
                else:
                    label = "all"
                
                if len(grp_raw) < 30:
                    if verbose:
                        print(f"    Stratum ({label}): n={len(grp_raw)} < 30, skipped")
                    continue
                
                grp = grp_raw.copy()
                grp = self._compute_y_rank_for_stratum(grp)
                if verbose:
                    y_name = grp['_y_name'].iloc[0] if '_y_name' in grp.columns and len(grp) > 0 else 'NA'
                    print(f"    Stratum ({label}): n={len(grp)}, Y={y_name}")
                stratified_pools.append(grp)
        
        if stratified_pools:
            ranked_pool = pd.concat(stratified_pools, ignore_index=True)
            if verbose:
                print(f"  Total stratified samples: {len(ranked_pool):,}")
        else:
            ranked_pool = pool.copy()
            ranked_pool['y_rank'] = np.nan
            if verbose:
                print(f"  Warning: No valid strata, returning unranked pool")
        
        return ranked_pool
    
    def _compute_y_rank_for_stratum(self, grp: pd.DataFrame) -> pd.DataFrame:
        """
        为单个 stratum 计算 Y 分位秩
        
        根据 targetType 选择 Y 公式和方向（PLAN v4 Phase 3）
        
        A1 最终定案 (2026-10-06 用户裁决):
          rank 在全 stratum 口径上计算, 不分规模桶, 不过滤.
          对照实验: 规模桶三分位导致 lift 衰减 80-90%, 显著 9→0,
          用户裁定规模偏差可接受, 回退到全 stratum rank.
        """
        return self._rank_within_group(grp.copy())
    
    def _add_scale_bucket(self, grp: pd.DataFrame) -> pd.DataFrame:
        """PLAN v4 §3: log1p(sum_b14_cost) 三分位 → scale_bucket"""
        if 'sum_b14_cost' not in grp.columns:
            grp['_scale_bucket'] = 'all'
            return grp
        
        cost = grp['sum_b14_cost'].fillna(0)
        log_cost = np.log1p(cost)
        
        # 分布检查: P50 接近 0 → 第一档为"近乎停投"(<$10)
        p50 = log_cost.median()
        
        try:
            buckets = pd.qcut(log_cost, q=3, labels=['small', 'mid', 'large'], duplicates='drop')
            grp['_scale_bucket'] = buckets
        except ValueError:
            # 值太集中无法分 3 桶
            grp['_scale_bucket'] = 'all'
        
        return grp
    
    def _rank_within_group(self, grp: pd.DataFrame) -> pd.DataFrame:
        """原始 Y rank 计算逻辑 (PLAN v4 Phase 3 公式)"""
        tt_str = str(grp['targetType'].iloc[0]) if 'targetType' in grp.columns else 'unknown'
        
        if tt_str == '1':
            # tt=1: 扩大销量 → w1·rank(sales) + w2·mean(rank(imp), rank(cvr), rank(ctr))
            has_sales = 'sum_a7_sales' in grp.columns
            has_imp = 'sum_a7_imp' in grp.columns
            has_cvr = 'a7_CVR' in grp.columns
            has_ctr = 'a7_CTR' in grp.columns
            
            if has_sales and (has_imp or has_cvr or has_ctr):
                rank_sales = grp['sum_a7_sales'].rank(pct=True, ascending=False)
                combo_ranks = []
                if has_imp:
                    combo_ranks.append(grp['sum_a7_imp'].rank(pct=True, ascending=False))
                if has_cvr:
                    combo_ranks.append(grp['a7_CVR'].rank(pct=True, ascending=False))
                if has_ctr:
                    combo_ranks.append(grp['a7_CTR'].rank(pct=True, ascending=False))
                # [v8] combo 三分量均已零档化, 无 NaN, 无需 fillna
                # 零档方案取代 fillna(0.5) 过渡方案: 真零=0 → rank 有定义 → 均值守恒 0.5
                combo_mean = pd.concat(combo_ranks, axis=1).mean(axis=1) if combo_ranks else 0
                grp['y_rank'] = 0.7 * rank_sales + 0.3 * combo_mean
                grp['_y_name'] = 'a7:sales+imp/cvr/ctr'
            elif has_sales:
                grp['y_rank'] = grp['sum_a7_sales'].rank(pct=True, ascending=False)
                grp['_y_name'] = 'a7:sales'
            else:
                grp['y_rank'] = np.nan
                grp['_y_name'] = 'NA'
                
        elif tt_str == '2':
            # tt=2: 控制成本 → w1·rank(−a7_ACOS) + w2·rank(sales)
            has_acos = 'a7_ACOS' in grp.columns
            has_sales = 'sum_a7_sales' in grp.columns
            
            if has_acos and has_sales:
                # [v8] ACOS 保留 NaN (sales<$50 出局), 不 fillna
                # NaN y_rank 样本在 lift 计算时被 pool_valid 排除 (口径对齐)
                rank_neg_acos = grp['a7_ACOS'].rank(pct=True, ascending=True)
                rank_sales = grp['sum_a7_sales'].rank(pct=True, ascending=False)
                grp['y_rank'] = 0.7 * rank_neg_acos + 0.3 * rank_sales
                grp['_y_name'] = 'a7:-ACOS+sales'
            elif has_acos:
                grp['y_rank'] = grp['a7_ACOS'].rank(pct=True, ascending=True)
                grp['_y_name'] = 'a7:-ACOS'
            else:
                grp['y_rank'] = np.nan
                grp['_y_name'] = 'NA'
                
        elif tt_str == '3':
            # tt=3: 活动冲量 → w1·rank(sales) + w2·mean(rank(imp), rank(cvr))
            has_sales = 'sum_a7_sales' in grp.columns
            has_imp = 'sum_a7_imp' in grp.columns
            has_cvr = 'a7_CVR' in grp.columns
            
            if has_sales and (has_imp or has_cvr):
                rank_sales = grp['sum_a7_sales'].rank(pct=True, ascending=False)
                combo_ranks = []
                if has_imp:
                    combo_ranks.append(grp['sum_a7_imp'].rank(pct=True, ascending=False))
                if has_cvr:
                    combo_ranks.append(grp['a7_CVR'].rank(pct=True, ascending=False))
                # [v8] 同 tt=1: 零档化后无 NaN, 无需 fillna
                combo_mean = pd.concat(combo_ranks, axis=1).mean(axis=1) if combo_ranks else 0
                grp['y_rank'] = 0.7 * rank_sales + 0.3 * combo_mean
                grp['_y_name'] = 'a7:sales+imp/cvr'
            elif has_sales:
                grp['y_rank'] = grp['sum_a7_sales'].rank(pct=True, ascending=False)
                grp['_y_name'] = 'a7:sales'
            else:
                grp['y_rank'] = np.nan
                grp['_y_name'] = 'NA'
        else:
            grp['y_rank'] = np.nan
            grp['_y_name'] = 'unknown'
        
        return grp
    
    def _compute_rank(self, pool: pd.DataFrame) -> pd.DataFrame:
        """
        Step 5: Y 分位秩计算已移至 _apply_stratum（按 stratum 分组后各自算秩）
        
        此函数保留为占位符，实际逻辑在 stratum 中完成
        """
        # y_rank 已在 _apply_stratum 中按 (targetType, marketplace) 分组计算
        if 'y_rank' not in pool.columns:
            print("  Warning: y_rank not computed in stratum")
        
        return pool
    
    def _noise_qualification_test(self, pool: pd.DataFrame, 
                                   features: Dict) -> List[Dict]:
        """
        Step 6: 噪声资格检验 (v8.1: per-param pool + 四态标注)
        
        [v8.1] 核心变更:
          - per-param top: 每个参数独立切 top 30% (基于该参数非NA样本)
          - 四态标注: 显著/边缘/弱证据/证据不足
          - 全局 y_rank 只算一次, per-param 只做触及过滤
        
        正交性断言 [2b]:
          a7_ACOS (Y 侧) 守卫宽严不得因 cf_acos (X 侧) 等 config 参数而调整
        """
        if len(pool) == 0 or 'y_rank' not in pool.columns:
            return []
        
        # 口径对齐: lift 分子分母只用 y_rank 非 NaN 的样本
        valid_mask = pool['y_rank'].notna()
        pool_valid = pool[valid_mask]
        n_nan = (~valid_mask).sum()
        if n_nan > 0:
            print(f"  [lift口径] 排除 {n_nan} 个 y_rank=NaN 样本 (stratum skip)")
        
        if len(pool_valid) == 0:
            return []
        
        # [P1] 口径断言: lift 分母不得含 NaN y_rank (防回归)
        assert pool_valid['y_rank'].isna().sum() == 0, \
            "lift 分母混入 NaN y_rank — 口径回归! 检查 _apply_stratum 和 pool_valid 构造."
        
        # [v8.1 正交性断言] a7_ACOS (Y) vs cf_acos (X) 独立性
        # a7 守卫的宽严不得因任何 config 参数的触及率而调整
        # 评价标准 (y_rank) 独立于被评价对象 (config params)
        # (与 targetType 退出推荐参数同理)
        
        print(f"  Noise test: pool_valid n={len(pool_valid)} (per-param top 30%)")
        
        # [v9] 推荐池收窄 13 参数 (= 白名单, 用户裁决)
        # acos → acos_bin (v9 分箱, A4 细节)
        CONFIG_FULL_COLS = [
            'acos_bin',  # v9: 分箱替代原始值 [low/mid_low/mid_high/high]
            'aiPersonality', 'bidAdPlaceStatus', 'bidDaypartStatus',
            'budgetDaypartStatus', 'budgetDynamicStatus',
            'targetHarvestStatus', 'bidPerformanceStatus', 'negativeTargetStatus',
            'targetPausedAddStatus', 'budgetRedistributeStatus',
            'structPauseProductStatus', 'structPauseCampaignStatus',
        ]
        
        config_cols = [c for c in CONFIG_FULL_COLS if c in pool.columns]
        if not config_cols:
            config_cols = pool.select_dtypes(include=['object', 'category']).columns.tolist()[:10]
        
        skills = []
        
        for param in config_cols:
            if param not in pool_valid.columns:
                continue
            
            # [v8.1] per-param pool: 该参数非 NA 的样本子集
            param_mask = pool_valid[param].notna()
            param_pool = pool_valid[param_mask]
            n_param = len(param_pool)
            
            if n_param < 10:
                # 触及样本太少, 全部标"证据不足"
                all_dist = param_pool[param].value_counts(normalize=True)
                for val in all_dist.index:
                    n_touched = int(all_dist[val] * n_param)
                    skills.append({
                        'param': param, 'recommended_value': val,
                        'lift': 0.0, 'baseline_80': 0.0, 'baseline_95': 0.0,
                        'significance': '证据不足', 'n': n_touched,
                        'pool_n': n_param,
                        '分位优势': 0.0
                    })
                continue
            
            # per-param top 30% (基于该参数非NA样本的 y_rank)
            top_threshold_p = param_pool['y_rank'].quantile(0.7)
            top_pool_p = param_pool[param_pool['y_rank'] >= top_threshold_p]
            n_top_p = len(top_pool_p)
            
            # 全体分布 (param_pool 内)
            all_dist = param_pool[param].value_counts(normalize=True)
            # top 分布
            top_dist = top_pool_p[param].value_counts(normalize=True)
            
            for val in top_dist.index:
                if val not in all_dist.index:
                    continue
                
                lift = top_dist[val] - all_dist[val]
                if lift <= 0:
                    continue
                
                n_touched = int(top_dist[val] * n_top_p)
                
                # [v8.1] 四态标注
                if n_touched < 10:
                    significance = '证据不足'
                    baseline_80 = 0.0
                    baseline_95 = 0.0
                elif n_touched < 30:
                    # [v8.1] 弱证据档: 展示 lift, 强制低置信, 标注触及数
                    significance = '弱证据'
                    baseline_80 = 0.0
                    baseline_95 = 0.0
                else:
                    # 噪声检验: 打乱 Y 100 次 (从 param_pool 中抽样)
                    baseline_lifts = []
                    for _ in range(SHUFFLE_TIMES):
                        shuffled_top_idx = np.random.choice(
                            param_pool.index, size=n_top_p, replace=False)
                        shuffled_top = param_pool.loc[shuffled_top_idx]
                        shuffled_top_dist = shuffled_top[param].value_counts(normalize=True)
                        if val in shuffled_top_dist.index:
                            shuffled_lift = shuffled_top_dist[val] - all_dist[val]
                            baseline_lifts.append(shuffled_lift)
                        else:
                            baseline_lifts.append(0.0)
                    
                    baseline_80 = np.percentile(baseline_lifts, 80) if baseline_lifts else 0.0
                    baseline_95 = np.percentile(baseline_lifts, 95) if baseline_lifts else 0.0
                    
                    if lift > baseline_95:
                        significance = '显著'
                    elif lift > baseline_80:
                        significance = '边缘'
                    else:
                        significance = '不显著'
                
                skills.append({
                    'param': param,
                    'recommended_value': val,
                    'lift': round(lift, 4),
                    'baseline_80': round(baseline_80, 4),
                    'baseline_95': round(baseline_95, 4),
                    'significance': significance,
                    'n': n_touched,
                    'pool_n': n_param,
                    '分位优势': round(top_pool_p[top_pool_p[param] == val]['y_rank'].mean(), 4) if len(top_pool_p[top_pool_p[param] == val]) > 0 else 0.0
                })
        
        # 按 lift 降序排序
        skills.sort(key=lambda x: x['lift'], reverse=True)
        
        # 统计四态分布
        sig_counts = {}
        for s in skills:
            sig = s['significance']
            sig_counts[sig] = sig_counts.get(sig, 0) + 1
        
        print(f"  Noise test: {len(skills)} total skills")
        print(f"    显著: {sig_counts.get('显著', 0)}, 边缘: {sig_counts.get('边缘', 0)}, "
              f"弱证据: {sig_counts.get('弱证据', 0)}, 不显著: {sig_counts.get('不显著', 0)}, "
              f"证据不足: {sig_counts.get('证据不足', 0)}")
        
        return skills
    
    def _compute_confidence(self, skills: List[Dict], pool_n: int, 
                            relax_chain: List[RelaxStep]) -> List[float]:
        """
        Step 7: 计算置信度 (v8.1: per-param pool_n + 弱证据强制低置信)
        
        因子: n（对数缩放, per-param）+ 分离度 + 匹配质量 + 弱证据惩罚
        """
        confidences = []
        for skill in skills:
            # [v8.1] per-param pool_n (该参数非NA的样本数)
            param_n = skill.get('pool_n', pool_n)
            n_score = min(np.log10(max(param_n, 10)) / np.log10(N_MIN * 10), 1.0)
            
            # 放宽惩罚（每步 -10%）
            relax_penalty = max(1.0 - (len(relax_chain) * 0.1), 0.5)
            
            # lift 强度加分（lift 越高越可信）
            lift_bonus = min(skill.get('lift', 0) * 0.2, 0.2)
            
            # [v8.1] 弱证据强制低置信: 上限 0.4
            weak_penalty = 1.0
            if skill.get('significance') == '弱证据':
                weak_penalty = 0.5  # 强制压低
            
            # 综合置信度
            conf = (n_score * 0.5 + lift_bonus * 0.3 + relax_penalty * 0.2) * weak_penalty
            confidences.append(round(conf, 3))
        
        return confidences
    
    def _get_tier(self, feature: str) -> int:
        """获取特征的 Tier 级别"""
        if feature in self.tier1_features:
            return 1
        elif feature in self.tier2_features:
            return 2
        elif feature in self.tier3_features:
            return 3
        else:
            return 0
    
    def _get_tier1_composition(self, pool: pd.DataFrame) -> Dict:
        """获取池内 Tier1 组成分布"""
        tier1_cols = [c for c in self.tier1_features if c in pool.columns]
        if tier1_cols:
            composition = pool.groupby(tier1_cols).size().to_dict()
            return {str(k): int(v) for k, v in composition.items()}
        return {}
    
    def _get_stratum_composition(self, pool: pd.DataFrame) -> Dict:
        """获取 stratum 组成"""
        comp = {}
        if 'targetType' in pool.columns:
            comp['targetType'] = pool['targetType'].value_counts().to_dict()
        if 'marketplace_id' in pool.columns:
            comp['marketplace_id'] = pool['marketplace_id'].value_counts().to_dict()
        return comp
    
    def _get_largest_stratum_n(self, stratum_pool: pd.DataFrame) -> int:
        """
        检查 stratum 健康度：返回最大有效 stratum 的样本量
        
        有效 stratum = 包含 y_rank 且 n >= 30 的分组
        """
        if stratum_pool is None or len(stratum_pool) == 0:
            return 0
        if 'y_rank' not in stratum_pool.columns:
            return 0
        
        # 按 stratum key 分组计数
        # stratum key 取决于 merge_level，但这里只关心最大组的 n
        # 用 y_rank 非空来判断该样本属于有效 stratum
        valid = stratum_pool[stratum_pool['y_rank'].notna()]
        if len(valid) == 0:
            return 0
        
        # 按 (targetType, _stratum_key) 分组
        if '_stratum_key' in valid.columns:
            grp_sizes = valid.groupby(['targetType', '_stratum_key']).size()
        else:
            grp_sizes = valid.groupby('targetType').size()
        
        return int(grp_sizes.max()) if len(grp_sizes) > 0 else 0
    
    def _get_stratum_total_n(self, raw_pool: pd.DataFrame, merge_level: int) -> int:
        """
        [v8.1] 计算某 merge level 下所有 stratum 的总样本量 (含 n<30 的组)
        
        用于降维决策: 判断该 level 是否有足够数据支撑挖掘.
        与 _get_largest_stratum_n 的区别: 后者只计有效 stratum (n>=30),
        前者计全量 (含被 skip 的小组), 避免顺序倒挂.
        """
        if raw_pool is None or len(raw_pool) == 0:
            return 0
        if 'targetType' not in raw_pool.columns:
            return len(raw_pool)
        
        # 根据 merge_level 构造分组键
        if merge_level == 0:
            if 'marketplace_id' not in raw_pool.columns:
                return len(raw_pool)
            grp_sizes = raw_pool.groupby(['targetType', 'marketplace_id']).size()
        elif merge_level == 1:
            if 'marketplace_id' not in raw_pool.columns:
                return len(raw_pool)
            US_MKT = 'ATVPDKIKX0DER'
            mkt_bin = raw_pool['marketplace_id'].apply(
                lambda x: 'US' if x == US_MKT else 'non-US')
            grp_sizes = raw_pool.groupby(['targetType', mkt_bin]).size()
        else:  # level 2, 3: tt_only
            grp_sizes = raw_pool.groupby('targetType').size()
        
        return int(grp_sizes.sum())
    
    def _coverage_check(self, pool: pd.DataFrame, relax_chain: List[RelaxStep],
                        max_relax_steps: int = MAX_RELAX_STEPS) -> Dict:
        """
        [v9] 改动 2: 可用率感知放宽 — 参数覆盖预检
        
        机制 (brief 规定):
          阶段A: largest_stratum >= 100 → 进入阶段B
          阶段B: 仅检查白名单中带参数 (10%<=可用率<=50%)
                 高带(>50%): stratum 达标即自然达标, 不查
                 低带(<10%): 预检无效, 不查
          B1: 白名单中带参数全部 n_param >= 100 → 停
          B2: 某白名单中带参数 n_param < 100 → 估边际收益
        
        三红线:
          ① 单链原则: 只维护一条 relax_chain
          ② 相似度预算: B2 的多让计入 MAX_RELAX_STEPS
          ③ 不逆向: stratum 未达标时不因覆盖提前停
        
        当前数据: 13 白名单参数全部 100% 可用率 (高带) → 阶段B 无作用对象
        """
        result = {
            'whitelist_checked': [],
            'coverage_limited': [],
            'extra_relax_for_coverage': False,
        }
        
        if len(pool) == 0:
            return result
        
        # 阶段A: largest_stratum >= 100?
        largest_n = self._get_largest_stratum_n(pool)
        if largest_n < 100:
            # stratum 未达标, 不进入覆盖预检 (红线③: stratum 健康优先)
            return result
        
        # 阶段B: 检查白名单中带参数
        # 当前数据: 全部 13 参数 100% 可用率 → 全在高带 → 中带 0 个 → 直接返回
        # 框架代码保留, 待未来数据变化时激活
        
        for param in WHITELIST_PARAMS:
            if param not in pool.columns:
                continue
            n_param = pool[param].notna().sum()
            availability = n_param / len(pool)
            
            # 高带 (>50%): 不查
            if availability > 0.5:
                continue
            # 低带 (<10%): 预检无效, 标 coverage_limited
            if availability < 0.1:
                result['coverage_limited'].append(param)
                continue
            
            # 中带 (10-50%): 检查 n_param
            result['whitelist_checked'].append({
                'param': param,
                'n_param': int(n_param),
                'availability': round(availability, 3),
            })
            
            if n_param < 100:
                # B2: 估边际收益 (用当前池实测可用率)
                # 当前数据不触发, 框架保留
                result['coverage_limited'].append(param)
        
        return result
    
    def _get_relax_final_state(self, relax_chain: List[RelaxStep]) -> str:
        """
        [v9.1] 提取放宽终态: 每个被放宽特征的最终接受值集合
        
        Returns:
            人类可读字符串, 如 "price_bucket_mode: 低价→{中低价,低价}"
            无放宽时返回空字符串
        """
        if not relax_chain:
            return ''
        
        final_accepted = {}
        for step in relax_chain:
            feat = step.feature
            accepted_str = step.relaxed_to  # "accepted={set}"
            final_accepted[feat] = accepted_str
        
        parts = []
        for feat, accepted_str in final_accepted.items():
            # accepted_str 格式: "accepted={'val1', 'val2'}"
            parts.append(f"{feat}: {accepted_str}")
        
        return '; '.join(parts)
    
    def _build_result(self, stratum_pool: pd.DataFrame, relax_chain: List[RelaxStep],
                      status: str, features: Dict, stratum_merge_level: int = 0,
                      tt_distribution: Dict = None, target_type: str = None,
                      param_coverage: Dict = None,
                      relax_final_state: str = None) -> QueryResult:
        """
        构建最终输出（Step 5-7 抽取）
        """
        # Step 5: 噪声资格检验
        qualified_skills = self._noise_qualification_test(stratum_pool, features)
        
        # Step 6: 置信度
        confidence_scores = self._compute_confidence(qualified_skills, len(stratum_pool), relax_chain)
        
        # Step 7: 构建输出
        match_level = 'exact'
        if stratum_merge_level > 0:
            match_level = f'stratum_merged_level_{stratum_merge_level}'
        elif relax_chain:
            match_level = f'relaxed_{len(relax_chain)}_steps'
        
        result = QueryResult(
            pool={
                'n': len(stratum_pool),
                'tier1_composition': self._get_tier1_composition(stratum_pool),
                'relax_chain': [vars(r) for r in relax_chain],
                'match_level': match_level,
                'stratum_merge_level': stratum_merge_level,
                'largest_stratum_n': self._get_largest_stratum_n(stratum_pool),
            },
            skills=[
                {**skill, 'confidence': conf} 
                for skill, conf in zip(qualified_skills, confidence_scores)
            ],
            fairness={
                'stratum_composition': self._get_stratum_composition(stratum_pool),
                'marketplace_distribution': stratum_pool['marketplace_id'].value_counts().to_dict() if 'marketplace_id' in stratum_pool.columns else {},
                'targetType_distribution': stratum_pool['targetType'].value_counts().to_dict() if 'targetType' in stratum_pool.columns else {}
            },
            status=status,
            tt_distribution=tt_distribution,
            target_type=target_type,
            param_coverage=param_coverage,
            relax_final_state=relax_final_state,
        )
        
        print(f"\nFinal Status: {result.status}")
        print(f"Skills found: {len(result.skills)}")
        print(f"{'='*80}\n")
        
        return result


# ==================== 分桶工具函数 ====================

def bucket_acos_bin(df: pd.DataFrame) -> pd.DataFrame:
    """
    [v9] cf_acos 分箱 (A4 五细节)
    
    分箱规则:
    ① 新增 acos_bin 列, 原始 acos 保留 (v8.1 兼容)
    ② NA → bin=NA
    ③ 左开右闭: 15 落入 [15,25), 25 落入 [25,35), 35 落入 [35,+∞)
    ④ acos>100 归 35+ 档
    ⑤ skill 粒度: 整档为一条 value
    
    边界: low[0,15) / mid_low[15,25) / mid_high[25,35) / high[35,+∞)
    """
    df = df.copy()
    
    def assign_bin(val):
        try:
            v = float(val)
        except (ValueError, TypeError):
            return np.nan
        if pd.isna(v):
            return np.nan
        if v < 15:
            return 'low'
        if v < 25:
            return 'mid_low'
        if v < 35:
            return 'mid_high'
        return 'high'
    
    df['acos_bin'] = df['acos'].apply(assign_bin)
    
    # 打印分布
    dist = df['acos_bin'].value_counts(dropna=False)
    print(f"[acos_bin] Distribution:")
    for bucket, count in dist.items():
        pct = count / len(df) * 100
        print(f"  {bucket}: {count:,} ({pct:.1f}%)")
    
    return df

def bucket_campaign_budget(df: pd.DataFrame) -> pd.DataFrame:
    """
    将 campaign_budget_usd 分桶为 campaign_budget_bucket
    
    分桶逻辑:
    - NULL/0 → 'no_budget' (未设预算)
    - 非空正值 → log1p 三分位: 'low', 'mid', 'high'
    
    Args:
        df: 包含 campaign_budget_usd 列的 DataFrame
    
    Returns:
        添加了 campaign_budget_bucket 列的 DataFrame
    """
    df = df.copy()
    col = 'campaign_budget_usd'
    bucket_col = 'campaign_budget_bucket'
    
    if col not in df.columns:
        print(f"Warning: {col} not found, skipping bucketing")
        return df
    
    # NULL/0 → 'no_budget'
    null_zero = df[col].isna() | (df[col] == 0)
    df[bucket_col] = 'no_budget'
    
    # 非空正值 → log1p 三分位
    pos_mask = ~null_zero
    if pos_mask.sum() > 0:
        log_vals = np.log1p(df.loc[pos_mask, col])
        # 三分位边界
        terciles = log_vals.quantile([1/3, 2/3])
        
        def assign_bucket(log_val):
            if log_val <= terciles.iloc[0]:
                return 'low'
            elif log_val <= terciles.iloc[1]:
                return 'mid'
            else:
                return 'high'
        
        df.loc[pos_mask, bucket_col] = log_vals.apply(assign_bucket)
    
    # 打印分布
    dist = df[bucket_col].value_counts()
    print(f"[bucket_campaign_budget] Distribution:")
    for bucket, count in dist.items():
        print(f"  {bucket}: {count:,} ({count/len(df)*100:.1f}%)")
    
    return df


# ==================== 主入口 ====================

def load_engine(sample_pool_path: str = '_phase1_clean_sample_pool.pkl') -> QueryEngine:
    """加载查询引擎"""
    print(f"Loading sample pool from {sample_pool_path}...")
    df = pd.read_pickle(sample_pool_path)
    print(f"Loaded {len(df):,} rows × {len(df.columns)} cols")
    
    # 添加 campaign_budget_bucket 分桶
    df = bucket_campaign_budget(df)
    
    # [v9] 添加 acos_bin 分箱
    df = bucket_acos_bin(df)
    
    engine = QueryEngine(df)
    return engine


if __name__ == '__main__':
    # 测试用例
    engine = load_engine()
    
    # 示例查询：Home×低价（注意：实际值为中文"低价"）
    result = engine.query({
        'category_l1': 'Home',
        'price_bucket_mode': '低价'  # 实际 DB 中的值
    })
    
    print("\nResult summary:")
    print(f"  Status: {result.status}")
    print(f"  Pool size: {result.pool['n']}")
    print(f"  Skills: {len(result.skills)}")
    if result.skills:
        print(f"  Top skill lift: {result.skills[0]['lift']:.3f}")
    print(f"  Fairness targetType dist: {result.fairness['targetType_distribution']}")
