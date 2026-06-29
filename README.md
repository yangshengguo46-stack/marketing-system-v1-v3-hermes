# 智能营销桌面 Agent

面向长期账号运营的桌面智能体。Electron/React 提供账号、趋势、选题、任务与审批界面；营销引擎提供结构化业务能力；Hermes 源码作为可裁剪的 Agent Runtime，而不是外置 CLI 依赖。

## 目录边界

| 目录 | 责任 |
|---|---|
| `src/` | React 产品界面 |
| `electron/` | 桌面生命周期、平台登录会话、安全边界与 IPC |
| `engine/marketing-os/` | 本项目自己的 FastAPI、营销工具和技能源码 |
| `runtime/hermes-agent/` | 官方 Hermes 上游源码工作副本，不存放业务数据 |
| `backend/` | Python 后端打包配置与构建产物目录 |
| `docs/research/` | Agent memory、harness 与长期学习资料库 |
| `tests/` | 营销引擎和桌面契约测试 |

用户数据、登录态、API Key 和 Agent 记忆必须写入应用数据目录，不得写回源码树。项目决策以 `LEDGER.md`、`AGENT_CORE_LEDGER.md` 和 `docs/research/` 为准。

## 本地启动

```bash
npm run runtime:bootstrap
npm run runtime:status
npm run dev
```

源码 runtime 使用 `runtime/hermes-agent/.venv`。运行数据位于 `~/Library/Application Support/marketing-os-desktop/agent-runtime`，模型凭据位于同级 `secrets/providers.env`，二者都不进入 Git。

## 验证

```bash
npm test
npx vite build
```

研究结论和重建顺序从 `docs/research/README.md` 开始阅读。
