# 内容生产端执行台账

> 建立日期：2026-07-08
> 关联资料库：`docs/research/08-data-flywheel-strategy.md`、`docs/research/09-video-ecosystem-research.md`、`docs/ledgers/05-content-publishing-feedback.md`、`docs/ledgers/08-video-generation-volcano.md`
> 当前判断：内容生产端是产品闭环缺口。没有可审稿、可配图/可渲染、可发布、可回收指标的内容资产，账号定位、热点、发布、复盘都只能停在“看起来智能”的半闭环。
> **2026-07-10 所有权更新：Hermes 是唯一 Agent 主运行时；本台账早期写在 `engine/agent_core` 的工单、Skill 白名单和资产写入属于旧桌面兼容实现。新默认所有权已进入 `runtime/hermes-agent/marketing_os/domains` 与 Hermes 原生 tool registry，旧模块冻结，不再扩功能。**

## 一、产品分层

内容生产端从今天起按三种主交付形态执行，不再把“视频生成”当成唯一内容生产入口。注意：这三条 lane 不是三条互相隔离的烟囱，而是共享同一组生产能力。

| Lane | 产品形态 | 第一目标 | 采用地基 | 当前状态 |
|---|---|---|---|---|
| `article_soft` | 知乎 / 微信公众号软文 | 最快形成可审稿、可发布的长文资产 | Firecrawl 公开证据、平台矩阵、content_assets；必要时调用授权图库/生图补封面和插图 | 🟡 Hermes 原生工单 checkpoint + 草稿资产已接入；真实父稿质量待验 |
| `faceless_video` | 网上找授权素材，拼接合成的不露脸视频 | 用低成本素材视频闭合“脚本→素材→EDL→渲染→发布” | 授权图库/搜索、Hermes Web/Skill/代码工具、content_assets；缺关键镜头时调用生图/生视频补齐 | 🟡 Hermes 原生工单 checkpoint + 视频草稿资产已接入；素材/剪辑执行待迁移 |
| `premium_human_video` | 真人数字人 / AI 人高质量视频 | 高质量视频项目，先样片和预算，再正片 | 独立影像预演 Agent、Seedream/Seedance、共享剪辑引擎；复用证据研究/授权素材做参考或 B-roll | 🟡 Hermes 原生工单 checkpoint 已接入；影像 provider/poller/renderer 仍独立待做 |

## 二、共享能力池，而不是三条烟囱

真实产品体验应该是“用户要一个结果，Agent 自己组织能力”，不是让用户先判断该走哪条死管道。因此内容生产底层按共享能力池建模：

| 能力 | 作用 | 软文 | 不露脸视频 | 高级视频 | 当前成熟度 |
|---|---|---:|---:|---:|---|
| 账号/受众上下文 | 读取账号生命周期、定位、粉丝画像、历史偏好；无账号时自然对话补齐目标用户 | 必需 | 必需 | 必需 | ✅ ready |
| 证据/趋势研究 | Firecrawl、热点缓存、资料库，生成可回链证据 | 必需 | 必需 | 可选 | ✅ ready |
| 文案/脚本写作 | 父稿、平台变体、旁白、镜头清单、CTA | 必需 | 必需 | 必需 | 🟡 partial |
| 授权素材检索 | 找图片、视频、音效、引用材料并保存 license/source/hash | 可选 | 必需 | 可选 | 🟡 partial |
| 代码生成视觉素材 | 用 Remotion / HyperFrames / Canvas / SVG / Lottie 生成数据图、流程图、UI 演示、动效字幕和信息包装素材，并保存源码/参数/hash | 可选 | 可选/常用 | 可选 | 🟡 partial |
| 生图/封面补齐 | 封面、插图、分镜参考图、素材缺口图 | 可选 | 可选 | 必需 | ⏳ planned |
| 生视频/缺口镜头 | 只生成缺口镜头或高级视频镜头，不整条无脑烧钱 | - | 可选 | 必需 | ⏳ planned |
| 配音/音乐/音效 | TTS、BGM、SFX，与 EDL 时间轴绑定 | - | 可选 | 可选 | ⏳ planned |
| EDL/渲染 | 时间线、字幕、素材、渲染 mp4 | - | 必需 | 必需 | 🟡 partial |
| 评分/盲预测/学习 | 发布前评分和不可变预测，发布后校准策略 | 必需 | 必需 | 必需 | ✅ ready |
| 发布/回执/指标回收 | 发布审批、回执、指标 checkpoint 和复盘 | 可选 | 可选 | 可选 | 🟡 partial |

关键规则：

1. `content_assets` 是唯一交付真相源，脚本、文章、图片、素材、EDL、回执都挂到这里。
2. 软文可以调用授权图库或生图补封面/插图，但必须记录来源或生成参数。
3. 不露脸视频优先授权素材；缺关键镜头才调用生图/生视频补齐，不整条烧钱。
4. 代码生成视觉素材是第三类素材源，适合数据、流程、UI、字幕动效和抽象概念；不能用大字卡片糊弄成片，必须有镜头运动、节奏和可复用模板。
5. 代码生成素材必须保留 `source_code/template_id/props/output_path/sha256/render_engine`，作为可复现资产进入 EDL；它不需要外部版权 license，但要标记为 internal/generated。
6. 高级视频可复用证据研究和授权素材做参考/B-roll，但正片生成必须走成本和权利审批。
7. 完整草稿不进入长期记忆；长期记忆只沉淀偏好、账号 DNA、成功流程和失败恢复方式。

当前代码所有权：`runtime/hermes-agent/marketing_os/domains/content_production.py` 负责共享能力池和三条 lane；`content_assets.py` 负责账号级生产 checkpoint 与草稿真相。`engine/agent_core/content_production.py` 仅保留旧桌面兼容，不再接新能力。

## 三、纯素材合成视频管线收口（2026-07-09）

本轮重新确认：`faceless_video` 不应该被继续叫成泛泛的“视频生成”。这条 lane 的核心瓶颈只有两个：

1. **素材**：从哪里找、是否贴题、是否可商用、是否能被证明。
2. **剪辑**：如何把脚本、素材、配音和字幕变成可审片的时间线。

因此后续产品和代码都按“双引擎 + 补充素材源”收口：

