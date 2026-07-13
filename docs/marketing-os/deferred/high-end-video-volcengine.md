# 高级视频引擎已迁出

多 Agent 高级视频产品已经迁入独立仓库：

- 本地目录：`/Users/yangyucheng/projects/video-studio`
- 架构与执行记录：`docs/architecture-and-execution-ledger.md`
- Provider 与生态研究：`docs/research/`

Marketing OS 不再拥有 `video_core`、`video_runtime`、`video_agents`、视频
Studio UI 或视频 Provider 状态机。后续若恢复营销接入，只能作为可选 host
adapter 消费独立产品的 Port/API，不得在营销仓库复制引擎状态、Agent 调度、
预算、审批、任务或项目画布。
