# Web 视频与外部沟通 Surface 执行台账

## 完成目标

Web 视频工作台、微信和飞书只是同一 Agent 的能力与沟通表面，共享 user/project/account/task/artifact/event 真相源，不建立第二套智能体、记忆或任务系统。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| SURF-01 | Contract 定版 | 复核 `VIDEO_WEB_CONTRACT.md`：SSO、project/task/context/artifact/event、版本与错误 | OpenAPI/JSON schema 契约测试 | 📐 |
| SURF-02 | 身份映射 | 桌面 user 与 Web identity 一一映射；短期 token、撤销、设备丢失 | 登录/撤销/过期测试 | ⏳ |
| SURF-03 | 项目与账号 scope | Web 请求必须绑定 project/account；不能浏览其他账号资产或记忆 | 越权测试 | ⏳ |
| SURF-04 | 视频任务提交 | 桌面 Agent 创建 Web job；包含脚本、素材引用、模板、参数和审批状态 | 一次真实 job contract | ⏳ |
| SURF-05 | 事件同步 | queued/running/preview/waiting_user/completed/failed/cancelled 回写同一 AgentTask | 断线重连和顺序测试 | ⏳ |
| SURF-06 | Artifact 回流 | 预览、工程文件、成片、字幕、封面、license/provenance 进入 ContentAsset | 血缘可追溯 | ⏳ |
| SURF-07 | 大文件上传 | 分片、断点、hash、配额、过期、恶意文件扫描；桌面不经 Agent transcript 传二进制 | 中断恢复和安全测试 | ⏳ |
| SURF-08 | 开源视频方案 ADR | 比较 ComfyUI/Remotion/OpenMontage；许可证、GPU、队列、模板和可替换性 | 选型 ADR，不直接复制 AGPL | ⏳ |
| SURF-09 | 人工检查点 | 脚本、分镜、预览、成片分别可确认/修改；已渲染产物不丢 | 真人制作一条样片 | ⏳ |
| SURF-10 | 成本与配额 | 模型/渲染/GPU/存储成本预估、用户确认、超额停止 | 账单/配额测试 | ⏳ |
| SURF-11 | 微信/飞书接入边界 | 仅消息 surface；消息映射稳定 user/session，不复制 memory | 架构与隐私评审 | ⏳ P2 |
| SURF-12 | 扫码与绑定 | 官方/可核验通道；绑定、解绑、重连、设备丢失；不使用来路不明 hook | 真人扫码矩阵 | ⏳ P2 |
| SURF-13 | 收发与去重 | inbound→同一 AgentTask；outbound receipt、幂等、重试、顺序和附件限制 | 双向消息 E2E | ⏳ P2 |
| SURF-14 | 离线通知 | 行业简报、异常、等待审批可推送；营销群发默认禁止 | 通知偏好与安静时段 | ⏳ P2 |
| SURF-15 | 渠道隐私 | 私聊不自动写长期记忆；敏感附件、删除和数据保留可控 | 隐私测试 | ⏳ P2 |

