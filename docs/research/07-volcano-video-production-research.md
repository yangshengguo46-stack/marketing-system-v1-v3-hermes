# 火山引擎视频生成能力调研

> 建立日期：2026-07-02
> 调研目标：为 VIDEO-01 视频生成板块提供架构决策依据。
> 证据等级标注：A=官方文档/源码，B=官方工程博客/可复现仓库，C=厂商宣传/二手总结。

---

## 一、字节系 AI 视频创作产品全景

### 1.1 小云雀 AI（剪映团队，C 端）

| 维度 | 信息 |
|---|---|
| 定位 | C 端短视频创作，"一句话生成 15-60s 视频" |
| 架构 | **单 Agent + 多模型调用**，非多 Agent 协同 |
| 模型栈 | 豆包（理解）+ DeepSeek（推理）+ Seedance 2.0（视频）+ Seedream 5.0（图片） |
| 核心能力 | 智能成片、照片口播（数字人）、AI 设计、爆款复刻 |
| 特点 | 轻量，用户一句话指令自动拆解，不需要用户理解流程 |
| 证据等级 | C（厂商宣传 + 产品体验） |

**关键启示**：小云雀是 C 端单 Agent 路线，能力上限受限于单 Agent 的编排能力。无法做到工业级的分环节质量校验和资产复用。

### 1.2 火山剧创 / Dramart（火山引擎官方，B 端）

| 维度 | 信息 |
|---|---|
| 定位 | B 端短剧/漫剧工业化生产，"制作周期缩短 80%" |
| 架构 | **工业级多 Agent 协同**，4 个核心环节各有专用 Agent |
| 模型栈 | Seedance 2.0（视频）+ Seedream（图片）+ 豆包（剧本理解） |
| 产品入口 | 火山引擎控制台 → Dramart，产品代码 `Dramart` |
| 证据等级 | B（官方产品页 + 开发者文档） |

**4 个核心环节**：

| 环节 | Agent 职责 | 输入 | 输出 |
|---|---|---|---|
| ① 剧本解析 | 拆解剧本为场景、角色、对白 | 剧本文本 | 结构化剧本数据 |
| ② 资产设定 | 生成角色/变装/场景/道具设定图 | 角色描述、场景描述 | 资产图片库（可复用） |
| ③ 分镜生成 | 按场景生成分镜图和运镜描述 | 剧本 + 资产 | 分镜列表 + 运镜参数 |
| ④ 视频生成/剪辑 | 调用 Seedance 生成视频片段，合成成片 | 分镜 + 资产图 | 最终视频 |

**关键设计特点**：
- **全局风格锁定**：跨镜头保持角色/场景一致性
- **素材资产库**：角色/变装/场景/道具可跨镜头复用
- **200+ 爆款镜头策略**：内置镜头模板库
- **多 Agent 校验机制**：每个环节有质量校验
- **人工介入**：每个核心节点保留人工编辑和确认权限
- 证据等级：B

**关键启示**：火山剧创的多 Agent 协同架构是工业级视频生产的标杆。每个环节的专用 Agent 有自己的领域知识、质量评估标准和重试策略。

### 1.3 ArkClaw 最佳实践（火山引擎官方推荐）

| 维度 | 信息 |
|---|---|
| 定位 | 火山版 OpenClaw，面向个人/企业的 AI 助手 |
| 产品代码 | `ArkCalw` |
| 视频制作能力 | 通过 SKILL.md + 脚本工具 + 火山 API 实现短剧生产 |
| 证据等级 | A（官方开发者文档 + 可复现脚本） |

**三层架构**：

```
SKILL.md 定义层（工作流 + 交互规范 + API 配置）
        ↓
脚本工具层（new_project / generate_image / generate_video / merge_videos / query_task）
        ↓
外部 API 层（Seedream 图片生成 + Seedance 视频生成 + FFmpeg 合成）
```

**关键设计细节**：
- **异步任务处理**：视频生成是异步的，提交后轮询查询状态
- **参考图规范**：严格的图 1/图 2 命名规则确保 API 调用一致性
- **成本控制**：批量操作前需用户确认
- **项目数据结构**：每个项目独立目录（project.json + script.md + frames/ + videos/ + final/）
- **FFmpeg 本地合成**：最终剪辑、字幕、配音、贴纸等合成走本地 FFmpeg
- 证据等级：A

