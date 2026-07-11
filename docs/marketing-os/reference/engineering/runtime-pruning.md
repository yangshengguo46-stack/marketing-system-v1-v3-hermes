# Hermes → Marketing OS 产品化裁剪基线

> 日期：2026-07-11  
> 状态：audit complete / implementation pending  
> 原则：先缩首包和默认能力，再删除源码；任何删除必须有真实 import、构建和端到端证据。

## 一、结论

Hermes 的 Agent 核心并不构成主要体积。当前“太大”来自三类不同问题，不能混为一谈：

1. **开发工作区大**：`node_modules`、`.venv`、`.git` 合计约 1.67GB，但不会原样交付用户。
2. **产品运行时打包过宽**：当前 staging 复制开发 `.venv` 的全部 site-packages，导致测试工具、Google、Discord、Telegram、Slack 等与首版无关的依赖进入安装包。
3. **上游仓库附带面广**：官网、生成的 PR 信息图、TUI、Docker/Nix/Termux、通用平台与可选 Skill 让源码仓库显得庞大，但其中多数未进入桌面安装包。

所以第一刀不是删 Agent，而是建立 **Marketing OS Runtime Profile**。源码可以保留上游生态和未来能力，首包只带当前产品必需能力；需要时再通过受控渠道包、Skill 或 Plugin 更新扩展。

## 二、实测体积

| 对象 | 实测体积 | 说明 |
|---|---:|---|
| Git 跟踪内容 | 172MB / 5842 文件 | 包含测试、官网、生成图片、所有平台与生态源码 |
| 开发 `node_modules` | 约 1.0GB | 不应进入安装包 |
| 开发 `.venv` | 约 343MB | 当前含 dev、Google 和多消息平台依赖 |
| `.git` | 约 331MB | 用户安装包不包含 |
| 当前 staged 产品运行时 | **447MB** | Python 103MB + site-packages 304MB + Agent 源码 40MB |
| 精简核心渠道运行时依赖 | **88MB** | Web、MCP、Firecrawl、Edge TTS、微信所需 aiohttp/qrcode/python-socks |
| 精简核心 + 飞书依赖 | **139MB** | 飞书 SDK 额外约 51MB |
| 预计核心 staged runtime | 约 231MB | Python 103MB + 依赖 88MB + Agent 源码 40MB |
| 预计核心 + 飞书 staged runtime | 约 282MB | 尚未计算 Electron 壳和压缩收益 |

当前最大的错误依赖：

- `googleapiclient` 109MB：首版不需要。
- `lark_oapi` 43MB + `Crypto` 5.3MB：飞书连接需要，但适合评估为独立渠道包。
- `debugpy` 17MB、setuptools/测试依赖：绝不能进入正式运行时。
- Discord、Telegram、Slack SDK：首版不交付这些渠道，不应随首包安装。

## 三、不可裁剪红线

### 3.1 唯一 Agent 与长期经营能力

必须保留：

- `run_agent.py`、`agent/`、`model_tools.py`、`toolsets.py`
- `hermes_state.py`、SessionDB、conversation loop、prompt caching、compression
- 长任务、checkpoint、interrupt/resume、approval/effect、cron
- memory、Skill、MCP、Plugin 的原生合同
- `gateway/` 的核心 session、授权、事件、消息与渠道注册机制
- `agent/marketing/` 中的原生账号经营与内容能力

### 3.2 代码能力与代码生成视觉

代码能力必须完整保留，它既服务工程任务，也服务内容生产的代码生成素材：

```text
read_file / write_file / patch / search_files
  → terminal / process
  → execute_code
  → browser / web / vision
  → p5.js / HyperFrames / Manim / SVG / Canvas / 信息图 Skill
  → 可复现图片、动态图表、UI 演示和视频 clip
```

必须保留：

- `tools/terminal_tool.py`、process、文件读写、patch 和搜索
- `tools/code_execution_tool.py` 及其安全边界
- `agent/coding_context.py`、子目录提示、LSP/代码上下文能力
- 浏览器、网页提取、视觉分析和图片生成接口
- `skills/software-development`
- `skills/creative/p5js`
- `skills/creative/baoyu-infographic`
- `skills/creative/manim-video`
- `skills/creative/excalidraw`
- `optional-skills/creative/hyperframes`，后续应提升为 Marketing OS 内容能力包

代码生成素材必须保存：

`source_code/template_id/props/render_engine/output_path/sha256/duration/resolution`

只保存最终 PNG/MP4 而不保存源码和参数，不算可复现内容资产。

### 3.3 桌面本体

必须保留：

