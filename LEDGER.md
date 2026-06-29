# 智能营销系统 — 项目台账

> 最后更新: 2026-06-29
>
> 状态口径：`✅ done` = 已完成且有验证；`🟡 partial` = 有代码但未形成完整可用闭环；`🔴 blocked` = 阻断真实交付；`⏳ pending` = 尚未实现。视频生成/制作模块不纳入本轮交付缺口审计。
>
> 智能体内核、长期任务、记忆、技能与账号运营知识系统的专项台账见 `AGENT_CORE_LEDGER.md`。
>
> 2026-06-29 起，营销引擎源码已从用户级 `~/.hermes/plugins/marketing-os` 收回项目内 `engine/marketing-os`；官方 Hermes 源码基线位于 `runtime/hermes-agent`，两者不再混放。

## 一、组件清单

### A. 前端 (Electron + React + Tailwind v4)

| ID | 组件 | 文件 | 状态 | 依赖 | 备注 |
|----|------|------|------|------|------|
| FE-01 | Electron 主进程 | `electron/main.js` | ✅ done | - | Hermes 生命周期/spawn/health |
| FE-02 | IPC 桥接 | `electron/preload.js` | ✅ done | FE-01 | contextBridge 安全暴露 |
| FE-03 | 侧边栏导航 | `src/components/Sidebar.tsx` | ✅ done | FE-02 | 引擎状态指示灯 |
| FE-04 | 营销主控台 | `src/pages/Overview.tsx` | ✅ done | FE-02 | 4 统计卡片 + 快捷操作 |
| FE-05 | 热点趋势 | `src/pages/Trending.tsx` | 🟡 partial | BE-01 | 页面与缓存完成；登录态行业采集仅支持抖音，真实网络链路待验收 |
| FE-06 | 账号管理 | `src/pages/Accounts.tsx` | 🟡 partial | BE-03 | 登录入口与元信息 CRUD 完成；缺会话过期检测、多账号隔离和真正注销 |
| FE-07 | 选题建议 | `src/pages/Suggestions.tsx` | 🟡 partial | BE-02 | 展示与加入任务完成；当前建议主要由规则模板生成 |
| FE-08 | 创作工作台 | `src/pages/Creator.tsx` | ✅ placeholder | - | ACP 接口预留 |
| FE-09 | Electron 打包 | `package.json` build | 🟡 partial | 全部 | macOS DMG/ZIP 可构建；未签名/公证，未内置精简 Hermes 网关，Windows 未验证 |
| FE-10 | 发布任务 | `src/pages/Operations.tsx` | 🟡 partial | BE-05 | 仅本机任务看板；缺状态流转、预览、审批、实际发布和失败重试 |
| FE-11 | 数据分析 | `src/pages/Operations.tsx` | 🟡 partial | BE-05 | 不展示演示数据；但发布指标没有采集/写入链路，日趋势为空 |
| FE-12 | 自动化控制 | `src/pages/Operations.tsx` | 🟡 partial | BE-01/02 | 手动/定时编排完成；关闭窗口后后端停止，不能持续后台运行 |
| FE-13 | Hermes 营销助手 | `src/components/AgentPanel.tsx` | 🟡 partial | Hermes CLI | 桌面只读问答完成；打包版仍依赖本机 Hermes CLI |
| FE-14 | Electron 登录态采集 | `electron/main.js` + `src/pages/Trending.tsx` | 🟡 partial | 抖音登录 | Cookie 不出 Electron；缺可靠登录校验、过期检测与验证码可见回退 |
| FE-15 | 智能巡检控制台 | `src/pages/Operations.tsx` | ✅ done | FE-14/BE-13 | 行业目标、实时步骤、证据、错误和降级来源 |
| FE-16 | 微信/飞书随身助手 | `electron/channel_bridge.py` + `src/pages/Accounts.tsx` | 🟡 partial | Hermes gateway | 扫码、自动绑定、送达记录和重试代码完成；数据目录待统一，真人扫码收发未验收 |

### B. 后端引擎 (Hermes plugin)

