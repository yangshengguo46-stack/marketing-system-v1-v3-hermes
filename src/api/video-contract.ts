export type VideoStudioMode = 'create' | 'edit' | 'review'

export interface OpenVideoStudioCommand {
  project_id: string
  job_id?: string
  mode: VideoStudioMode
  locale: 'zh-CN'
  return_to: 'ideas' | 'publish' | 'overview'
  one_time_token: string
}

export type VideoStudioEvent =
  | { type: 'studio.ready'; project_id: string }
  | { type: 'project.updated'; project_id: string; updated_at: string }
  | { type: 'job.progress'; job_id: string; progress: number; stage?: string }
  | { type: 'job.failed'; job_id: string; code: string; retryable: boolean }
  | { type: 'render.ready'; project_id: string; render_id: string }
  | { type: 'user.approved'; project_id: string; render_id: string }
  | { type: 'studio.close'; project_id: string; return_to: string }

export type DesktopStudioEvent =
  | { type: 'agent.apply_revision'; project_id: string; instruction: string }
  | { type: 'account.changed'; project_id: string; account_id: string }
  | { type: 'theme.changed'; theme: 'dark' | 'light' }
  | { type: 'studio.focus'; project_id: string; target?: string }
