const fs = require('node:fs')
const path = require('node:path')

const frontendRoot = path.resolve(__dirname, '..')
const releaseDir = path.join(frontendRoot, 'release')
const pkg = require(path.join(frontendRoot, 'package.json'))
const currentVersion = String(pkg.version || '').trim()
const beforeBuild = process.argv.includes('--before-build')

if (!fs.existsSync(releaseDir)) {
  process.exit(0)
}

const keepNames = new Set([
  `AI Proxy Manager Setup ${currentVersion}.exe`,
  `AI Proxy Manager Setup ${currentVersion}.exe.blockmap`,
  'builder-debug.yml',
])

for (const entry of fs.readdirSync(releaseDir, { withFileTypes: true })) {
  if (!entry.isFile()) continue
  const fullPath = path.join(releaseDir, entry.name)
  const isInstallerArtifact =
    entry.name.endsWith('.exe') ||
    entry.name.endsWith('.exe.blockmap') ||
    entry.name.endsWith('.__uninstaller.exe')
  if (!isInstallerArtifact) continue
  if (!beforeBuild && keepNames.has(entry.name)) continue
  fs.rmSync(fullPath, { force: true })
  console.log(`removed ${entry.name}`)
}
