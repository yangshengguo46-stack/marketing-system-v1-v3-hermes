# 工作区清理与重塑台账（2026-07-08）

> 目的：把连续多模型开发后的脏工作区重新整理成可长期迭代的产品工程，而不是为了 `git status` 好看而误删有效资产。

## HYGIENE-01 当前判断

当前工作区“脏”的主要原因不是语法坏，而是多条产品线同时落地：

1. 桌面主架构：Agent Runtime、任务、记忆、账号生命周期、内容资产、发布审批、工作台 UI。
2. 数据/开源能力：MCP、Firecrawl、图库、供应链审计、秘密扫描。
3. 视频项目骨架：`engine/video_core` 与 `engine/video_agents`，按独立项目合同保留，不能计入桌面主架构完成度。
4. 资料库/台账：研究、ADR、执行台账数量变多，需要总控入口统一。
5. 本地生成产物：Playwright 日志、pycache、打包产物、backend build/dist。

## 本轮已清理

| 类别 | 路径 | 动作 | 说明 |
|---|---|---|---|
| 浏览器调试日志 | `.playwright-mcp/` | 删除 | 约 113M，本地 MCP 调试日志，可再生成 |
| Python 缓存 | `__pycache__/`、`*.pyc` | 删除 | 不含 `runtime/hermes-agent`、`.venv`、`node_modules` |
| 测试缓存 | `.pytest_cache/` 等 | 删除 | 可再生成 |
| 打包产物 | `release/` | 删除 | 约 1.4G，可通过 `npm run build:mac` 重建 |
| 后端构建产物 | `backend/build`、`backend/dist` | 删除 | 可通过 `npm run build:backend` 重建 |
| 忽略规则 | `.gitignore` | 强化 | 增加本地 runtime、缓存、日志和覆盖率忽略 |
| 清理入口 | `scripts/clean-local-artifacts.sh`、`npm run clean:local` | 新增 | 后续清理统一走脚本，不手工乱删 |
| 慢测试治理 | `scripts/dependency_audit.py` | 修正 | 依赖审计只使用本地 `license-checker`，无本地工具时快速降级，禁止 `npx` 隐式联网拖慢常规验证 |

## 保留/隔离/删除口径

| 分区 | 处理口径 | 代表路径 |
|---|---|---|
| 必须保留并继续收口 | 桌面智能体主链，属于当前产品身体 | `engine/agent_core/*`、`engine/marketing-os/server.py`、`src/components/AgentPanel.tsx`、`src/pages/Overview.tsx` |
| 必须保留但不扩张 | MCP/Firecrawl/图库/供应链等工具能力，只服务主链 | `engine/agent_core/mcp_*`、`marketing_tools/firecrawl_provider.py`、`scripts/secret_scanner.py` |
| 隔离保留 | 视频项目骨架，作为独立项目合同和未来接入点，不纳入桌面主架构完成度 | `engine/video_core/`、`engine/video_agents/`、`docs/ledgers/08-video-generation-volcano.md` |
| 保留为审计快照 | SBOM/许可证是交付证据，不是临时垃圾 | `docs/sbom/*.json` |
| 可随时删除 | 本地运行、测试、打包生成物 | `release/`、`backend/build/`、`.playwright-mcp/`、`__pycache__/` |

## 重塑后的工程边界

1. **一个 Agent runtime**：前端/用户只认 Marketing Agent Runtime；Hermes 是内部源码内核，不再当“插件”心智暴露。
2. **一个业务真相源**：`engine/agent_core` 保存任务、计划、记忆、内容资产、发布、复盘和账号生命周期。
3. **一个外部动作边界**：MCP/API/发布/浏览器都必须经工具网关、审批和 effect receipt；不能从 UI 直接绕。
4. **一个内容管线**：脚本/文案/图文/视频草稿进内容资产，不进长期记忆；长期记忆只存偏好、DNA、规律和可复用流程。
5. **视频独立但可接入**：视频 Web/引擎按 contract 接入内容资产；桌面主架构不因视频 stub 未完成而阻塞收口。
6. **资料库不冒充实现**：调研、开源候选、SBOM、ADR 都是决策证据；只有代码路径 + 自动化 + 真人验收才能算产品完成。

