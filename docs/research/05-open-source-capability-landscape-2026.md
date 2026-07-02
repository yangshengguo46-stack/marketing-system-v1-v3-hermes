# 开源能力全景与采用边界（2026-07-01）

## 一、目的

本项目以后默认执行“先检索成熟开源实现，再决定采用、封装、参考或自研”。开源项目存在不等于可以直接进入产品：必须同时核验来源、许可证、维护状态、数据真实性、平台条款、秘密边界、多账号隔离和失败行为。

核验日期为 2026-07-01。星标和活跃度只用于发现候选，不作为采用依据；发布前还要重新核验固定 commit、依赖树和许可证。

## 二、采用等级

| 等级 | 含义 | 工程规则 |
|---|---|---|
| A 直接采用 | 官方或边界清楚，许可证兼容，能固定版本 | 固定版本/commit、最小权限、SBOM、回归测试 |
| B 封装采用 | 能力可用，但需 sidecar、适配器或额外隔离 | 不让业务层依赖其 schema；可一键停用和替换 |
| C 参考实现 | 架构/算法值得借鉴，但不复制代码或不进生产 | 记录借鉴点，独立实现并保留来源 |
| D 隔离 PoC | 来源、许可证、稳定性或合规尚不充分 | 默认禁用；测试账号、测试数据、不得打包交付 |
| X 不采用 | 安全、许可证、真实性或架构边界不满足 | 写明原因，避免以后重复踩坑 |

## 三、浏览器、MCP 与账号会话

| 项目 | 来源/许可证 | 可借能力 | 结论 |
|---|---|---|---|
| Microsoft Playwright MCP | `microsoft/playwright-mcp`，Apache-2.0，已固定 `@playwright/mcp@0.0.77` | 页面快照、导航、受控点击、等待、标签页；MCP 工具协议 | **A**。每个 `accountId` 独立进程和 `--user-data-dir`；首次 headed 登录，后续后台运行；禁止任意 JS、Cookie/storage-state 导出、文件上传和 DevTools |
| MCP reference servers | `modelcontextprotocol/servers`，各子项目许可证需单独核验 | stdio/HTTP 生命周期、工具发现、错误处理 | **C**。只参考协议实现，不批量安装社区 server |
| Playwright | `microsoft/playwright`，Apache-2.0 | browser context、trace、录像、网络等待 | **A/C**。由 MCP 间接使用；trace 只存脱敏测试数据 |
| Electron session | Electron 官方能力，MIT | 登录窗口、系统 Keychain/本机生命周期 | **保留**。作为产品 host；浏览器执行逐步迁往 account-scoped MCP，不承担 Agent 推理 |

关键决定：MCP 不是绕过登录。用户首次仍在官方页面扫码/验证码；改变的是登录后的自动化、观察、恢复和跨平台复用能力。

## 四、短视频与社交平台数据

| 项目 | 来源/许可证 | 能力与风险 | 结论 |
|---|---|---|---|
| MediaCrawler | `NanmiCoder/MediaCrawler`，GitHub 元数据无法确认标准许可证 | 抖音/小红书/快手/B站/微博/知乎采集；需要登录态且页面适配脆弱 | **C/D**。只研究平台适配、字段和失败模式；不复制、不打包、不接用户真实 Cookie |
| TikHub SDK/API | `TikHub/TikHub-API-Python-SDK`，Apache-2.0；服务端为第三方托管 | 多平台统一 API、搜索、详情、评论、趋势 | **B 候选**。只作为可选付费数据源；必须明确数据外发、费用、地区与来源，不成为唯一主链 |
| Douyin/TikTok Download API | `Evil0ctal/Douyin_TikTok_Download_API`，Apache-2.0 | 分享链接解析、公开媒体信息与下载 | **D**。仅限用户提供/公开链接 PoC；验证真实性、版权、限流与平台条款后再决定 |
| 抖音数据分析 MCP 候选 | `kk520879/undoom-douyin-data-analysis`，MIT，0.1.3 | 搜索与基础分析；无 account profile 注入、DOM 脆弱、部分指标固定/不完整 | **X/D**。不能直接用于产品结论，最多隔离 PoC |
| 抖音内容提取 MCP 候选 | `yangbuyiya/yby6-crawling-short-video-mcp`，MIT，1.0.2 | 分享链接解析、下载、转写 | **D**。stdout 可能破坏 MCP framing；转写会下载并外发音频，须 fork、拆权限和明确同意 |
| `douyin-chat-mcp-server` | 未找到可核验的唯一可信仓库 | 私信搜索、同步、回复的宣称无法验证 | **X**。保持禁用，不猜仓库 |
| yt-dlp | `yt-dlp/yt-dlp`，Unlicense | 多站点公开媒体元数据/下载 | **B**。只处理用户有权使用的链接；下载为 L1，来源、版权和落盘位置可见 |
| faster-whisper | `SYSTRAN/faster-whisper`，MIT | 本地音频转写，避免第三方外发 | **A/B**。优先作为桌面本地转写候选；模型包大小、CPU/GPU 和语言准确率需基准 |
| OpenAI Whisper | `openai/whisper`，MIT | 转写基线和模型 | **C**。作为准确率基线；桌面交付优先评估 faster-whisper |

