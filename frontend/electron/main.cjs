const { app, BrowserWindow, Menu } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')

let mainWindow
let pythonProcess

const isDev = !app.isPackaged

function findBackendScript() {
  const baseName = 'api_server.py'
  const exeDir = path.dirname(process.execPath)
  const prodPath = path.join(exeDir, baseName)
  if (fs.existsSync(prodPath)) return prodPath
  const devPath = path.join(__dirname, '..', '..', baseName)
  if (fs.existsSync(devPath)) return devPath
  return null
}

function installDeps(scriptDir, callback) {
  const reqPath = path.join(scriptDir, 'requirements.txt')
  if (!fs.existsSync(reqPath)) {
    callback()
    return
  }
  // Try pip3 first, then python -m pip, then pip
  const pipCmds = [
    {cmd: 'pip', args: ['install', '-r', reqPath, '-q']},
    {cmd: 'pip3', args: ['install', '-r', reqPath, '-q']},
    {cmd: 'python', args: ['-m', 'pip', 'install', '-r', reqPath, '-q']},
  ]
  function tryPip(idx) {
    if (idx >= pipCmds.length) { callback(); return }
    const c = pipCmds[idx]
    const child = spawn(c.cmd, c.args, {stdio: 'pipe', windowsHide: true})
    child.on('close', (code) => {
      if (code === 0) callback()
      else tryPip(idx + 1)
    })
    child.on('error', () => tryPip(idx + 1))
  }
  tryPip(0)
  })
  pip.stderr.on('data', (d) => { console.error(`[pip] ${d}`) })
}

function startPythonBackend() {
  const scriptPath = findBackendScript()
  if (!scriptPath) {
    console.error('Could not find api_server.py')
    return
  }
  const scriptDir = path.dirname(scriptPath)

  // Auto-install Python dependencies, then start backend
  installDeps(scriptDir, () => {
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'
    console.log(`Starting backend: ${pythonCmd} ${scriptPath}`)
    pythonProcess = spawn(pythonCmd, [scriptPath], {
      stdio: 'pipe',
      windowsHide: true,
    })
    pythonProcess.on('error', (err) => {
      // Try python3 if python failed
      if (pythonCmd === 'python') {
        console.log('python failed, trying python3')
        pythonProcess = spawn('python3', [scriptPath], {
          stdio: 'pipe', windowsHide: true,
        })
        pythonProcess.on('error', () => {})
      }
    })
    pythonProcess.on('error', (err) => {
      console.error(`Failed to start Python: ${err.message}`)
    })
    pythonProcess.stdout.on('data', (data) => {
      console.log(`[Python] ${data}`)
    })
    pythonProcess.stderr.on('data', (data) => {
      console.error(`[Python Error] ${data}`)
    })
    pythonProcess.on('close', (code) => {
      console.log(`Python process exited with code ${code}`)
    })
  })
}

function createWindow() {
  Menu.setApplicationMenu(null)

  mainWindow = new BrowserWindow({
    width: 900,
    height: 700,
    minWidth: 700,
    minHeight: 500,
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
    console.log(`Loading from: ${indexPath}`)
    console.log(`__dirname: ${__dirname}`)
    mainWindow.loadFile(indexPath)
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })
}

app.whenReady().then(() => {
  startPythonBackend()
  setTimeout(() => {
    createWindow()
  }, 4000)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill()
  }
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill()
  }
})