| ID | 组件 | 文件 | 状态 | 依赖 | 备注 |
|----|------|------|------|------|------|
| BE-01 | 热点抓取工具 | `tools/scraping.py` | 🟡 partial | 4 backends | 可插拔后端架构完成；多个真实后端仍依赖外部安装/网络 |
| BE-01a | Agent-Reach 后端 | `tools/scraping_backends/agent_reach.py` | ✅ done | pip install | 最高优先级 |
| BE-01b | HotTopicsAPI 后端 | `tools/scraping_backends/hot_topics_api.py` | ✅ done | 免费API | 无需登录 |
| BE-01c | MediaCrawler 后端 | `tools/scraping_backends/mediacrawler.py` | ⏳ 待clone | GitHub | 网络就绪后激活 |
| BE-01d | BrowserCDP 后端 | `tools/scraping_backends/browser_cdp.py` | ✅ done | agent-browser | 兜底方案 |
| BE-01e | 后端注册/路由 | `tools/scraping_backends/__init__.py` | ✅ done | - | 优先级链 |
| BE-02 | 内容分析工具 | `tools/content.py` | 🟡 partial | BE-01 | 当前为前五字去重、关键词分类和固定角度模板，尚非模型驱动分析 |
| BE-03 | 账号管理工具 | `tools/account.py` | 🟡 partial | Bitwarden | 元信息 CRUD 完成；Bitwarden 未联调，监控覆盖有限 |
| BE-04 | 插件注册入口 | `__init__.py` | ✅ done | BE-01/02/03 | register_tool/hook |
| BE-05 | Desktop API | `server.py` | ✅ done | BE-01/02/03 | 真实 CRUD、缓存、画像、发布、分析、工作流接口 |
| BE-11 | 后台调度器 | `server.py` lifespan | 🟡 partial | BE-01/02 | 并发锁与状态持久化完成；Electron 模式由主进程调度，窗口关闭后停止 |
| BE-12 | 账号指标同步 | Electron session + `server.py` | ✅ partial | 已登录会话 | 抖音/B站复用 Electron 登录态；其余平台可通过指标接口写入 |
| BE-13 | 统一智能巡检 | `electron/main.js` orchestrator | 🟡 partial | BE-01/02/05/12 | 编排与真实失败报告完成；采集覆盖、后台常驻和真实端到端数据待补 |
| BE-14 | 跨端营销上下文 | `tools/monitor.py` | 🔴 blocked | BE-13 | 工具完成；打包版 App 数据目录与 Hermes 默认读取目录不一致 |
| BE-06 | Skill: 热点抓取 | `skills/hot-topic-scraper.md` | ✅ done | BE-01 | 后端架构已更新 |
| BE-07 | Skill: 趋势分析 | `skills/trend-analyzer.md` | ✅ done | - | |
| BE-08 | Skill: 内容建议 | `skills/content-suggester.md` | ✅ done | - | |
| BE-09 | Skill: 账号监控 | `skills/account-monitor.md` | ✅ done | - | |
| BE-10 | 用户画像 | `config/user-profiles.yaml` | ✅ done | - | 默认科技创业者画像 |

### C. 外部集成

| ID | 组件 | 方式 | 状态 | 备注 |
|----|------|------|------|------|
| EXT-01 | MediaCrawlerPro | MCP server 接入 | 🔧 待接入 | 替换手写 agent-browser 抓取 |
| EXT-02 | Bitwarden | bw CLI | ⚠️ 未联调 | 账号凭据加密存储 |
| EXT-03 | aPaaS 短视频 | ACP 协议 | ⏳ 预留 | 创作智能体接入点 |
| EXT-04 | FireRed-OpenStoryline | MCP (备选) | ⏳ 预留 | 备用视频生成方案 |
| EXT-05 | Hermes 微信/飞书网关 | iLink QR / Feishu device QR | 🟡 partial | 桌面端不接触明文密钥；代码已接入，真人扫码、收发和重连待验收 |
| EXT-06 | Web 视频工作台 | `VIDEO_WEB_CONTRACT.md` | 📐 contract | 已冻结项目、任务、认证和事件契约；暂不实现 Web 生成能力 |

### D. 智能体分工 (Sub-agent Persona)

| ID | Persona | Skill 文件 | 职责 | 状态 |
|----|---------|-----------|------|------|
| AGT-01 | Researcher | `skills/researcher-persona.md` | 热点抓取 + 趋势分析 | ✅ done |
| AGT-02 | Writer | `skills/writer-persona.md` | 选题角度 + 脚本生成 | ✅ done |
| AGT-03 | SocialOp | `skills/socialop-persona.md` | 账号监控 + 异常告警 | ✅ done |
| AGT-04 | CreativeAI | 预留 | 视频生成 (外部 aPaaS) | ⏳ 预留 |

