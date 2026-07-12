# 开源/第三方视频生成与素材生态调研

> 建立日期：2026-07-03
> 当前任务入口：[`../current/EXECUTION_LEDGER.md`](../current/EXECUTION_LEDGER.md)；高级视频历史方案：[`../deferred/high-end-video-volcengine.md`](../deferred/high-end-video-volcengine.md)。
> 调研目标：评估 MoneyPrinterTurbo、素材 MCP、音效方案、LibTV 技术路径，为视频生成板块补充技术选型依据。

---

## 一、MoneyPrinterTurbo（开源短视频自动生成）

### 1.1 基本信息

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/harry0703/MoneyPrinterTurbo |
| Stars | 95K+ |
| 许可证 | MIT |
| 语言 | Python 98% |
| 最新版本 | v1.3.0 (2026-06-10) |
| 证据等级 | A（源码可直接审查） |

### 1.2 核心能力

- 输入主题/关键词 → 自动生成文案、素材匹配、配音、字幕、背景音乐 → 合成短视频
- MVC 架构，支持 Web UI（Streamlit）和 REST API
- 素材来源：Pexels / Pixabay / Coverr（无版权素材库搜索拼接）
- 合成：MoviePy（FFmpeg 的 Python 封装）
- LLM 接入：OpenAI / DeepSeek / Gemini / Qwen / Ollama 等多模型
- 配音：Edge TTS / Whisper 字幕
- 跨平台发布：TikTok / Instagram / YouTube Shorts（通过 Upload-Post）
- 批量生成 + 选最优

### 1.3 与我们方案的对比

| 维度 | MoneyPrinterTurbo | 我们 |
|---|---|---|
| **素材路线** | 搜索已有无版权素材拼接 | AI 生成全新画面（Seedream + Seedance） |
| **架构** | 单流程管线 | 多 Agent 协同（对标火山剧创） |
| **审批/人工介入** | 无 | plan→approval→effect 全链路 |
| **数据飞轮** | 无 | prompt 效果库 + 爆款归因 + 网感学习 |
| **合成** | MoviePy | FFmpeg（可考虑用 MoviePy 封装） |

### 1.4 可借鉴点

| 点 | 说明 |
|---|---|
| **MoviePy 合成层** | Python 封装 FFmpeg，比裸命令更可维护，MIT 协议无风险 |
| **字幕样式参数化** | 字体/位置/颜色/大小/描边全部参数化 |
| **批量生成 + 选最优** | 子 Agent 重试策略可借鉴 |
| **跨平台发布** | Upload-Post 集成模式，PUB 模块可参考 |
| **config.toml 多模型配置** | 多模型/多素材源配置方式简洁 |

**核心差异**：MoneyPrinterTurbo 是"素材拼接"路线（搜已有视频拼接），我们是"AI 生成"路线（生成全新画面）。本质不同，但合成层技术可复用。

---

## 二、素材搜索 MCP Server 生态

视频生产不只是 AI 生成，还需要大量辅助素材：背景图、过渡视频片段、贴纸元素、参考图等。以下 MCP Server 可直接集成。

### 2.1 Pexels MCP

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/developer-ishan/mcp-pexels |
| 协议 | 未明确（开源） |
| 证据等级 | A |

**工具列表**：
- `pexels_search_photos` — 按关键词搜索照片，支持方向/尺寸/颜色/语言过滤
- `pexels_curated_photos` — Pexels 团队策展照片
- `pexels_get_photo` — 按 ID 获取单张照片
- `pexels_search_videos` — 按关键词搜索视频，支持方向/尺寸/语言过滤
- `pexels_popular_videos` — 热门视频，支持分辨率/时长过滤
- `pexels_get_video` — 按 ID 获取单个视频
- `pexels_featured_collections` — 精选合集
- `pexels_my_collections` — 用户自建合集
- `pexels_collection_media` — 合集内媒体

**适用场景**：搜索辅助素材、参考图、过渡视频片段、背景图。

### 2.2 Pixabay MCP

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/zym9863/pixabay-mcp |
| 备选 | https://github.com/Unlock-MCP/pixabay-mcp-server |
| 协议 | 未明确（开源） |
| 证据等级 | A |

**工具列表**：
- `search_pixabay_images` — 按关键词搜索图片，支持类型（照片/插画/矢量）、方向、分类、颜色、最小尺寸
- `search_pixabay_videos` — 按关键词搜索视频，支持类型（影片/动画）、时长范围、方向
- `get_video_by_id` — 按 ID 获取视频

**适用场景**：同 Pexels，可作为备选素材源或互补素材源。

### 2.3 多源聚合 MCP

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/jeanpfs/stock-images-mcp |
| 协议 | 未明确（开源） |
| 证据等级 | A |

**特点**：同时支持 Pexels + Unsplash + Pixabay 三个源，`search_images` 可指定 `provider: "all"` 跨源搜索。

**适用场景**：一个 MCP 覆盖三个素材源，减少集成成本。

### 2.4 素材 MCP 在我们架构中的定位

