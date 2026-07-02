# 开源候选核验（DATA-02）

> 日期：2026-07-02 | 按核验日期，非按采用状态  
> 未核验的候选默认禁用；以下每项结论来自固定 commit 或版本

## TrendRadar

- 仓库：`sansan0/TrendRadar`
- 许可证：GPL-3.0
- 结论：**C（参考）** — 借鉴其源健康检查、去重、时间窗、通知与报告设计模式。GPL 代码**不复制**进 MIT 桌面端。若将来以独立 sidecar 形式使用，必须先做许可证评审。

## RSSHub

- 仓库：`DIYgod/RSSHub`
- 许可证：AGPL-3.0
- 结论：**C（参考）** — 大量站点路由和 RSS 标准化思路可借鉴。可作为用户自行部署的远程可选源，**不嵌入**桌面包。不强依赖单一路由作为稳定事实源。

## TikHub

- 仓库：`TikHub/TikHub-API-Python-SDK`
- 许可证：Apache-2.0（SDK 端）；服务端为第三方托管
- 结论：**B 候选** — 只作为可选付费数据源。使用前必须明确：数据外发范围、费用模型、地区覆盖、来源声明。**不成为唯一主链**。

## MediaCrawler

- 仓库：`NanmiCoder/MediaCrawler`
- 许可证：GitHub 元数据**无法确认**标准许可证
- 结论：**D（隔离 PoC）** — 只研究平台适配、字段和失败模式。**不复制**、**不打包**、**不接**用户真实 Cookie。许可证不明是阻断项。

## Douyin Download API

- 仓库：`Evil0ctal/Douyin_TikTok_Download_API`
- 许可证：Apache-2.0
- 结论：**D（隔离 PoC）** — 仅限用户提供/公开链接 PoC。需验证：真实性、版权、限流、平台条款。现阶段不接入生产。

## YT-DLP

- 仓库：`yt-dlp/yt-dlp`
- 许可证：Unlicense
- 结论：**B** — 只处理用户有权使用的链接。下载为 L1 操作，来源、版权和落盘位置必须对用户可见。

## faster-whisper

- 仓库：`SYSTRAN/faster-whisper`
- 许可证：MIT
- 结论：**A/B** — 优先作为桌面本地转写候选。需验证模型包大小、CPU/GPU 性能、语言准确率。

## promptfoo

- 仓库：`promptfoo/promptfoo`
- 许可证：MIT
- 结论：**A** — 用于行业简报、证据引用、拒答和提示注入的 Agent/RAG 回归评测。**不接**生产用户秘密。

## Langfuse

- 仓库：`langfuse/langfuse`
- 许可证：仓库组成需逐项核验
- 结论：**C（参考）** — 先定义本地可观测事件（已有 task_events）。如 self-host，需单独评估许可证和运维成本。