---

## 二、接口契约

### Hermes Plugin → Electron App

```
POST /api/plugins/marketing-os/dashboard/overview
GET  /api/plugins/marketing-os/trending
POST /api/plugins/marketing-os/trending/refresh
GET  /api/plugins/marketing-os/accounts
POST /api/plugins/marketing-os/accounts
DELETE /api/plugins/marketing-os/accounts/:id
GET  /api/plugins/marketing-os/suggestions
GET  /api/plugins/marketing-os/profiles
PUT  /api/plugins/marketing-os/profiles/:id
```

### MediaCrawlerPro → Hermes (MCP)

```
工具: scrape_trending(platform, count)
平台: douyin / weibo / bilibili / kuaishou / zhihu
输出: [{rank, title, heat_value, url, scraped_at}]
```

### ACP → aPaaS (预留)

```
JSON-RPC: initialize → new_session → prompt → session/update → close
输入: {topic, platform, duration, style}
输出: {video_url, thumbnail, metadata}
```

---

## 三、Cron 任务清单

| 任务 | 表达式 | Skill | 状态 |
|------|--------|-------|------|
| 每日热点营销分析 | `3 8 * * *` | scraper + analyzer + suggester | ⚠️ 未部署 |
| 账号数据监控 | `7 9,18 * * *` | account-monitor | ⚠️ 未部署 |
| 午间热点速报 | `17 12 * * *` | hot-topic-scraper | ⚠️ 未部署 |

---

## 四、测试覆盖

| 模块 | 测试文件 | 用例数 | 状态 |
|------|---------|--------|------|
| tools/scraping.py | `tests/test_scraping.py` | 10 | ✅ 10/10 |
| tools/account.py | `tests/test_account.py` | 12 | ✅ 12/12 |
| tools/content.py | `tests/test_content.py` | 12 | ✅ 12/12 |
| tools/scraping_backends | (同上) | 2 | ✅ 2/2 |
| dashboard/plugin_api.py | `tests/test_api.py` | 8 | ✅ 8/8 |
| 集成测试 | `tests/test_integration.py` | 4 | ✅ 3/3 (1 skip) |
| Electron + standalone backend | `tests/test_server.py` | 6 | ✅ 6/6 |
| **最近一次全量测试** | | **89** | **88 passed, 1 skipped** |

---

## 五、风险与遗留问题

| ID | 风险 | 级别 | 应对 |
|----|------|------|------|
| RISK-01 | 抖音反爬升级导致 MediaCrawlerPro 失效 | 高 | SmartAgent 作备选，CDP 模式兜底 |
| RISK-02 | Hermes v0.17 plugin API 签名变化 | 中 | 升级后验证 register() 参数 |
| RISK-03 | Bitwarden CLI 环境依赖复杂 | 低 | 可降级为加密文件存储 |
| RISK-04 | Electron 打包后端路径问题 | 已解决 | PyInstaller 独立后端已随 DMG 打包并实机启动验证 |
| RISK-05 | aPaaS 接口规范未确定 | 低 | ACP 通用协议，适配成本可控 |
| RISK-06 | macOS 安装包未使用 Developer ID 签名/公证 | 高 | 发布给其他用户前配置 Apple Developer 签名与 notarization |
| RISK-07 | 抖音页面 DOM 或反爬策略变化 | 中 | Electron 会话保留登录态；选择器失效时需要更新采集适配器 |
| RISK-08 | 系统代理不可用会阻止平台登录/采集 | 中 | 前端返回明确代理错误；使用前确认本机代理或直连网络可用 |
| RISK-09 | 固定端口本机 API 的访问边界 | 中 | 随机访问令牌已完成；仍需处理端口冲突和补充渗透测试 |
| RISK-10 | App 数据与 Agent Runtime 数据目录分离 | 已缓解 | 统一到 `~/Library/Application Support/marketing-os-desktop` 下的 config/agent-runtime/secrets，并由 Electron 显式传递 |
| RISK-11 | 安装包依赖外部 Hermes/Python 运行时 | 高 | 官方源码 runtime 已纳入项目并完成开发态验证；仍需精简后随安装包交付 |

---

## 六、交付缺口台账（不含视频模块）

### P0：阻断真实试用或造成错误认知

