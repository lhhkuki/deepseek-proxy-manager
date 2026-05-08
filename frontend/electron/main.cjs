const { app, BrowserWindow, Menu } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')

let mainWindow
let backendProcess

const isDev = !app.isPackaged

function findBackend() {
  // Standalone exe (production)
  const exeDir = path.dirname(process.execPath)
  const exePath = path.join(exeDir, 'proxy-backend.exe')
  if (fs.existsSync(exePath)) return { path: exePath, isExe: true }

  // Dev: fall back to Python script
  const devScript = path.join(__dirname, '..', '..', 'api_server.py')
  if (fs.existsSync(devScript)) return { path: devScript, isExe: false }

  return null
}

function startBackend() {
  const backend = findBackend()
  if (!backend) {
    console.error('Could not find backend')
    return
  }
  console.log(`Starting backend: ${backend.path}`)

  if (backend.isExe) {
    backendProcess = spawn(backend.path, [], {
      stdio: 'pipe', windowsHide: true,
    })
  } else {
    backendProcess = spawn('python', [backend.path], {
      stdio: 'pipe', windowsHide: true,
    })
  }
  backendProcess.on('error', (err) => {
    console.error(`Backend start failed: ${err.message}`)
  })
  backendProcess.stdout.on('data', (d) => console.log(`[Backend] ${d}`))
  backendProcess.stderr.on('data', (d) => console.error(`[Backend] ${d}`))
  backendProcess.on('close', (code) => console.log(`Backend exited: ${code}`))
}

function createWindow() {
  Menu.setApplicationMenu(null)

  mainWindow = new BrowserWindow({
    width: 900, height: 700,
    minWidth: 700, minHeight: 500,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      webSecurity: false,
    },
    titleBarStyle: 'default',
    backgroundColor: '#f5f5f7',
    show: false,
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    const indexPath = path.join(__dirname, '..', 'dist', 'index.html')
    mainWindow.loadFile(indexPath)
  }

  mainWindow.once('ready-to-show', () => mainWindow.show())
}

app.whenReady().then(() => {
  startBackend()
  setTimeout(createWindow, 4000)
})

app.on('window-all-closed', () => {
  if (backendProcess) backendProcess.kill()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (backendProcess) backendProcess.kill()
})
