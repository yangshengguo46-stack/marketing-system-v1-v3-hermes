# Playwright MCP 供应链固定记录

> 日期：2026-07-01 | MCP-02 交付物
> 基线版本：`@playwright/mcp@0.0.77`

## 一、来源与身份

| 属性 | 值 |
|---|---|
| 项目名 | `@playwright/mcp` |
| 固定版本 | `0.0.77` (exact, no range) |
| 上游仓库 | `https://github.com/microsoft/playwright-mcp` |
| npm 注册地址 | `https://registry.npmjs.org/@playwright/mcp/-/mcp-0.0.77.tgz` |
| 许可证 | Apache-2.0 |
| lockfile 完整性 | `sha512-vf3PmCdOWVvEc3Vmh8DVWvsbz6/rIGi+OG0cyC/2YTn10U8tZMHEiRG62LHdPTTf0qCjoS7/1mbyS5F0RHoTzQ==` |
| 本机 CLI 路径 | `node_modules/.bin/playwright-mcp` → `node_modules/@playwright/mcp/cli.js` |
| 本机 CLI 版本 | `Version 0.0.77` |
| 构建期安装命令 | `npm ci` (lockfile deterministic) |

## 二、依赖树

### 直接依赖

```
@playwright/mcp@0.0.77
  ├── playwright@1.62.0-alpha-2026-06-29
  └── (others resolved by lockfile)
```

### 关键传递依赖（来自 lockfile）

`package-lock.json` 中 `node_modules/@playwright/mcp` 的 `dependencies` 对象锁定了所有传递依赖的版本。完整列表见 lockfile。

## 三、禁止项

| 禁止 | 说明 |
|---|---|
| `npx @playwright/mcp` | 必须使用 `node_modules/.bin/playwright-mcp` 固定路径 |
| `npx -y @playwright/mcp@latest` | 禁止自动确认和自动最新版 |
| `npm install @playwright/mcp` 运行时 | 只能在构建/安装阶段执行 |
| 版本范围 `^` `~` `>` `<` | package.json 中必须是 `"0.0.77"` 精确固定 |
| 无 integrity 的包 | lockfile 必须包含 sha512 integrity |

## 四、构建期与运行时边界

### 构建/安装阶段

- `npm ci` 使用 lockfile 精确安装 `@playwright/mcp@0.0.77` 及其传递依赖。
- 浏览器二进制（Chromium）后续在构建阶段通过固定本地入口 `node_modules/.bin/playwright install chromium` 准备，路径在构建期固定。运行时使用 `--executable-path` 指向该路径；本任务未执行或验收该打包步骤。

### 运行时

- 启动命令：`node_modules/.bin/playwright-mcp`（固定本地路径）。
- **禁止运行时下载**：网络不可用、二进制缺失或版本不匹配均 fail closed。
- CLi 启动参数由 ADR-01 §4.3 定义。

### 浏览器二进制（属于 DESK-08，不在本任务假装完成）

- Chromium 二进制打包和分发由 `@playwright/mcp` 的 `playwright` 依赖提供。
- 构建期二进制安装的自动化、跨平台路径和打包策略由 DESK-08 处理。
- 本 MCP-02 只保证 `@playwright/mcp` npm 包本身的供应链完整性。

## 五、验证脚本

```bash
node scripts/verify-playwright-mcp.mjs
```

检查项目：
1. `package.json` 精确版本（无 ^/~/>/<）
2. `package-lock.json` 版本、resolved URL、integrity、license
3. 本地安装包版本与 license
4. CLI 二进制文件和 symlink 存在
5. `CLI --version` 返回 0.0.77
6. package.json scripts 中无 `npx`/`latest`/`-y` 等禁止模式

## 六、SBOM

`npm sbom --sbom-format cyclonedx` 因 `fsevents@2.3.3` optional dependency mismatch 当前无法完整生成（npm 已知问题）。复核者追加 `--omit=optional` 重跑仍返回 `ESBOMPROBLEMS`。该阻断必须在 DESK-08 前关闭，不能把 lockfile 摘要冒充完整 SBOM。

替代验证：
- `npm ls @playwright/mcp` 确认依赖树完整
- `verify-playwright-mcp.mjs` 确认 lockfile integrity、版本、许可证
- `npm audit --omit=dev` 确认 0 vulnerabilities

完整的 CycloneDX SBOM 将在 DESK-08 整体打包验收时重新生成。

## 七、升级与回滚

1. 变更 `package.json` 中 `@playwright/mcp` 版本号。
2. `npm install --package-lock-only` 重新生成 lockfile。
3. 运行 `node scripts/verify-playwright-mcp.mjs` 确认新版本完整性。
4. 核验上游 CHANGELOG、许可证变更和工具列表差异。
5. 更新本文件的版本号和 integrity。
6. 更新 `mcp-servers.json` 中 `source.package` 和 `source.sha256`。
7. 经复核后合并。
8. 回滚：恢复上一版本的 package.json + package-lock.json → `npm ci`。

## 八、验证结果（2026-07-01）

| 检查项 | 结果 |
|---|---|
| `scripts/verify-playwright-mcp.mjs` | ALL CHECKS PASSED |
| `npm audit --omit=dev` | 0 vulnerabilities |
| 真离线安装 `npm ci --offline --ignore-scripts`（隔离目录） | installed version: 0.0.77；复核者实际重跑通过 |
| CLI `--version` | Version 0.0.77 |
| 许可证 | Apache-2.0 |
| package.json 版本固定 | `"0.0.77"` (精确) |
| lockfile resolved | `registry.npmjs.org` |
| lockfile integrity | `sha512-...` 存在 |

### 未完成风险

- 浏览器二进制（Chromium）的打包、分发和离线验证属于 DESK-08，不在 MCP-02 完成范围内。
- `npm sbom --sbom-format cyclonedx` 因 fsevents optional dependency 问题无法完整生成（已知 npm 工具链限制），生成的 SBOM 文件不完整。
- 完整 SBOM 是延后交付，不是已完成项；必须在 DESK-08 前关闭。

## 九、Python MCP Client SDK

| 项目 | 固定值 |
|---|---|
| 包 | `mcp==1.26.0` |
| 许可证 | MIT |
| 后端声明 | `backend/requirements.txt` |
| Hermes Runtime 声明 | 上游 `hermes-agent[mcp]` extra |
| 构建闸门 | `scripts/build-backend.mjs` 在 PyInstaller 前核验版本与核心 import |
| 打包范围 | 仅 `mcp`、`mcp.client.stdio`、`mcp.shared.session`；不收集需要可选 `typer` 的 MCP CLI |

后端与 Hermes Runtime 两个虚拟环境均已实际导入 `ClientSession`、`StdioServerParameters`。PyInstaller 归档包含 `mcp-1.26.0`，打包后二进制健康启动通过。SDK 缺失或版本漂移时构建直接失败，运行时 Manager 返回 `mcp_sdk_unavailable`，均不自动下载。
