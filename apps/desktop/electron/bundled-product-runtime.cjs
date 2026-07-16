'use strict'

const fs = require('node:fs')
const path = require('node:path')

function safeRuntimePath(root, relative, label) {
  if (typeof relative !== 'string' || !relative.trim() || path.isAbsolute(relative)) {
    throw new Error(`invalid ${label} path in bundled runtime manifest`)
  }
  const resolvedRoot = path.resolve(root)
  const resolved = path.resolve(resolvedRoot, relative)
  if (resolved !== resolvedRoot && !resolved.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw new Error(`${label} path escapes bundled runtime root`)
  }
  return resolved
}

function resolveBundledProductRuntime(resourcesPath, options = {}) {
  const fsImpl = options.fsImpl || fs
  const platform = options.platform || process.platform
  const arch = options.arch || process.arch
  if (!resourcesPath) return null
  const root = path.join(path.resolve(resourcesPath), 'marketing-os-runtime')
  const manifestPath = path.join(root, 'runtime-manifest.json')
  if (!fsImpl.existsSync(manifestPath)) return null
  const manifest = JSON.parse(fsImpl.readFileSync(manifestPath, 'utf8'))
  if (manifest.schemaVersion !== 1 || manifest.productId !== 'marketing-os') {
    throw new Error('unsupported bundled Marketing OS runtime manifest')
  }
  if (manifest.platform !== platform || manifest.arch !== arch) {
    throw new Error(`bundled runtime target mismatch: ${manifest.platform}/${manifest.arch} != ${platform}/${arch}`)
  }
  const pythonExecutable = safeRuntimePath(root, manifest.python?.executable, 'python executable')
  const agentRoot = safeRuntimePath(root, manifest.paths?.agent, 'agent')
  const sitePackages = safeRuntimePath(root, manifest.paths?.sitePackages, 'site-packages')
  const nodeModules = safeRuntimePath(root, manifest.paths?.nodeModules, 'browser node_modules')
  const playwrightBrowsers = safeRuntimePath(root, manifest.paths?.playwrightBrowsers, 'Playwright browsers')
  const playwrightBrowserExecutable = safeRuntimePath(
    root,
    manifest.paths?.playwrightBrowserExecutable,
    'Playwright browser executable'
  )
  const videoRenderers = safeRuntimePath(root, manifest.paths?.videoRenderers, 'video renderers')
  for (const [label, target] of [
    ['python executable', pythonExecutable],
    ['Hermes agent', path.join(agentRoot, 'hermes_cli', 'main.py')],
    ['site-packages', sitePackages],
    ['marketing browser MCP', path.join(agentRoot, 'mcp', 'marketing-browser', 'src', 'server.js')],
    ['browser node_modules', nodeModules],
    ['Playwright browsers', playwrightBrowsers],
    ['Playwright browser executable', playwrightBrowserExecutable],
    ['video renderer package', path.join(videoRenderers, 'package.json')],
    ['Remotion renderer', path.join(videoRenderers, 'render-remotion.mjs')],
    ['HyperFrames renderer', path.join(videoRenderers, 'render-hyperframes.mjs')],
    ['video renderer dependencies', path.join(videoRenderers, 'node_modules', '.package-lock.json')]
  ]) {
    if (!fsImpl.existsSync(target)) throw new Error(`bundled ${label} missing: ${target}`)
  }
  return {
    root,
    manifest,
    pythonExecutable,
    agentRoot,
    sitePackages,
    nodeModules,
    playwrightBrowsers,
    playwrightBrowserExecutable,
    videoRenderers
  }
}

module.exports = { resolveBundledProductRuntime, safeRuntimePath }
