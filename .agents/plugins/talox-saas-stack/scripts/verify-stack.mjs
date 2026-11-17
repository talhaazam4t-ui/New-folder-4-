#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';

// Determine repository root
let repoRoot = process.cwd();
if (!existsSync(join(repoRoot, 'frontend')) && existsSync(join(repoRoot, '..', 'frontend'))) {
  repoRoot = resolve(repoRoot, '..');
}

// Resolve main git repository root so linked git worktrees can find shared .venv / node_modules
let mainRepoRoot = repoRoot;
const gitCommonDir = spawnSync('git', ['rev-parse', '--git-common-dir'], {
  cwd: repoRoot,
  encoding: 'utf8',
});
if (gitCommonDir.status === 0 && gitCommonDir.stdout) {
  const commonPath = gitCommonDir.stdout.trim();
  if (commonPath && commonPath !== '.git') {
    mainRepoRoot = dirname(resolve(repoRoot, commonPath));
  }
}

const frontendDir = join(repoRoot, 'frontend');
const mainFrontendDir = join(mainRepoRoot, 'frontend');
const frontendExecDir = existsSync(join(frontendDir, 'node_modules', '.bin'))
  ? frontendDir
  : existsSync(join(mainFrontendDir, 'node_modules', '.bin'))
    ? mainFrontendDir
    : frontendDir;
const backendDir = join(repoRoot, 'backend');

console.log(`[verify-stack] Running stack verification at: ${repoRoot}`);

let hasErrors = false;

// 1. Run Next.js lint
console.log('\n--- [1/3] Frontend: npm run lint ---');
if (existsSync(frontendExecDir)) {
  const isWindows = process.platform === 'win32';
  const npmCmd = isWindows ? 'npm.cmd' : 'npm';

  const lintResult = spawnSync(npmCmd, ['run', 'lint'], {
    cwd: frontendExecDir,
    stdio: 'inherit',
    shell: true,
    env: { ...process.env, NODE_OPTIONS: '--max-old-space-size=512' },
  });

  if (lintResult.status !== 0) {
    console.error('❌ Frontend lint failed.');
    hasErrors = true;
  } else {
    console.log('✔ Frontend lint passed.');
  }

  // 2. Run TypeScript type checking
  console.log('\n--- [2/3] Frontend: tsc --noEmit ---');
  const npxCmd = isWindows ? 'npx.cmd' : 'npx';
  const tscResult = spawnSync(npxCmd, ['tsc', '--noEmit'], {
    cwd: frontendExecDir,
    stdio: 'inherit',
    shell: true,
    env: { ...process.env, NODE_OPTIONS: '--max-old-space-size=512' },
  });

  if (tscResult.status !== 0) {
    console.error('❌ TypeScript check (tsc --noEmit) failed.');
    hasErrors = true;
  } else {
    console.log('✔ TypeScript check passed.');
  }
} else {
  console.warn('⚠️ Frontend directory not found; skipping frontend checks.');
}

// 3. Optional Backend sanity check
console.log('\n--- [3/3] Backend: Ruff / Python Sanity ---');
if (existsSync(backendDir)) {
  const isWindows = process.platform === 'win32';
  let ruffExecutable = 'ruff';
  const venvCandidates = [
    isWindows ? join(repoRoot, '.venv', 'Scripts', 'ruff.exe') : join(repoRoot, '.venv', 'bin', 'ruff'),
    isWindows ? join(mainRepoRoot, '.venv', 'Scripts', 'ruff.exe') : join(mainRepoRoot, '.venv', 'bin', 'ruff'),
  ];

  if (existsSync(venvRuff)) {
    ruffExecutable = `"${venvRuff}"`;
  }

  const ruffResult = spawnSync(ruffExecutable, ['check', 'backend'], {
    cwd: repoRoot,
    stdio: 'inherit',
    shell: true,
  });

  if (ruffResult.status !== 0) {
    console.error('❌ Backend ruff check failed.');
    hasErrors = true;
  } else {
    console.log('✔ Backend ruff check passed.');
  }
}
}

console.log('\n========================================');
if (hasErrors) {
  console.error('❌ Stack verification failed with errors. Please fix before proceeding.');
  process.exit(1);
} else {
  console.log('✔ All stack verification checks passed cleanly!');
  process.exit(0);
}
