# Marketing OS 当前执行台账

> 日期：2026-07-11
> 分支：`codex/marketing-os-product-source`
> 本文件是唯一任务入口。研究资料、ADR 和 Git 历史不得直接发任务。

## 不得遗忘的执行禁令

1. **默认先改原生 owner；禁止因为怕碰上游，就在外围再加适配层。只有上游确实无法承担、且证据充分时，才允许新增边界。**
2. **Electron 只负责显示和交互，不参与其它任何东西。** Electron 不拥有账号、Cookie、profile、浏览器、任务、记忆、业务状态、自动化或执行。

每个纵切、任务和完成口径都必须同时满足这两条；否则任务不得开始。它们优先于局部实现计划、上游同步便利和已经写完的代码。

## 证据等级

`designed → code → automated → dev-runtime → packaged → human-loop`

只有达到 `human-loop` 才能宣称用户闭环完成；单测、页面、mock、占位 provider 和本地成功 toast 都不是产品完成。

## 当前代码事实

| 领域 | 当前状态 | 证据 | 主要缺口 |
|---|---|---|---|
| Hermes 产品本体 | 完整源码已成为主仓库根 | code + automated | 上游吸收 CI、正式签名发布 |
| Desktop | `apps/desktop` 唯一 UI/Electron | automated build | 干净机安装和真实连续对话 |
| Session/account scope | SessionDB、AccountRegistry、会话级 MCP pool 与 Playwright contextGetter 已贯通；`accounts.json` 仅一次迁移 | dev-runtime | 真人登录、多账号恢复、打包浏览器策略 |
| Account lifecycle | Hermes AccountRegistry 已拥有注册、认证状态、断开、删除、会话绑定和 BrowserContext 租约；旧 JSON 一次性迁移 | automated | 切换 UI、真人多账号与 profile 清理 |
| EvidencePack | `web_extract` 后自动固化 | automated | 多源交叉核验、来源语义、时效治理 |
| Content plan/assets | 三 lane policy、图文质量门、版本资产 | automated | 真实高质量内容与素材生产 |
| Preflight | InfluenceOS + 不可变记录 + draft gate | automated | 真实账号历史校准、发布前版本链 |
| Receipt/Learning store | ReceiptRef、LearningCandidate、PublishAction 合同 | automated | 真实 Provider 与跨天指标尚未接入 |
| Hermes memory/Skill | 原生能力保留，经营写入规则已加入 | automated | 候选治理后投影、重复成功流程沉淀 |
| Publishing/metrics | 原生发布 intent、一次性审批、Provider 插槽、unknown 恢复、回执校验、5 段指标 checkpoint | automated | 缺实际 L3 Provider 和真人发布 |
| Packaging | 自包含 staging 可构建 | automated | 精简依赖、签名、公证、干净机断网首启 |
| High-end video | 独立项目/合同 | deferred | 不计桌面 v0.1 完成 |

## 当前唯一主线

### LOOP-01 真实发布回执进入三核闭环

目标：让一个真实内容 action 从 Hermes 原生审批/执行边界得到可验证 ReceiptRef，并且未知结果不能被当成成功。

执行顺序：

1. 审计 Hermes 当前 approval/tool/effect 事实源，确定唯一 receipt hook。
2. 恢复旧发布合同中仍有效的 idempotency、unknown outcome 和 post ID/URL 规则，不恢复旧 Store/FastAPI。
3. 定义发布 action 与当前 ContentAsset、account scope、preflight ID 的绑定。
4. 成功只接受平台 post ID、稳定 URL 或官方作品列表反查。
5. 失败、取消、超时、未知分别落状态；未知先查询，禁止盲重试。
6. 自动创建 1h/6h/24h/3d/7d metric checkpoints。
7. 至少完成一条开发机真实图文发布回执，再进入下一个任务。

当前落地（2026-07-11）：