## 本轮继续收口（2026-07-08）

| 类别 | 动作 | 说明 |
|---|---|---|
| Renderer runtime 命名 | 移除当前 preload 暴露的 `api/hermes` 旧别名 | 主进程保留兼容 handler，当前 UI 不再呈现“插件壳”心智 |
| 账号同步入口 | 账号页改走 Electron main `account:sync(account_id)` | 前端只传 accountId，main 读取账号元数据后执行 MCP → Electron session fallback |
| 旧 session 直连 | 当前 preload 不再暴露 `session:scrape-industry`、`session:sync-account` | Agent 受控能力统一走 approval/effect host |
| 产品守门 | 新增 `tests/test_product_closure_guard.py` | 守住四入口导航、微博产品移除、视频隔离和 native runtime |
| 验证 | `tests/test_product_closure_guard.py tests/test_architecture_boundaries.py` + `npx tsc --noEmit` | 18 项测试与 TypeScript 通过 |

## 后续拆分建议

如果要把当前巨大的 dirty diff 收成可审查提交，建议按下面顺序拆：

1. `hygiene/docs-ledgers`：台账、研究、ADR、SBOM、清理脚本。
2. `runtime-agent-core`：Hermes bridge、tool gateway、store、plan/checkpoint、memory guard。
3. `account-content-loop`：账号生命周期、对标、定位、内容资产、发布/指标复盘。
4. `desktop-ui-shell`：工作台、新对话、历史会话、白天模式、账号管理图标与布局。
5. `video-contract-skeleton`：`engine/video_core`、`engine/video_agents`、视频测试，标记独立项目。
6. `delivery-security`：secret scanner、dependency audit、offline launch、MCP supply chain。

拆分时不得使用 `git reset --hard` 或全量 `git clean`；只能按上述分区移动、提交或删除。

## 本轮验证

- `npm run clean:local`
- `.venv/bin/python` 编译检查：`engine/agent_core`、`engine/marketing-os`、`engine/video_core`、`scripts`
- `npx tsc --noEmit`
- `git diff --check`
- `tests/test_desk_06_supply_chain.py`：20 passed，依赖审计测试不再触发慢速外部安装路径
- `tests/test_video_core_boundary.py tests/test_video_core_schema.py tests/test_secret_scanner.py`：53 passed

当前结论：工作区已清掉本地生成垃圾；剩余 dirty 主要是有效产品改动和需继续收口的新增模块。

## HYGIENE-02 未纳入 git 的真实模块体检（2026-07-08 追加）

这轮再次确认：当前 `git status` 里大量 `??` 不是“垃圾文件”，而是过去两天真实推进出来的产品模块。清理原则仍然是：源码、测试、台账、资料库保留；只清可再生成的缓存/构建产物。

| 模块 | 代表路径 | 体检动作 | 结论 |
|---|---|---|---|
| 账号生命周期 / 对标 / 受众画像 | `engine/agent_core/account_lifecycle.py`、`benchmark_discovery.py`、`audience_persona.py`、对应 `tests/test_*` | `.venv/bin/python -m pytest tests/test_account_lifecycle.py tests/test_benchmark_discovery.py tests/test_run21_benchmark_coldstart.py tests/test_run23_audience_persona.py -q` | 62 passed；真实模块，应纳入 git |
| 内容生产 / 资料飞轮 / 评分复盘 | `engine/agent_core/content_production.py`、`content_matrix.py`、`blind_eval.py`、`content_retro.py`、`content_rubric.py`、`content_bump.py` | `.venv/bin/python -m pytest tests/test_content_production.py tests/test_upgrade_content_matrix.py tests/test_run17_content_scoring.py tests/test_run18_blind_prediction.py tests/test_run19_retro_reconciliation.py tests/test_run20_rubric_bump.py tests/test_run22_cadence_buffer.py -q` | 已并入 156 passed 组；真实模块，应纳入 git |
| Firecrawl / 图库素材 | `engine/marketing-os/marketing_tools/firecrawl_provider.py`、`stock_images.py` | 同 156 passed 组内 `tests/test_firecrawl_provider.py tests/test_stock_images.py` | 供应能力真实存在，但图库视频/Freesound 仍待扩展 |
| 视频框架 / 视频 Agent 骨架 | `engine/video_core/`、`engine/video_agents/`、`docs/ledgers/08-video-generation-volcano.md` | `.venv/bin/python -m pytest tests/test_video_core_boundary.py tests/test_video_core_schema.py ... -q` | 83 passed 组覆盖边界与 schema；作为独立项目合同保留，不计入主架构完成 |
| 交付安全 / 供应链 / 清理脚本 | `scripts/clean-local-artifacts.sh`、`secret_scanner.py`、`dependency_audit.py`、`docs/sbom/` | 同 83 passed 组内 `tests/test_desk_06_supply_chain.py tests/test_secret_scanner.py tests/test_product_closure_guard.py` | 属于交付证据和守门能力，应纳入 git |
| 台账 / 资料库 / ADR | `docs/ledgers/08-14*.md`、`docs/research/07-11*.md`、`docs/architecture/*.md` | 人工复核 + 路径归类 | 是产品决策证据，不删除 |