## 五、热点、舆情与营销研究

| 项目 | 来源/许可证 | 可借能力 | 结论 |
|---|---|---|---|
| TrendRadar | `sansan0/TrendRadar`，GPL-3.0 | 多平台热榜、关键词过滤、报告、MCP、微信/飞书推送 | **C/B**。重点借鉴源健康、去重、时间窗、通知与报告；GPL 代码不复制进 MIT 桌面端，若 sidecar 使用先做许可证评审 |
| RSSHub | `DIYgod/RSSHub`，AGPL-3.0 | 大量站点路由、RSS 标准化、缓存 | **B/C**。可作为用户自行部署或远程可选源；不把其代码嵌入桌面包，不把单一路由当稳定事实源 |
| HotTopics/Bilibili 当前实现 | 本项目 | 公共热点聚合、跨平台均衡、缓存降级 | **保留**。升级为 source adapter + evidence contract；MCP 登录态数据是增强源，不是公共主链前置条件 |
| promptfoo | `promptfoo/promptfoo`，MIT | Agent/RAG 回归、红队、模型比较 | **A**。用于行业简报、证据引用、拒答和提示注入评测；不接生产用户秘密 |
| Langfuse | `langfuse/langfuse`，仓库许可证组成需逐项核验 | trace、dataset、eval、成本与延迟 | **B/C**。先定义本地可观测事件；是否 self-host 另做许可证和运维评估 |

营销研究输出必须保留 `source_url/source_platform/collected_at/query/account_scope/backend/confidence`，模型不能把搜索摘要伪装成平台事实。

## 六、Agent Runtime、长任务与审批

| 项目 | 来源/许可证 | 可借能力 | 结论 |
|---|---|---|---|
| Hermes Agent | 项目固定上游源码 | Agent loop、session、tools、skills、cron、delegation | **A + 自有 adapter**。继续作为唯一 Agent Runtime，不建立第二套智能体 |
| LangGraph | `langchain-ai/langgraph`，MIT | checkpoint、interrupt、durable execution、状态图 | **C**。借鉴 checkpoint/interruption 语义；不替换 Hermes，不让业务状态依赖 LangGraph schema |
| Temporal | `temporalio/temporal`，MIT | durable workflow、activity retry、idempotency、timer | **C**。借鉴 activity/effect/重试分类；桌面第一版不引入独立集群 |
| OpenHands/同类 coding harness | 官方仓库需单独固定版本核验 | 事件流、工具审计、sandbox、长任务 UI | **C**。只借鉴 harness 体验，不开放系统级 coding 权限 |
| MCP | 开放协议 | 外部能力适配 | **A（协议）**。所有 server 必须经过 ProductMCPBroker、白名单和 L0-L4 policy，不直接暴露给模型 |

## 七、记忆、知识与自我学习

| 项目 | 来源/许可证 | 强项 | 结论 |
|---|---|---|---|
| Mem0 | `mem0ai/mem0`，Apache-2.0 | 记忆抽取、更新、用户 scope、图记忆扩展 | **C/D**。做离线对照 PoC；用户/账号/实验真相源仍由本地结构化模型掌握 |
| Letta | `letta-ai/letta`，Apache-2.0 | stateful agent、memory blocks、上下文自管理 | **C**。借鉴热记忆块与归档分层，不引入第二个 Agent runtime |
| Graphiti | `getzep/graphiti`，Apache-2.0 | 时态知识图、实体关系、事实失效与追溯 | **B/C（后期）**。适合平台规则和账号关系图；先证明 SQLite 结构化事实不足再引入图数据库 |
| LangMem | `langchain-ai/langmem`，MIT | 从对话抽取/更新长期记忆、后台管理 | **C/D**。用于比较抽取质量，不让框架直接写 verified memory |
| sqlite-vec | `asg017/sqlite-vec`，Apache-2.0 | 单机 SQLite 向量检索 | **A/B**。仅在结构化检索和 FTS 不够时启用；向量是索引，不是真相源 |
| Qdrant 等独立向量库 | 官方项目需部署服务 | 大规模向量检索 | **X（当前）**。桌面第一版规模不足以承担额外服务和迁移成本 |

