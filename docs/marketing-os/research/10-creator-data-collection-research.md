# 创作者中心数据采集方案调研

> 建立日期：2026-07-03
> 关联台账：`01-mcp-browser-account.md`（MCP-13）、`02-data-trends-research.md`（DATA-06）
> 核心问题：MCP accessibility snapshot 解析出的账号数据不完整，需要参考开源社区方案确定采集策略。

> **2026-07-03 安全复核：** 本文中的社区项目、字段和实现路径由 GLM 整理，尚未完成官方源码、commit、许可证和真实账号回放核验，只能作为候选线索。尤其“导出/下载”和任意页面脚本不属于当前只读 MCP 能力，不能据本文直接实现。

---

## 一、开源项目调研

### 1.1 TzFilm-Douyin-Tool（MIT）

| 维度 | 信息 |
|---|---|
| 仓库 | `TradingAi666/TzFilm-Douyin-Tool` |
| 许可证 | MIT |
| 方式 | AppleScript 操控 Chrome → 切「投稿列表」tab → 点「导出数据」→ 下载 Excel → openpyxl 解析 |
| 字段 | 播放、平均播放时长、5s完播率(CTR)、点赞、评论、分享、收藏、弹幕 |
| 优势 | 导出按钮是平台官方功能，最稳定；字段完整 |
| 劣势 | AppleScript 依赖 macOS + Chrome 焦点；需处理文件下载 |
| 可借鉴 | **导出按钮路径**是最稳定的数据采集方式 |

### 1.2 creator-stats（GitCode）

| 维度 | 信息 |
|---|---|
| 仓库 | `water_yi/creator-stats`（GitCode） |
| 方式 | Node.js + Playwright 登录创作者后台 → 每日抓取视频数据 → SQLite → Web 看板 |
| 字段 | 播放、点赞、评论、转发、收藏、粉丝数 |
| 优势 | 每日快照 + 趋势对比；多平台（抖音/视频号/小红书） |
| 可借鉴 | **每日快照模式**和趋势对比 |

### 1.3 autody（MIT）

| 维度 | 信息 |
|---|---|
| 仓库 | `kizzhang/autody` |
| 许可证 | MIT |
| 方式 | Codex Chrome Extension 接管已登录的 creator.douyin.com tab → 读可见 DOM / 官方导出 |
| 字段 | 最完整：基础数据 + 深度数据 + 4 个原生 tab |
| 优势 | 字段定义最全；dataGap 机制；分 tab 采集；不碰 Cookie/localStorage |
| 劣势 | 依赖 Codex Chrome Extension，非通用方案 |
| 可借鉴 | **字段定义**、**dataGap 标记机制**、**分 tab 采集流程** |

### 1.4 autody 定义的视频详情页 4 个原生 tab

| Tab | 中文名 | 包含字段 |
|---|---|---|
| overview | 总览 | 核心指标、观看趋势、留存分析、跳出分析、互动指标、弹幕分析 |
| trafficAnalysis | 流量分析 | 抖音App来源分享、其他App来源、额外流量、平台助推流量、前后搜索词 |
| audienceAnalysis | 观众分析 | 关注指标、关注趋势、性别分布、年龄分布、地域分布、兴趣分布、关注热词 |
| commentHotWords | 评论热词 | 排名热词 |

### 1.5 autody 的 dataGap 机制

- 读不到的字段标记 `dataGap`，不猜、不伪造
- 记录 `capturedAt`、`source.kind`（visible_dom / official_export）、`dataGaps[]`
- 审计脚本检查缺口，后续只补缺失或过期字段

---

## 二、候选方案：只读 snapshot 优先，导出另立高风险 ADR

### 2.1 采集策略

| 数据类型 | 采集方式 | 字段 |
|---|---|---|
| **视频列表基础数据** | 当前仅用投稿列表 accessibility snapshot；官方导出作为独立候选 | 播放、点赞、评论、分享、收藏；其余字段缺失时标记 dataGap |
| **账号概览** | 导航到首页 → accessibility snapshot 解析 | 粉丝、获赞、播放、关注、作品数 |
| **单视频深度数据** | 逐个进入视频详情 → 切 4 个 tab → snapshot 解析 | 留存、流量来源、粉丝画像、评论热词 |
| **读不到的字段** | 标记 `dataGap` | 不猜、不伪造 |

### 2.2 MCP 工具使用

| 工具 | 用途 | MCP-05 状态 |
|---|---|---|
| `browser_navigate` | 导航到投稿列表/视频详情 | ✅ 已开放 |
| `browser_snapshot` | 读取页面 accessibility tree | ✅ 已开放 |
| `browser_click` | 只读 tab 与明确无副作用提示 | 🟡 受元素白名单约束；`导出/下载/确定` 明确未开放 |
| `browser_wait_for` | 等待页面加载 | ✅ 已开放 |

### 2.3 实施阶段

| 阶段 | 内容 | 前置条件 |
|---|---|---|
| **阶段 1** | 投稿列表 snapshot → 可见视频基础数据 | 固定 fixture + 真人回放，缺失字段明确 dataGap |
| **阶段 2** | 首页 snapshot → 账号概览指标（已有，需校准解析器） | dump 真实 snapshot 文本 |
| **阶段 3** | 视频详情 4 tab snapshot → 深度数据 | 确认 tab 切换在 snapshot 中的 ref |
| **阶段 4** | dataGap 审计 + 补采机制 | 阶段 1-3 完成 |

---

## 三、与现有架构的对接

- MCP sync 端点（`/accounts/{id}/mcp-sync`）扩展为多页面采集
- `video_metrics` 当前只存已验证可见字段；扩展字段需来源核验和跨版本 fixture 后再迁移
- `video_deep_metrics` 暂不新建，先证明 4 tab 稳定可达且字段语义一致
- `dataGap` 字段存入 stats，Agent 可据此判断数据完整性
- 采集频率：每日 1 次（参考 creator-stats），避免触发风控

---

## 四、合规边界

- 只采集用户自己登录的账号数据
- 不碰 Cookie/localStorage/password/session
- 不调逆向 API、不执行签名 JS
- 不开放 `browser_evaluate`；输出脱敏不能替代脚本副作用控制
- 导出/下载涉及文件写入，未来必须走独立审批、固定下载目录、文件类型/大小校验和清理策略
- 采集频率 ≥ 1 小时一次（参考 TzFilm 建议）
- 页面结构变化时明确报 degraded，不冒充成功
