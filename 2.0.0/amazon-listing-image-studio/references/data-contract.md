# 数据来源、指标与报告版本契约

## 数据来源表

| source_id | 角色 | 类型 | 入口 | 粒度 | 时效/追溯 | 主来源与降级 |
|---|---|---|---|---|---|---|
| `amazon_listing_public` | basic | official_public | 用户提供的 Amazon 商品页 | ASIN/图片位/A+ 模块 | 保存 URL、读取状态和时间 | 主来源；阻断时要求用户上传截图或原图，不绕过限制 |
| `requirements_sheet` | basic | manual | 用户上传的 XLSX/CSV/TSV | 产品/类目/图片需求 | 保存文件名、哈希和读取时间 | 缺必填列时阻断表格模式 |
| `generated_image_requirements` | output | generated | 多链接、无需求表分支 | 目标图片位/需求行 | 保存生成依据、来源 ASIN、字段状态和确认状态 | 必须先落地 XLSX 与同结构 JSON；未确认时阻断图片生成 |
| `prompt_matrix` | output | generated | 逐图分析与需求映射 | 目标图片位/提示词版本 | 保存需求行、参考素材、产品事实和置信度 | 高影响未知未确认时阻断图片生成 |
| `amazon_best_sellers` | basic | official_public | 同站点同节点公开 Best Sellers 页面 | 类目排名/ASIN | 保存节点、页码、读取时间和有效数量 | 受限时降级为用户导出；不用于精确销量 |
| `user_market_export` | basic/fallback | manual | 用户提供的类目或竞品导出 | 类目/ASIN/排名/估算销量 | 保存文件名、字段映射和数据日期 | 可替代公开榜单，但必须声明提供方和口径，并执行相似性筛选 |
| `third_party_market` | enhancement | third_party | 当前可发现且已授权的市场数据工具 | 节点/ASIN/BSR/估算销量 | 保存 provider、tool、站点、字段和 `dataAsOf` | 只作公开市场增强；冲突时并列保留 |
| `user_product_assets` | basic | manual | 用户产品图片和事实表 | SKU/产品/素材 | 保存文件清单、权利声明和读取时间 | 生成阶段事实主源；不得用竞品资料替代 |
| `generated_assets` | output | generated | imagegen | 图片位/批次 | 保存提示词、工具状态、时间和路径 | 不反向升级为产品事实 |

禁止在报告或 manifest 中保存 Token、Cookie、授权头、Secret 或完整登录链接。

生成交付新增 `amazon-listing-image-studio/dual-export/v1` 配对契约，见 `export-quality.md`：每个 asset_id 同时指向无文案原始文件和无损文案母版，记录 native_dimensions、export_dimensions、scale_factor、upscaled、source_sha256、copy_applied 与 visual_qa。generation-manifest 保持原有结构并引用 export-manifest；旧项目重导出无需改写历史记录。双版本缺失或原图哈希不一致时只可 PARTIAL，不得 COMPLETE。

## 指标字典

| metric_id | 名称 | 定义 | 粒度/单位 | 来源 | 字段等级 | 缺失行为 |
|---|---|---|---|---|---|---|
| `accessible_asset_count` | 可访问素材数 | 实际读取且能归属到主图/副图/A+ 的素材数量 | ASIN/张 | `amazon_listing_public` | `basic_required` | `BLOCK` 对应 ASIN 的完整分析 |
| `asset_role` | 图片角色 | 主图、副图或 A+ 及页面顺序 | 图片 | `amazon_listing_public` | `basic_required` | `BLOCK` 该图片分析 |
| `visual_observations` | 视觉观察 | 构图、镜头、光线、背景、色板和信息层级 | 图片 | `amazon_listing_public` | `basic_required` | `BLOCK` 该图片提示词 |
| `selling_point_evidence` | 卖点证据 | 可观察卖点及 observed/inferred/unknown 状态 | 图片 | 页面+用户事实 | `basic_required` | `MANUAL` |
| `workflow_mode` | 三模式路由 | `links_without_requirements|links_with_requirements|requirements_sheet` | 项目 | 输入清单 | `basic_required` | 无法唯一判定时 `BLOCK` |
| `requirements_row_coverage` | 图片需求行覆盖 | 已映射并通过字段检查的目标图片位数/全部目标图片位数 | 项目/比例 | 需求表或 `generated_image_requirements` | `basic_required`（生成阶段） | 未覆盖行保持 `NEEDS_USER_CONFIRMATION`，不得按零处理 |
| `requirements_confirmation_status` | 需求确认状态 | `REQUIREMENTS_CONFIRMATION_REQUIRED|CONFIRMED|AUTO_AUTHORIZED|NEEDS_USER_CONFIRMATION` | 项目 | 用户确认与工作流状态 | `basic_required`（生成阶段） | 非 `CONFIRMED`/`AUTO_AUTHORIZED` 时阻断对应生成 |
| `category_rank` | 类目排名 | 同站点同节点同读取时间的公开排名或 BSR | ASIN/名次 | `amazon_best_sellers` 或导出 | `module_required` | `SKIP` 销量排序模块 |
| `estimated_units_30d` | 近 30 天估算销量 | 同一第三方模型给出的估算值 | ASIN/件 | `third_party_market` | `module_required` | `SKIP` 估算销量模块 |
| `product_similarity` | 产品相似性 | `same_product|similar_product|not_comparable` 及理由 | ASIN/标签 | 页面与本品资料 | `basic_required`（研究） | 不可比样本不纳入；不要求轻量模式补全销量 |
| `market_sample_count` | 有效样本数 | 可比、去重、实际读到视觉素材的ASIN数 | 项目/个 | 声明的研究来源 | `basic_required`（研究） | light记录实际n及目标3/上限5，不称排名；full不足10标`PARTIAL_MARKET_SET (n/10)` |
| `asset_coverage_rate` | 素材覆盖率 | 有效素材 ASIN 数/有效市场样本数 | 类目/% | 采集结果 | `full_required` | 不影响已有基础分析，但不能标完整增强 |
| `pattern_frequency` | 视觉模式频次 | 具有某离散风格标签的有效 ASIN 数 | 标签/个与% | 视觉分析 | `full_required` | `SKIP` 类目规律结论 |
| `product_fact_coverage` | 产品事实覆盖 | 目标图片卖点中可回链用户事实的比例 | 批次/% | `user_product_assets` | `basic_required`（生成阶段） | `BLOCK` 无事实图片生成 |
| `generation_qa_status` | 生成质检状态 | `PASS|REVISION_NEEDED|REJECTED` | 图片 | `generated_assets` | `display_optional` | 展示并阻断错误图交付 |

