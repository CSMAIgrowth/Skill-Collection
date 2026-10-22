# Value Mapping Tables

The engine stores parameter values as raw numbers in its training data. This document maps them to human-readable labels.

## On/Off Parameters (11 params)

Used by: `bidAdPlaceStatus`, `bidPerformanceStatus`, `bidDaypartStatus`, `budgetDaypartStatus`, `budgetDynamicStatus`, `budgetRedistributeStatus`, `structPauseCampaignStatus`, `structPauseProductStatus`, `targetHarvestStatus`, `targetPausedAddStatus`

| Raw Value | Display |
|-----------|---------|
| 0 | Off |
| 1 | On |

## negativeTargetStatus

| Raw Value | Display | Notes |
|-----------|---------|-------|
| 0 | Off | Negative targeting disabled |
| 1 | On | Negative targeting enabled |
| 3 | 待确认 | Legacy/special value — verify before applying |

## aiPersonality

| Raw Value | Display | Behavior |
|-----------|---------|----------|
| 1 | Conservative | Minimal changes, low risk |
| 2 | Moderate | Gentle optimization |
| 3 | Balanced | Equal weight to growth and efficiency |
| 4 | Aggressive | Active optimization, higher risk |
| 5 | Very Aggressive | Maximum optimization intensity |

## acos_bin

| Value | ACOS Range | Meaning |
|-------|-----------|---------|
| `low` | < 15% | Very efficient |
| `mid_low` | 15-25% | Good efficiency |
| `mid_high` | 25-35% | Moderate efficiency |
| `high` | ≥ 35% | Low efficiency |

## campaign_budget_bucket

Computed from training pool using log1p tercile boundaries:

| Value | Boundary | Typical Range |
|-------|----------|---------------|
| `low` | ≤ low_max | ~$0-5 |
| `mid` | low_max < x ≤ mid_max | ~$5-12 |
| `high` | > mid_max | ~$12+ |
| `no_budget` | Budget = 0 or null | No budget set |

**Note**: Exact boundaries are computed at engine load time from the training pool data. Typical values: low_max ≈ $5.00, mid_max ≈ $11.74.

## price_bucket_mode

| Value | Price Range (USD) |
|-------|-------------------|
| `高价` | ≥ $30 |
| `中高价` | $20 - $30 |
| `中价` | $13 - $20 |
| `中低价` | $8 - $13 |
| `低价` | < $8 |

## bsr_bucket

**Input**: BSR percentile (0-100). If source provides absolute rank, convert to percentile first.

| Value | BSR Percentile |
|-------|---------------|
| `Best Seller` | Top 1% (≤1) |
| `热销` | Top 1-10% (≤10) |
| `中等` | Top 10-50% (≤50) |
| `中下` | Top 50-80% (≤80) |
| `长尾` | Top 80-95% (≤95) |
| `极长尾` | Bottom 5% (>95) |
| `未知` | BSR = 0 or null |

## inventory_status

| Value | Total Stock (FBA + FBM) |
|-------|------------------------|
| `库存冗余` | ≥ 100 |
| `库存充足` | 50 - 99 |
| `库存适中` | 20 - 49 |
| `库存紧张` | 1 - 19 |
| `缺货/无数据` | 0 or null |

## lifecycle_stage

| Value | Days Since Listing |
|-------|-------------------|
| `新品冷启动` | 0 - 179 |
| `新品成长` | 180 - 364 |
| `成长期` | 365 - 729 (1-2 years) |
| `成熟期` | 730 - 1094 (2-3 years) |
| `老品` | ≥ 1095 (3+ years) |

## Significance Levels

| Level | Meaning | Recommended Action |
|-------|---------|-------------------|
| `显著` | Statistically significant (lift > P95 baseline) | Strong recommendation — apply change |
| `边缘` | Marginally significant (lift > P80 baseline) | Suggest change — apply with business judgment |
| `弱证据` | Weak evidence (n_touched 10-29) | Reference only — do not apply directly |
| `不显著` | Not significant | No change recommended |
| `证据不足` | Insufficient data (n_touched < 10) | Cannot determine — need more data |

## Scope Note

This skill only supports **Sponsored Products (SP)** managed groups. SP groups have the full 13-parameter space including all bid-related parameters. SB and SD groups are out of scope and will be filtered out by the recommendation script.
