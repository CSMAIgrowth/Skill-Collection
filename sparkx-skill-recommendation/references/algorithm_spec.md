# Algorithm Spec (Condensed) — v9.1 Engine

> Full spec: `Pipeline_算法规格书_v9.1.md` (719 lines)
> Source code: `scripts/query_engine.py` (1453 lines)
> Scope: **SP (Sponsored Products) only**

## Architecture: Case-Based Reasoning

The engine finds historically similar SP product configurations and extracts their optimal settings as recommendations. Training data (pool_min.pkl.gz) contains only SP managed group samples.

## Query Pipeline

```
query(features, target_type)
│
├─ Step 0: Target Type
│  Filter pool by targetType. If not provided, use mode of pool.
│  targetType is NEVER relaxed.
│
├─ Step 1: Exact Filter
│  Match pool rows where ALL features equal query values.
│  NA values in pool are excluded (not matched).
│
├─ Step 2: (removed in v9.1 — unified path)
│
├─ Step 3: Stratum Health Probe
│  Group by (targetType, marketplace_id) → compute y_rank per stratum.
│  Stratum with n < 30 → skip.
│  Check if largest_stratum_n ≥ 100.
│
├─ Step 4: Degradation Decision
│  Level 0 (tt × mkt): largest_n ≥ 100? → status="OK"
│  Level 1 (tt × mkt_bin): US/non-US merge → status="DEGRADED_STRATUM"
│  Level 2 (tt_only): ignore marketplace → status="DEGRADED_STRATUM"
│  Level 3 (none): same as L2 but prevents Y formula pollution
│
│  If all levels fail → Round-robin Feature Relaxation:
│    Order: T3 → T2 → T1 (relax least important first)
│    Types: ordered (expand adjacent), nominal (drop in 1 round),
│           subset_expand, distance_expand
│    Stop when largest_n ≥ 100 → status="DEGRADED"
│    Or pool ≥ 30 → status="DEGRADED_HEAVY"
│    Or pool < 30 → status="INSUFFICIENT"
│
├─ Step 5: Final Stratum + Rank
│  Recompute y_rank with final merge_level.
│
│  Y formula by targetType:
│    tt=1 (sales growth): Y = 0.7·rank(sales) + 0.3·mean(rank(imp),rank(cvr),rank(ctr))
│    tt=2 (cost control): Y = 0.7·rank(-ACOS) + 0.3·rank(sales)
│    tt=3 (activity):     Y = 0.7·rank(sales) + 0.3·mean(rank(imp),rank(cvr))
│
├─ Step 6: Noise Qualification Test
│  For each of 13 whitelist params independently:
│    Split pool into top 30% (by y_rank) vs all.
│    lift = top_dist[val] - all_dist[val] (only positive lifts kept)
│
│    Significance by n_touched (samples with this value in top):
│      < 10: "证据不足" (insufficient evidence)
│      10-29: "弱证据" (weak evidence)
│      ≥ 30: Noise test — shuffle Y 100 times
│        lift > P95 baseline → "显著" (significant)
│        lift > P80 baseline → "边缘" (marginal)
│        else → "不显著" (not significant)
│
├─ Step 7: Confidence Scoring
│  conf = (n_score×0.5 + lift_bonus×0.3 + relax_penalty×0.2) × weak_penalty
│    n_score = min(log10(max(param_n,10)) / 3.301, 1.0)
│    lift_bonus = min(lift × 0.2, 0.2)
│    relax_penalty = max(1.0 - len(relax_chain)×0.1, 0.5)
│    weak_penalty = 0.5 if "弱证据" else 1.0
│  Range: [0, ~0.76]. All skills output regardless of threshold.
│
└─ Step 8: Output
   QueryResult {
     pool: {n, match_level, stratum_merge_level, relax_chain, largest_stratum_n},
     skills: [{param, recommended_value, lift, baseline_80/95,
               significance, n, pool_n, confidence}],
     fairness: {stratum_composition, marketplace_distribution}
   }
```

## Status Hierarchy

| Status | Meaning | Action |
|--------|---------|--------|
| `OK` | Exact match, large pool | Trust recommendations fully |
| `DEGRADED_STRATUM` | Stratum merged | Recommendations reliable but less specific |
| `DEGRADED` | Features relaxed | Use with caution, check relax_chain |
| `DEGRADED_HEAVY` | Pool 30-99 after relaxation | Low confidence, limited recommendations |
| `INSUFFICIENT` | Pool < 30 | Do not use — data too scarce |

## Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `N_MIN` | 200 | n_score log denominator base |
| `STRATUM_N_MIN` | 100 | Min stratum size for valid rank |
| `ABSOLUTE_MIN` | 30 | Absolute minimum pool for any output |
| `SHUFFLE_TIMES` | 100 | Noise test permutations |
| `MAX_RELAX_ROUNDS` | 6 | Safety valve for relaxation |

## Whitelist Parameters (13)

The engine only recommends values for these parameters:

`acos_bin`, `aiPersonality`, `bidAdPlaceStatus`, `bidPerformanceStatus`, `bidDaypartStatus`, `budgetDaypartStatus`, `budgetDynamicStatus`, `budgetRedistributeStatus`, `negativeTargetStatus`, `structPauseCampaignStatus`, `structPauseProductStatus`, `targetHarvestStatus`, `targetPausedAddStatus`
