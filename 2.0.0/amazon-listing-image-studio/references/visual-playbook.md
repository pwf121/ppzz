# 视觉拆解与原创提示词方法

## 1. 图片角色分类

先判断素材属于哪一种，不能混用评价标准：

| 角色 | 核心任务 | 常见检查点 |
|---|---|---|
| 主图 | 识别产品并争取点击 | 产品占比、背景、结构真实性、配件边界、缩略图可读性 |
| 副图-卖点 | 解释一项核心利益 | 一个主卖点、事实证据、视觉焦点、文字密度 |
| 副图-尺寸 | 降低尺寸误解 | 单位、参照物、尺寸线、变体一致性 |
| 副图-场景 | 建立使用想象 | 人群、环境、姿态、道具、真实尺度 |
| 副图-对比 | 说明差异 | 可核验维度、对比对象中立、避免贬损和无证据优越宣称 |
| 副图-结构 | 展示材质或内部结构 | 局部放大、爆炸图、剖面、部件标签 |
| 副图-步骤 | 降低安装或使用门槛 | 顺序、动作、时间、配件、警示 |
| A+ 品牌/故事 | 建立品牌与信任 | 叙事节奏、品牌资产权利、产品系列一致性 |
| A+ 功能模块 | 深化理解和交叉销售 | 模块目的、桌面/移动端阅读、事实与宣称边界 |

## 2. 每张图片的分析卡

full研究或用户明确要求逐图拆解时，每张可见图片输出以下字段；light先总览，只对能解决图需缺口的图片深入记录，不为每张竞品图重复写完整提示词。没有观察到写`unknown`，不要补猜：

```yaml
asset_id: listing-01-secondary-03
source_url: https://...
asin: B0XXXXXXXX
asset_type: main|secondary|a_plus
position: 3
funnel_job: click|explain|prove|reassure|compare|instruct
observed:
  composition: ""
  camera: ""
  background: ""
  lighting: ""
  palette: []
  material_rendering: ""
  information_hierarchy: ""
  text_summary: ""
selling_points:
  - claim: ""
    visual_evidence: ""
    evidence_status: observed|inferred|unknown
style_tags: []
prompt_hypothesis: ""
negative_prompt: ""
replace_with_user_product: []
copyright_exclusions: []
confidence: high|medium|low
```

## 3. 图片需求表格契约

进入制作流程的`links_without_requirements`必须先把竞品观察转换成用户可编辑的图片需求表。用户只要竞品分析时交分析及限制，不强制生成本品需求表；用户明确要求表格时即使暂不生图也先交表。表格每行只代表一个目标图片位，不能把竞品的一张图直接当成用户成图要求。

基础字段：

```yaml
asset_id: target-secondary-01
asset_type: main|secondary|a_plus
position: 1
content_type: main|lifestyle_scene|selling_point|dimensions|structure|comparison|steps|brand_story
image_goal: ""
display_effect: ""
composition: ""
camera: ""
lighting: ""
palette: []
copy_safe_area: ""
headline: ""
subheadline: ""
selling_point_copy: ""
reference_asins: []
product_fact_source: ""
copyright_exclusions: []
confidence: high|medium|low
status: DRAFT|NEEDS_FACT_CONFIRMATION|REQUIREMENTS_CONFIRMATION_REQUIRED|CONFIRMED
```

条件字段：

- 场景图 `lifestyle_scene`：必须填写 `scene_name`、`space_type`、`space_expression`、`use_action`、`mood`。`space_expression` 要说明希望传达的空间尺度、布局关系或生活状态，不能只写“客厅”“厨房”等地点名。
- 卖点图 `selling_point`：必须填写 `selling_point`、`visual_evidence`、`fact_source`。一张图只设一个核心卖点；证据缺失时标 `NEEDS_FACT_CONFIRMATION`。
- 主图 `main`：必须填写产品主体占比、角度、背景、阴影、配件边界和缩略图识别效果，并把不确定的站点规则标为人工复核。

`links_with_requirements` 不另造第二份互相冲突的需求表；应保留用户原始行号并把每一行映射到标准字段、参考素材与原创化提示词。用户表格中的明确要求优先于竞品视觉偏好，产品事实与权利边界高于两者。

