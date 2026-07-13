# 高级视频引擎已迁出

多 Agent 高级视频产品已经迁入独立仓库：

- 本地目录：`/Users/yangyucheng/projects/video-studio`
- 架构与执行记录：`docs/architecture-and-execution-ledger.md`
- Provider 与生态研究：`docs/research/`

迁移验收（2026-07-13）：

- Marketing OS 原高阶视频提交父版本中的 26 个文件，在独立仓库中 `missing=0`；2 个内容一致，24 个已继续演进。
- 独立仓库后端 `111 passed, 1 skipped`，UI `4 passed`，TypeScript typecheck 与正式 build 通过。
- 独立仓库迁移提交：`d4ab50e`、`1fdf8af`、`dcbe598`。

Marketing OS 不再拥有 `video_core`、`video_runtime`、`video_agents`、视频
Studio UI 或视频 Provider 状态机。后续若恢复营销接入，只能作为可选 host
client 消费独立产品公开且稳定的 Port/API，不得在营销仓库复制引擎状态、
Agent 调度、预算、审批、任务或项目画布，也不得以兼容层重建第二套视频 owner。