```mermaid
flowchart LR
  A["选题/账号定位/热点证据"] --> B["脚本与镜头拆分"]
  B --> C["素材引擎 Material Engine"]
  C --> D["素材入库 MaterialAsset"]
  D --> E["剪辑引擎 Editing Engine"]
  E --> F["EDL/Remotion/HyperFrames/FFmpeg"]
  F --> G["内容资产 content_assets"]
  G --> H["审片/替换素材/发布/复盘"]
```

> 2026-07-09 追加决策：剪辑引擎不再区分“纯素材剪辑”和“AI 生视频剪辑”。两条视频 lane 共享 `engine/video_core/editing_engine.py`：先产时间线骨架，再把授权素材、用户素材、代码生成视觉素材、Seedance 生成镜头统一填入 EDL。素材来源不同，剪辑协议只有一套。

### 3.1 工具归位

| 工具/能力 | 归属 | 作用 | 产品纪律 |
|---|---|---|---|
| Agent Reach | 素材发现 | 扩展网络搜索、找候选材料/参考项目/公开内容线索 | 只能产出候选，不直接入库为可用素材 |
| OpenCLI | 素材发现 / 自动化检索 | 调外部 CLI/网页/搜索流程，补 Agent 自己够不到的信息 | 必须隔离执行，避免像历史测试一样触发不可控集成路径 |
| NotebookLM skill | 素材理解 / 资料总结 | 对长资料、网页、文档、视频转写做摘要和结构化拆解 | 结果要保留来源，不把总结当一手事实 |
| ListenHub | 素材发现 / 舆情线索 | 找讨论热点、观点、音频/播客/信息源线索 | 进入证据包，不直接进入视频素材 |
| humanizer-zh | 文案润色 | 去 AI 味、口语化、短视频话术压缩 | 只改表达，不改事实 |
| baoyou skill | 文案润色 / 创作辅助 | 做更像人的标题、开场、转折、评论区话术 | 产出要过证据守门和账号调性守门 |
| Remotion | 剪辑/渲染/代码生成视觉 | React/TS 组件化生成视频、字幕、动态图表、UI 演示 | 不是素材搜索器；它吃素材和 props，负责时间线/模板化渲染 |
| HyperFrames | 剪辑/动态包装/代码生成视觉 | 用 HTML/CSS/JS/参数生成短视频动效、字幕、图表和信息包装 | 适合快速把 Agent 的剪辑意图变成可渲染镜头 |
| FFmpeg | 最终合成/转码 | concat、混音、字幕、转码、抽帧、探测时长 | 保留 command/receipt，保证可复现 |

### 3.2 三类素材源

| 素材源 | 适合内容 | 示例 | 入库要求 |
|---|---|---|---|
| 授权素材 | 真实世界画面、空镜、人物、办公室、城市、产品、环境音、BGM | Pexels / Pixabay / Freesound / 用户上传 | `provider/source_url/author/license/local_path/sha256/duration/resolution` |
| 代码生成素材 | 信息表达、流程、数据、UI、字幕动效、账号画像、增长曲线 | Remotion / HyperFrames / Canvas / SVG / Lottie | `render_engine/template_id/source_code/props/output_path/sha256/duration/resolution` |
| 生成式素材 | 素材库找不到的关键镜头、插画、封面、概念画面、缺口视频 | Seedream / Seedance / 其他 provider | `provider/model/prompt/seed/request_id/output_path/sha256/cost/license_policy` |

代码生成素材是正式素材源，不是临时补丁。它尤其适合营销、AI 工具、数据复盘、账号增长、工作流教程类内容，因为这些画面本来就不是“拍出来”的，而是“解释出来”的。

### 3.3 MaterialAsset 最小模型

后续素材入库统一使用 `MaterialAsset` 思路，不允许工具直接把搜索结果塞进 EDL：

```json
{
  "id": "mat_xxx",
  "kind": "video|image|audio|code_visual|generated_video|generated_image",
  "source_type": "licensed|code_generated|model_generated|user_supplied",
  "provider": "pexels|pixabay|freesound|remotion|hyperframes|seedance|user",
  "local_path": "runtime/materials/...",
  "source_url": "",
  "author": "",
  "license": "",
  "sha256": "",
  "duration_sec": 0,
  "resolution": "1080x1920",
  "tags": [],
  "fit_scores": {
    "semantic": 0,
    "visual": 0,
    "platform": 0,
    "license": 0,
    "account_tone": 0
  },
  "receipt": {}
}
```

### 3.4 判断素材是否有用

素材不是搜到就能用。`MaterialRanker` 至少按以下维度打分：

1. 是否贴合镜头意图，而不是只命中关键词。
2. 是否能商用、能追溯来源、能保存 hash。
3. 横竖屏、分辨率、时长、可裁切空间是否合适。
4. 是否有水印、平台 logo、低清、乱码、强版权主体。
5. 是否符合账号定位、受众、情绪和平台风格。
6. 是否重复、廉价、像素材库味。
7. 是否能和前后镜头剪在一起，不突兀。

### 3.5 下一步代码收口

后续开发不再继续堆“生成一个视频”的临时脚本，而是按以下模块收口：

| 模块 | 职责 | 首批落点 |
|---|---|---|
| `MaterialAsset` | 素材资产协议、receipt、hash、license、标签、评分 | `engine/agent_core/material_asset.py` |
| `MaterialBroker` | 多源搜索/下载/缓存/入库 provider 层 | `engine/agent_core/material_broker.py` |
| `MaterialRanker` | 根据镜头意图、账号 DNA、版权和平台打分 | `engine/agent_core/material_ranker.py` |
| `CodeVisualProvider` | Remotion/HyperFrames/Canvas/SVG/Lottie 生成动态视觉素材 | `engine/agent_core/code_visual_provider.py` |
| `EditingPlan` | 把脚本、素材和配音组织成可渲染 EDL v2 | `engine/agent_core/editing_plan.py` |
| `SharedEditingEngine` | `faceless_video` 与 `premium_human_video` 共用的 EDL 骨架、素材填坑、审片交接摘要 | `engine/video_core/editing_engine.py` |
| `ContentSkillRegistry` | 将 Hermes 现有内容/视频/编剧/视觉 skill 以白名单方式挂到三条内容 lane | `engine/agent_core/content_skill_registry.py` |

