# 高清双版本导出

版本：2.0.0。适用：新批次、已有项目排版与重新导出；读取旧清单不自动升级QA。产品专属事实仍读取项目资料，不写入本参考。

## 两套交付

默认export_root为`<batch_root>/exports`；也可使用独立项目导出目录或用户指定的外部delivery_root。沿用已确认批次，保留旧结果。同名同哈希可跳过，不同哈希停止冲突；不覆盖原图或用户其他交付。copy_only只复制已有选定文件，不重新编码、缩放或生成。

- `无文案原图/`：每个通过产品 QA 的图片位复制选定的原始完整文件，保留原像素、格式、色彩信息与透明通道，SHA-256 必须与底图一致。这里包括白底主图、场景及细节底图。“无文案”表示没有后加营销文字，不删除真实产品上的标签。不得从文案图擦字恢复，也不得先缩图/压缩后冒充原图。
- `亚马逊文案图/`：同 asset_id 的成品，默认无损 RGB PNG；文字按已确认 typography_role_map 在最终像素网格渲染。主图 `copy_applied=false`，不要为了凑数量加标题。文案必须来自已确认需求。需要 JPG 时从无损母版额外导出高质量单次编码，记录质量/色度采样；不得只交小尺寸预览 JPG。
- 可编辑 SVG/排版 JSON 放 export_root 下 `layout/`，记录字体家族/样式/字重及位置。SVG 可嵌入源图或引用稳定的本地副本，确保可复现。
- 上传模块若需要较小尺寸，在文案文件夹的 `upload/` 中另外导出；高清母版仍保留。不要把某个尺寸写成所有站点和模块统一政策。

## 清晰度与排版

多场景拼图先生成和验收单张素材，再排版；完整无文案拼图是正式图位的源文件。原生单张素材另存`无文案原图/场景素材/`，不从拼图裁切冒充独立生成原图。顶层可选`supporting_assets`记录单张，正式`assets`行用`component_asset_ids`引用；4张场景＋1张四宫格按1个设计图位、4个素材计数，不要求素材也有文案配对。任一素材缺失/待审/拒收则该拼图不能通过。

每个supporting_assets条目包含`asset_id`、`source_path`（绝对）、`source_sha256`、`no_copy_path`（在无文案原图内）、`native_dimensions`、`visual_qa=PASS`与`reviewed_sha256`（绑定源图字节）。所有引用必须存在、唯一、已验收，素材ID与正式图位ID不能重名，未被引用的额外素材拒收以免误计范围。无该字段的历史清单不受影响。可选变体关联按[变体套版](variants.md)校验。

1. 检查真实 native_dimensions；只有已确认选定版本可作为源。禁止重新选择含结构错误的较大文件。
2. 将 native_dimensions、export_dimensions、scale_factor、resampling、source_sha256 写入 manifest。放大时记录 `upscaled=true` 与 detail_limit；提高 DPI、PNG 文件变大、锐化或插值不代表新增原生细节。
3. 尽量在底图原生尺寸制作母版；用户指定更大画布时从原图单次高质量重采样，输出与原始像素分开说明。需要真正新增细节时使用获准的图像生成/修复流程，并重新验收产品身份；不静默重绘结构。
4. 普通版式与文字层采用确定性排版。禁止对整张成图做模糊、降噪、反复缩放；不在低清预览上叠字后再放大。仅文字层可以高分辨率抗锯齿渲染后合成。
5. 先量文字边界，再渲染；不足时换行或调整版面，禁止 Ellipsis/静默截字。字体角色默认跨图一致；用户明确授权的局部例外须按visual-playbook记录typography_exceptions并单独验收，其他图片不改。未授权差异或例外记录/QA缺失仍拒收。脚本只检查文件，不自动证明字体和例外授权正确。
6. 不用大面积半透明蒙层覆盖产品主体、接口、纹理或结构。预留区不足时使用独立边栏/窄标题栏，保证产品轮廓及卖点可见。保留产品比例，不拉伸照片。
7. 每张以 100% 像素检查柜体/产品边缘、细节纹理、透明材质、文字边缘与覆盖区域。源图本身失焦时记录限制，不能因文件数/尺寸通过就宣称视觉完全通过。

## export-manifest.json 契约

schema：`amazon-listing-image-studio/dual-export/v1`。
顶层：`export_root`（绝对路径）、`expected_assets`（本次assets条数）、`assets`；完整验收还需`expected_asset_ids`（全部批准图位）、`selected_asset_ids`（本次子集）。设计图位、尺寸版本和文件份数分别计数，不缩小完整范围掩盖缺图。
每行：

```json
{
  "asset_id": "SECONDARY-01",
  "asset_type": "secondary",
  "source_path": "<absolute approved source path>",
  "source_sha256": "<actual hash>",
  "with_copy_sha256": "<actual output hash>",
  "reviewed_sha256": "<visually reviewed output hash>",
  "no_copy_path": "无文案原图/SECONDARY-01.png",
  "with_copy_path": "亚马逊文案图/SECONDARY-01.png",
  "native_dimensions": [1600, 1600],
  "export_dimensions": [2000, 2000],
  "placement_dimensions": [2000, 2000],
  "upscaled": true,
  "scale_factor": 1.25,
  "resampling": "single-pass Lanczos3",
  "detail_limit": "插值放大；原生细节上限为 1600×1600。",
  "copy_applied": true,
  "visual_qa": "PASS"
}
```

PNG/JPEG原图允许原格式；校验器用Pillow完整验证/解码，不重编码。缺依赖或损坏文件明确报错，不凭文件头PASS。文案母版必须PNG。with_copy_sha256或output_sha256至少一个记录实际成品字节，两者同时存在均核验；reviewed_sha256绑定真实目视检查过的成品。不能仅计算哈希就填visual_qa=PASS。

scale_factor为照片放置/源尺寸，独立留白可能与画布倍率不同；placement_dimensions可核验实际缩放，不由画布比猜测。visual_qa为PASS/REVISION_NEEDED/REJECTED/PENDING；拒收或试稿不因复制晋级。

返回selected_subset与task_scope分别说明本次子集和全部批准范围。没有expected_asset_ids时task_scope=UNVERIFIED，缺旧输出/QA哈希时保留limits；可能为PASS_WITH_LIMITS/PARTIAL而非完整PASS。selected_subset通过但全套缺图仍PARTIAL。校验器只证明文件契约，不代替产品视觉或平台规则验收。

运行 `python scripts/validate_export.py --manifest <path>`：配对覆盖率 100%、原图哈希一致率 100%、缺失/越界/伪尺寸为 0 才可通过。视觉验收单独进行，脚本不证明产品真实性。图像生成失败或原图缺失时交付 PARTIAL 与缺口，不从旧小图伪造原图。

## 示例与反例

示例：7 张方图、6 张横图 → 两个主文件夹各 13 张；主图在两套中均无营销文案；无文案文件原样复制；文案母版无损保存；最终给出两个绝对路径和分辨率列表。

反例：仅将旧 JPG 另存 PNG → 压缩损失未恢复，拒绝作为原图。把 1200px 放大到 3000px 称“原生 3K” → 标注错误，必须修正。缺任一对应图或图上文字截断 → 不得标 COMPLETE。

失败案例须先定位到原图、重采样、编码、覆盖或字形层，再在项目中修正；稳定的通用失败回填匿名 eval，产品专属事实不得进入 Skill。
