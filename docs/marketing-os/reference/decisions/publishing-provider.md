# ADR-02：抖音首版真实发布 Provider

- 状态：Accepted（2026-07-04）
- 范围：桌面 v0.1 的抖音视频发布；不包含批量群发和独立视频 Web 实现

## 决策

首版采用 **Hermes 原生 account-scoped Playwright/MCP 发布 Provider**：复用账号管理中同一 `account_id` 的持久 profile，由用户导入媒体到 App 管理目录，Provider 完成预检、上传和字段填写；最终“发布”通过 Hermes 原生任务、工具审批和回执循环执行。成功必须从创作者中心作品列表反查稳定作品标识或作品 URL，不能凭 toast、按钮消失或空 post ID 宣布成功。

长期保留官方开放平台发布 API adapter；取得平台权限后可替换执行 Provider，但不改变 ContentAsset、approval、effect、receipt 和 metrics contract。

## 为什么不选另外三条路线

| 路线 | 结论 | 原因 |
|---|---|---|
| 官方开放平台 API | 长期首选，当前不阻塞 v0.1 | 权限、账号类型、审核和能力范围尚未取得，不能假装可调用 |
| 外部 huimei MCP | 当前不采用 | 本机未安装；会形成独立账号/登录真相源；许可证、固定版本、receipt 语义和卸载路径尚未验收 |
| douyin-upload CDP | 当前不采用 | 本机无 server；依赖外部 Chrome/CDP，与已冻结的内置 MCP profile 架构冲突 |
| 完全人工发布 | 只作故障兜底 | 可以保证用户能发出去，但无法可靠生成 post ID、指标计划和学习闭环，不算产品完成 |

## 强制安全边界

1. Agent 和后端不得提交任意本机 `file_path` 给浏览器。
2. 媒体只能经用户文件选择器导入 App 管理目录，业务层只看不可猜测的 `attachment_id`。
3. 导入时记录原文件名、MIME、大小、SHA-256；发布前重新校验文件仍在管理目录内且 hash 未变。
4. Provider 只允许 `creator.douyin.com` 的已审查发布路径、上传控件、标题/描述字段和最终发布按钮。
5. 上传、填写可以属于一次发布 effect 的准备阶段；最终点击发布必须有有效 approval，不能被永久授权静默跳过。
6. 网络超时、页面失联或点击后进程崩溃一律记为 `unknown`，先查询作品列表再决定是否重试。
7. 同一 `asset_id + platform + version` 使用稳定幂等键；没有查询结果前禁止再次上传发布。
8. receipt 至少包含：provider、account_id、asset_id、published_version、platform_post_id 或 published_url、verified_at、verification_source。

## 实施顺序

1. `PUB-06A MediaAttachment`：安全导入、hash、删除与账号/资产 scope。
2. `PUB-07A prepare`：校验 approved video、附件、账号、格式、标题和登录态；打开发布页并上传，停在最终确认前。
3. `PUB-07B publish`：消费逐次 approval，点击发布并保存 effect receipt。
4. `PUB-09 query`：作品列表按发布时间、标题、附件 hash/封面等证据反查；解决 unknown。
5. `PUB-10 metrics`：拿到 post ID 后建立 1h/6h/24h/3d/7d 指标任务。

## 完成口径

- 测试账号发布一条授权测试视频，取得并反查真实作品 ID/URL。
- 点击后断网、MCP 崩溃、App 重启均不会重复发布。
- 跨账号附件、审批和 profile 不能互用。
- 删除 App 内附件不会删除用户原文件；卸载/保留策略明确。
