# 智能营销桌面 Agent

面向长期账号运营的桌面智能体。Hermes 源码是唯一 Agent 主运行时；Marketing OS 的账号、趋势、内容、发布与学习能力直接增强 Hermes 的原生会话、任务、记忆、工具和渠道链路，不建立第二套 Agent。

## 目录边界

| 目录 | 责任 |
|---|---|
| `runtime/hermes-agent/` | Hermes 主运行时、原生桌面与 Marketing OS 增强源码；不存放业务数据 |
| `engine/marketing-os/` | 迁移期领域服务与旧 FastAPI，逐段并入 Hermes 原生能力边界 |
| `src/`、`electron/` | 冻结的旧桌面交互来源；根目录已无 Electron `main` 和打包配置，不再是可启动产品 |
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

根目录 `npm run dev / build / build:mac / build:win / preview` 全部转发到 `runtime/hermes-agent/apps/desktop`，不会再启动旧 React/FastAPI Agent 壳。源码 runtime 使用 `runtime/hermes-agent/.venv`。运行数据位于 `~/Library/Application Support/marketing-os-desktop/agent-runtime`，Hermes 原生模型凭据位于该目录的 `.env`，二者都不进入 Git。

## 验证

```bash
npm test
npm run runtime:verify
npm run build
```

研究结论和重建顺序从 `docs/research/README.md` 开始阅读。
