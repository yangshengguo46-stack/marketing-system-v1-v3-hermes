# Marketing OS Desktop

这是 Marketing OS 唯一桌面应用源码。它直接从 Hermes Desktop 演化，复用 Hermes 原生会话、长任务、工具中间件、审批、记忆、Skill、MCP、Plugin、消息渠道和设置体系；账号经营、证据、内容、发布、指标与学习能力在同一源码树内原生增强。

## 所有权原则

1. Hermes 已有且更成熟的能力直接复用，不再建立 Marketing adapter、bridge 或第二套状态仓。
2. Hermes 有缺口时修改或重写原 owner，不从外层壳反向接管 Agent。
3. 只有 Hermes 确实没有的营销领域能力，才在 `marketing_os/` 原生 domain 中新增。
4. 根仓库旧 `src/`、`electron/` 只作为迁移素材，不是可启动或可打包的第二个产品。

## 开发

从 Marketing OS 根目录运行：

```bash
npm run runtime:bootstrap
npm run dev
```

也可以在本目录运行：

```bash
npm run dev
npm run typecheck
npm run lint
npm run test:desktop:platforms
npm run build
```

## 打包

```bash
npm run dist:mac
npm run dist:win
npm run dist:linux
```

当前安装包仍继承 Hermes 的薄安装器机制，首次运行会安装受固定 commit 约束的 Agent runtime。它尚未满足“干净电脑、断网、无全局 Python/Node/Hermes 也能启动”的最终交付门；这一点必须在发布 v0.1 前通过内嵌运行时和真实干净机验收解决，不能用结构测试冒充完成。

产品架构和删除门以根仓库 `docs/architecture/REBUILD_BASELINE.md` 与 `docs/ledgers/00-current-product-status.md` 为准。