```
导演 Agent
  ├── 文生图 Agent → Seedream API（生成全新画面）
  ├── 素材搜索 Agent → 素材 MCP（搜索辅助素材）
  │     ├── Pexels MCP（照片 + 视频）
  │     ├── Pixabay MCP（图片 + 视频 + 插画）
  │     └── 多源聚合 MCP（跨源搜索）
  ├── 视频生成 Agent → Seedance API（生成视频片段）
  └── 合成 Agent → FFmpeg/MoviePy（合成成片）
```

**分工**：
- AI 生成负责"不存在的画面"（角色、场景、故事画面）
- 素材搜索负责"已有的辅助素材"（背景纹理、过渡片段、环境空镜、参考图）
- 两者互补，不是替代关系

---

## 三、音效与配乐方案

### 3.1 问题定义

一条视频包含：画面 + 配音 + 字幕 + **音效** + **背景音乐**。音效的难点不在"找什么音效"，而在"**什么时候加什么音效**"——需要理解画面内容、节奏、情绪，在正确的时间点放置正确的音效。

### 3.2 音效自动放置技术前沿

#### EchoFoley（学术论文，2025）

| 维度 | 信息 |
|---|---|
| 论文 | https://arxiv.org/html/2512.24731v1 |
| 核心能力 | 事件中心的分层控制：何时、何物、如何发声 |
| 证据等级 | A（论文 + 开源代码 + 预训练模型） |

**技术路径**：
- **慢快思维策略**：快路径 1fps 全局概览，慢路径 16x 慢动作精确事件定位
- **符号化事件计划**：先分析视频识别发声事件和时间戳，构造符号化描述，再驱动音频生成
- **时间控制**：精确到秒的音效放置（"1 秒长的魔法爆炸在 0:03 处"）
- **语义控制**：描述音效类型（"猫叫"、"球撞瓶子"）
- **属性控制**：音调、音色等（"低音"、"柔和音色"）

**启示**：音效放置本质是"视频理解 + 事件检测 + 音频生成"三步。我们的合成 Agent 可以用类似分层策略。

#### Resound（开源 CLI 工具）

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/sanity-labs/resound |
| 核心能力 | Markdown 驱动的音效/配音/音乐生成，输出带时间戳的 manifest |
| 证据等级 | A（源码可直接审查） |

**工作方式**：
- 用 Markdown 文件定义音轨：对话、音效、音乐分轨
- `sounds:` 块定义音效名称和 prompt
- 在 Markdown 正文中按位置放置音效
- 输出 `manifest.json`（时间标记）+ 各轨音频文件
- 原生集成 Remotion（React 视频框架）

**启示**：Markdown 驱动的音效编排模式非常适合 Agent——Agent 可以生成 Markdown 描述音效计划，再由 Resound 渲染。

#### Krotos Video to Sound（商业产品）

| 维度 | 信息 |
|---|---|
| 产品 | https://krotos.studio/premiere-pro-plugin |
| 核心能力 | AI 辅助选择 + 同步音效到时间线，10 万+ 真实录音库 |
| 证据等级 | B |

**特点**：AI 不生成音频，而是从 10 万+ 真实录音中选择合适的并自动同步到视频时间线。Premiere Pro 插件。

**启示**：音效不一定要 AI 生成，"从音效库中智能选择 + 自动同步"是更实用的路线。

#### Video to Sfx（Picasso IA）

| 维度 | 信息 |
|---|---|
| 产品 | https://picassoia.com/en/collection/video-editing/mirelo-video-to-sfx-v1 |
| 核心能力 | 上传视频 → AI 读取画面内容 → 生成同步音效 → 输出带音轨的视频 |
| 证据等级 | C |

**特点**：全自动，读取画面动作生成匹配音效，支持文本提示引导，可生成多个变体。

### 3.3 音效/音乐搜索 MCP Server

#### Freesound MCP

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/johnkimdw/freesound-mcp-server |
| 备选 | https://github.com/timjrobinson/FreesoundMCPServer |
| 数据源 | Freesound.org（CC 协议音效库） |
| 证据等级 | A |

**能力**：用自然语言搜索音效、环境音、音乐循环。

#### Epidemic Sound MCP

| 维度 | 信息 |
|---|---|
| 文档 | https://developers.epidemicsite.com/docs/mcp/ |
| 数据源 | Epidemic Sound（商业音乐/音效/人声库） |
| 证据等级 | A（官方 MCP Server） |

**能力**：按情绪/场景/元数据搜索音乐和音效，如"mood: calm"、"scene: dark forest at dawn"。

### 3.4 音效方案建议（待审核）

| 方案 | 描述 | 优点 | 缺点 |
|---|---|---|---|
| A | Agent 分析画面 → 从 Freesound/Epidemic 搜索音效 → 自动放置 | 真实音效质量高，成本低 | 需要画面理解能力 |
| B | Agent 生成 Markdown 音效计划 → Resound 渲染 | 编排灵活，Agent 友好 | Resound 依赖外部 TTS/音频生成 |
| C | 直接用 AI 生成音效（EchoFoley / Video to Sfx） | 全自动，无需搜索 | 生成质量不稳定，成本高 |
| D | 混合：Agent 分析画面 → 搜索音效库 + AI 生成补充 → 自动放置 | 质量和覆盖兼顾 | 实现复杂度高 |

