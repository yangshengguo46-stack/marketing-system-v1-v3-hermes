export const SESSION_ROUTE_PREFIX = '/chat/'
export const NEW_CHAT_ROUTE = '/chat'
export const WORKBENCH_ROUTE = '/'
export const CONTENT_FACTORY_ROUTE = '/content'
export const ARTICLE_CREATION_ROUTE = '/content/article'
export const VIDEO_CREATION_ROUTE = '/content/video'
export const MATERIAL_LIBRARY_ROUTE = '/materials'
export const ACCOUNT_CENTER_ROUTE = '/accounts'
export const MANAGED_ROUTE = '/managed'
export const SETTINGS_ROUTE = '/settings'
export const COMMAND_CENTER_ROUTE = '/command-center'
export const SKILLS_ROUTE = '/skills'
export const MESSAGING_ROUTE = '/messaging'
export const ARTIFACTS_ROUTE = '/artifacts'
export const CRON_ROUTE = '/cron'
export const PROFILES_ROUTE = '/profiles'
export const AGENTS_ROUTE = '/agents'

export type AppView =
  | 'accounts'
  | 'agents'
  | 'artifacts'
  | 'chat'
  | 'command-center'
  | 'cron'
  | 'messaging'
  | 'profiles'
  | 'settings'
  | 'skills'
  | 'workbench'
  | 'content'
  | 'article-creation'
  | 'video-creation'
  | 'materials'
  | 'managed'

export type AppRouteId =
  | 'accounts'
  | 'agents'
  | 'artifacts'
  | 'command-center'
  | 'cron'
  | 'messaging'
  | 'new'
  | 'profiles'
  | 'settings'
  | 'skills'
  | 'workbench'
  | 'content'
  | 'article-creation'
  | 'video-creation'
  | 'materials'
  | 'managed'

export interface AppRoute {
  id: AppRouteId
  path: string
  view: AppView
}

export const APP_ROUTES = [
  { id: 'workbench', path: WORKBENCH_ROUTE, view: 'workbench' },
  { id: 'content', path: CONTENT_FACTORY_ROUTE, view: 'content' },
  { id: 'article-creation', path: ARTICLE_CREATION_ROUTE, view: 'article-creation' },
  { id: 'video-creation', path: VIDEO_CREATION_ROUTE, view: 'video-creation' },
  { id: 'materials', path: MATERIAL_LIBRARY_ROUTE, view: 'materials' },
  { id: 'accounts', path: ACCOUNT_CENTER_ROUTE, view: 'accounts' },
  { id: 'managed', path: MANAGED_ROUTE, view: 'managed' },
  { id: 'new', path: NEW_CHAT_ROUTE, view: 'chat' },
  { id: 'settings', path: SETTINGS_ROUTE, view: 'settings' },
  { id: 'command-center', path: COMMAND_CENTER_ROUTE, view: 'command-center' },
  { id: 'skills', path: SKILLS_ROUTE, view: 'skills' },
  { id: 'messaging', path: MESSAGING_ROUTE, view: 'messaging' },
  { id: 'artifacts', path: ARTIFACTS_ROUTE, view: 'artifacts' },
  { id: 'cron', path: CRON_ROUTE, view: 'cron' },
  { id: 'profiles', path: PROFILES_ROUTE, view: 'profiles' },
  { id: 'agents', path: AGENTS_ROUTE, view: 'agents' }
] as const satisfies readonly AppRoute[]

const APP_VIEW_BY_PATH = new Map<string, AppView>(APP_ROUTES.map(route => [route.path, route.view]))
const RESERVED_PATHS: ReadonlySet<string> = new Set(APP_ROUTES.map(route => route.path))

// Views that render as a full-screen modal card (OverlayView) over the shell.
// While one is open the app's titlebar control clusters must hide so they don't
// bleed over the overlay (they sit at a higher z-index than the overlay card).
export const OVERLAY_VIEWS: ReadonlySet<AppView> = new Set(['agents', 'command-center', 'cron', 'profiles', 'settings'])

export function isOverlayView(view: AppView): boolean {
  return OVERLAY_VIEWS.has(view)
}

export function isNewChatRoute(pathname: string): boolean {
  return pathname === NEW_CHAT_ROUTE
}

export function routeSessionId(pathname: string): string | null {
  if (!pathname.startsWith(SESSION_ROUTE_PREFIX) || RESERVED_PATHS.has(pathname)) {
    return null
  }

  const id = pathname.slice(SESSION_ROUTE_PREFIX.length)

  return id && !id.includes('/') ? decodeURIComponent(id) : null
}

export function sessionRoute(sessionId: string): string {
  return `${SESSION_ROUTE_PREFIX}${encodeURIComponent(sessionId)}`
}

export function appViewForPath(pathname: string): AppView {
  if (isNewChatRoute(pathname) || routeSessionId(pathname)) {
    return 'chat'
  }

  return APP_VIEW_BY_PATH.get(pathname) ?? 'chat'
}