## 4. 风格维度

至少从以下维度总结，避免只写“高级”“简约”“科技感”等空泛形容词：

- 构图：居中、三分法、对角线、悬浮、平铺、爆炸、局部特写、前后景。
- 镜头：正视、俯拍、45 度、微距、广角、长焦压缩、景深。
- 光线：高键、低键、柔光、硬光、轮廓光、窗光、渐变棚拍光。
- 背景：纯白、纯色、渐变、室内、户外、材质台面、抽象空间。
- 色板：主色、辅助色、强调色、背景对比关系。
- 材质表达：反射、粗糙度、透明度、纹理、边缘和阴影。
- 信息设计：标题、数字、图标、标注线、对比表、留白和阅读顺序。
- 人物与场景：人群、动作、情绪、服装、环境、道具和尺度参照。
- 后期语言：写实摄影、3D 产品渲染、合成、信息图、插画或混合。

## 5. 跨图字体角色契约

主图或副图需要文案时，先在批次级视觉蓝图中定义唯一的 `typography_role_map`，再进行排版：

```yaml
typography_role_map:
  headline:
    label: 大标题
    font_family: "<准确字体家族 A>"
    font_style: "<准确样式>"
    font_weight: "<准确字重>"
  subheadline:
    label: 小标题
    font_family: "<准确字体家族 B>"
    font_style: "<准确样式>"
    font_weight: "<准确字重>"
  selling_point:
    label: 卖点文案
    font_family: "<准确字体家族 C>"
    font_style: "<准确样式>"
    font_weight: "<准确字重>"
```

执行规则：

1. A/B/C 是角色占位符，实际执行时必须写入准确字体家族、样式和字重；三者允许相同或不同，不要求必须使用三种字体。
2. 默认同一批次所有副图中，对应角色使用字体表指定的同一字体身份（`font_family + font_style + font_weight`）；未经用户明确授权，不允许逐图替换字体。不能由助手为“更有变化”自行制造例外。
3. 字号、字距、行距和颜色可以按预先定义的版式 token 调整。用户明确指定某些图位的字体例外时尊重其选择；已有授权不重复询问，只补实际替代字体等关键未知，不擅自改其他图。
4. 某张图没有某一文案角色时记录 `not_applicable`，不得为了凑齐角色而增加无必要文字。主图没有文案时同样记录 `not_applicable`；是否允许主图文字必须以目标站点当前规则为准。
5. 字体文件不可用、授权不清或目标语言缺字时，先停止最终排版；选定替代字体后更新批次级映射，并对使用该角色的全部图片统一替换和复验。禁止只让个别图片静默 fallback。
6. 图片生成模型只负责底图和文字安全区；最终文字使用可编辑文字层排版，以便准确控制字体、字形和可读性。

授权例外在layout JSON和QA回执中记录`typography_exceptions`：每条包含`asset_id`、`role`、实际`font_family/font_style/font_weight`、`approval_source`、`qa_status`及绑定成品的`reviewed_sha256`。保留批次默认映射，不伪造所有图仍使用同一字体；只将真实授权且单独验收通过的记录视为例外。缺授权、缺QA、超出授权图位/角色、字体无授权或缺字仍标`REVISION_NEEDED`。只改文字层，不重生成底图；双版本文件与哈希契约不变。导出脚本不验证字体例外的真实授权或字形，必须单独检查布局和视觉，不以脚本PASS代替。

## 6. 卖点提取规则

1. 先写“图片看到了什么”，再写“它可能表达什么”。
2. 只有产品页面或用户事实表能证明的属性才可标 `fact`。
3. 图片暗示但没有事实支持的功效标 `inferred`，不得迁移到用户产品。
4. 尺寸、材质、认证、耐用性、健康、安全和性能数字必须有来源。
5. 文案只做短摘要，避免整段抄录竞争对手受保护表达。

## 7. 重构提示词模板

提示词不是对竞品的像素级复刻，应使用下列原创结构：

