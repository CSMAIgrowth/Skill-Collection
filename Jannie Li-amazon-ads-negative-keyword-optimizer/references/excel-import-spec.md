# 客户否词清单导入规范

用于模式 B（客户清单导入驱动）。目标是把客户手里的任意格式否词表，标准化成可提交的否词条目，并把所有问题显式暴露出来。

## 1. 推荐表格结构

| 关键词 | 匹配类型 | 广告活动 | 广告组 | 层级 |
|--------|---------|---------|--------|------|
| ear buds | 精准否定 | SparkX AI ARC 4 plus-Cleer Brand-Exact | ARC 4 plus--Brand-Exact | 广告组 |
| long battery open ear earbuds | 词组否定 | SparkX AI ARC 4 plus-Cleer Brand-Exact | ARC 4 plus--Brand-Exact | 广告组 |
| sexy jumpsuit | 精准 | SparkX AI ARC 4 plus-Cleer Brand-Exact | — | 广告活动 |

只有「关键词」列是必需的。其余列缺失时用脚本参数补默认值。

## 2. 列名识别规则

脚本对列名做归一化（转小写、去符号、保留中英文）后按正则匹配，因此下列写法都能识别：

| 字段 | 可识别写法 |
|------|-----------|
| 关键词 | `Keyword`、`Keyword Text`、`Search Term`、`Negative Keyword`、`否词`、`关键词`、`词`、`否定词` |
| 匹配类型 | `Match Type`、`匹配类型`、`匹配方式`、`类型` |
| 广告活动 | `Campaign`、`Campaign Name`、`Campaign ID`、`广告活动`、`活动`、`活动名称` |
| 广告组 | `Ad Group`、`AdGroup`、`Ad Group Name`、`Ad Group ID`、`广告组`、`广告组名称` |
| 层级 | `Business Type`、`Level`、`层级`、`否词层级`、`作用层级` |
| 账户 | `Profile ID`、`账户 ID`、`店铺 ID` |

列名不在上表内时，脚本会报「未能识别关键词列」并打印实际表头，按提示改名即可。

## 3. 匹配类型归一化

| 输入 | 归一化结果 |
|------|-----------|
| `exact`、`negativeExact`、`negative exact`、`精准否定`、`否定精准`、`精准` | `negativeExact` |
| `phrase`、`negativePhrase`、`negative phrase`、`词组否定`、`否定词组`、`词组` | `negativePhrase` |
| 空值 | 用 `--default-match-type`（默认 `negativeExact`） |
| 其他任何值 | **报错**，不猜 |

## 4. 层级归一化

| 输入 | 归一化结果 |
|------|-----------|
| `adgroup`、`ad group`、`广告组`、`组` | `adgroup` |
| `campaign`、`广告活动`、`活动` | `campaign` |
| 空值 | 用 `--default-business-type`（默认 `adgroup`） |

层级决定否词的作用范围，也决定需要哪个目标 ID：

- `adgroup` → 必须有 `adGroupId`（活动级 ID 可一并带上）
- `campaign` → 必须有 `campaignId`

## 5. 目标位定位

清单里通常写名称而非 ID，必须先用 `get_entity_metadata` 拉元数据做映射：

```
get_entity_metadata(entity='campaign', filters={'campaignId': {'in': [...]}})
get_entity_metadata(entity='adGroup',  filters={'campaignId': {'in': [...]}})
```

把响应原样存为 JSON 传给 `--metadata`。脚本按以下顺序解析：

1. 有 `adGroupId` → 直接查 `adGroup` 元数据补 `campaignId`
2. 有 `adGroupName` → 按归一化名称匹配 `adGroupName`
3. 有 `campaignName` → 按归一化名称匹配 `campaignName`

**匹配不上的一律报「目标位无法定位」，不得猜 ID、不得模糊匹配到相似名称。**

常见匹配失败原因：

| 原因 | 处理 |
|------|------|
| 广告组名称有前后空格或全半角差异 | 脚本已归一化；仍失败说明确实不同 |
| 名称是历史命名，已被重命名 | 让用户提供当前名称或 ID |
| 广告组属于未授权 profile | 先确认 profile 授权范围 |
| 元数据查询范围漏了该活动 | 扩大 `filters.campaignId` 范围重新拉取 |

## 6. 校验项

| 校验 | 规则 | 失败处理 |
|------|------|---------|
| 关键词长度 | ≤ 80 字符 | 报错，需用户缩短 |
| 关键词字符 | 不含 `/` | 报错，需用户改写 |
| 匹配类型 | 仅 `negativeExact` / `negativePhrase` | 报错，不猜 |
| 层级 | 仅 `adgroup` / `campaign` | 报错 |
| 目标位 | 必须能解析出内部 ID | 报错，列入「无法定位」 |
| 重复 | 同一目标位 + 同一文本 + 同一匹配类型只保留一条 | 跳过并列出 |
| 已存在 | 与 `--existing` 传入的现有否词比对 | 跳过并列出 |

## 7. 输出

| 文件 | 内容 |
|------|------|
| `approved_items.json` | 通过校验的条目，可直接喂给 `build_negative_batches.py` |
| `import_report.md` | 校验报告：列识别结果、统计、三类问题明细 |

`approved_items.json` 的条目结构：

```json
{
  "profileId": "2950993281269288",
  "campaignType": "sponsoredProducts",
  "businessType": "adgroup",
  "keywordText": "ear buds",
  "matchType": "negativeExact",
  "campaignId": 44400757,
  "adGroupId": 133264344
}
```

## 8. 必须向用户交代的事

模式 B 没有搜索词表现数据，因此：

1. **不能判断这些词是否真的该被否**。清单正确性由客户负责，但需明确声明这一局限。
2. 若清单含品牌词、核心类目词或已转化词，必须单独列出并请用户逐条确认。
3. 无法定位的条目**不得静默剔除**，必须逐条列出让用户补充。
4. 提交前的最终预览必须给出总条数、层级分布、批次数，让用户核对数量是否与自己的清单一致。

## 9. 全流程命令示例

```bash
# 1. 导入并校验
python scripts/import_negative_list.py \
  --file customer_negatives.xlsx \
  --metadata campaigns.json adgroups.json \
  --default-profile-id 2950993281269288 \
  --default-business-type adgroup \
  --default-match-type negativeExact \
  --out approved_items.json --report import_report.md

# 2. 与现有否词比对后分批
python scripts/build_negative_batches.py \
  --items approved_items.json \
  --outdir batches \
  --batch-size 100 \
  --existing existing_negatives.json

# 3. 按 manifest.json 顺序逐批提交，每批提交后重新读取验证
```