记忆主链固定为 `event → pending candidate → evidence aggregation/conflict → verified/locked → scoped retrieval → user correction/forget`。任何框架只能替换其中的抽取或召回算法，不能跳过治理状态。

## 八、内容生产、发布与复盘

| 项目 | 来源/许可证 | 可借能力 | 结论 |
|---|---|---|---|
| Postiz | `gitroomhq/postiz-app`，AGPL-3.0 | 社交媒体排期、渠道 adapter、发布队列、指标 UI | **C**。借鉴 publication/channel adapter 和队列模型；不复制 AGPL 代码，且不能假设支持国内平台 |
| BrightBean Studio | `brightbeanxyz/brightbean-studio`，AGPL-3.0 | 多平台内容管理、排期、发布 | **C**。作为发布 UX 与 provider contract 参考 |
| ComfyUI | `Comfy-Org/ComfyUI`，许可证需发布前复核 | 图式生成工作流、模型节点生态 | **B/C（Web 视频）**。通过 Web capability contract 接入，不嵌入桌面 Agent runtime |
| Remotion | `remotion-dev/remotion`，许可证/商业条款需版本核验 | React 视频合成、模板化渲染 | **B/C（Web 视频）**。适合可重复模板与渲染队列，先核验商业许可 |
| OpenMontage | `calesthio/OpenMontage`，AGPL-3.0 | Agent 化视频生产流水线 | **C**。借鉴 pipeline、artifact 和人工检查点，不复制代码 |

真实发布必须经过 `intent → approval/grant → platform execution → post_id/receipt → scheduled metrics → experiment attribution → strategy candidate`，本地“success”不能冒充平台成功。

## 九、技能、评测与供应链

1. 技能规范优先兼容 Hermes 已有 Skill 形态；社区技能只作为输入材料，不能自动安装或继承权限。
2. 技能 promotion 固定为 `candidate → static scan → permission diff → redacted replay → user approve → version → rollout/rollback`。
3. MCP/npm/Python 依赖必须固定版本和 hash，生成 SBOM；禁止运行时 `latest`、`npx -y`、`uvx` 自动下载。
4. 每项开源采用都建立 ADR：解决的问题、替代方案、许可证、数据流、秘密、失败回退、卸载路径。
5. Prompt/Agent 回归至少覆盖：证据忠实、跨账号污染、记忆误写、提示注入、重复副作用、审批绕过、断网恢复。

## 十、当前采用清单

| 能力 | 当前决定 | 进入主链前置条件 |
|---|---|---|
| Playwright MCP | 已固定依赖，未启用 | account-scoped process manager + 双账号零串号 + 真人验证码接管 |
| 短视频登录态采集 | 自有产品能力经 MCP 执行 | 平台 adapter、证据 schema、DOM replay、限流与失效重登 |
| 公共热点 | 保留现有聚合，参考 TrendRadar/RSSHub | source contract、健康度、缓存、来源均衡、许可证边界 |
| 本地转写 | faster-whisper 候选 | 桌面性能/体积/中文准确率基准 |
| 记忆 | 自有结构化治理，参考 Mem0/Letta/Graphiti/LangMem | 真实反馈闭环与离线 eval 胜过当前基线 |
| 长任务 | 自有 AgentTask + Hermes，参考 LangGraph/Temporal | 确定性 checkpoint、跨重启、不重复 effect |
| 发布 | 自研 provider/effect contract，参考 Postiz | 官方/可控平台通道、真实 post ID、指标回收 |
| Agent 评测 | 引入 promptfoo 候选 | 建立脱敏数据集与 CI 阈值 |
| Web 视频 | capability contract，参考 ComfyUI/Remotion/OpenMontage | 单一 AgentTask/artifact/event 真相源 |