| ID | 缺口 | 当前证据/现状 | 完成标准 | 状态 |
|----|------|---------------|----------|------|
| GAP-P0-01 | 统一桌面与 Hermes 数据目录 | Electron 已将规范数据目录传给 FastAPI 和扫码桥，并写入 Hermes 环境；待打包版联调 | 桌面、FastAPI、Hermes 网关读写同一份账号、趋势、选题和巡检报告；增加打包版集成测试 | 🟡 partial |
| GAP-P0-02 | 精简 Hermes 网关运行时 | 官方 0.17.0 源码和独立 `.venv` 已进入 `runtime/hermes-agent`，Electron 开发态直接调用；尚未裁剪、打入安装包 | 未安装 Hermes 的干净 macOS 机器可直接扫码、收发消息和调用营销工具 | 🟡 partial |
| GAP-P0-03 | 真正后台常驻 | 已增加托盘与显式退出；关闭主窗口不再停止 FastAPI 和定时器；缺开机启动和独立守护 | 关闭窗口后托盘/后台服务继续巡检和推送；支持开机启动、崩溃拉起和明确退出 | 🟡 partial |
| GAP-P0-04 | 可靠登录与会话健康 | 当前以域名、Cookie 数量和通用 DOM 猜测登录；所有账号前端固定显示“在线” | 平台级登录校验；区分在线/过期/验证码/网络异常；可重新授权并保留审计时间 | 🔴 blocked |
| GAP-P0-05 | 网络、代理和验证码自检 | 仅在隐藏窗口捕获部分代理错误；没有统一诊断页 | 一键检测 DNS/代理/目标站点/网关/模型；验证码时切回可见窗口并继续任务 | ⏳ pending |
| GAP-P0-06 | 本机 API 安全 | Electron 每次启动生成随机令牌，FastAPI 对 `/api/*` 使用常量时间校验；已移除开放 CORS；端口仍固定 | 每次安装生成本机令牌；Electron 请求携带令牌；限制 Origin；端口冲突可自动迁移 | 🟡 partial |
| GAP-P0-07 | 真人端到端验收 | 单元/接口测试通过，但微信、飞书均未配置；真实缓存仍为 `no_data/never_run` | 抖音登录→行业采集→选题→定时巡检→微信/飞书推送→追问方案全链路留存证据 | ⏳ pending |
| GAP-P0-08 | 真实智能分析 | 当前采用前五字去重、关键词匹配、固定三角度模板和无数据依据的流量等级 | 使用模型结合行业、账号历史和来源证据推理；输出依据、置信度；数据不足时不做流量承诺 | 🟡 partial |

### P1：从控制台走向完整业务闭环

| ID | 缺口 | 当前证据/现状 | 完成标准 | 状态 |
|----|------|---------------|----------|------|
| GAP-P1-01 | 内容/发布状态机 | 发布 API 只有查询、创建、删除；看板卡片不能流转 | 支持草稿→审核→排期→发布→失败→重试；每次外部副作用需授权并记录审计 | 🟡 partial |
| GAP-P1-02 | 发布指标回收与归因 | 新任务 `metrics={}`，没有更新任务指标接口，`daily_views=[]` | 自动同步作品播放、互动、评论；关联选题、账号、发布时间并形成趋势曲线 | ⏳ pending |
| GAP-P1-03 | 账号作品列表与单条指标 | 当前只尝试同步账号级粉丝/点赞/播放 | 展示最近作品、单条指标和变化；异常可定位到具体内容 | ⏳ pending |
| GAP-P1-04 | 多平台采集与账号同步 | 登录入口很多；行业登录态采集仅抖音，账号会话同步仅抖音/B站 | UI 只展示真实支持能力；逐个平台完成适配、健康检查和回归样本 | 🟡 partial |
| GAP-P1-05 | 多账号隔离 | 同一平台只允许一张连接卡；所有账号共用 Electron `defaultSession` | 同平台多账号使用独立持久化 partition，明确切换与任务归属 | ⏳ pending |
| GAP-P1-06 | 彻底注销与数据清理 | 删除账号只删除元信息，不清理 Electron Cookie | 用户可选择移除记录、退出平台或彻底清理本地会话和凭据 | ⏳ pending |
| GAP-P1-07 | 用户画像设置 | 后端有 profile GET/PUT，前端没有编辑入口 | 用户可设置行业、受众、风格、禁区和目标；建议展示采用了哪些画像条件 | ⏳ pending |
| GAP-P1-08 | 消息渠道重连管理 | 已有状态、送达记录和失败重试；缺重新授权/解绑/切换通知会话 | 支持解绑、重新扫码、切换通知窗口、查看最近送达和网关健康 | 🟡 partial |
| GAP-P1-09 | 产品状态真实性 | 侧栏固定显示“7 个工具在线”，账号固定显示“在线” | 所有状态来自实时探测，不使用硬编码在线数字或状态 | ⏳ pending |