**当前倾向**：方案 A 或 D，先从音效库搜索开始，AI 生成作为补充。

---

## 四、LibTV 技术路径分析

### 4.1 基本信息

| 维度 | 信息 |
|---|---|
| 产品 | LibTV（LiblibAI 旗下 AI 视频创作平台） |
| 发布时间 | 2026 年 3 月 |
| 定位 | 专业级 AI 动态内容创作引擎 |
| 证据等级 | B（官方产品页 + 多篇深度报道） |

### 4.2 核心架构

#### 双入口架构（Dual-Entry）

LibTV 从第一天起就为**人类创作者和 Agent 各有各的入口**，不是先做 GUI 再补 API，两个入口在产品架构层面并行。

| 入口 | 面向 | 方式 |
|---|---|---|
| 无限画布 + 节点工作流 | 专业创作者 | 可视化非线性编辑，手动操控 |
| libtv-skills（开源 MIT） | AI Agent | Skill 封装，一句话触发全流程 |

**关键启示**：我们的架构也是双入口——桌面端 GUI 给用户操作，Agent 通过 plan→effect 链路自动执行。LibTV 验证了这个设计方向。

#### 三级解耦架构

```
场景（Scene）→ 镜头（Shot）→ 帧（Frame）
```

- 场景级：剧本拆解、角色设定、场景设定
- 镜头级：分镜生成、运镜设计、视频生成
- 帧级：单帧特效叠加、动态元素独立控制

**关键启示**：我们的 6 环节可以进一步细化为三级解耦。导演 Agent 管场景级，子 Agent 管镜头级，合成 Agent 管帧级。

#### 多模型协同

| 维度 | 信息 |
|---|---|
| 模型数量 | 30+ 视频生成模型 |
| 代表模型 | Seedance 2.0、Kling 3.0、Wan 2.6、Vidu、Pixverse |
| 调度方式 | 聚合式模型调度系统，异构模型动态适配与任务分配 |
| 价格 | 声称比 Runway/Pika 低 76-92% |

**关键启示**：不要绑定单一模型。我们的 volcengine_adapter 应设计为可扩展的多模型适配层，火山引擎是首选但不是唯一。

### 4.3 Agent 集成方式

#### libtv-skills 项目

| 维度 | 信息 |
|---|---|
| 许可证 | MIT |
| 集成方式 | Agent 添加 LibTV Skill → 一句话触发全流程 |
| 示例 | "创建一个 1 分钟科幻预告片，流浪地球风格" → 自动完成剧本→分镜→视频→剪辑 |

#### Agent 返回值设计（关键）

LibTV 的 Agent 调用返回不是简单的任务 ID，而是三样东西：

| 返回值 | 用途 |
|---|---|
| `sessionId` | Agent 持续查询进展 |
| `projectUuid` | 整个创作挂在可持续的项目对象上 |
| `projectUrl` | 人类可以随时打开画布接管 |

**Agent 交付的不是孤立的 mp4 文件，而是整个可继续编辑的项目。**

**关键启示**：我们的 effect receipt 应该不只记录结果 URL，还要记录项目上下文（可恢复的项目 ID + 可人工接管的入口）。这与我们的 plan→effect→receipt 链路天然契合——receipt 里可以包含 `project_url` 字段。

### 4.4 专业功能清单

LibTV 内置 20+ 专业创作功能：

| 功能 | 说明 | 我们的对应 |
|---|---|---|
| 9 宫格分镜生成 | 一次出 9 张构图方案 | 文生图 Agent 批量生成 |
| 25 宫格分镜 | 连续分镜板 | 文生图 Agent 批量生成 |
| 剧情推演四宫格 | 故事发展预测 | 剧本 Agent |
| 多机位镜头设计 | 多角度镜头规划 | 视频生成 Agent |
| 角色三视图 | 锁定角色形象，跨镜头一致 | 风格预设 + seed 固定 |
| 画面时间推演（3 秒后） | 预测画面后续发展 | 视频生成 Agent |
| 画面时间推演（5 秒前） | 预测画面之前状态 | 视频生成 Agent |
| 电影级光影校正 | 光影修正 | 后处理 |
| 镜头扭曲特效 | 变形特效 | 后处理 |
| 逐镜头生成视频 | 按分镜逐个生成 | 视频生成 Agent |
| 画布直接剪辑配乐 | 可视化剪辑 | 合成 Agent |
| 工作流存为模板 | 参数偏好记录 | 合成模板库（数据飞轮） |

### 4.5 审美资产流通（飞轮）

LibTV 的飞轮逻辑：

```
创作者调好工作流 → 存为模板（记录参数偏好：镜头时长/构图/色调/节奏）
→ 另一个创作者拿去用 → 出来的东西带着前一个人的审美印记
→ Agent 拿去执行 → 同样带着审美印记
→ 人出审美，Agent 出产能，社区做流通
```

**关键启示**：这与我们的"网感"数据飞轮完全一致。LibTV 的模板 = 我们的合成模板库 + 风格预设 + 镜头策略库。区别是 LibTV 靠社区流通，我们靠数据飞轮自动学习。

