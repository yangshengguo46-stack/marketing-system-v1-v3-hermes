# P0-04/05 审批链路真人验收

> 日期：2026-06-30
> 前置：后端/前端集成代码已就绪；本清单必须真人执行，自动化数量不得冒充完成。
> 需要：macOS + 完整 Electron 环境 + 有效 API key + 抖音登录态

---

## 准备

1. 启动完整桌面应用（Electron + Python 后端）
2. 确认 Agent 对话界面正常，有模型回复
3. 确认抖音已登录（或准备扫码登录）

---

## 路径 1：成功

**场景：** Agent 需要使用平台登录态搜索抖音内容

- [ ] 在 Agent 对话中说：**"帮我搜抖音 AI 教育相关的内容"**
- [ ] Agent 开始规划步骤，然后触发 `marketing_trending_search` 工具
- [ ] **审批卡片出现**在 Agent 面板中，显示：
  - 能力标签（「行业搜索」）
  - 风险说明
  - 参数（platform: douyin, keyword: AI 教育）
  - 三个批准按钮：仅本次 / 本次对话 / 永久记住
  - 一个拒绝按钮
- [ ] 点击**「仅本次」**
- [ ] 后端调用 `POST /agent/approvals/{id}/approve` (scope=once)
- [ ] Electron 执行 `scrapeIndustryWithSession`（使用已登录的抖音 session）
- [ ] Electron 提交 effect receipt：`POST /agent/effects/submit`
- [ ] Agent 任务从 `waiting_user` 恢复为 `running`
- [ ] Agent 继续回复，引用搜索结果，说明来源
- [ ] 审批卡片消失

---

## 路径 2：拒绝

**场景：** 用户不想让 Agent 执行搜索

- [ ] 触发审批（说"帮我搜抖音 美妆 内容"）
- [ ] 审批卡片出现
- [ ] 点击**「拒绝」**
- [ ] 后端调用 `POST /agent/approvals/{id}/reject`
- [ ] Agent 任务恢复，收到拒绝通知
- [ ] Agent 回复说明操作被拒绝，建议替代方案或不继续
- [ ] 任务不卡在 `waiting_user`，进入 `paused` 或 `completed`
- [ ] 审批卡片消失

---

## 路径 3：取消

**场景：** 审批卡挂起时用户取消整个任务

- [ ] 触发审批
- [ ] 审批卡片出现后**不点任何按钮**
- [ ] 在 Agent 界面点击**「取消任务」**（或等价的停止按钮）
- [ ] 后端调用 `POST /agent/tasks/{id}/cancel`
- [ ] 任务状态变为 `cancelled`
- [ ] 审批卡片消失
- [ ] 可以开始新的对话，不受影响

---

## 路径 4：超时

**场景：** 审批长时间无响应自动过期

- [ ] 触发审批
- [ ] 审批卡片出现
- [ ] **等待 5 分钟**不操作（或缩短超时时间测试）
- [ ] 后端 `expire_stale_approvals` 将审批标记为 `expired`
- [ ] 任务状态从 `waiting_user` 变为 `paused`
- [ ] `approval.decided` 事件 (decision=expired) 被发出
- [ ] 前端如果仍连接，审批卡片消失
- [ ] 恢复任务后 Agent 知道审批已过期

---

## 路径 5：Session 授权

**场景：** 同一会话内多次相同工具调用不重复弹卡

- [ ] 触发审批（说"帮我搜抖音 AI 内容"）
- [ ] 点击**「本次对话」**批准
- [ ] 后端 `grant_authorization(scope="session")`，`_session_auths` 填充
- [ ] 第一次搜索完成，Agent 回复
- [ ] **再次说"再搜一下抖音 AI 编程"**（同样 capability，同样 platform）
- [ ] **不弹审批卡**，工具直接执行
- [ ] 说"搜抖音 美妆"（同样 capability 但不同 keyword，platform 相同）
- [ ] **不弹审批卡** 或 弹卡（取决于参数匹配策略——当前只约束 platform）
- [ ] 切换到新 session → 搜索时应再次弹卡

---

## 路径 6：永久授权

**场景：** 永久授权跨重启生效

- [ ] 触发审批
- [ ] 点击**「永久记住」**批准
- [ ] 后端 `grant_authorization(scope="permanent")`，写入 `user_authorizations` 表
- [ ] 同一 session 内再次调用相同 capability + 相同 platform → 不弹卡
- [ ] **重启应用**
- [ ] 再次说"帮我搜抖音 AI 内容"
- [ ] **不弹审批卡**
- [ ] 打开记忆管理页（如有）→ 可看到永久授权记录
- [ ] 撤销该授权 → 再次搜索 → 弹卡

---

## 问题记录

| 路径 | 问题 | 严重级别 |
|---|---|---|
| | | |

---

## 验收结论

- [ ] 全部 6 条路径通过
- [ ] 部分通过（记录具体路径）
- [ ] 不通过（记录阻断问题）
