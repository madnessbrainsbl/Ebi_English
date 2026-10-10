const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const playwright = require('playwright');
const artifactDir = process.env.ARTIFACT_DIR || path.join(__dirname, 'audit-artifacts');
fs.mkdirSync(artifactDir, { recursive: true });
const appUrl = process.env.BASE_URL || pathToFileURL(path.join(__dirname, '..', 'index.html')).href;
module.exports = { ...playwright, playwright, artifactDir, appUrl };