### 4.6 Seedance 2.0 在 LibTV 中的参数

| 参数 | 值 |
|---|---|
| 参考资产上限 | 最多 12 个：9 张图片 + 3 个视频 + 3 个音频 |
| 原生能力 | 音视频同步、多镜头序列、8+ 语言唇同步 |
| 输出分辨率 | 最高 1080p |
| 单片段时长 | 最长 15 秒 |

**关键启示**：Seedance 2.0 支持多图多视频参考输入，我们的参考图/视频生视频 Agent 应支持多资产输入，不是单图。

---

## 五、技术选型建议汇总（待审核）

| 领域 | 候选 | 建议 | 优先级 |
|---|---|---|---|
| **合成层** | 裸 FFmpeg / MoviePy | MoviePy（MIT，Python 封装，Agent 友好） | P0 |
| **素材搜索** | Pexels MCP / Pixabay MCP / 多源聚合 MCP | 多源聚合 MCP（一个覆盖三个源） | P1 |
| **音效搜索** | Freesound MCP / Epidemic Sound MCP | Freesound（CC 协议，免费）+ Epidemic（商业质量） | P1 |
| **音效放置** | EchoFoley / Resound / Krotos / Video to Sfx | 先用 Agent 分析 + 搜索音效库自动放置（方案 A） | P2 |
| **配音/TTS** | Edge TTS / 火山引擎 TTS / 其他 | 待调研 | P1 |
| **视频模型** | Seedance 2.0（首选）/ Kling 3.0 / Wan 2.6 | adapter 设计为多模型可扩展 | P0 |
| **项目交付** | LibTV 模式（sessionId + projectUuid + projectUrl） | effect receipt 增加项目上下文 | P1 |

---

## 六、参考资料

| 资料 | 类型 | 证据等级 | URL |
|---|---|---|---|
| MoneyPrinterTurbo | 开源项目 | A | https://github.com/harry0703/MoneyPrinterTurbo |
| Pexels MCP | 开源 MCP | A | https://github.com/developer-ishan/mcp-pexels |
| Pixabay MCP | 开源 MCP | A | https://github.com/zym9863/pixabay-mcp |
| 多源聚合 MCP | 开源 MCP | A | https://github.com/jeanpfs/stock-images-mcp |
| EchoFoley 论文 | 学术论文 | A | https://arxiv.org/html/2512.24731v1 |
| Resound | 开源工具 | A | https://github.com/sanity-labs/resound |
| Krotos Video to Sound | 商业产品 | B | https://krotos.studio/premiere-pro-plugin |
| Video to Sfx (Picasso IA) | 商业产品 | C | https://picassoia.com/en/collection/video-editing/mirelo-video-to-sfx-v1 |
| Freesound MCP | 开源 MCP | A | https://github.com/johnkimdw/freesound-mcp-server |
| Epidemic Sound MCP | 官方 MCP | A | https://developers.epidemicsite.com/docs/mcp/ |
| LibTV 产品介绍 | 官方/媒体报道 | B | https://www.houdao.com/d/5585-LibTV-Revolutionizing-AllinOne-AI-Video-Creation-with-NodeBased-Workflows-and-Agent-Skill-Entry-Points |
| LibTV + Seedance 2.0 | 媒体报道 | B | https://abit.ee/en/artificial-intelligence/libtv-seedance-20-liblibai-ai-video-bytedance-video-generation-2026-en |
| LibTV 双入口设计分析 | 知乎深度文章 | B | https://zhuanlan.zhihu.com/p/2018072443852465515 |
| LibTV 产品页 | 官方 | B | http://prompt.cn/sites/10031.html |

---

## 六点五、Cheat on Content（网红作弊器）—— 网感校准引擎

### 基本信息

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/XBuilderLAB/cheat-on-content |
| Stars | 5K+ |
| 许可证 | 未明确（开源） |
| 语言 | Python |
| 证据等级 | A（源码 + SKILL.md 可直接审查） |
| 定位 | 不是"帮你写内容"的工具，是"帮你量化自己的网感"的校准系统 |

### 核心理念

**与所有其他工具的根本区别**：

| 别的工具 | Cheat on Content |
|---|---|
| 给你"灵感" | 让你**自己的直觉被量化** |
| AI 帮你写 | AI 帮你**判**——稿子还是你的 |
| 发 10 个版本 A/B 测 | 发一个就**赌**——把判断写下来，数据出来对账 |
| 静态数据看板 | **会进化的评分公式**——三个月后的 rubric 已不是初始版 |

**核心循环**：

```
打分（Score）→ 盲预测（Blind-predict）→ 发布（Publish）→ T+3d 复盘（Retro）→ 进化 rubric（Evolve）
```

### 三条不可妥协原则

1. **盲预测**：预测必须在看到实际数据之前写完，写完后不可修改（immutability hook 强制执行）
2. **升级 = 全量重打**：rubric 升级时，校准池所有样本必须用新公式重打分；新排序与实际表现排序若在 ≥4/5 样本上不一致，升级被拒；升级需跨模型独立审核
3. **rubric 是工作台不是博物馆**：被推翻的观察直接删掉，不留考古层。git history 才是档案

