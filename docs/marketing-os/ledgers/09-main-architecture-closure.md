# 桌面智能体主架构收口台账（2026-07-03）

> 目标：先把营销桌面智能体的可信主骨架完工。视频生成已拆为独立项目，本台账只保留 Web/项目接口边界，不把视频实现计入完成度。

## 2026-07-08 Agent Runtime 原生边界收口

- 产品心智统一为：`用户操作 → Marketing Agent Runtime → Hermes 源码内核`。Hermes 继续作为内部推理源码运行时存在，但不再作为前端/用户可见的“插件”概念暴露。
- Renderer 到 Electron preload 优先调用 `runtimeApi / runtime:api`；`api / hermes:api` 保留为兼容别名，避免旧 UI 构建或测试链路中断。
- Electron 主进程状态事件改为同时广播 `runtime:status` 与旧 `hermes:status`；前端状态变量已从 `hermesStatus` 收口为 `runtimeStatus`。
- 前端对话区文案从 “Hermes 源码运行时 / Hermes 不可用” 调整为 “Agent Runtime 在线 / Agent Runtime 未连接”，避免用户误解为外接插件。
- 后端仍保留 `HermesAgentService` 内部类名：这是源码内核适配器，不代表产品 API 边界。当前 Python 端已直接 import `runtime/hermes-agent` 源码执行 Agent loop，不通过 Hermes CLI 跑主 Agent。
- 当前验证：`npx tsc --noEmit`；`pytest tests/test_architecture_boundaries.py tests/test_server.py -k "native_api_prefix or renderer_api_waits_for_backend_readiness"`。

## 2026-07-07 工作台信息架构收口（以当前代码为准）

- 主导航收口为工作台、新对话、内容工厂、账号管理；趋势、选题和数据分析并入工作台，发布能力并入内容工厂，自动化不再占主导航；历史会话在左侧常驻，记忆治理隐藏到顶部“研究数据源”入口。
- 应用主结构改为“可折叠导航 / 业务工作台或新对话”；AgentPanel 只在“新对话”中出现，其它业务页不再保留巨大对话框。
- 工作台新增按真实已连接账号动态生成的数据罗盘：涨粉、浏览量、粉丝、点赞和近 30 天历史快照；一个平台只显示一个，多平台用多条颜色曲线；历史不足不生成假曲线。
- 趋势和选题改为工作台内的 1:1 信息流窗口，支持鼠标局部滚动和低干扰文字翻页。
- 账号“接管”改为“托管”，实际调用 MCP 后台模式，不再打开可见浏览器冒充全自动。
- 当前验证：工作台 UI 与对话会话增量修改已通过 `npx tsc --noEmit`、`npx vite build`、`git diff --check`；以 `12-product-closure-control.md` CLOSE-01/CLOSE-02 记录为准。

## 2026-07-07 接管修订

- GLM/Claude 既有改动可被修正、回退或合并，不再作为任务边界。
- 主架构不再继续横向扩项；后续只围绕真人经营闭环、稳定交付和代码/台账一致性修复。
- 发布中心、趋势中心、创意中心、自动化等旧主导航语义不再作为产品体验入口；旧路由如仍存在，只用于兼容或调试，用户主线以工作台、新对话、内容工厂和账号管理为准。

## 主架构完工口径

“主架构完成”指下面六条均有真实代码路径和自动化证据；不等于所有平台业务功能、真人验收、签名公证均完成。

1. Hermes 是唯一推理运行时，任务、计划、checkpoint、审批、effect 和恢复以本地持久状态为准。
2. 浏览器/MCP 按账号隔离，外部 MCP 只能经产品能力、审批和 effect 边界调用。
3. 记忆有类型、证据、scope、冲突、衰减、撤销；学习模块未接真实数据时不得冒充闭环。
4. 发布等副作用只能凭真实 receipt 成功；失败和未知结果不能记为 executed。
5. 数据库可从旧版本安全启动、备份、迁移和失败恢复；秘密不以明文长期保存。
6. 桌面端可全量测试、类型检查、构建；真人/干净机项目明确列为验收而非代码完成。

## 收口任务

| ID | 内容 | 完成证据 | 状态 |
|---|---|---|---|
| ARCH-01 | 任务/计划/checkpoint/replan 主链 | 结构化 plan、工具回调 checkpoint、跨进程恢复；replan 的线程等待已移出 asyncio 事件循环；前端竞态不再重复用户消息 | ✅ automated verified |
| ARCH-02 | Effect 真实性 | receipt 根据真实结果进入 executed/failed/unknown；未接发布 Provider 时明确失败，删除空 post ID 的假成功 | ✅ automated verified |
| ARCH-03 | 数据库升级主链 | `AgentCoreStore` 启动自动迁移；SQLite online backup 包含 WAL；事务迁移、无版本旧库接管、失败恢复均有测试；2026-07-03 真实用户库 v0→v9，`integrity_check=ok` 且备份存在 | ✅ automated + local data verified |
| ARCH-04 | 秘密与 renderer 边界 | Provider Key 自动迁移至 Electron safeStorage；主 renderer CSP+sandbox+导航/弹窗限制 | 🟡 自动化完成，桌面重启真人验收待做 |
| ARCH-05 | MCP 边界 | 原生 Playwright MCP 按账号隔离；外部 MCP 有调用超时且只作为可替换下游 | 🟡 外部桥仍应迁移到官方 MCP SDK；不阻塞原生登录/采集主链 |
| ARCH-06 | 记忆治理主链 | typed event、candidate、晋升、冲突、衰减、scope 检索已有 | 🟡 MEM-02/06/07 尚需真实工作流与 UI 验收 |
| ARCH-07 | 数据飞轮接口 | 内容资产、评分、预测、复盘、cadence、persona 数据底座已有 | 🟡 主链已接：Agent 内容评审→评分/预测→发布节奏→指标复盘→pending 结果记忆；真实发布/指标 Provider、persona 合规评论入口、rubric 独立审核仍待接 |
| ARCH-08 | 桌面交付 | 全量 pytest、TypeScript、Electron syntax、Vite/PyInstaller 构建 | 🟡 自动化完成后仍需断网干净机、签名、公证 |

## 今天剩余的阻塞清单

1. 跑全量测试、后端与前端构建，处理新增改动回归。
2. 用当前桌面 App 重启一次，真人确认 API Key 明文迁移后模型仍可对话。
3. 真人执行一次：长任务启动 → 中途改目标 → 关闭/重启 → 从 checkpoint 恢复。
4. 真人执行一次：双抖音账号切换、热点采集，确认无串号。

完成 1 后可称“主架构代码收口”；完成 2~4 后可称“主架构真人验收收口”。签名、公证、真实发布和指标飞轮属于后续产品交付，不伪装成今天已完成。

## 2026-07-04 收口结果

- **主架构代码已收口。** 全量 1107 项、TypeScript、Electron syntax、PyInstaller、Vite、MCP runtime、macOS zip/DMG 构建通过。
- 账号生命周期 v0.1 已冻结，不再扩能力面；详见 `10-account-lifecycle.md` 的收口冻结线。
- 真实用户库已由 v11 安全升级至 v17，备份存在且 integrity check 通过。
- 当前只进入真人 smoke 与缺陷修复阶段，不再以新功能延后收口。
- 2026-07-04 交付线新增安全媒体附件后，真实用户库由 v17 升级至 v18；主架构冻结边界不变。
- 2026-07-07 后的新增发布、指标、素材和工作台 UI 调整统一进入稳定交付台账与产品收口总控，不再改写“主架构已收口”的完成口径。
