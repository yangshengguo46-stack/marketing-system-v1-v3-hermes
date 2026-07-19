# Marketing OS 架构教义

> 日期：2026-07-19
> 状态：当前原生 owner 与权限边界基线

## 两条铁律

1. 默认修改真正拥有能力的原生 owner；没有源码证据，不得新增外围适配层。
2. Electron 只有显示和交互；业务事实、自动化、任务、学习和执行全部在 Hermes 原生运行时。

## 前台 Agent 与后台观察者

```text
用户 ↔ 个人 IP Agent（Hermes 原生会话）
          ├─ 用户画像 / IP 战略 / 内容 / 发布授权
          ├─ Evidence → Preflight → Action → Receipt → Retro
          └─ 只读消费领域知识与研究投影

后台系统
  ├─ KnowledgeMaintenance：候选 → 证据/时效/冲突/回放 → 投影或淘汰
  └─ HumanObserverMaintenance：观察 → 竞争解释 → 假设 → 封存预测 → 结果 → 模型修订
```

个人 IP Agent 是产品主体；Human Observer 只是后台研究 owner。两者共享经过治理的观察来源，但不共享写权限。Marketing 可以单向贡献 Receipt，不能直接修改人类模型；Human Observer 的研究结论也不能绕过经营证据替 Agent 做账号决策。

Gateway 在每次模型调用的最后时刻重建 `MARKETING OS LIVE PERSONAL IP CONTEXT`：稳定的 user/entity/action-account 只负责路由，可变的创作者画像、经营选择、真实平台快照和系统推断从各自原生 owner 重新投影。画像内部的 `human_projection_model` 与受众心理投影会被拆到 `system_derived`，不会随用户确认的外壳升级成自述或事实。

## 原生权限实现

`agent/epistemic_contract.py` 定义六类记录及各自 authority。系统学习写入需要进程内 `SystemAuthority` capability；该 capability 不可序列化，也不接受 RPC、Tool、Prompt 或 renderer 参数构造。

- `OperatingLoopRepository.decide_learning_candidate` 必须持有 system capability。
- `SystemLearningProjector` 才能把 accepted candidate 投影到账号知识或策略。
- `KnowledgeBaseRepository` 的证据知识和账号学习投影必须持有同一 capability。
- Human Observer 写 owner 是包内私有 `_HumanObserverWriter`，构造时必须持有 human-research capability。
- `MarketingPersonalIPConnector` 只把已经确认的用户自述和经营选择转成伪名化观察；它不自动产生心理解释，且不会保存 user/account/entity/project 直接引用。发布回执则同时绑定伪名 subject 与匿名 cohort，使长期结果能与同一观察主体对账。
- Gateway 不注册学习候选 list/decide RPC；Desktop 不请求、不展示、不确认候选。
- 创作者画像、赛道选择、受众假设、定位和内容系统继续要求用户明确确认，因为这些是用户自我陈述或经营选择，不是系统学习结论。

这是一条产品能力边界，不是假装对同一 OS 用户下的任意恶意 Python 代码提供密码学隔离。产品顶层 Agent 已禁止直接使用 terminal/file/code；受限媒体代码 worker 不能获得学习或 Human Observer 工具。若未来引入不可信本地插件或多租户执行，需要把研究 writer 移入单独进程和 OS 权限域，不能继续依靠 Python 模块边界。

## 写入路径

### 用户权威路径

```text
用户明确陈述/选择
→ 原生 account strategy owner 建立 draft/version
→ 用户确认准确版本
→ 当前版本生效
```

它适用于偏好、创作者画像、IP 方向、赛道选择、受众假设、定位、内容系统和高影响动作授权。确认不写平台/市场/账号知识。

### 系统事实与学习路径

```text
Provider/Evidence/Receipt
→ 不可变观察
→ pending candidate
→ system capability
→ 来源 + 重复样本 + 时效 + 冲突 + 反证 + replay
→ accepted/rejected/waiting/superseded
→ 版本化投影
```

普通用户界面没有这个工作流。需要运营可观测性时，只能建设受控的系统审计面，不得重新把候选决策交给对话或普通用户。

### 数据主体权利路径

同意、撤回、删除和保留期由 privacy/rights owner 执行。它可以阻断处理、撤回来源或删除允许删除的数据，但不能伪造“理论已被证伪”或“事实从未发生”。审计 tombstone 与业务事实的保留必须服从法律和产品政策。

## 完成门

任何声称该架构完成的改动，必须同时证明：

- 会话能确认用户偏好和 IP 战略，但不能决定学习候选；
- Gateway/Desktop 没有 Human Observer 或学习写入口；
- 直接调用系统学习 repository 没有 capability 会失败；
- 原始观察和预测仍不可变；
- 用户纠错能进入证据/冲突路径，而非被忽略或直接覆盖；
- 个人 IP 内容生产、发布授权与回执闭环没有因研究系统而退化。