验收口径：同一条不露脸视频可以混用授权素材、代码生成素材、TTS、BGM/SFX，并且每个镜头都能追溯素材来源、替换素材、重算时长、重新渲染。

## 四、Claude 框架复核结论

Claude 写的 `engine/video_core` / `engine/video_agents` 不是废物，但它只覆盖第三条高级视频 lane：

- ✅ 有价值：`schema.py`、`edl.py`、`project_store.py`、`cost.py`、`hooks.py`、`testing.py` 已经形成“视频项目画布 + 预算 + 测试 harness”的工程地基。
- ⚠️ 未完成：`VolcengineAdapter`、`TaskPoller`、`Renderer` 均为 TODO；8 个角色 `SKILL.md` 只有职责骨架，不能宣称可生成成片。
- ✅ 正确定位：高级视频引擎应继续解耦为独立项目合同；Marketing OS 主链只消费它的项目 ID、样片、预算、成片 receipt 和反馈定位结果。
- ❌ 不能再犯的错误：不能因为视频引擎看起来宏大，就把软文和不露脸素材视频都堵在它后面。

## 五、本轮已落地（2026-07-08）

| ID | 任务 | 代码路径 | 完成证据 | 状态 |
|---|---|---|---|---|
| CPF-01 | 三类内容生产工单协议 | `engine/agent_core/content_production.py` | 确定性输出 lane、步骤、工具序列、质量门、版权门、成本门、降级方案 | ✅ code |
| CPF-01A | 共享能力池架构 | `engine/agent_core/content_production.py` | 三条 lane 共享 `audience_context/evidence_research/copywriting/stock_material/generated_image/generated_video/edl_render/review_learning/publish_feedback`，软文和视频可互相借能力 | ✅ code |
| CPF-02 | Agent 工具接入 | `engine/agent_core/tool_manifest.py`、`engine/agent_core/hermes_adapter.py` | 新增 `marketing_plan_content_production`；内容生产请求初始计划第一步生成工单 | ✅ code |
| CPF-03 | 后端只读 API | `engine/marketing-os/server.py`、`electron/main.js` | `POST /api/plugins/marketing-os/content/production/plan` 返回工单；Electron allowlist 已放行；不写库、不下载、不烧钱 | ✅ code |
| CPF-04 | 内容工厂入口 | `src/pages/Creator.tsx`、`src/api/client.ts` | 顶部入口分为“写软文 / 不露脸视频 / 数字人视频”；点击进入新对话并要求先生成工单 | ✅ code |
| CPF-05 | 回归守卫 | `tests/test_content_production.py` | 覆盖软文、不露脸视频、高级视频 provider blocked、工具只读注册、初始计划路由、共享能力池不是三条烟囱 | ✅ automated |
| CPF-06 | 软文真实生产链 v1 | `engine/agent_core/article_soft_production.py`、`engine/marketing-os/server.py`、`engine/agent_core/tool_manifest.py`、`src/api/client.ts`、`src/pages/Creator.tsx` | 新增 `marketing_draft_soft_article_create`：生成并保存父稿、知乎/公众号变体、证据状态、配图需求、评分和发布前预测；证据缺 URL 时标记 `needs_evidence`，不伪造可发布状态 | ✅ code |
| CPF-07 | 不露脸素材视频链 v1 | `engine/agent_core/faceless_video_production.py`、`engine/marketing-os/server.py`、`engine/agent_core/tool_manifest.py`、`src/api/client.ts`、`src/pages/Creator.tsx` | 新增 `marketing_draft_faceless_video_create`：生成并保存旁白脚本、镜头清单、素材检索包、授权字段要求、缺口生成请求、EDL 草案、评分和发布前预测；`render_status=not_rendered`，不注册假附件、不冒充成片 | ✅ code |
| CPF-08A | Faceless renderer 命令层 | `engine/video_core/renderer.py`、`engine/agent_core/faceless_video_production.py`、`engine/marketing-os/server.py`、`src/api/client.ts` | `Renderer` 支持 final/animatic ffmpeg 命令生成和执行入口；新增 `marketing_prepare_faceless_render` 只读检查，素材/EDL clips 不齐返回 blocked，齐了只返回命令，不执行渲染 | ✅ code；真实执行器待素材接入 |
| CPF-08B | Faceless 本地文字分镜样片 | `engine/agent_core/faceless_video_production.py`、`engine/video_core/renderer.py`、`engine/marketing-os/server.py`、`src/api/client.ts` | 新增 `render_faceless_animatic` / `/faceless-render/animatic`：用 Python 标准库生成 PNG 分镜卡，再用 ffmpeg 合成本地 mp4，并写回 asset `render_status=animatic_rendered`；该结果标记为样片，不冒充最终素材视频 | ✅ code |
| CPF-08C | 授权图片素材填坑 | `engine/agent_core/faceless_video_production.py`、`engine/marketing-os/server.py`、`src/api/client.ts`、`electron/main.js` | 新增 `fill_faceless_image_materials` / `/faceless-render/fill-image-materials`：接收已授权本地图片，校验 Pexels/user_supplied provenance 和 sha256，转为 `project_dir/videos/{shot_id}.mp4`，回写 EDL clips、licensed_assets、shot 状态与版权门 | ✅ code |
| CPF-08D | Faceless 本地粗剪 mp4 | `engine/agent_core/faceless_video_production.py`、`engine/video_core/renderer.py`、`engine/marketing-os/server.py`、`src/api/client.ts` | 新增 `render_faceless_final` / `/faceless-render/final`：只使用已填 EDL clips 和本地素材片段输出 rough cut mp4；不冒充最终发布成片 | ✅ code |
| CPF-08E | 字幕 sidecar + 配音/BGM 混音 | `engine/agent_core/faceless_video_production.py`、`engine/video_core/renderer.py`、`src/api/client.ts`、`tests/test_content_production.py` | `render_faceless_final` 默认导出 SRT 字幕；可接用户/素材库配音与 BGM，本地 ffmpeg 混音输出 AAC，并把 audio_tracks、subtitle_path、command、sha256/license/source_url 写回 receipt；仍标记为 review cut，需人工审片 | ✅ code |
| CPF-08F-a | IndexTTS2 本地运行时评估 | `runtime/index-tts`（git ignored）、`scripts/bootstrap-index-tts2.sh`、`engine/agent_core/local_tts_provider.py`、`src/api/client.ts` | 主模型约 5.5G，完整辅助依赖还需约 4G+；Intel Mac 还需 torch 降级兼容。结论：不适合作为 C 端默认能力，仅保留为高级本地包/私有化候选。2026-07-08 已删除本地 `runtime/index-tts` 下载包，释放约 12G | ⚪ optional / not default |
| CPF-08F-b | 火山 V1 TTS 冒烟验证 | `runtime/tts-smoke/volcengine_v1_smoke_1783508050.mp3` | 新版 `x-api-key` 调 `https://openspeech.bytedance.com/api/v1/tts` 成功；HTTP 200，code=3000，返回 mp3，约 5.3s / 24kHz / mono / 160kbps。适合作为 C 端默认云端配音闭环候选；密钥不得入库 | ✅ smoke |
| CPF-08F-c | 火山 TTS Provider 产品边界 | `engine/agent_core/volcengine_tts_provider.py`、`engine/marketing-os/server.py`、`electron/main.js`、`src/api/client.ts`、`tests/test_volcengine_tts_provider.py` | 新增 `volcengine_tts_v1`：文本→mp3→sha256/duration/provider receipt；API Key 只从参数/环境进入，不写 receipt；新增 `/tts/volcengine/v1/synthesize` 本地 API 和 Electron allowlist | ✅ code |
| CPF-08F-d | 不露脸视频 + 火山配音端到端 | `runtime/e2e/volcengine_tts_1783508985/final/02_review_cut_with_volcengine_voice.mp4` | 模拟真实用户：创建 6 镜头不露脸视频资产→渲染文字分镜→frame 填坑为视频 clips→火山 TTS 生成 51.672s 旁白→渲染 49s 审片版 mp4；ffprobe 确认 h264 video + aac audio + SRT sidecar | ✅ e2e；⚠️ 需做音画时长对齐 |
| CPF-08G-a | 内容生产入口统一预演门 | `engine/agent_core/content_lane_gate.py`、`engine/agent_core/article_soft_production.py`、`engine/agent_core/faceless_video_production.py`、`tests/test_content_production.py` | 软文和不露脸视频创建资产前强制运行 `PreflightDecision`；通过才写评分/盲预测；不通过只保存阻断草稿并写入 `content.preflight_gate` / `质量门: 总预演门`。高阶视频仍委派独立片子预演 Agent | ✅ code |
| CPF-08H-a | 纯素材视频双引擎收口 | `docs/ledgers/14-content-production-factory.md` | 明确 `faceless_video` 后续按“素材引擎 + 剪辑引擎 + 代码生成素材补充”执行；把 Agent Reach/OpenCLI/NotebookLM/ListenHub/humanizer-zh/baoyou/Remotion/HyperFrames 全部归位 | ✅ ledger |
| CPF-08J-a | 共享剪辑引擎 v1 | `engine/video_core/editing_engine.py`、`engine/agent_core/faceless_video_production.py`、`tests/test_video_core_schema.py` | 新增共享 EditingEngine：脚本/镜头段落→EDL 骨架；素材引用→EDL clips；EDL→审片交接摘要。`faceless_video` 的 EDL 草案已改为走共享引擎，后续 `premium_human_video` 直接复用同一协议 | ✅ code |
| CPF-08S-a | 内容生产 skill 白名单 | `engine/agent_core/content_skill_registry.py`、`engine/agent_core/content_production.py`、`tests/test_content_production.py` | 将 Hermes 已有 `content-creation`、`video-production`、`screenwriting`、`creative/humanizer`、`baoyu-infographic`、`manim/p5js` 等 skill 显式映射到三条 lane；生产工单返回 `recommended_skills`，避免 Agent 随机翻 skill 目录 | ✅ code |
| CPF-13-a | 图文平台 Stylebook v1 | `engine/agent_core/platform_stylebook.py`、`engine/agent_core/article_soft_production.py`、`tests/test_content_production.py` | 公众号/知乎软文资产新增平台级编辑规范：区分 hard rules 与 best practices，输出封面比例/安全区、字体字号/行距建议、结构规范、审稿清单和平台发布包；知乎字体标记为平台编辑器控制，避免伪造可控字体 | ✅ code |