## 报告版本与模块

### 三模式基础契约

以下是制作输入契约。纯竞品分析先在对话意图层分流，只输出实际可见素材分析、来源和限制，不要求本品图需或制作目录；用户要求制作图片或明确要求图需表后才进入制表/确认门。意图分流不增加operation/input_mode枚举，也不改变已有脚本输入格式。

- `links_without_requirements`：两个以上同站点 Amazon 链接且不含 `requirements_path`。完成逐图分析后，先生成 `image-requirements.xlsx` 与同结构 JSON；默认进入 `REQUIREMENTS_CONFIRMATION_REQUIRED`。
- `links_with_requirements`：两个以上同站点 Amazon 链接并提供可读取的需求表。先完成表格字段映射和逐行原创化提示词重构；高影响未知项进入 `NEEDS_USER_CONFIRMATION`。
- `requirements_sheet`：无链接有表；新任务默认research_depth=light（3个目标、最多5个，按图需缺口扩展）；明确Top10/排名/类目共性时为full。详见research-policy.md。只有链接且无图需仍先生成表，不能跳过确认门。
- `SINGLE_REFERENCE`：一个链接的降级分支，可同时有表；不是第四种完整市场研究模式，不选销量最佳。
- `operation=new|continue|revise|export`独立于input_mode；旧项目未记录research_depth时不能以新默认降低历史授权，已有Top10记录保留full，历史不明列迁移待确认；仅导出不重新开展研究。
- 旧值 `links` 只作为输入兼容别名，由脚本根据 `requirements_path` 是否存在规范化到前两种模式；任何新 manifest 和回执都写规范化后的三模式值。

### 基础版报告

- 多链接模式：链接、站点、ASIN、素材角色和逐图视觉观察有效；制作流程有需求表时还需字段映射有效，无表时还需生成需求表及确认状态有效。纯分析报告不因没有本品图需表而失败。
- 需求表light：本品与图需有效，站点/用途/关键结构可比、视觉观察可追溯；输出代表参考与具体图需建议，不以精确节点或销量模块作为视觉方案前置。没有有效视觉观察时不生成伪研究；不足目标列实际n、缺口和影响。
- 需求表full：精确站点/可比节点有效，10个相似性筛选、去重且排序口径一致的样本；不足仅带缺口数据包，不称完整Top10报告。
- 输出来源、读取时间、素材缺失和逐图置信度。

### 增强模块

| 模块 | `module_required` | 完成信号 |
|---|---|---|
| 可比销量/BSR | 同站点、同节点、同时间附近的排名或同模型估算 | 可以按声明口径选择表现最强参考 |
| 同类/相似产品 Top 10 视觉统计 | 10 个去重有效 ASIN、相似性标签、有效视觉标签与样本追溯 | 输出 Top 10 的模式频次与逐 ASIN 纳入理由 |
| 第三方销量估算 | provider、tool、站点、节点、时间和估算字段有效 | 输出“第三方估算”，不写成官方销量 |
| 用户产品融合 | 产品素材、事实表、权利确认、项目名和批次名有效 | 允许调用 imagegen 并记录 manifest |

完整增强清单 `full_required`：

- 可比销量/BSR 模块完成；
- research_depth=full时市场样本满足Top10证据门且素材覆盖率可计算；light不能因3个样本齐全而标“完整Top10”；
- 所有进入提示词矩阵的卖点都能回链产品事实；
- 来源、读取时间、节点和父子体口径完整；
- 已生成图片全部有 QA 状态和 generation manifest。

