import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const readJson = (relative) => JSON.parse(fs.readFileSync(path.join(root, relative), 'utf8'));
const policy = readJson('version-policy.json');
const manifest = readJson('package.json');
const lock = readJson('package-lock.json');
const installedLock = readJson('node_modules/.package-lock.json');
const expected = policy.dependencies;

const assertVersions = (label, actual) => {
  for (const [name, version] of Object.entries(expected)) {
    if (actual?.[name] !== version) {
      throw new Error(`${label} drifted: ${name} must remain ${version}, got ${actual?.[name] ?? 'missing'}`);
    }
  }
};

assertVersions('package.json', manifest.dependencies);
assertVersions('package-lock root', lock.packages?.['']?.dependencies);
for (const [name, version] of Object.entries(expected)) {
  const key = `node_modules/${name}`;
  if (lock.packages?.[key]?.version !== version) {
    throw new Error(`package-lock package drifted: ${name} must remain ${version}`);
  }
  if (installedLock.packages?.[key]?.version !== version) {
    throw new Error(`installed lockfile drifted: ${name} must remain ${version}`);
  }
  const installedPackage = readJson(`${key}/package.json`);
  if (installedPackage.version !== version) {
    throw new Error(`installed package drifted: ${name} must remain ${version}`);
  }
}
if (expected.remotion !== policy.remotion_upgrade_gate.locked_version) {
  throw new Error('Remotion upgrade gate and dependency pin disagree');
}
if (policy.remotion_upgrade_gate.blocked_major !== 5) {
  throw new Error('Remotion 5 upgrade gate is missing');
}
const requiredReviews = ['explicit_user_approval', 'license_review', 'renderer_regression'];
if (JSON.stringify(policy.remotion_upgrade_gate.requires) !== JSON.stringify(requiredReviews)) {
  throw new Error('Remotion upgrade requirements have drifted');
}
if (Number(expected.remotion.split('.')[0]) >= policy.remotion_upgrade_gate.blocked_major) {
  throw new Error('Remotion major upgrade requires explicit approval and license review');
}

process.stdout.write(`video renderer pins verified; Remotion ${expected.remotion} is locked\n`);
