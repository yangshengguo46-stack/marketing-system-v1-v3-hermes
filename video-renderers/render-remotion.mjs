import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const [specPath, outputPath, browserExecutable] = process.argv.slice(2);
if (!specPath || !outputPath || !browserExecutable) {
  throw new Error('usage: render-remotion.mjs <spec.json> <output.mp4> <browser>');
}
for (const [label, target] of [['scene spec', specPath], ['browser', browserExecutable]]) {
  if (!fs.existsSync(target)) throw new Error(`${label} is missing: ${target}`);
}

fs.mkdirSync(path.dirname(path.resolve(outputPath)), {recursive: true});
const cli = path.join(root, 'node_modules', '@remotion', 'cli', 'remotion-cli.js');
const args = [
  cli,
  'render',
  path.join(root, 'remotion', 'index.ts'),
  'MarketingScene',
  path.resolve(outputPath),
  `--props=${path.resolve(specPath)}`,
  `--public-dir=${path.dirname(path.resolve(specPath))}`,
  `--browser-executable=${path.resolve(browserExecutable)}`,
  '--codec=h264',
  '--crf=20',
  '--concurrency=1',
  '--overwrite',
  '--log=warn',
];
const result = spawnSync(process.execPath, args, {
  cwd: root,
  env: {...process.env, REMOTION_NO_UPDATE_CHECK: '1'},
  stdio: 'inherit',
});
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);