### P2：形成可学习、可规模化的产品

| ID | 缺口 | 当前证据/现状 | 完成标准 | 状态 |
|----|------|---------------|----------|------|
| GAP-P2-01 | 反馈学习闭环 | 未记录用户采纳/拒绝选题及原因 | 记录反馈并进入后续排序特征；可解释权重变化 | ⏳ pending |
| GAP-P2-02 | 多账号差异化策略 | 所有账号共享同一画像与建议逻辑 | 按账号历史表现、平台和受众生成不同策略 | ⏳ pending |
| GAP-P2-03 | 自动更新与版本迁移 | 无自动更新；配置迁移策略未建立 | 签名更新、灰度发布、失败回滚、配置/数据库版本迁移 | ⏳ pending |
| GAP-P2-04 | 正式发布工程 | macOS 未签名/公证，Windows 未验证，无干净机验收矩阵 | Developer ID 签名、公证；Windows 安装验证；干净机、升级、卸载测试通过 | ⏳ pending |

### 当前真实验收基线（2026-06-29）

| 项目 | 当前结果 |
|------|----------|
| 自动化测试 | 根项目已限定 `testpaths=tests`，避免误收集 Hermes 上游测试；`88 passed, 1 skipped` |
| macOS 构建 | DMG/ZIP 构建成功；未签名/公证 |
| 本机 API 安全 | 打包版启动成功；无令牌访问 `/api/*` 实测返回 `401` |
| 规范数据目录 | `~/Library/Application Support/marketing-os-desktop/{config,agent-runtime,secrets}`；源码与用户数据分离 |
| Hermes runtime | 旧安装、CLI、`~/.hermes` 和 launchd 网关已删除；官方 0.17.0 源码 runtime 已通过 DeepSeek 健康检查 |
| Agent 状态 | 旧会话/旧技能/旧 Cron 未恢复；当前 session 0、cron 0，gateway stopped |
| 账号数据 | 仅有测试账号元信息，无真实指标 |
| 热点/选题 | `no_data` |
| 智能巡检 | `never_run`，自动化未启用 |
| 发布数据 | 无真实发布任务指标和归因数据 |

### 推荐推进顺序

1. `GAP-P0-01` 统一数据目录。
2. `GAP-P0-03` 后台常驻，并同步完成 `GAP-P0-02` 精简网关运行时设计。
3. `GAP-P0-04`、`GAP-P0-05` 登录健康与网络自检。
4. `GAP-P0-06` 本机 API 安全。
5. `GAP-P0-08` 用真实模型重构分析与选题依据。
6. `GAP-P0-07` 完成抖音→巡检→微信/飞书真人端到端验收。
7. 进入 P1 发布、指标回收和多账号闭环。

---

## 七、清场重建台账（2026-06-29）

| ID | 工作 | 结果 | 证据 |
|---|---|---|---|
| REBUILD-01 | 后端源码内聚 | 营销引擎从 `~/.hermes/plugins` 收回 `engine/marketing-os`，测试与打包路径已改 | `engine/marketing-os`、`scripts/build-backend.mjs` |
| REBUILD-02 | 旧 Hermes 清场 | 完整备份后执行官方 full uninstall；旧 CLI、代码、状态、网关已删除 | `~/HermesResetBackups/20260629-113942` |
| REBUILD-03 | API 独立保留 | 仅保留 DeepSeek provider 凭据和模型配置，权限 600 | App Support `secrets/` |
| REBUILD-04 | 官方源码基线 | 拉取 NousResearch/hermes-agent 0.17.0，固定 commit `4488fe1` | `runtime/HERMES_UPSTREAM.md` |
| REBUILD-05 | 源码运行验证 | Python 3.13 独立环境安装完成；真实 API 返回 `SOURCE_RUNTIME_OK` | `scripts/bootstrap-hermes-runtime.sh` |
| REBUILD-06 | 安全默认值 | memory/skill 写入需审批；自生成技能扫描；subagent 不自动批；Tirith fail-closed | Agent runtime config |
| REBUILD-07 | 前沿资料库 | Memory、harness、安全、评测与 Hermes 源码差距已成库 | `docs/research/README.md` |
| REBUILD-08 | 新 Agent Core 地基 | task event、持久审批、effect 幂等回执、memory candidate、L0–L4 policy | `engine/agent_core` |