### 14 个子 Skill

| 触发词 | 子 Skill | 作用 |
|---|---|---|
| 初始化 | `cheat-init` | 5 个 yes/no 搞定 onboarding |
| 找对标 / learn from | `cheat-learn-from` | 导入对标账号 5-10 条样本，派生 base rubric |
| 找选题 / seed | `cheat-seed` | cold-start 用户一次性种子选题 |
| 打分这篇 | `cheat-score` | 7 维度打分 |
| 启动预测 | `cheat-predict` | 盲预测 + 决策日志（不可修改） |
| 拍了 | `cheat-shoot` | 建视频文件夹 + buffer +1 |
| 已发布 | `cheat-publish` | buffer -1 |
| 复盘 | `cheat-retro` | T+3d 数据回收 + 复盘对账 |
| 构造受众画像 | `cheat-persona` | 从评论数据派生受众画像 |
| 升级 rubric | `cheat-bump` | 全量重打 + 跨模型审核 |
| 推荐选题 | `cheat-recommend` | 从候选池推荐 |
| 抓热点 | `cheat-trends` | 抓热点补充候选池 |
| 状态 | `cheat-status` | 看板 |
| 迁移 | `cheat-migrate` | schema 版本迁移 |

### 7 维度评分 rubric（观点类视频）

基于参考博主 25+ 已发样本拟合，7 个维度。具体维度名称在 starter-rubrics 中定义。rubric 可进化——每次复盘后用数据校准权重。

### 与我们系统的对标

| Cheat on Content 概念 | 我们的对应 | 现状 | 差异 |
|---|---|---|---|
| **5 阶段校准循环** | 数据飞轮闭环 | 飞轮策略已设计 | 我们是自动化的，CoC 是人机协作的 |
| **盲预测 + T+3d 复盘** | 发布指标回收 + 爆款归因 | PUB 模块待实现 | CoC 强调人先赌再对账，我们可以 Agent 赌 + 数据对账 |
| **进化 rubric** | 网感学习 + 镜头策略库 | 飞轮策略已设计 | CoC 的 rubric = 我们的爆款因子库 |
| **对标账号导入** | DATA 模块竞品采集 | DATA 模块已有地基 | CoC 用对标账号做 cold-start anchor |
| **14 个子 skill** | 我们的 Agent skill 体系 | skill 架构已有 | CoC 是 Claude Code skill，我们是 Hermes skill |
| **盲预测不可修改** | effect receipt 不可修改 | receipt 已有 idempotency | 相同原则 |
| **跨模型审核 bump** | 多 Agent 审核 | 审批链已有 | CoC 用外部 LLM 审核，我们用审批链 |
| **buffer 警戒系统** | 排期队列 | PUB-08 待实现 | CoC 的 cadence-protocol 可参考 |
| **受众画像 persona** | 账号 DNA | MEM 模块已有 | 相同概念 |

### 关键启示

1. **网感是可校准的**：CoC 证明了"感觉"可以变成 7 维度评分 + 盲预测 + 数据对账的校准循环。我们的数据飞轮应该内置这个循环，不是只做"指标回收"，还要做"预测 vs 实际"的对账。

2. **盲预测是核心**：Agent 在内容发布前应该先做预测（预计播放量/完播率/互动率），发布后用实际数据对账。对账结果用于校准 Agent 的判断模型。这比单纯"回收数据"更有价值——它让 Agent 知道自己哪里准、哪里偏。

3. **rubric 进化机制**：CoC 的"全量重打 + 跨模型审核 + 4/5 一致性检验"是一套严谨的 rubric 进化协议。我们的爆款因子库升级应该借鉴这个机制，不能随便改权重。

4. **cold-start 用对标账号**：新用户没有历史数据时，导入对标账号 5-10 条样本作为初始 anchor。这解决了我们数据飞轮的冷启动问题。

5. **人出判断，AI 出校准**：CoC 的理念是"稿子还是你的，AI 帮你判"。我们的系统应该是"Agent 出初稿 + 预测，用户确认/修改，数据对账校准 Agent"。不是 Agent 替用户做一切。

6. **三 channel 模型**：CoC v2 引入了 blind scoring sub-agent（channel B 隔离），主 agent 和 blind agent 评分不一致时触发仲裁。我们的多 Agent 架构可以借鉴——文生图 Agent 的质量评估可以用独立子 Agent 盲评。

### 可直接借鉴的设计

| 设计 | 借鉴方式 | 优先级 |
|---|---|---|
| 盲预测 + T+3d 对账 | Agent 发布前写预测，发布后自动对账 | P0 |
| rubric 进化协议（全量重打 + 跨模型审核） | 爆款因子库升级机制 | P1 |
| 对标账号 cold-start | 新用户导入对标账号做初始 anchor | P1 |
| buffer 警戒系统 | 排期队列的断更预警 | P2 |
| 三 channel 盲评 | 子 Agent 质量评估用独立盲评 | P2 |
| 14 个子 skill 的路由表设计 | 我们的 skill 触发词路由可参考 | P2 |

---