验证：

- `.venv/bin/python -m pytest tests/test_content_production.py -q` → 15 passed
- `.venv/bin/python -m pytest tests/test_content_production.py tests/test_video_core_schema.py -q` → 39 passed（字幕 sidecar、配音/BGM 混音、renderer 音轨命令）
- `.venv/bin/python -m pytest tests/test_content_production.py tests/test_product_closure_guard.py -q` → 25 passed（授权图片填坑、本地粗剪输出、前端/主进程 allowlist）
- `.venv/bin/python -m pytest tests/test_content_production.py tests/test_run_12_13_14.py tests/test_product_closure_guard.py -q` → 44 passed（软文真实生产链、不露脸素材视频链、工具快照、前端/主进程 allowlist）
- `.venv/bin/python -m pytest tests/test_content_production.py tests/test_run_12_13_14.py tests/test_product_closure_guard.py tests/test_video_core_schema.py tests/test_video_core_boundary.py -q` → 71 passed（加入 renderer 命令层、渲染准备检查、音轨混合命令）
- `.venv/bin/python -m pytest tests/test_account_lifecycle.py tests/test_benchmark_discovery.py tests/test_run21_benchmark_coldstart.py tests/test_run23_audience_persona.py -q` → 62 passed
- `.venv/bin/python -m pytest tests/test_content_production.py tests/test_firecrawl_provider.py tests/test_stock_images.py tests/test_upgrade_content_matrix.py tests/test_run17_content_scoring.py tests/test_run18_blind_prediction.py tests/test_run19_retro_reconciliation.py tests/test_run20_rubric_bump.py tests/test_run22_cadence_buffer.py -q` → 156 passed
- `.venv/bin/python -m pytest tests/test_video_core_boundary.py tests/test_video_core_schema.py tests/test_desk_06_supply_chain.py tests/test_secret_scanner.py tests/test_product_closure_guard.py -q` → 83 passed
- `.venv/bin/python -m pytest tests/test_content_production.py tests/test_run_12_13_14.py tests/test_product_closure_guard.py tests/test_server.py tests/test_e2e_01_internal_chain.py tests/test_media_attachments.py tests/test_firecrawl_provider.py tests/test_stock_images.py tests/test_video_core_boundary.py tests/test_video_core_schema.py tests/test_desk_06_supply_chain.py tests/test_secret_scanner.py -q` → 231 passed, 1 warning（内容生产主链 + 服务/素材/视频核心/安全回归）
- `.venv/bin/python -m pytest tests/test_local_tts_provider.py tests/test_product_closure_guard.py tests/test_content_production.py tests/test_video_core_schema.py -q` → 54 passed（IndexTTS2 状态/命令构建、内容工厂和视频 schema 回归）
- `.venv/bin/python -m pytest tests/test_volcengine_tts_provider.py tests/test_content_production.py tests/test_product_closure_guard.py -q` → 30 passed（火山 TTS provider、内容生产、Electron allowlist 回归）
- `npx tsc --noEmit` → passed
- `node --check electron/main.js && node --check electron/preload.js && .venv/bin/python -m py_compile engine/agent_core/volcengine_tts_provider.py engine/agent_core/faceless_video_production.py engine/marketing-os/server.py` → passed
- `.venv/bin/python -m pytest tests/test_content_production.py tests/test_production_preflight.py tests/test_preflight_decision.py -q` → 27 passed（内容生产入口统一预演门）
- `.venv/bin/python -m pytest -q` → 1272 passed, 1 warning（全量回归）