---

## 八、前期推进台账（2026-06-28）

> 说明：今日产出不只包含前端。可见页面只是最上层，Electron 会话、后端编排、数据真实性、消息网关和打包测试占了主要工作量；但真人主链路尚未验收，所以用户体感仍像“只有界面”。

| ID | 层级 | 今日完成 | 主要文件/证据 | 状态 |
|----|------|----------|---------------|------|
| DAY-01 | 产品/UI | 主控台、趋势、选题、账号、发布、分析、自动化页面接入真实 API，移除演示数字 | `src/pages/*` | ✅ done |
| DAY-02 | Electron | 内嵌平台登录、Cookie 仅留主进程、隐藏窗口复用登录态采集 | `electron/main.js` | ✅ done |
| DAY-03 | 后端 | FastAPI 账号/趋势/画像/发布/分析/工作流/巡检报告接口及原子持久化 | `engine/marketing-os/server.py` | ✅ done |
| DAY-04 | 智能编排 | 账号同步→多行业采集→趋势分析→选题→真实失败报告；手动和定时共用 | `electron/main.js` | ✅ framework |
| DAY-05 | 数据真实性 | 删除假数据；失败、降级、来源、采集时间进入报告 | `PRODUCT_BLUEPRINT.md`、`server.py` | ✅ done |
| DAY-06 | 桌面助手 | Hermes safe-mode 只读顾问接入当前营销上下文 | `src/components/AgentPanel.tsx`、`server.py` | ✅ read-only |
| DAY-07 | 消息网关 | 微信/飞书扫码桥、可信用户、首次私聊绑定、送达记录和失败重试 | `electron/channel_bridge.py`、`tools/channel_context.py` | 🟡 待真人验收 |
| DAY-08 | 跨端上下文 | Hermes 增加只读营销数据工具，微信/飞书可读取趋势、选题、巡检和账号指标 | `tools/monitor.py` | ✅ code |
| DAY-09 | 构建发布 | PyInstaller 独立后端、Electron DMG/ZIP、扫码桥 asar 解包 | `scripts/*`、`package.json` | ✅ macOS build |
| DAY-10 | 自动化质量 | 全量自动化测试达到 `82 passed, 1 skipped` | `tests/*` | ✅ verified |
| DAY-11 | 数据一致性 | 增加桌面规范配置目录，并自动同步到 Hermes 网关环境 | `electron/main.js`、`electron/channel_bridge.py` | 🟡 待打包联调 |
| DAY-12 | 后台运行 | 增加托盘、隐藏窗口继续巡检、托盘立即巡检和明确退出 | `electron/main.js` | 🟡 待实机验收 |
| DAY-13 | 本机安全 | Electron 随机 API 令牌、FastAPI 鉴权、移除开放 CORS | `electron/main.js`、`server.py` | ✅ code |
| DAY-14 | Web 预留 | 冻结桌面与 Web 视频工作台的 SSO、项目、任务和事件契约 | `VIDEO_WEB_CONTRACT.md`、`src/api/video-contract.ts` | 📐 contract |

### 下一工作队列（不实现视频生成）

| 顺序 | 台账 ID | 下一动作 | 验收结果 |
|------|---------|----------|----------|
| 1 | GAP-P0-01/03/06 | 完成本轮测试、生产构建和安装包实机验收 | 关闭窗口后仍定时运行；API 无令牌返回 401；Hermes 读取同一数据目录 |
| 2 | GAP-P0-04/05 | 登录健康检查、过期状态、网络/代理诊断和验证码可见回退 | 用户明确知道是已登录、过期、网络失败还是需验证码 |
| 3 | GAP-P0-08 | 把规则模板替换成有证据、置信度的模型分析 | 不再用固定角度和无依据“流量高/中/低” |
| 4 | GAP-P1-07 | 增加用户画像设置页并接入建议依据 | 用户可配置行业、受众、风格、禁区和目标 |
| 5 | GAP-P1-01/02 | 发布状态机、指标回收与选题归因 | 从建议到结果形成非视频业务闭环 |
| 6 | GAP-P0-07 | 真人完成抖音→巡检→桌面决策全链路验收 | 真实数据替换当前 `no_data/never_run` 基线 |