- `apps/desktop`、`apps/shared`
- `tui_gateway`：当前桌面后端协议和流式会话仍依赖它，不能因名字含 TUI 就删除
- `web`/dashboard server 所需 Python 路径
- Electron 内置浏览器、终端、审批、安全存储和文件宿主能力

## 四、四级裁剪清单

### A. 首包必须包含

- Agent/harness、SessionDB、Gateway、Cron、Memory
- Marketing domains
- Desktop/Shared
- terminal/file/patch/execute_code/browser/web/vision
- MCP/Skill/Plugin loader
- DeepSeek/OpenAI-compatible Provider 主链
- 微信核心连接依赖
- Web dashboard、Firecrawl、基础 TTS
- 创作、研究、社交媒体、软件开发相关核心 Skill

### B. 源码保留，但不进入首包

- Google Workspace SDK
- Telegram、Discord、Slack、Matrix、Teams 等平台依赖
- 第三方 memory provider 依赖
- 大多数模型 Provider 的专用 SDK
- 高阶图片/视频 Provider SDK
- ML/MLOps、金融、区块链、支付、游戏等 optional Skill
- ACP、批处理训练与数据生成能力

这些能力继续以 Plugin/Skill/渠道包形式存在；用户实际启用时才安装依赖。

### C. 可删除的仓库资产候选

以下内容不影响桌面运行，但删除前仍需逐项清除引用并跑 upstream merge 演练：

- `infographic/`：约 60MB，主要是上游 PR/修复说明生成图片，不是信息图生成引擎；真正要保留的是 `baoyu-infographic` Skill。
- `website/`：约 26MB，上游官网源码；只需迁出仍被运行时读取的 model catalog 数据。
- `apps/bootstrap-installer`：自包含产品安装包验收后，旧 Hermes bootstrap 安装器应退役。
- 多语言上游 README、贡献指南和发布宣传资产。
- Docker/Nix/Termux 发布面：Marketing OS 不交付这些安装方式时可移到 upstream-only 分支。
- `optional-skills` 中与营销、研究、代码视觉无关的类别。

### D. 必须重构后才能裁剪

- `ui-tui`：桌面不需要终端 UI 本身，但 `hermes_cli` 和 dashboard 中仍存在构建/恢复路径，不能直接删除。
- `web`：需先区分远程 Web UI 与桌面依赖的 dashboard API。
- `plugins/platforms`：保留平台 ABC/registry，依赖和具体 adapter 改为渠道包。
- `plugins/model-providers`：保留 provider ABC、OpenAI-compatible 主链和已配置 Provider，其他实现延迟加载。
- `plugins/hermes-achievements`：约 3MB，与 Marketing OS 核心价值弱，需先确认桌面无入口再删除。
- 前端 icon/Markdown/diagram 工具：代码能力需要代码高亮、diff 和 Mermaid，但必须拆包、懒加载，不能整体删除。

## 五、前端体积与性能

桌面 production JS 当前约 26MB，并出现 `@tabler/icons-react` 6149 个 re-export 的构建警告。主要方向：

1. 图标改为可 tree-shake 的直接路径或 transform-imports。
2. Mermaid、Shiki、语言包、Diff 编辑器按消息类型动态加载。
3. 保留代码高亮、终端、Diff、Mermaid——这些属于代码能力和内容视觉能力，不因体积整体删除。
4. 将渠道设置、模型设置等低频页面拆成异步 chunk。

目标是缩短首屏解析时间，而不阉割 Agent 能力。

## 六、安全实施顺序

1. 修复并真实执行 `stage-product-runtime`，禁止只用 mock PythonInfo 的测试冒充通过。
2. 新建干净、锁定的 `marketing-os-runtime` 构建环境，禁止复制开发 `.venv`。
3. 定义首包 extras：Web、MCP、Firecrawl、基础 TTS、微信网络依赖；飞书做 bundled 与 channel pack 两档测试。
4. 运行根源码导入、dashboard 启动、真实 Agent、MCP、微信/飞书和代码执行 smoke。
5. 再调整 `SOURCE_DIRS`、Plugin/Skill allowlist。
6. 最后删除 `infographic/website/bootstrap-installer` 等仓库资产候选。
7. 每次裁剪后执行 upstream merge 演练，避免为了省几十 MB 让长期维护成本失控。

## 七、第一阶段目标

- staged Python/Agent runtime：447MB → **不高于 285MB（含飞书）**。
- 不含飞书核心 runtime：**不高于 235MB**。
- 正式包不得包含 debugpy、pytest、Google SDK、Discord、Telegram、Slack。
- 保留完整代码执行和代码生成视觉合同。
- 干净机无全局 Python/Node/Hermes 仍能对话、调用一个营销工具并生成一份代码视觉资产。