```text
[目标图片角色]，展示[用户产品的准确身份与外观]。
核心卖点：[来自用户事实表的一个可证明卖点]。
构图：[抽象后的构图逻辑]；镜头：[角度、焦段、景别]；
环境：[原创场景]；光线：[方向、软硬、色温]；
材质表现：[表面、纹理、反射与阴影]；
色板：[品牌允许的主色/辅助色/强调色]；
信息安全区：[为后期文案保留的位置，不直接生成难以控制的文字]；
字体角色表：[大标题/小标题/卖点文案分别绑定的批次级字体家族；无文案则 not_applicable]；
输出：[宽高比、分辨率方向、写实/3D/信息图风格]；
保持产品的结构、颜色、Logo、配件数量和相对比例与参考图一致。
```

负面提示词至少包含：

```text
不要出现竞品品牌、竞品 Logo、竞品包装、受保护角色、原竞品文案、
不可验证认证或功效、错误配件、结构变形、颜色漂移、数量错误、
多余手指、不可读文字、水印、平台 UI、截图边框。
```

### 生成前不确定项门

重构提示词后、调用图片生成工具前，将未知项分成三类：

1. `VERIFY_FROM_SOURCE`：可从链接、需求表、产品事实或产品图片确认，先自行核验并记录来源。
2. `ASSUMPTION_ALLOWED`：不影响产品真实性、交付数量、尺寸、文案或权利，可写明假设后继续。
3. `NEEDS_USER_CONFIRMATION`：会改变产品结构、颜色、尺寸、材质、配件数量、变体、图片数量/类型、场景、核心卖点、文案、宽高比、字体或权利边界；只汇总这类问题向用户提问，并暂停生成。

不得把可自行核验的问题转给用户，也不得为了保持“全自动”而跳过 `NEEDS_USER_CONFIRMATION`。

## 8. 同类/相似产品 Top 10 模式统计（仅full）

light与full分流见research-policy.md。新建无链接有表默认目标3个、按缺口最多5个代表参考；不计算或宣称类目普遍规律。明确完整研究与历史Top10授权不降级。

先判断是否为相同或类似产品，再对每个纳入样本标注离散视觉标签并计数；不要凭类目名自动纳入，也不要凭印象写“多数都这样”。最低统计字段：

- 有效 ASIN 数；
- `same_product`、`similar_product`、`not_comparable` 数量及逐 ASIN 理由；
- Top 10 的排序口径（官方公开类目排名中的同类筛选顺序，或同一第三方模型估算销量）；
- 有主图的比例；
- 有副图的比例和中位图片数；
- 可见 A+ 的比例；
- 主图构图标签频次；
- 副图任务标签频次；
- 场景、人像、尺寸、对比、结构、步骤等标签频次；
- 缺图、重复变体和无法访问数量。

如果有效样本不足 10，标题和结论都必须显示 `PARTIAL_MARKET_SET (n/10)`。只有重复模式有足够样本支持时，才把它写入视觉蓝图；单一样本特征只能写为个案观察。

## 9. 生成后 QA

四宫格等多场景内容必须先分别生成并验收单张，再拼版；分别保留单张无文案原生素材与完整无文案拼图，详情见export-quality.md。家人/宠物/商务/聚会仅为用户选择的场景，不是所有产品固定四场景；不得凭人物坐扶手证明承重，或凭宠物同框证明耐抓、防污。

按优先级检查：

1. 产品身份：结构、部件、Logo、颜色、尺寸关系。
2. 事实：卖点、配件、数量、材质和使用方式。
3. 权利：竞品品牌、人物、角色、包装和文案残留。
4. 平台：主图/A+ 当前规则与文字安全区。
5. 字体系统：逐图读取实际字体家族、样式和字重，对照`typography_role_map`及已授权、已验收的`typography_exceptions`。未授权差异、未声明fallback、例外证据不完整或字体不可追溯标`REVISION_NEEDED`；有效例外不强改其他图，报告“默认统一，含用户授权例外”，不伪称全套完全同字体。
6. 视觉：焦点、留白、对比、清晰度、批次一致性。

任一产品身份或事实错误都标 `REJECTED`；纯审美问题可标 `REVISION_NEEDED`。