---

## 二、火山引擎 API 体系

### 2.1 API 总览

| API | 用途 | 模型 | 模式 | 证据等级 |
|---|---|---|---|---|
| 创建视频生成任务 | 文生视频/图生视频/参考视频生视频 | Seedance 2.0 / 2.0 fast / 1.5 pro / 1.0 lite / pro / pro-fast | **异步**（提交→轮询） | A |
| 查询视频生成任务 | 查询视频任务状态和结果 | — | 同步 | A |
| 查询视频生成任务列表 | 批量查询 | — | 同步 | A |
| 取消或删除视频生成任务 | 取消/删除 | — | 同步 | A |
| 图片生成 API | 文生图 | Seedream 5.0 | 同步（或流式） | A |
| 流式响应（图片） | 流式图片生成 | Seedream | 流式 | A |
| 创建 3D 生成任务 | 3D 内容生成 | — | 异步 | A |

### 2.2 创建视频生成任务 API

**Base URL**: `https://ark.cn-beijing.volces.com/api/v3`

**请求结构**（基于搜索结果和 ArkClaw 文档推断）：

```json
{
  "model": "seedance-2-0",  // 或 seedance-2-0-fast, seedance-1-5-pro 等
  "content": [
    {
      "type": "text",
      "text": "视频描述 prompt"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "https://..."  // 首帧图片 URL（图生视频时使用）
      }
    }
  ],
  "duration": 5,  // 视频时长（秒）
  "resolution": "720p",  // 或 1080p
  "service_tier": "standard",  // 或 priority
  "timeout": 172800  // 任务超时（秒），默认 48h
}
```

**响应结构**：

```json
{
  "id": "task_xxx",  // 任务 ID
  "model": "seedance-2-0",
  "status": "queued",  // queued / running / succeeded / failed / expired
  "created_at": 1234567890
}
```

**关键参数说明**（证据等级 A）：
- **model**：Seedance 2.0 & 2.0 fast 默认 720p；Seedance 1.0 pro & pro-fast 默认 1080p
- **timeout**：范围 [3600, 259200] 秒，默认 172800（48h），超时自动终止标记 expired
- **service_tier**：standard / priority
- **content**：支持 text + image_url 组合，对应不同生成模式
  - 纯 text → 文生视频
  - text + image_url（首帧）→ 图生视频
  - text + 多个 image_url → 参考图生视频
  - text + video_url → 参考视频生视频

> **注意**：以上请求结构基于搜索摘要和 ArkClaw 文档推断，实际字段名需以官方 API 文档为准。API 文档页面为 SPA 渲染，未能完整抓取。

### 2.3 查询视频生成任务 API

**请求**：`GET /api/v3/contents/generations/tasks/{task_id}`

**响应**：

```json
{
  "id": "task_xxx",
  "model": "seedance-2-0",
  "status": "succeeded",  // queued / running / succeeded / failed / expired
  "content": {
    "video_url": "https://...",  // 成功时返回
    "error": "..."  // 失败时返回
  },
  "created_at": 1234567890,
  "updated_at": 1234567890
}
```

证据等级：A（官方 API 文档目录确认存在，字段结构基于 ArkClaw 脚本推断）

### 2.4 图片生成 API（Seedream）

**请求**：`POST /api/v3/images/generations`

```json
{
  "model": "seedream-5-0",
  "prompt": "图片描述",
  "size": "1024x1024",
  "response_format": "url"
}
```

**响应**：

```json
{
  "created": 1234567890,
  "data": [
    {
      "url": "https://..."
    }
  ]
}
```

证据等级：B（API 目录确认存在，字段结构基于 OpenAI 兼容接口推断，火山方舟兼容 OpenAI SDK）

### 2.5 鉴权

- **API Key**：通过 `Authorization: Bearer <API_KEY>` 头部传递
- **获取方式**：火山方舟控制台 → 获取 API Key
- **环境变量**：推荐 `ARK_API_KEY`
- 证据等级：A

### 2.6 SDK 兼容性

- 火山方舟兼容 OpenAI SDK
- 可直接使用 `openai` Python 包，修改 `base_url` 即可
- 证据等级：A

---

## 三、Seedance 2.0 能力详解

### 3.1 支持的生成模式

