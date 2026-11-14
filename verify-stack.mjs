#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve, join } from 'node:path';

// Determine repository root
let repoRoot = process.cwd();
if (!existsSync(join(repoRoot, 'frontend')) && existsSync(join(repoRoot, '..', 'frontend'))) {
  repoRoot = resolve(repoRoot, '..');
}

const frontendDir = join(repoRoot, 'frontend');
const backendDir = join(repoRoot, 'backend');

console.log(`[verify-stack] Running stack verification at: ${repoRoot}`);

let hasErrors = false;

// 1. Run Next.js lint
console.log('\n--- [1/3] Frontend: npm run lint ---');
if (existsSync(frontendDir)) {
  const isWindows = process.platform === 'win32';
  const npmCmd = isWindows ? 'npm.cmd' : 'npm';
  
  const lintResult = spawnSync(npmCmd, ['run', 'lint'], {
    cwd: frontendDir,
    stdio: 'inherit',
    shell: true,
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
    cwd: frontendDir,
    stdio: 'inherit',
    shell: true,
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
  const venvRuff = isWindows
    ? join(repoRoot, '.venv', 'Scripts', 'ruff.exe')
    : join(repoRoot, '.venv', 'bin', 'ruff');

  if (existsSync(venvRuff)) {
    ruffExecutable = `"${venvRuff}"`;
  }

  const ruffResult = spawnSync(ruffExecutable, ['check', 'backend'], {
    cwd: repoRoot,
    stdio: 'inherit',
    shell: true,
  });

  if (ruffResult.error) {
    console.log('ℹ Ruff not available in environment; skipping backend ruff check.');
  } else if (ruffResult.status !== 0) {
    console.error('❌ Backend ruff check failed.');
    hasErrors = true;
  } else {
    console.log('✔ Backend ruff check passed.');
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
