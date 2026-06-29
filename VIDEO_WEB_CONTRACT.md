# Web 视频工作台预留接口契约

> 状态：接口冻结，暂不实现视频生成。桌面智能体继续作为唯一编排入口，Web 应用只承担可视化制作与云端生成。

## 一、产品边界

- 桌面端负责：理解目标、采集热点、选择账号、生成 brief、创建任务、展示全局进度、审核与发布衔接。
- Web 工作台负责：脚本/分镜编辑、素材管理、字幕配音、生成渲染、版本对比与成品导出。
- 双方共享同一个 `project_id`；禁止要求用户复制提示词、重复登录或手工下载后再上传。
- 微信/飞书不是主链路，不进入本契约。

## 二、打开工作台

桌面端通过 Electron `WebContentsView` 内嵌 Web 工作台，不使用外部浏览器或普通 iframe。

```ts
type OpenVideoStudioCommand = {
  project_id: string
  job_id?: string
  mode: 'create' | 'edit' | 'review'
  locale: 'zh-CN'
  return_to: 'ideas' | 'publish' | 'overview'
  one_time_token: string
}
```

`one_time_token` 只能使用一次、有效期不超过 60 秒；Web 应用换取自己的短期会话后立即销毁。

## 三、核心数据对象

```ts
type VideoProject = {
  id: string
  title: string
  status: 'brief' | 'editing' | 'generating' | 'review' | 'approved' | 'failed'
  target_account_id: string
  target_platform: string
  trend_evidence_ids: string[]
  brief: ContentBrief
  script_versions: ScriptVersion[]
  storyboard?: Storyboard
  assets: MediaAsset[]
  renders: RenderVersion[]
  created_at: string
  updated_at: string
}

type ContentBrief = {
  objective: string
  audience: string
  angle: string
  evidence: Array<{ title: string; source: string; url?: string; collected_at?: string }>
  constraints: string[]
}

type VideoJob = {
  id: string
  project_id: string
  kind: 'script' | 'storyboard' | 'asset' | 'render' | 'export'
  status: 'queued' | 'running' | 'waiting_user' | 'completed' | 'failed' | 'cancelled'
  progress: number
  stage?: string
  error?: { code: string; message: string; retryable: boolean }
  created_at: string
  updated_at: string
}
```

## 四、预留 HTTP 接口

| Method | Path | 用途 |
|--------|------|------|
| `POST` | `/v1/desktop/session-exchange` | 一次性令牌换取 Web 会话 |
| `POST` | `/v1/video/projects` | 智能体创建已填充 brief 的项目 |
| `GET` | `/v1/video/projects/{project_id}` | 桌面与 Web 获取同一项目状态 |
| `PATCH` | `/v1/video/projects/{project_id}` | 保存用户编辑和审核状态 |
| `POST` | `/v1/video/projects/{project_id}/jobs` | 创建脚本、分镜、生成或导出任务 |
| `GET` | `/v1/video/jobs/{job_id}` | 查询任务状态 |
| `POST` | `/v1/video/jobs/{job_id}/retry` | 重试可恢复失败 |
| `POST` | `/v1/video/jobs/{job_id}/cancel` | 取消任务 |
| `POST` | `/v1/video/projects/{project_id}/approve` | 用户批准当前成片 |
| `GET` | `/v1/video/projects/{project_id}/events` | SSE 进度与版本事件 |

## 五、桌面桥事件

Web → Desktop：

```ts
type VideoStudioEvent =
  | { type: 'studio.ready'; project_id: string }
  | { type: 'project.updated'; project_id: string; updated_at: string }
  | { type: 'job.progress'; job_id: string; progress: number; stage?: string }
  | { type: 'job.failed'; job_id: string; code: string; retryable: boolean }
  | { type: 'render.ready'; project_id: string; render_id: string }
  | { type: 'user.approved'; project_id: string; render_id: string }
  | { type: 'studio.close'; project_id: string; return_to: string }
```

Desktop → Web：

```ts
type DesktopStudioEvent =
  | { type: 'agent.apply_revision'; project_id: string; instruction: string }
  | { type: 'account.changed'; project_id: string; account_id: string }
  | { type: 'theme.changed'; theme: 'dark' | 'light' }
  | { type: 'studio.focus'; project_id: string; target?: string }
```

## 六、验收标准

1. 用户从选题点击“开始制作”后，3 秒内看到已填好的项目，不出现第二次登录。
2. 关闭视频页不会中断云端任务，重新打开恢复原进度和版本。
3. Web 中的每次关键修改可被桌面智能体读取，用户无需重复描述。
4. 成片批准后自动进入桌面发布任务，不需要下载/上传中转。
5. Web 服务不可用时桌面保留项目与任务状态，并提供明确重试，不显示假进度。