| 模式 | 输入 | 说明 |
|---|---|---|
| 文生视频 | 纯文本 prompt | 根据文字描述生成视频 |
| 图生视频 | 首帧图片 + 运镜 prompt | 以图片为起始帧，按描述生成运镜动画 |
| 参考图生视频 | 参考图片 + prompt | 以参考图作为风格/角色参考生成视频 |
| 参考视频生视频 | 参考视频 + prompt | 以参考视频作为风格/动作参考生成新视频 |

### 3.2 分辨率与时长

| 参数 | 选项 | 默认 |
|---|---|---|
| 分辨率 | 720p / 1080p | 2.0 系列默认 720p，1.0 pro 默认 1080p |
| 时长 | 5s / 10s（推断） | 5s |
| service_tier | standard / priority | standard |

### 3.3 提示词最佳实践（来自 ArkClaw 文档）

- **运镜描述**：推/拉/摇/移 + 速度 + 幅度
- **场景描述**：主体动作 + 环境 + 光影 + 氛围
- **风格锁定**：固定描述词 + seed 参数保持一致性
- 证据等级：B

---

## 四、Seedream 5.0 能力详解

### 4.1 核心能力

| 能力 | 说明 |
|---|---|
| 文生图 | 根据文字描述生成图片 |
| 风格控制 | 支持多种艺术风格（写实/动漫/油画等） |
| 构图控制 | 支持指定构图、视角、光影 |
| 高分辨率 | 最高支持 2K 分辨率 |
| 角色一致性 | 通过固定描述词 + seed 保持角色外观一致 |

### 4.2 提示词结构（最佳实践）

```
[主体描述] + [风格] + [构图] + [光影] + [质感] + [负面提示]
```

证据等级：B

---

## 五、与火山剧创架构对标

### 5.1 火山剧创的 4 环节 vs 我们的 6 环节

| 火山剧创环节 | 我们的环节 | 对应火山 API | 差异说明 |
|---|---|---|---|
| 剧本解析 | 已有 screenwriting skills | 豆包模型 | 我们已有 |
| 资产设定 | 文生图 | Seedream 5.0 | 生成角色/场景/道具图 |
| 分镜生成 | 已有 storyboard-creator | Seedream 5.0 | 分镜图 + 运镜描述 |
| 视频生成 | 图生视频 / 文生视频 / 参考图生视频 / 参考视频生视频 | Seedance 2.0 | 4 种模式 |
| 剪辑导出 | FFmpeg 合成 | 本地 FFmpeg | 剪辑、字幕、配音、贴纸 |

### 5.2 火山剧创的关键能力映射

| 火山剧创能力 | 我们的对应 | 现状 |
|---|---|---|
| 全局风格锁定 | adapter 参数固化 style seed | 需新建 |
| 素材资产库 | content_assets 表 | 已有 |
| 200+ 爆款镜头策略 | SKILL.md 镜头模板库 | 需新建 |
| 多 Agent 校验 | plan step 间依赖 + 审批节点 | 已有（plan_protocol + tool_gateway） |
| 人工介入 | approval chain | 已有 |

---

## 六、架构方案讨论（待审核，不固定）

### 6.1 方案 A：1 导演 Agent + 6 effect 工具

```
导演 Agent → plan 6 步 → 每步调一个工具 → 完成
```

- 每个环节只是"调一次 API"，没有智能决策
- 无法自动评估结果质量并重试
- 实现简单

### 6.2 方案 B：1 导演 Agent + 6 专用子 Agent（对标火山剧创）

```
导演 Agent（编排）
  ├── 文生图 Agent（Seedream 专家）
  │     收到场景描述 → 拆 prompt → 调 API → 评估结果 → 不满意自动重试
  ├── 图生视频 Agent（Seedance 图生视频专家）
  │     收到图片+运镜描述 → 构造参数 → 调 API → 轮询 → 评估 → 可重试
  ├── 文生视频 Agent（Seedance 文生视频专家）
  ├── 参考图生视频 Agent（Seedance 参考图专家）
  ├── 参考视频生视频 Agent（Seedance 参考视频专家）
  └── 合成 Agent（FFmpeg 专家）
        收到所有片段 → 编排剪辑命令 → 字幕 → 配音 → 贴纸 → 输出成片
```

- 每个子 Agent 有自己的 SKILL.md（领域知识）
- 每个子 Agent 有自主决策能力（评估 + 重试）
- 每个子 Agent 的 API 调用仍走 tool_gateway 审批
- 对标火山剧创的工业级多 Agent 协同