专项验证合计：

- 账号生命周期 / 对标 / 画像：62 passed
- 内容生产 / Firecrawl / 图库 / 数据飞轮：156 passed
- 视频合同 / 供应链 / 安全 / 产品守门：83 passed
- 合计：301 passed

本轮处理口径：

1. 不执行 `git clean -fd`，避免误删真实模块。
2. 统一使用 `npm run clean:local` 清理本地生成物。
3. 后续应按“台账/资料 → agent core → 内容生产 → 视频合同 → 交付安全 → UI”拆分提交，避免一个巨型提交不可审。
4. 内容生产不再按三条孤立管道组织，已在 `docs/ledgers/14-content-production-factory.md` 和 `engine/agent_core/content_production.py` 改成共享能力池架构。

## HYGIENE-03 工作区接管清理与暂存（2026-07-09 追加）

用户已明确：当前项目由 Codex 单 Agent 负责，不再为 Claude/GLM 的潜在改动保留脏状态；有用的测试后留下，没用的清理。

本轮执行口径：

1. 有代码路径、测试覆盖、台账/资料库依据的模块保留。
2. 本地抓取样本、抽帧、临时音频、e2e 视频、打包产物、PyInstaller 产物、pytest/python 缓存删除。
3. 保留下来的源码、测试、资料库和台账统一 `git add -A` 纳入暂存，避免继续以 `??` 形式散落。
4. 不提交；暂存区作为下一步拆分提交或整包审查的基线。

本轮删除/忽略：

| 路径 | 动作 | 原因 |
|---|---|---|
| `runtime/research/` | 删除并加入 `.gitignore` | 抖音样本视频、抽帧和 contact sheet，属于可再生成研究产物 |
| `runtime/e2e/` | 删除 | 端到端视频输出，属于本地验证产物 |
| `runtime/tts-smoke/` | 删除 | TTS 冒烟音频，台账保留结论即可 |
| `dist/`、`release/` | 删除 | 前端/Electron 打包产物，可由 `npm run build` 重建 |
| `backend/build/`、`backend/dist/`、`backend/*.spec` | 删除 | PyInstaller 构建产物，可重建 |
| `.pytest_cache/`、`__pycache__/` | 删除 | 测试/解释器缓存 |

本轮验证：

```text
npm run build
通过：后端 PyInstaller、前端 Vite、MCP runtime 准备、Electron mac zip/dmg 打包均完成；未签名为本机缺 Developer ID，属交付签名问题。

.venv/bin/python -m pytest -q
1261 passed, 1 warning in 88.63s

.venv/bin/python scripts/secret_scanner.py --help
✅ No secrets found in DB, events, logs, or traces.

git diff --check
通过
```

当前结论：

- 当前剩余变更不是“乱文件”，而是已测试通过的产品增量：主架构、账号生命周期、内容生产、记忆/回执/预演闭环、视频 core/agents、UI、交付安全和资料库。
- 工作区已经从“未跟踪散落状态”整理为“统一暂存、可审阅状态”。
- 下一步如果要继续压缩风险，应拆成多个提交；如果要快速建立新基线，可以直接审查暂存区后提交。
