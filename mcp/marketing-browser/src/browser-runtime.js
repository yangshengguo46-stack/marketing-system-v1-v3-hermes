import fs from 'node:fs'
import path from 'node:path'

function executableOnPath(name, env, exists) {
  for (const dir of String(env.PATH || '').split(path.delimiter)) {
    if (!dir) continue
    const candidate = path.join(dir, name)
    if (exists(candidate)) return candidate
  }
  return ''
}

export function resolveBrowserExecutable({
  env = process.env,
  platform = process.platform,
  exists = fs.existsSync,
} = {}) {
  const override = String(env.HERMES_BROWSER_EXECUTABLE || '').trim()
  if (override) {
    if (!exists(override)) throw new Error('configured Hermes browser executable does not exist')
    return override
  }

  const candidates = platform === 'darwin'
    ? [
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
      ]
    : platform === 'win32'
      ? [
          path.join(env.PROGRAMFILES || '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
          path.join(env['PROGRAMFILES(X86)'] || '', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
          path.join(env.LOCALAPPDATA || '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
        ]
      : [
          executableOnPath('google-chrome', env, exists),
          executableOnPath('microsoft-edge', env, exists),
          executableOnPath('chromium', env, exists),
          executableOnPath('chromium-browser', env, exists),
        ]
  return candidates.find(candidate => candidate && exists(candidate)) || ''
}
