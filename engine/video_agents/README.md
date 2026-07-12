# video_agents — 剧组 8 角色定义包（纯资产，无 runtime 代码）

ADR v2 决策 7：多 Agent 是执行形态，SKILL 包是分发形态。
本包只含 SKILL.md 与工具声明，可装载到任意宿主：
- 营销系统模式：Hermes 主链加载 skills，子 Agent 由主链孵化
- 独立模式：随包轻量 runtime / 客户自带 Agent（MCP）

## 解耦纪律（架构回归测试强制）
- skills 只准引用画布（video_core/schema.py、edl.py）和 tools.json 声明的引擎工具
- 禁止引用 Hermes 私有 API、agent_core、营销系统表

## 角色清单
| 目录 | 角色 | 上下文隔离要求 |
|---|---|---|
| director/ | 导演：创意决策 + 反馈四级定位 | 只看画布状态，不看子 Agent 过程 |
| producer/ | 制片人：预算/批额/叫停，唯一花钱角色 | 独写 budget |
| screenwriter/ | 编剧：剧本 + 叙事结构 | 复用 screenwriting skills |
| editor/ | 剪辑师：时间线骨架先行 + 最终 EDL | 贯穿首尾 |
| art/ | 美术：资产库 best-of-k | 独写 assets[] |
| cinematographer/ | 摄影：按槽位规格生成镜头 | 只带分镜+资产，可多实例 |
| continuity/ | 场记：盲评 + 相邻镜头连续性 | 与生成者完全隔离 |
| sound/ | 音效师：TTS/音效/BGM 卡点 | 独写 tracks |

每个角色目录：`SKILL.md`（领域知识 + 评估标准 + 重试策略，待填）。
`tools.json`：引擎工具 function-call 声明（骨架已建，待 VIDEO-03/04/05 接口冻结后补全参数）。
