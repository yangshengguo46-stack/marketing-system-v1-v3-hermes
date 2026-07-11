const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const { ROOT_FILES, SOURCE_DIRS, stageProductRuntime } = require('./stage-product-runtime.cjs')

test('stages a self-contained product runtime without editable checkout pointers', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'marketing-os-runtime-stage-'))
  const desktopRoot = path.join(root, 'apps', 'desktop')
  const agentRoot = path.join(root, 'agent-source')
  const pythonRoot = path.join(root, 'python-source')
  const purelib = path.join(root, 'site-packages')
  const executable = path.join(pythonRoot, 'bin', 'python3')
  fs.mkdirSync(path.dirname(executable), { recursive: true })
  fs.writeFileSync(executable, '#!/bin/sh\n')
  fs.mkdirSync(purelib, { recursive: true })
  fs.writeFileSync(path.join(purelib, 'runtime_dependency.py'), 'READY = True\n')
  fs.writeFileSync(path.join(purelib, '__editable__.hermes_agent.pth'), '/developer/checkout\n')
  for (const relative of SOURCE_DIRS) {
    fs.mkdirSync(path.join(agentRoot, relative), { recursive: true })
    fs.writeFileSync(path.join(agentRoot, relative, 'marker.txt'), relative)
  }
  for (const relative of ROOT_FILES) {
    fs.mkdirSync(path.dirname(path.join(agentRoot, relative)), { recursive: true })
    fs.writeFileSync(path.join(agentRoot, relative), relative)
  }

  const result = stageProductRuntime({
    desktopRoot,
    agentRoot,
    productTree: 'a'.repeat(40),
    pythonInfo: {
      base_prefix: pythonRoot,
      executable,
      machine: process.arch,
      platform: process.platform,
      purelib,
      version: '3.13.0'
    }
  })

  assert.equal(result.manifest.productId, 'marketing-os')
  assert.equal(result.manifest.productTree, 'a'.repeat(40))
  assert.equal(result.manifest.python.executable, 'python/bin/python3')
  assert.ok(fs.existsSync(path.join(result.output, 'agent', 'marketing_os', 'marker.txt')))
  assert.ok(fs.existsSync(path.join(result.output, 'site-packages', 'runtime_dependency.py')))
  assert.equal(fs.existsSync(path.join(result.output, 'site-packages', '__editable__.hermes_agent.pth')), false)
})