### 6.3 方案 C：混合方案

- 核心环节（文生图、图生视频）用专用子 Agent
- 辅助环节（文生视频、参考图/视频生视频）用简单工具调用
- 合成用专用 Agent（FFmpeg 命令复杂度高）

### 6.4 待决策项

| 决策点 | 选项 | 建议 | 待确认 |
|---|---|---|---|
| Agent 架构 | A / B / C | B（对标火山剧创） | 用户 + 其他 Agent 审核 |
| 子 Agent 实现方式 | 轻量 Hermes 实例 / 独立进程 / 函数调用 | 轻量 Hermes 实例 | 架构审核 |
| 先做哪些环节 | 全部 6 个 / 核心 3 个（文生图+图生视频+合成） | 核心 3 个先行 | 用户确认 |
| API Key 管理 | secret store / 环境变量 | secret store（DESK-03 已完成） | 无争议 |
| 合成方式 | 本地 FFmpeg / 云端 | 本地 FFmpeg | 用户已确认 |
| 风格一致性策略 | 固定 seed / 描述词模板 / 参考图 | 三者结合 | 实现时定 |
| 质量评估方式 | Agent 自评 / 人工确认 / 模型评分 | Agent 自评 + 人工确认 | 实现时定 |

---

## 七、参考资料

| 资料 | 类型 | 证据等级 | URL |
|---|---|---|---|
| 火山方舟 API 参考（目录页） | 官方文档 | A | https://www.volcengine.com/docs/82379/1541523 |
| 创建视频生成任务 API | 官方 API 文档 | A | https://www.volcengine.com/docs/82379/1520757 |
| 查询视频生成任务 API | 官方 API 文档 | A | https://www.volcengine.com/docs/82379/1521309 |
| 查询视频生成任务列表 | 官方 API 文档 | A | https://www.volcengine.com/docs/82379/1521675 |
| 取消或删除视频生成任务 | 官方 API 文档 | A | https://www.volcengine.com/docs/82379/1521720 |
| 图片生成 API | 官方 API 文档 | A | https://www.volcengine.com/docs/82379/1541523 |
| 流式响应（图片生成） | 官方 API 文档 | A | https://www.volcengine.com/docs/82379/1824137 |
| CreateContentsGenerationsTasks API | 官方 API 参考 | A | https://api.volcengine.com/api-docs/view?action=CreateContentsGenerationsTasks&version=2024-01-01&serviceCode=ark |
| 火山剧创产品页 | 官方产品页 | B | https://www.volcengine.com/product/dramart |
| ArkClaw 短剧制作最佳实践 | 官方开发者文章 | A | https://developer.volcengine.com/articles/7629571084442861606 |
| Seedance 2.0 介绍文章 | 官方开发者文章 | B | https://developer.volcengine.com/articles/7622325633040793641 |
| 快速入门（火山方舟） | 官方文档 | A | https://www.volcengine.com/docs/82379/1399008 |
| 兼容 OpenAI SDK | 官方文档 | A | https://www.volcengine.com/docs/82379/1330626 |
| Seedance 2.x 效果问题上报 API | 官方 API 文档 | A | https://www.volcengine.com/docs/82379/2389900 |

---

## 八、未解决问题（供其他 Agent 审核）

1. **API 请求体精确字段**：API 文档页面为 SPA 渲染，未能完整抓取请求/响应的完整字段定义。需要通过实际调用或 SDK 文档补充。
2. **参考图生视频 vs 参考视频生视频的 API 差异**：两者都通过 content 数组传不同类型输入，但具体参数差异需确认。
3. **Seedream 5.0 的精确参数**：size 选项、style 预设、seed 参数是否支持需确认。
4. **子 Agent 调度机制**：`marketing_invoke_agent` 工具的设计是否是最优方案？是否应该用 Hermes 原生的 sub-agent 机制？
5. **风格一致性的技术实现**：跨镜头角色一致性的具体实现方式（seed 固定 / 参考图 / LoRA 微调）需要实验验证。
6. **成本估算**：Seedance 2.0 和 Seedream 5.0 的调用成本，按一条 60s 视频（约 12 个 5s 镜头）估算。
7. **异步任务崩溃恢复的边界**：进程崩溃后恢复轮询的超时策略和清理策略。