## 七、待讨论问题（供审核）

1. **MoviePy vs 裸 FFmpeg**：MoviePy 封装更友好但增加一层依赖，是否值得？还是直接用 FFmpeg 命令 + Agent 动态编排？
2. **素材搜索 Agent 是否独立**：素材搜索是作为导演 Agent 的一个工具，还是独立的子 Agent？
3. **音效放置方案选择**：方案 A（搜索+自动放置）vs D（混合），先做哪个？
4. **TTS 配音方案**：Edge TTS 免费但质量一般，火山引擎 TTS 质量好但需额外 API Key，如何选择？
5. **多模型适配层设计**：volcengine_adapter 是否应设计为通用 video_model_adapter，支持 Seedance / Kling / Wan 等多模型？
6. **LibTV 的项目交付模式**：effect receipt 增加 project_url 字段是否值得？还是保持纯结果 URL？
7. **审美模板流通**：是否参考 LibTV 的社区模板模式，还是纯靠数据飞轮自动学习？
8. **盲预测机制**：是否在 Agent 发布内容前强制写预测（播放量/完播率/互动率），发布后自动对账？这比单纯回收数据更有校准价值。
9. **rubric 进化协议**：爆款因子库的权重升级是否需要"全量重打 + 4/5 一致性 + 跨模型审核"机制？还是用更轻量的方案？
10. **cold-start 策略**：新用户没有历史数据时，是否用对标账号导入做初始 anchor（CoC 模式）？
11. **三 channel 盲评**：子 Agent 生成结果的质量评估是否用独立盲评 Agent？还是主 Agent 自评即可？

---

## 八、深度调研补充（2026-07-03 第二轮）

### 8.1 ViMax — 多 Agent 视频生成框架（港大）

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/HKUDS/ViMax |
| Stars | 11K+ |
| 论文 | arxiv.org/html/2606.07649 |
| 语言 | Python |
| 证据等级 | A（源码 + 论文） |

**核心架构**：Director + Screenwriter + Producer + Video Generator 四角色一体的多 Agent 视频生成框架。

**关键创新**：
- **分层叙事引擎**：RAG-based 长脚本设计，智能分析并自动分段
- **角色/环境一致性**：dependency-aware visual consistency mechanism，跨场景追踪角色和环境状态
- **多镜头拍摄模拟**：multi-camera filming simulation
- **智能参考图选择**：自动选择参考图 + 视觉逻辑排序
- **并行镜头生成**：parallel shot generation + best-of-k selection
- **VLM 质量审核**：VLM-guided agents 持续监控和改进叙事连贯性和视觉保真度

**三种工作流**：
1. `idea2video` — 从模糊想法到视频
2. `script2video` — 从具体脚本到视频
3. `novel2video` — 从小说文本到视频

**与我们的对比**：
- ViMax 的 Director/Screenwriter/Producer/Generator 四角色 = 我们的 director-pipeline + 6 个 effect 工具
- ViMax 的 VLM 质量审核 = 我们的 RUN-17 内容评分 + RUN-18 盲预测
- ViMax 的 character consistency = 我们暂无（可考虑在 effect 工具中加入角色一致性检查）
- ViMax 用 Gemini-3-Flash 做语言骨干 + Veo 3 / Wan 2.x 做视频生成，我们用火山引擎 Seedance/Doubao

**可直接借鉴**：
- 分层叙事引擎的 RAG 设计思路 → 可集成到 director-pipeline skill
- best-of-k selection → 可作为视频生成 effect 的质量门控
- VLM judge 的多候选评估 → 可用于 RUN-17 的 `scored_by="blind_agent"` 盲评路径

### 8.2 OpenMontage — 开源 Agent 视频生产系统

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/calesthio/OpenMontage |
| Stars | 3K+（单日涨 3K） |
| 语言 | Python |
| 证据等级 | A（源码） |

**核心架构**：三层设计
1. **Tools 层** — 52 个 Python 可执行工具（视频生成、图像生成、TTS、音乐、分析）
2. **Pipeline Manifests 层** — YAML playbooks 定义每种视频类型的生产阶段
3. **Skills 层** — 500+ agent skills

**关键特点**：
- 不做封闭平台，而是让 AI coding agent 驱动整个视频生产
- 12 条 pipeline，覆盖从研究→脚本→素材→编辑→合成的全链路
- 支持真实视频（非仅图片动画）+ 归档素材编辑
- 与 AI coding assistant（如 Claude Code）深度集成

**与我们的对比**：
- OpenMontage 的 52 tools = 我们的 tool_manifest 中的 effect 工具集
- OpenMontage 的 YAML pipeline manifests = 我们的 plan_protocol declare_plan
- OpenMontage 的 500+ skills = 我们的 director-pipeline skill 库
- OpenMontage 是"让 AI coding agent 当导演"，我们是"让 desktop agent 当运营"

**可直接借鉴**：
- YAML pipeline manifest 格式 → 可作为 director-pipeline 的计划模板
- 52 tools 的分类方式 → 可指导我们的 tool_manifest 扩展
- "agent 驱动而非编辑器驱动"的理念 = 我们的设计哲学一致