## 五-A、2026-07-10 Hermes 原生内容纵切

| ID | 落地 | 代码事实 | 证据等级 |
|---|---|---|---|
| CPF-NATIVE-01 | 原生共享能力池 | `ContentProductionPolicy` 直接运行在 Hermes 源码内，三条 lane 共享账号、证据、文案、授权素材、生成视觉、音频和剪辑能力；只引用当前实际存在的 Hermes 工具/Skill，不再宣称不存在的 Skill 已安装 | automated |
| CPF-NATIVE-02 | 持久生产 checkpoint | `content_production_plans` 绑定 `user_id + account_id + kind + platforms`；相同目标得到稳定 `plan_id`，跨重启可恢复 | automated |
| CPF-NATIVE-03 | 草稿强制走工单 | `marketing_draft_content_create` 不接受 `account_id`；必须携带当前账号真实 `plan_id`，管线或平台不匹配直接拒绝 | automated |
| CPF-NATIVE-04 | 内容资产可恢复 | `marketing_read_content_assets` 只读取当前 Hermes session 绑定账号；完整草稿进入 `content_assets`，不进入长期记忆 | automated |
| CPF-NATIVE-05 | 原生工具链 | `marketing_plan_content_production / marketing_read_evidence_pack / marketing_read_content_assets / marketing_draft_article_create / marketing_draft_content_create` 进入 Hermes `marketing` toolset，并默认覆盖桌面、消息渠道与 cron surface | automated |
| CPF-NATIVE-06 | 原生证据捕获 | Hermes `model_tools` 在真实 `web_extract` handler 返回后按当前 SessionDB 账号自动固化 `evidence_records`；模型没有 create-evidence 工具 | automated |
| CPF-NATIVE-07 | 原文指纹与摘要边界 | `web_extract` 对预摘要原始抓取内容计算 SHA-256，并显式返回 `content_origin`；EvidencePack 区分 source integrity 与 claim truth | automated |
| CPF-NATIVE-08 | 证据引用强校验 | 计划和草稿只接受当前账号真实 verified `evidence_id`；原始 URL、`source:` 字符串、跨账号引用、失败或空抓取被拒绝 | automated |
| CPF-NATIVE-09 | ArticleBundle | 父稿、知乎/公众号变体、EvidencePack、视觉需求、stylebook、验证与未校准声明作为同一可恢复内容资产持久化 | automated |
| CPF-NATIVE-10 | 平台差异质量门 | 父稿长度/章节/引用与平台变体缺失、短稿、复制父稿、版本近似均进入确定性 validation；不达标保存为 `needs_revision`，不冒充可审稿 | automated |
| CPF-NATIVE-11 | 关闭通用绕过 | `marketing_draft_content_create` 拒绝 `article_soft`；文章必须经 `marketing_draft_article_create`，模型不能用任意 JSON 绕过父稿/证据/平台门 | automated |
| CPF-NATIVE-12 | 主张级证据守门 | `marketing.article_validation.v2` 对父稿和平台稿逐段检查高风险归因、泛化和数量主张；要求同段 `evidence_id`，并要求数量词能在被引证据摘要中找到。通过只代表引用邻近性与数字 token 支持，明确保持 `claim_truth_verified=false` | automated + real provider E2E |
| CPF-NATIVE-13 | 不可变修订链 | `marketing_draft_article_create(revision_of=...)` 在同账号、同工单范围生成下一版本；父版本转为 `superseded`，默认列表只返回当前版本，历史仍可追溯 | automated + real provider E2E |

边界：当前完成的是“工单 → 真实来源捕获 → 草稿资产”的原生状态所有权，不等于真实软文质量、主张级多源核验、素材下载、视频渲染、发布或指标回收已完成。EvidencePack 的 `verified/source_integrity` 只证明真实 collector、来源、时间与内容哈希完整，不把页面中的每句话宣布为客观事实。

真实验收：Hermes 原生 Agent 在真实账号作用域内读取 1 条 UNESCO EvidencePack 后生成 v2 初稿。旧结构门曾把包含虚构比例和时间区间的稿件误判为可审稿；v2 质量门上线后自动降级，并由同一 Agent 生成 v3、v4 修订链。当前 v4 为 `ready_for_human_review`，`uncited_findings=0`、`numeric_mismatch_findings=0`；语义真值、账号调性、视觉版权与敏感政策检查仍列为人工项。

