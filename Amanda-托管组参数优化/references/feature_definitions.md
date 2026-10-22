# Feature Definitions (Tier 0-3)

## Overview

The recommendation engine uses 18 features organized in 4 tiers. Each tier has a different role in the query relaxation process.

**Key principle**: Features with insufficient or uncertain data are set to `None` and excluded from the engine query. This prevents the pool from being narrowed by unreliable data.

## Tier 0 — Query Prerequisites

These are always required and never relaxed.

| Feature | Source | Values | Notes |
|---------|--------|--------|-------|
| `targetType` | Group config | `1` (imitation), `2` (differentiation) | Determines which sub-pool to search |
| `marketplace_id` | Store country | `US`, `BR`, `MX`, `CA`, etc. | Direct mapping from countryCode |

## Tier 1 — Core Product Features

Relaxed last (highest priority to keep). Relaxation order: price → lifecycle → promo → category.

| Feature | Source | Bucket Rules |
|---------|--------|-------------|
| `price_bucket_mode` | `asinPrice` | ≥$30=高价, $20-30=中高价, $13-20=中价, $8-13=中低价, <$8=低价 |
| `lifecycle_stage` | `asinOpenDate` → days since listing | <180d=新品冷启动, 180-364=新品成长, 1-2yr=成长期, 2-3yr=成熟期, ≥3yr=老品 |
| `promo_phase` | Promo calendar | `pre_heat`, `peak`, `post_clear`, `normal` — **requires external data, usually None** |
| `category_l1` | `asinTitle` keywords | Keyword match: mount/bracket→Home, pet/grooming→Pet Supplies, else→General |

## Tier 2 — Operational Features

Relaxed before Tier 1. Order: peak_seasons → variation → trend_sales → trend_imp → inventory → bsr → budget → b14_ACOS → b14_CTR.

| Feature | Source | Bucket Rules |
|---------|--------|-------------|
| `peak_seasons_std` | Historical seasonality | `none`, `summer`, `holiday`, `back_to_school`, etc. — **requires historical analysis, usually None** |
| `variation_bin` | Variant count under parent ASIN | 1=单变体, 2-5=中变体, >5=多变体 — **requires full variant data, usually None** |
| `trend_sales_bin` | 14-day daily sales trend | `up`, `mid`, `down` — **requires daily time series, usually None** |
| `trend_imp_bin` | 14-day daily impressions trend | `up`, `mid`, `down` — **requires daily time series, usually None** |
| `inventory_status` | `asinFbaQuantity` + `asinFbmQuantity` | ≥100=冗余, ≥50=充足, ≥20=适中, <20=紧张, 0=缺货/无数据 |
| `bsr_bucket` | `asinBsr` (percentile) | ≤1%=Best Seller, ≤10%=热销, ≤50%=中等, ≤80%=中下, ≤95%=长尾, >95%=极长尾 |
| `campaign_budget_bucket` | `totalDailyBudget` | log1p terciles from training pool: low/mid/high (boundaries computed at load time) |
| `b14_ACOS_bin` | 14-day ACOS | <15%=low, 15-25%=mid, 25-35%=high, ≥35%=high — **requires ASIN-level perf, usually None** |
| `b14_CTR_bin` | 14-day CTR | ≥1.0%=high, 0.3-1.0%=mid, <0.3%=low — **requires ASIN-level perf, usually None** |

## Tier 3 — Supplementary Features

Relaxed first (lowest priority). Order: peak_month → b14_CVR → b14_CPC → trend_click → marketplace.

| Feature | Source | Bucket Rules |
|---------|--------|-------------|
| `peak_month` | Historical monthly analysis | Month number or None — **requires historical data, usually None** |
| `b14_CVR_bin` | 14-day CVR | ≥10%=high, 3-10%=mid, <3%=low — **requires ASIN-level perf, usually None** |
| `b14_CPC_bin` | 14-day CPC | ≥$2.0=high, $0.8-2.0=mid, <$0.8=low — **requires ASIN-level perf, usually None** |
| `trend_click_bin` | 14-day daily click trend | `up`, `mid`, `down` — **requires daily time series, usually None** |
| `marketplace_id` | Store country | Same as Tier 0 — used as last relaxation lever |

## Input JSON Format

### groups.json

```json
[
  {
    "aiGroupId": 864843,
    "aiGroupName": "Group Name",
    "asin": "B0XXXXXXXX",
    "campaignType": "sponsoredProducts",
    "targetType": 1,
    "targetAcos": 20,
    "totalDailyBudget": 15,
    "aiPersonality": 3,
    "aiStatus": 1,
    "numCampaign": 1,
    "lastOnDays": 43,
    "aiActionSettings": {
      "bidAdPlaceStatus": 0,
      "bidPerformanceStatus": 0,
      "bidDaypartStatus": 1,
      "budgetDaypartStatus": 1,
      "budgetDynamicStatus": 0,
      "budgetRedistributeStatus": 0,
      "negativeTargetStatus": 1,
      "structPauseCampaignStatus": 0,
      "structPauseProductStatus": 0,
      "targetHarvestStatus": 1,
      "targetPausedAddStatus": 0
    }
  }
]
```

**Field notes:**
- `campaignType`: Only `sponsoredProducts` is supported. SB/SD groups are filtered out.
- `targetType`: 1=imitation, 2=differentiation
- `aiPersonality`: 1=Conservative, 2=Moderate, 3=Balanced, 4=Aggressive, 5=Very Aggressive
- `aiActionSettings` values: 0=Off, 1=On. SP groups have all 11 On/Off params.

### asins.json

```json
{
  "B0XXXXXXXX": {
    "asinPrice": 16.99,
    "asinBsr": 215,
    "asinInventoryStatus": "Active",
    "asinFbaQuantity": 226,
    "asinFbmQuantity": 0,
    "asinOpenDate": "2026-06-15 03:22:05 PDT",
    "parentAsin": "B0XXXXXXXX",
    "asinTitle": "Product Title Keywords"
  }
}
```

## Reliable vs Unreliable Features (Current MCP Data)

**Reliable (participate in query):**
- `price_bucket_mode` — from ASIN price
- `lifecycle_stage` — from ASIN open date
- `category_l1` — from ASIN title keyword matching
- `inventory_status` — from FBA/FBM quantity
- `bsr_bucket` — from ASIN BSR percentile
- `campaign_budget_bucket` — from group daily budget
- `marketplace_id` — from store country code

**Unreliable (set to None, excluded from query):**
- `promo_phase` — needs promo calendar data
- `peak_seasons_std` — needs historical seasonality analysis
- `variation_bin` — needs complete variant tree data
- `trend_sales_bin`, `trend_imp_bin`, `trend_click_bin` — need daily time series
- `b14_ACOS_bin`, `b14_CTR_bin`, `b14_CVR_bin`, `b14_CPC_bin` — need ASIN-level 14-day performance
- `peak_month` — needs historical monthly analysis

When these data sources become available through additional MCP tools, the corresponding features can be re-enabled.
