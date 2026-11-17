#!/usr/bin/env node

/**
 * Browser Enforcement Launcher for Teloxtech SaaS
 * Enforces Google Chrome execution and strictly bypasses Microsoft Edge / M365.
 */

import { spawnSync, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';

const targetUrl = process.argv[2] || 'http://localhost:3000';

const chromeCandidates = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  `${process.env.LOCALAPPDATA}\\Google\\Chrome\\Application\\chrome.exe`,
  `${process.env.ProgramFiles}\\Google\\Chrome\\Application\\chrome.exe`,
  `${process.env['ProgramFiles(x86)']}\\Google\\Chrome\\Application\\chrome.exe`,
];

let chromeExecutable = null;
for (const cand of chromeCandidates) {
  if (cand && existsSync(cand)) {
    chromeExecutable = cand;
    break;
  }
}

if (!chromeExecutable) {
  console.error('❌ Google Chrome executable not found. Google Chrome is required for this execution.');
  process.exit(1);
}

console.log('==========================================================');
console.log('🚀 Teloxtech SaaS — Browser Enforcement Policy');
console.log(`🌐 Enforced Browser: Google Chrome (${chromeExecutable})`);
console.log('🚫 Prohibited Browsers: Microsoft Edge, Microsoft 365');
console.log(`🔗 Target URL: ${targetUrl}`);
console.log('==========================================================');

// Enforce BROWSER environment variable for subprocesses
process.env.BROWSER = chromeExecutable;

// Launch Google Chrome in a dedicated new window
const child = spawn(chromeExecutable, ['--new-window', targetUrl], {
  detached: true,
  stdio: 'ignore',
});
child.unref();

console.log('✔ App successfully opened in Google Chrome.');