验证：Hermes 产品/SessionDB/Gateway/账号/内容组合回归 624 项通过；原生 EvidencePack + ArticleBundle 定向用例已扩展到主张守门、旧资产迁移和不可变修订；ModelTools/Web/异步桥/浏览器组合 124 项通过；Web 抽取、站点策略、秘密阻断与证据哈希组合 57 项通过；Ruff 与 py_compile 通过。以上测试存在集合重叠，不以相加数字冒充独立用例数。

## 六、下一步执行清单

| ID | 任务 | 具体执行 | 完成口径 | 状态 |
|---|---|---|---|---|
| CPF-06 | 软文真实生产链 | Agent 根据工单读取定位/证据→写父稿→拆知乎/公众号版本→按需找图/生图→保存资产→评分/盲预测 | 生成 1 篇可审稿长文资产，content_assets 有正文、证据、平台变体、配图需求/来源和预测 | ✅ code；待真人审稿 |
| CPF-07 | 不露脸视频素材链 | 生成脚本/镜头清单/素材关键词；接 Pexels 图片 + 后续 Pixabay/Pexels 视频/Freesound；缺口镜头写入 generated_asset_requests；保存授权凭证 | 一个视频资产含脚本、shot list、licensed asset requirements、generated_asset_requests、EDL 草案 | ✅ code；待接真实素材/渲染 |
| CPF-08 | Faceless renderer | 先用 FFmpeg 写实图文/素材拼接渲染；不依赖付费视频模型 | 本地生成一个可播放 mp4，命令/素材/许可证可追溯 | ✅ 文字分镜样片、授权图片填坑、本地粗剪、SRT 字幕、用户/素材库音轨混音已完成；待 TTS/真实下载器/审片 UI |
| CPF-08C | 授权素材填坑 | 把 Pexels 图片/后续视频源或用户上传素材填入 EDL clips，生成可追溯素材映射 | EDL clips 不为空；每个 clip 有 source_url/license/hash 或 user_supplied provenance | ✅ code |
| CPF-08D | 本地粗剪输出 | 基于已填 EDL clips 执行 FFmpeg concat，输出 rough cut mp4 并写回 asset receipt | 存在可播放 mp4，asset render_outputs 记录 command/path/duration，且标明非最终成片 | ✅ code |
| CPF-08E | 字幕/配音/BGM | 为 rough cut 增加可控字幕、用户/素材库配音、BGM 混音和审计 receipts | 输出接近可发布版本；字幕/音轨/版权来源可追溯 | ✅ code；火山 TTS 已接入，待审片 UI |
| CPF-08F | TTS/素材下载器接入 | 将火山 TTS/voice-clone、可选 IndexTTS2 本地包、Pexels/Pixabay/Freesound 下载结果转为本地授权素材，并复用 CPF-08C/E 渲染口 | C 端默认走云端轻量 TTS；IndexTTS2 不自动下载；下载/生成 receipt 完整、可删除、可复现 | ✅ 火山 TTS 已接入并 E2E；待音画时长对齐和 voice clone |
| CPF-08G | 音画时长对齐 | TTS 后用真实音频时长回写 EDL：自动调整 slot duration、或轻微 speech_rate 重试、或延长尾帧；禁止静默截断旁白 | 火山旁白时长与视频时长误差 < 300ms；超出时返回需要调整而不是直接截断 | ⏳ next |
| CPF-08H | 代码生成视觉素材 | 把 Remotion / HyperFrames / Canvas / SVG / Lottie 作为 `code_generated_visual` provider：输入镜头意图和数据，输出可复现视觉 clip，并写入 `source_code/template_id/props/output_path/sha256/render_engine` | 一条不露脸视频可混用授权视频、授权图片、代码生成动效和 TTS；EDL 能按镜头引用代码生成素材；审片时可替换/重渲染 | ⏳ next |
| CPF-08I | 素材资产与素材代理 | 新增 `MaterialAsset / MaterialBroker / MaterialRanker`，统一授权素材、代码生成素材、生成式素材的入库、打分和追溯 | 每个素材都能查来源、license/hash、适配分、镜头引用和替换记录；搜索结果不能绕过入库直接进 EDL | ⏳ next |
| CPF-08J | 剪辑计划与 EDL v2 | 把脚本、素材、配音、字幕、BGM/SFX、动效模板组织成 EditingPlan，再转 EDL/Remotion/HyperFrames 渲染；`editing_engine.py` 已先落共用 EDL 骨架和素材填坑函数 | 同一脚本可重排素材、替换模板、重算时长，并生成可审片 MP4 | 🟡 partial |
| CPF-09 | 高级视频 provider 校准 | 用真实 API Key 校准 Volcengine/Seedance 字段、价格、超时、错误语义 | 一条真实样片 + 台账记录字段和价格，不再 TODO | ⏳ |
| CPF-10 | 生产数据飞轮 | 保存 prompt、素材选择、用户采纳/拒绝、发布预测、真实指标和复盘结论 | 下一次生产能读取同账号最佳结构/禁忌/失败恢复 | ⏳ |

## 七、产品纪律

1. 软文和不露脸视频优先，因为它们能最快闭合“生产→发布→指标→学习”。
2. 三条 lane 共享能力池，不允许 UI 或 Agent 把“写软文”“找素材”“生视频”做成互不相通的三个小工具。
3. 高级视频不伪装：provider 未校准时只能输出项目画布、样片计划、预算和风险。
4. 外部素材必须有来源、作者、license、下载 hash；社交平台视频不能直接盗搬。
5. 代码生成素材必须能复现，不能只保存最终 mp4/png；至少保存模板、参数、输出 hash 和渲染引擎。
6. 完整草稿进入 `content_assets`，长期记忆只沉淀偏好、账号 DNA、规律和可复用流程。
7. 任何内容产出都要经过评分/盲预测，后续指标回收才有学习意义。

## 八、2026-07-09 落地记录：内容资产自动绑定账号实验

状态：`CPF-11 / CORE-LOOP-09 downstream / automated verified`

本轮补齐“实验草案 → 内容生产资产”的后端断点。

### 8.1 本轮改动