纯展示字段（如评论数、星级、价格、优惠标签）属于 `display_optional`，不控制完整增强判定，也不能代替销量。

## 路由规则

```text
if user_only_requests_analysis:
    return requested_analysis_with_sources_and_limits
# 制作或明确制表请求继续以下既有输入路由
if two_or_more_links and requirements_path:
    workflow_mode = links_with_requirements
elif two_or_more_links:
    workflow_mode = links_without_requirements
elif one_link:
    workflow_mode = SINGLE_REFERENCE
elif requirements_path:
    workflow_mode = requirements_sheet
else:
    BLOCKED_INPUT

if security_error or source_contract_conflict:
    BLOCK
elif workflow_mode == links_without_requirements and requirements_not_confirmed:
    REQUIREMENTS_CONFIRMATION_REQUIRED
elif workflow_mode == links_with_requirements and material_unknowns:
    NEEDS_USER_CONFIRMATION
elif basic_required_invalid:
    BLOCK_WITH_GAPS
elif report_edition == basic:
    BASIC
elif enhancement_global_invalid or complete_module_count == 0:
    BASIC_WITH_REASON if report_edition == auto else BLOCK
elif all_full_required_complete:
    FULL_ENHANCED
else:
    PARTIAL_ENHANCED
```

固定标签：

- `基础版报告`
- `增强版报告（部分增强）`
- `增强版报告（完整增强）`

报告版本、数据质量 A/B/C/D 和逐结论证据等级是三条独立轴。

research_depth=light|full|provided是第四个独立维度，不把研究范围与数据增强混淆。明确basic不调用第三方增强，但安全/损坏/口径错误必须优先阻断。来源选择和完整增强清单保持可审计，未使用增强模块不伪称enhanced。

## 产品认知与图需版本

产品档案记录product_family、product_subtype、configuration、viewpoint、confirmed_features、fact_revision、引用图片路径/SHA256。关键事实逐条记录value、source、evidence_status（user_confirmed/spec_document/visible/inferred/unknown）、conflict、affected_asset_ids。

结构、材质、功能未知不能用于确定性宣称。每个图位绑定本品事实与需求行；需求文件保留原始行号，优化建议保存原内容、建议、依据、需确认与确认状态。requirements_revision变化只使依赖图失效。

代表校样从正式图位选取，通过不新增冗余图位；事实变化可能使旧样图失效。原始素材、生成图片和选定验收版本分开。

## 增量计划

2.0兼容扩展：开场属于对话入口，不把任意文字作为validate-intake已通过；链接和表都缺失时仍保持业务BLOCKED_INPUT，先引导补材料。导出新增可选supporting_assets及component_asset_ids，场景素材不进入expected_asset_ids/selected_asset_ids正式图位计数。可选variant_template锁定已定稿母版和独立变体批次；详见export-quality和variants。无新增字段时保持旧schema和operation语义。

`scripts/workflow.py`仅输出只读计划，不代表工具已经生成/排版/导出。项目身份、selected_asset_ids归属与用户授权需先核验；legacy记录缺证据时needs_review，不凭文件存在跳过。

资产保存asset_id、选定版本记录、status（pending/trial/rejected/passed）、stage（pending/generated/layout/reviewed）及生成时fingerprints和当前current_fingerprints：source_hash、fact_revision、requirements_revision、prompt_hash、font_revision、copy_hash。实际source_path哈希需与当前记录相符，成品output_path/output_sha256/reviewed_sha256需匹配；需要重排版时base_path/base_sha256/base_reviewed_sha256锁定已审核底图。

CLI：`python scripts/workflow.py resume-plan --manifest <workflow.json>`（inspect同样只读）。project_root须有project.json且其中project_root相符。product_review包含status=passed、fact_revision、confirmed_facts与unknown_facts键列表；每个图位用required_facts声明依赖。product_review.fact_revision是本次所选资产组的版本；不同事实版本的独立组须分组调用，不能把全项目版本变化传播给无关图位。缺字段返回needs_review，不静默创建证据。

同输入且输出/QA有效可skip；文案/字体变化只layout；事实/素材/提示词/需求的相关依赖变化重审或generate；export绝不产生研究/生成计划。状态不明、缺选定版/缺QA、REJECTED/试稿不得自动晋级。相同结构/关键材质连续失败2次暂停该图，记录原因，未受影响图可继续。

完整批准图位expected_asset_ids与本次selected_asset_ids分别保存。执行者必须检查只读计划后在已有授权内执行；本脚本不是自动批处理执行器。

## 销量与排名口径

- Amazon Best Sellers 排名/BSR 是排名事实，不等于公开精确销量。
- `bsr_prediction` 等第三方结果是模型估算，必须展示提供方、时间和类目节点。
- 不同提供方的销量估算不得平均或多数表决。
- 父体和子体数据不得无声明混合。
- 评论数、评分、搜索位置和广告位不能单独支撑销量排名。
- 无法建立可比口径时，状态为 `BEST_SELLER_UNRESOLVED`，由用户指定参考样本。
