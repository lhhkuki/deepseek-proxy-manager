const { app, BrowserWindow } = require('electron')
const { spawn } = require('child_process')
const path = require('path')

let mainWindow
let pythonProcess

const isDev = !app.isPackaged

function startPythonBackend() {
  const scriptPath = path.join(__dirname, '..', 'api_server.py')
  pythonProcess = spawn('python', [scriptPath], {
    stdio: 'pipe',
    windowsHide: true,
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
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 700,
    minWidth: 700,
    minHeight: 500,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#f5f5f7',
    show: false,
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })
}

app.whenReady().then(() => {
  startPythonBackend()
  
  // Wait a bit for Python to start
  setTimeout(() => {
    createWindow()
  }, 1500)

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