- 更新 `engine/agent_core/content_lane_gate.py`
  - 新增 `requested_experiment_context(...)`：内容生产时如果传入 `experiment_id`，先校验 `user_id/account_id/project_id/experiment_id` 是否属于同一账号生命周期。
  - 新增 `attach_experiment_context(...)`：把实验假设、主指标、来源策略候选写入 `content_assets.content.experiment_binding`。
  - 新增 `attach_asset_to_requested_experiment(...)`：资产创建后通过 `AccountLifecycleService.attach_experiment_asset(...)` 挂回实验，并推进实验状态。

- 更新 `engine/agent_core/article_soft_production.py`
  - 软文资产支持 `project_id + experiment_id`。
  - 创建后自动写回 `account_experiments.asset_ids`，实验状态从 `draft` 进入 `running`。

- 更新 `engine/agent_core/faceless_video_production.py`
  - 不露脸素材视频资产支持同样的实验绑定协议。
  - 视频资产不再游离在实验系统之外。

- 更新 `tests/test_content_production.py`
  - 覆盖软文资产绑定账号实验。
  - 覆盖不露脸视频资产绑定账号实验。

### 8.2 产品意义

现在主循环多接上一段：

```text
策略候选 accepted
  → draft account experiment
  → soft article / faceless video content asset
  → experiment running
  → publish receipt
  → retro / learning candidate
```

这让内容生产不再是孤立功能，而是账号长期学习系统的一部分。

### 8.3 当前验证证据

```text
.venv/bin/python -m pytest tests/test_content_production.py::test_soft_article_asset_can_bind_back_to_account_experiment tests/test_content_production.py::test_faceless_video_asset_can_bind_back_to_account_experiment -q
2 passed

.venv/bin/python -m pytest tests/test_content_production.py tests/test_production_preflight.py -q
25 passed

.venv/bin/python -m pytest tests/test_account_lifecycle.py tests/test_content_production.py tests/test_production_preflight.py tests/test_influence_score_governance.py tests/test_server.py::test_weight_candidate_replay_and_decision_endpoints_guard_learning -q
57 passed, 1 warning

.venv/bin/python -m pytest -q
1281 passed, 1 warning
```

## 九、2026-07-09 落地记录：实验驱动内容生产入口

状态：`CPF-12 / experiment-driven production / automated verified`

本轮把“已有账号实验”接到内容生产入口，让 Agent 不再从空白目标凭空创作。

### 9.1 本轮改动

- 新增 `engine/agent_core/experiment_driven_production.py`
  - `build_content_request_from_experiment(...)`
    - 读取 `account_experiments`
    - 读取账号生命周期、approved positioning、受众假设和 DNA 投影
    - 自动生成内容生产请求：`objective/topic/platforms/audience_context/evidence/source`
  - `create_content_from_experiment(...)`
    - `article_soft`：调用现有软文生产链
    - `faceless_video`：调用现有不露脸素材视频链
    - `premium_human_video`：返回 blocked，要求先走独立片子预演 Agent
  - 自动 lane 判断：
    - 显式 `kind` 优先
    - 指定知乎/公众号平台 → 软文
    - 指定抖音/视频号/B站平台 → 不露脸素材视频
    - `attention / retention` 或 `PlatformReachPotential / RetentionDesign` 实验 → 不露脸素材视频
    - 其他默认走低成本软文闭环

- 更新 `engine/marketing-os/server.py`
  - 新增 `POST /api/plugins/marketing-os/content/production/from-experiment`
  - 新增 server action `create_content_from_experiment`

- 更新 `engine/agent_core/tool_manifest.py`
  - 新增 L1 可逆写工具 `marketing_draft_content_from_experiment`
  - 该工具只创建草稿资产并挂回 experiment，不发布、不下载素材、不调用付费视频 API

- 更新 `engine/agent_core/hermes_adapter.py`
  - 用户说“根据实验生产 / 从实验生产 / 继续实验 / experiment_id”时：
    1. 先读 `marketing_read_account_experiments`
    2. 再优先调用 `marketing_draft_content_from_experiment`
  - 避免 Agent 绕开实验重新做普通内容工单。

- 更新 `electron/main.js` / `src/api/client.ts`
  - 预留桌面 API 调用入口，不新增 UI。

### 9.2 产品意义

现在主循环继续接长：

```text
策略候选 accepted
  → draft account experiment
  → marketing_draft_content_from_experiment
  → article_soft / faceless_video content asset
  → experiment running
  → publish receipt
  → retro / learning candidate
```

这一步让“内容生产”真正服从账号长期实验，而不是单次对话里随机写稿。

### 9.3 当前验证证据

```text
.venv/bin/python -m pytest tests/test_content_production.py::test_experiment_driven_production_creates_soft_article_from_lifecycle_context tests/test_content_production.py::test_experiment_driven_production_auto_routes_retention_to_faceless_video tests/test_content_production.py::test_experiment_driven_production_blocks_premium_until_film_preflight tests/test_content_production.py::test_content_production_tool_is_read_only_and_registered tests/test_run_12_13_14.py::test_manifest_snapshot_tool_names tests/test_run_12_13_14.py::test_manifest_snapshot_tool_count tests/test_run_12_13_14.py::test_manifest_snapshot_level_distribution tests/test_run_12_13_14.py::test_manifest_snapshot_gateway_names_by_level tests/test_agent_core.py::test_tool_manifest_all_have_valid_levels tests/test_agent_core.py::test_only_implemented_tools_are_registered tests/test_agent_core.py::test_controlled_tools_count -q
11 passed

.venv/bin/python -m pytest tests/test_content_production.py tests/test_run_12_13_14.py tests/test_agent_core.py::test_tool_manifest_all_have_valid_levels tests/test_agent_core.py::test_only_implemented_tools_are_registered tests/test_agent_core.py::test_controlled_tools_count -q
46 passed

.venv/bin/python -m pytest tests/test_account_lifecycle.py tests/test_content_production.py tests/test_production_preflight.py tests/test_influence_score_governance.py tests/test_server.py::test_weight_candidate_replay_and_decision_endpoints_guard_learning tests/test_product_closure_guard.py tests/test_run_12_13_14.py -q
94 passed, 1 warning

./node_modules/.bin/tsc --noEmit
passed

node --check electron/main.js && node --check electron/preload.js && .venv/bin/python -m py_compile engine/agent_core/experiment_driven_production.py engine/agent_core/content_production.py engine/agent_core/hermes_adapter.py engine/marketing-os/server.py
passed

.venv/bin/python -m pytest -q
1285 passed, 1 warning
```