### 8.3 x-algorithm（X 推荐算法开源）— 内容评分的工业级参考

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/xai-org/x-algorithm |
| Stars | 26K+ |
| 语言 | Rust |
| 最新更新 | 2026-05-15（大更新） |
| 证据等级 | A（源码 + 官方文档） |

**核心架构**：Phoenix（Grok-based transformer）预测 19 种用户行为概率 → Weighted Scorer 加权求和 → 排序

**19 种行为信号**：
- 正向：favorite, reply, retweet, photo_expand, click, profile_click, vqv (video quality view), share, share_via_dm, share_via_copy_link, dwell, quote, quoted_click, cont_dwell_time, follow_author
- 负向：not_interested, block_author, mute_author, report, not_dwelled

**权重设计哲学**：
- 每种加权概率在平均情况下贡献大致相同（report 罕见所以权重大）
- 2023 年公开权重：reply=150× favorite, report=−738× favorite
- 2026 年权重已不公开（redacted params file）
- 校准逻辑：weights set so each weighted probability contributes roughly the same amount on average

**衍生项目**：
- `x-algo-optimizer` — Claude Code skill，分析内容并预测算法评分
- `x-algorithm-toolkit` — React app + MCP server，22 个算法信号 + 18 个过滤器检查
- `x-impact-checker` — AI agent skill，100 分制评分系统

**与我们的对比**：
- X 的 Phoenix scorer = 我们的 RUN-17 content_rubric（但 X 是 ML 预测，我们是规则评分）
- X 的 19 种行为信号 = 我们的 7 维度 rubric（hook/topic/emotion/density/pacing/viewpoint/cta）
- X 的 weighted scorer = 我们的 `compute_weighted_total`
- X 的 calibration = 我们的 RUN-20 rubric bump 协议
- X 的 "weights set so each contributes equally on average" = 我们的权重设计原则

**可直接借鉴**：
- **负面信号维度**：我们的 7 维度全是正向评分，可考虑加入"负面风险"维度（如"标题党风险"、"争议过度风险"）
- **校准哲学**：X 的"每个信号平均贡献相同"原则 → 可用于 RUN-20 bump 时的权重初始化
- **多衍生项目的分工**：x-algo-optimizer 做分析，x-algorithm-toolkit 做工具化，x-impact-checker 做评分 → 我们也可拆分 rubric 为"分析工具"+"评分工具"+"优化建议"

### 8.4 social-auto-upload — 多平台自动上传

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/dreammis/social-auto-upload |
| 语言 | Python |
| 证据等级 | A（源码） |

**核心能力**：一键发布视频到 抖音/Bilibili/小红书/快手/视频号/百家号/TikTok/YouTube
- 使用 Playwright 做浏览器自动化
- 支持定时发布
- 增强版（yang2632/social-auto-upload）增加了视频剪辑、背景音乐、批量处理

**与我们的对比**：
- social-auto-upload 的多平台上传 = 我们的 publishing_tasks + external_mcp_bridge
- social-auto-upload 用 Playwright 直接操作浏览器 = 我们通过 MCP browser 通道

**可直接借鉴**：
- 平台适配器模式 → 可作为 publishing_tasks 的 platform adapter 参考
- 定时发布逻辑 → 可集成到 RUN-22 发布节奏警戒

### 8.5 ShortGPT — AI 短视频自动创作框架

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/RayVentura/ShortGPT |
| 语言 | Python |
| 证据等级 | A（源码） |

**核心能力**：
- 自动脚本生成（OpenAI）
- 自动素材获取（互联网图片/视频素材搜索）
- 自动配音（ElevenLabs，多语言）
- 自动字幕生成
- 自动编辑（AI 驱动的剪辑流程）

**与我们的对比**：
- ShortGPT 的素材搜索 = 我们的 Pixabay/Pexels/Freesound MCP
- ShortGPT 的自动编辑 = 我们的 cloud video merging effect
- ShortGPT 是"全自动流水线"，我们是"Agent 驱动 + 人工审批"

### 8.6 AI 内容矩阵工具群

#### 8.6.1 ai-content-matrix

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/zhangyu0806/ai-content-matrix |
| 证据等级 | A（源码） |

**核心能力**：1 篇长文 → 6 平台 19 条内容（小红书 5 条/抖音 4 条/B 站 2 条/公众号 2 条/知乎 2 条/微博 4 条）
- TF-IDF 关键词提取 + 平台适配算法
- 批量处理 + CSV 导出 + 内容日历

#### 8.6.2 meiti-ai（美媒）

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/zhuixin8/meiti-ai |
| 证据等级 | A（源码） |

**核心能力**：AI 写文 + 去 AI 味 + 热点选题 + 定时自动发布 + 多账号矩阵 + 20+ 平台分发
- 桌面端 + 网页端
- 知识库（PDF/Word/Excel/TXT）
- 每号独立人设/风格/平台适配
- 定时无人值守"抓热点→成文→多账号发布"

#### 8.6.3 SynapseAutomation

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/Laihiujin/SynapseAutomation |
| 证据等级 | A（源码） |