- `agent/marketing/domains/publishing.py` 已成为发布经营事实的唯一 owner。
- 同一 `account + asset + version + platform` 使用稳定幂等键；重放只返回原 action。
- `prepared → executing → unknown/failed/cancelled/published` 状态已落库；`unknown` 可查询恢复，不能直接重试。
- 成功只接受目标平台的 `platform_post_id` 或具体 HTTPS 作品 URL，并要求 `verification_source`。
- 发布成功自动固化 ReceiptRef、结算 preflight、更新 ContentAsset/plan，并创建 1h/6h/24h/3d/7d checkpoint。
- `agent/marketing/publish_capture.py` 接入 Hermes 原生 post-tool 路径；只有未来的受信 `marketing_effect_publish` 工具结果能自动结算回执，没有模型可调用的“手填成功”工具。
- `marketing_prepare_publish` 与 `marketing_read_publish_state` 已进入原生 tool registry，负责预写 action 与重启恢复，不负责假装发布。
- Hermes 原生 Camofox 的 account_id 隔离作为兼容能力保留；Playwright MCP 已确定为桌面产品主线，但尚未接入 BrowserContext owner，不能宣称运行完成。
- `marketing_effect_publish` 已复用 Hermes 原生 MCP elicitation 一次性确认；拒绝、静默或超时不会启动 Provider，也不能永久放行最终发布。
- 发布 Provider 进入 `agent/marketing/providers/` 原生注册器；只有真实 Provider 已注册时 effect/query 工具才会出现在 Agent 工具集中，避免空按钮和占位能力。
- Hermes `state.db` 已新增原生账号注册表；`agent/account_registry.py` 是账号生命周期 owner，Gateway 只调用该 owner，Electron 不保存或修改账号真相。
- 旧 `accounts.json` 仅执行一次无敏感字段迁移；Cookie、token、验证码和 QR 内容禁止进入 SessionDB。
- AccountRegistry 已能为绑定会话签发 secret-free BrowserContext lease；认证失效、断开或删除账号不能获得执行租约。
- `mcp/marketing-browser` 直接调用 Playwright MCP `createConnection(config, contextGetter)`；schema discovery 不启动浏览器，实际工具调用才按账号租约创建上下文。
- Hermes 原生 MCP client 已支持 `session_scope=marketing_account`：账号连接池、RPC 串行、熔断与关闭均在原生 MCP owner 内；不存在外部 Router。
- 开发机真实 Hermes 工具分发已完成 `AccountRegistry → scoped MCP → navigate → snapshot`，52 个 Playwright 工具可见，证据等级为 `dev-runtime`。

尚未完成：

- Playwright/MCP 的真实发布动作与作品列表反查 Provider 尚未接入；当前不能宣称能自动发布。
- 仍需一条开发机真人图文发布和重启恢复证据，证据等级目前停在 `automated`。

下一纵切（当前环境核验后确定）：

1. 用平台 Skill 实现知乎第一条真人流程：headed 登录检测、认证状态回写、装载已审核变体、填写编辑器、一次性确认、作品页反查。
2. 实现账号 disconnect/delete 对 BrowserContext 进程与 profile 的原生清理，重启后恢复同一账号租约。
3. 同步开始第一阶段前端：只显示账号、内容审核、发布确认、执行状态和 unknown 恢复；前端不承载业务或执行真相。

浏览器二进制口径：开发机先使用后端检测到的系统 Chrome/Edge 验证链路；产品安装包必须在
“单独受控 Chromium”与“首次明确授权后下载”之间完成体积、离线和签名验证。禁止为了省掉
这个决策而复用 Electron 作为自动化宿主，也禁止运行时静默下载。

完成口径：

- 一个 Hermes session 中：资产 → 审批 → action → verified receipt → Agent 续答。
- 重启后能恢复并读取同一 receipt。
- 重放不会重复发布。
- 无 post ID/URL 时状态只能是 pending/unknown/failed。

## 后续顺序（不得并行扩建）

### LOOP-02 指标回收

- 到期 checkpoint 由 Hermes cron 扫描。
- 未知指标留空，不写 0。
- 原始平台字段保留，另映射 attention/retention/trust/action/fit/risk 标签。

### LOOP-03 自动复盘

- `content_retro` 比较发布前 prediction 与真实 metric receipt。
- 输出偏差、缺失字段、替代解释，不自动宣布因果。
- 生成 pending memory/strategy/weight/skill candidate。

### LOOP-04 学习投影

- 用户明确偏好进入 USER/MEMORY。
- 账号策略候选进入版本化 account strategy。
- 多次成功并有失败恢复的流程进入 Skill candidate。
- 权重候选必须有至少三个支持样本并通过历史回放。

### LOOP-05 真人闭环

- 新用户自然对话建模。
- 一篇知乎/公众号真实内容。
- 一次真实授权发布或可靠人工回执。
- 跨天指标回收与下一轮建议明显改变。

### DELIVERY-01 产品交付

- 产品依赖 allowlist。
- macOS 签名、公证。
- 干净机器无全局 Hermes/Python/Chrome 启动。
- 断网首启和升级回滚。

## 暂停项

- 新页面和工作台装饰。
- 全平台自动发布。
- 微信/飞书体验扩张。
- Windows 正式交付。
- 高阶视频 Provider 和多 Agent 片场。
- 未校准的流量、完播、互动和 InfluenceOS 对外承诺。

## 当前回归基线

- 营销、Agent、Gateway、审批与账号浏览器隔离组合回归：491 passed。
- LOOP-01 发布账本、审批、回执门与恢复路径单文件回归：16 passed（后续组合回归必须继续包含）。
- Desktop runtime staging：2 passed。
- Git 历史恢复白名单：见 `../reference/engineering/git-history-recovery.md`。
- 下一次更新本台账时必须写：代码路径、测试、dev-runtime、packaged、human-loop 和仍未完成的风险。