## 十、2026-07-09 落地记录：图文平台 Stylebook v1

状态：`CPF-13 / article platform stylebook / automated verified`

本轮确认：当前图文生产链已经能生成知乎/公众号父稿、平台变体、证据状态、配图需求和发布前预测，但还不够像“专业运营编辑”。真正的图文生产不能只会写正文，还要知道各平台的封面、正文排版、证据呈现、CTA 和发布前审稿纪律。

### 10.1 本轮改动

- 新增 `engine/agent_core/platform_stylebook.py`
  - `wechat_official` 与 `zhihu` 的平台编辑规范。
  - 明确区分：
    - `hard_rules`：平台/API/合规硬边界。
    - `best_practices`：运营排版经验，不冒充官方规则。
  - 输出 `cover_spec / typography_spec / structure_spec / review_checklist / source_policy`。

- 更新 `engine/agent_core/article_soft_production.py`
  - 每个平台变体新增 `style_profile` 和 `publish_pack`。
  - `content.platform_publish_packs` 作为图文发布/审稿/导出用的结构化平台包。
  - `visual_requirements` 按平台拆分封面需求：
    - 公众号：默认 2.35:1 封面建议，强调安全区和弱营销海报感。
    - 知乎：默认 16:9 文章封面建议；回答场景不强制封面，字体由平台编辑器控制。

- 更新 `tests/test_content_production.py`
  - 覆盖公众号字号/封面比例。
  - 覆盖知乎字体为 `platform_controlled`。
  - 覆盖平台封面需求按 `zhihu / wechat_official` 分开输出。

### 10.2 产品意义

这一步把软文从“能写一篇草稿”推进到“能生成一个可审稿的发布包”：

```text
选题 / 实验
  → 父稿
  → 知乎 / 公众号变体
  → 平台 Stylebook
  → 封面 / 插图需求
  → 审稿清单
  → 发布前预测
```

后续 UI 可以选择完全不暴露这些底层规则，只在用户点击“审稿/发布”时用它们自动检查。这样既专业，又不把底层预演和规则堆到界面上。

### 10.3 当前验证证据

```text
.venv/bin/python -m pytest tests/test_content_production.py::test_soft_article_builder_creates_reviewable_asset_with_variants -q
1 passed

.venv/bin/python -m pytest tests/test_content_production.py tests/test_upgrade_content_matrix.py -q
56 passed
```

## 十一、2026-07-09 产品原则：内容运营是道，平台运营是术

状态：`CPF-14 / content-ops-vs-platform-ops / product architecture principle`

本轮重新划清内容生产端的两个核心分工：

1. **内容运营（道）**
   - 负责内容本身是否值得被看、被信、被转发、被收藏、被转化。
   - 关注人的注意力、人性、信任、情绪、欲望、恐惧、身份认同、群体心理、证据和叙事。
   - 它更接近长期真理，变化慢，但会因国家、族群、性别、年龄、职业、阶层和平台用户结构而有不同底层“思想钢印”。
   - 在系统里对应：账号 DNA、受众画像、内容评分、预演引擎、盲预测、内容复盘、记忆沉淀。

2. **平台运营（术）**
   - 负责同一份内容在不同平台如何表达、如何包装、如何进入分发机制。
   - 关注平台规则、审核边界、推流机制、封面比例、标题长度、发布时间、标签/话题、首屏留存、互动信号、账号权重和冷启动策略。
   - 它变化快，必须版本化、来源化、可回滚，不能写死成永恒规则。
   - 在系统里对应：Platform Stylebook、平台机制画像、平台适配器、发布前平台 fit 检查、发布回执和平台维度复盘。

### 11.1 为什么这件事重要

很多同类产品把这两件事混在一起，最后只会“生成内容”，不会“运营内容”。

真实情况是：

- 好内容投到基因不匹配的平台，可能没有推流。
- 普通内容如果命中平台机制，也可能短期热门。
- 但长期做账号，不能只靠平台术；平台术可以放大，不能替代内容道。
- 最强闭环应该是：内容道决定长期信任，平台术决定当次分发效率，发布回执再反向校准两者权重。

### 11.2 系统分层

```text
用户目标 / 账号 DNA / 受众画像
  → 内容运营层 ContentOps
      - 注意力结构
      - 人性与信任
      - 选题价值
      - 证据与叙事
      - 预演评分
  → 平台运营层 PlatformOps
      - 平台规则
      - 推流机制
      - 版式/封面/标题/标签
      - 审核风险
      - 发布时间与互动设计
  → 内容资产 content_assets
  → 发布 / 回执 / 指标
  → 学习系统分别更新 ContentOps 与 PlatformOps
```

### 11.3 后续代码原则

1. `platform_stylebook.py` 只解决平台编辑规范，不等于完整平台运营。
2. 后续需要新增或扩展 `PlatformOps`：
   - `platform_rules`：官方规则、审核边界、接口限制。
   - `distribution_model`：平台推流机制假设、互动信号、冷启动策略。
   - `format_adapter`：标题、封面、正文结构、标签、CTA。
   - `risk_policy`：违规、低质、硬广、搬运、水印、夸大承诺。
   - `version/source/confidence/checked_at`：平台术必须可追溯、可过期。
3. `ContentOps` 继续放在影响力预演、内容评分、账号 DNA 和学习系统里，不被具体平台绑死。
4. 每次生产内容时，最终分数不应该只有“内容好不好”，而应该拆成：

```text
final_preflight_score
  = content_strength
  × account_audience_fit
  × platform_mechanism_fit
  × timing_fit
  × evidence_trust
  × execution_quality
```

5. 发布后回执要分别校准：
   - 内容运营权重：什么选题、叙事、情绪、证据真的有效。
   - 平台运营权重：什么标题、封面、标签、发布时间、互动设计在该平台有效。

这条原则决定内容生产端不能只继续堆“软文生成/视频生成”，而要逐步变成“内容道 + 平台术 + 数据回执”的双引擎系统。