**核心能力**：AI 矩阵投放/多平台批量发布视频
- 支持 抖音/小红书/快手/视频号/B 站
- **数据回收**：抖音/B 站已发布视频数据回收 → 直接对标我们的 RUN-19 T+3d 复盘
- 内置 HermesAgent AI 助手
- "一句话投放"自然语言生成标题/标签/排期
- 矩阵投放 SOP：绑号→素材入库→创建计划→调度执行→监控→数据回收→复盘

#### 8.6.4 xhs-matrix

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/zuowangyan/xhs-matrix |
| 证据等级 | A（源码） |

**核心能力**：小红书 AI 矩阵运营系统
- 采集竞品/热点 → AI 分析选题 → 按人设+知识库原创图文配图 → 多账号拟人自动发布
- Electron 桌面端，支持局域网共享
- 三层 LLM Wiki（来源/实体/主题）知识库
- 每号独立浏览器指纹 + 每日上限养号
- 拟人逐字填写、错峰发布
- 三种模式：手动/半自动/全自动

#### 8.6.5 fabuya（发布鸭）

| 维度 | 信息 |
|---|---|
| 仓库 | https://github.com/cuitingleigood/fabuya |
| 证据等级 | A（源码） |

**核心能力**：自媒体矩阵发布工具，支持 11+ 平台
- 浏览器指纹伪装 + 账号独立代理
- 四种混剪模式
- 本地素材仓库 + AI 自动匹配素材
- 接入 Coze（扣子）智能调用

### 8.7 内容矩阵工具群与我们的对比

| 能力维度 | 我们 | 矩阵工具群 | 差异 |
|---|---|---|---|
| **核心定位** | Agent 驱动的智能运营 | 工具驱动的批量分发 | 我们是"大脑"，它们是"手脚" |
| **内容生成** | Agent 理解需求→调研→脚本→评分→生成 | TF-IDF 拆解/模板填充 | 我们更深度但更慢 |
| **多平台发布** | publishing_tasks + MCP browser | Playwright 自动化 | 它们更成熟 |
| **数据回收** | RUN-19 T+3d 复盘（已实现） | SynapseAutomation 有抖音/B站回收 | 我们有完整对账链路 |
| **人设/知识库** | memory_candidates | xhs-matrix 三层 LLM Wiki | 可借鉴其知识库分层 |
| **养号/防风控** | 暂无 | 浏览器指纹/代理/拟人操作 | 需要补充 |
| **内容评分** | RUN-17 7维度 rubric（已实现） | 无 | 我们独有 |
| **盲预测** | RUN-18 immutable 预测（已实现） | 无 | 我们独有 |
| **rubric 进化** | RUN-20 bump 协议（已实现） | 无 | 我们独有 |

### 8.8 关键发现总结

**我们的独特优势（已实现且竞品没有的）**：
1. **内容评分协议**（RUN-17）— 7 维度 rubric + store 集成
2. **盲预测机制**（RUN-18）— immutable 预测 + 对账
3. **T+3d 复盘对账**（RUN-19）— 预测 vs 实际偏差检测
4. **Rubric 进化协议**（RUN-20）— 全量重打 + 一致性检验 + 跨模型审核
5. **发布节奏警戒**（RUN-22）— buffer 状态 + green/yellow/red 警戒

**需要补强的方向**：
1. **多平台自动发布** — social-auto-upload 和 SynapseAutomation 的平台适配器模式值得参考
2. **浏览器指纹/防风控** — xhs-matrix 和 fabuya 的指纹伪装 + 代理隔离
3. **知识库分层** — xhs-matrix 的三层 LLM Wiki（来源/实体/主题）
4. **内容矩阵拆解** — ai-content-matrix 的 1→N 平台适配算法
5. **负面信号维度** — X 算法的 not_interested/block/report 反向信号
6. **VLM 质量审核** — ViMax 的 best-of-k + VLM judge 多候选评估
7. **角色一致性** — ViMax 的 dependency-aware visual consistency

### 8.9 新增待讨论问题

12. **负面信号维度**：RUN-17 的 7 维度全是正向评分，是否需要加入"标题党风险"、"争议过度风险"等负面维度？参考 X 算法的 not_interested/block/report 信号。
13. **VLM 盲评**：是否在 RUN-17 的 `scored_by="blind_agent"` 路径中引入 VLM judge 做 best-of-k 评估？参考 ViMax 的 VLM 质量审核。
14. **平台适配器**：publishing_tasks 是否参考 social-auto-upload 的平台适配器模式，抽象出统一的 PlatformAdapter 接口？
15. **知识库分层**：memory_candidates 是否参考 xhs-matrix 的三层 LLM Wiki（来源/实体/主题）做结构化分层？
16. **内容矩阵拆解**：是否增加"1 篇长文→N 平台适配"的 effect 工具？参考 ai-content-matrix 的 TF-IDF + 平台适配算法。
17. **养号/防风控**：MCP browser 通道是否需要增加浏览器指纹伪装和代理隔离能力？参考 xhs-matrix 和 fabuya。
18. **YAML pipeline 模板**：director-pipeline skill 是否参考 OpenMontage 的 YAML pipeline manifest 格式，提供预置的视频生产模板？
