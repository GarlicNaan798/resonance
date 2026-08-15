/**
 * Resonance desktop shell.
 *
 * Runs the Next.js server as a child process on a loopback port and points a
 * BrowserWindow at it. The point of the desktop build is not convenience. It
 * is that the trust claim stops being a promise and becomes something the user
 * can check with their own firewall. Three things make that true:
 *
 *   1. The encoder weights ship inside the bundle (RESONANCE_ENCODER_DIR) and
 *      the runtime is locked to local files. See lib/inference/ranker.ts.
 *   2. Campaign data is written to the OS user-data directory and nowhere else.
 *   3. The window refuses to navigate anywhere but its own loopback origin, so
 *      a stray link cannot turn the shell into a browser.
 *
 * ponytail: spawns `next start` rather than embedding the server in-process.
 * One extra process, but the alternative is reimplementing Next's bootstrap;
 * revisit only if startup latency becomes a complaint.
 */

const { app, BrowserWindow, Menu, shell, dialog } = require("electron");
const { spawn } = require("node:child_process");
const { createServer } = require("node:net");
const path = require("node:path");

const isDev = !app.isPackaged;

/**
 * Resources live in different places packaged vs not. Getting this wrong is the
 * classic Electron bug. It works in development and ships broken.
 */
const APP_ROOT = isDev
  ? path.join(__dirname, "..")
  : path.join(process.resourcesPath, "app");

let serverProcess = null;
let serverPort = null;

/** Ask the OS for a free port rather than guessing one that may be in use. */
function freePort() {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.once("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

/** Resolve once the server answers, reject if it never does. */
function waitForServer(port, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const res = await fetch(`http://127.0.0.1:${port}/`, {
          method: "HEAD",
        });
        if (res.ok) return resolve();
      } catch {
        // Not up yet, expected while the server boots.
      }
      if (Date.now() > deadline) {
        return reject(new Error(`Server did not start within ${timeoutMs}ms`));
      }
      setTimeout(tick, 250);
    };
    tick();
  });
}

async function startServer() {
  serverPort = await freePort();

  const env = {
    ...process.env,
    PORT: String(serverPort),
    HOSTNAME: "127.0.0.1",
    NODE_ENV: "production",
    RESONANCE_MODE: "self-hosted",
    // Campaign data belongs in the OS user-data directory, not next to the
    // binary and not in whatever directory the app happened to be launched
    // from. This is what makes predictions survive an app upgrade.
    RESONANCE_DATA_DIR: app.getPath("userData"),
    RESONANCE_ENCODER_DIR: path.join(APP_ROOT, "models"),
  };

  // cwd is the standalone directory, not the app root: that is where the
  // traced node_modules and the copied static assets live.
  const standalone = path.join(APP_ROOT, ".next", "standalone");
  const server = path.join(standalone, "server.js");
  serverProcess = spawn(process.execPath, [server], {
    cwd: standalone,
    env: { ...env, ELECTRON_RUN_AS_NODE: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });

  serverProcess.stdout.on("data", (d) => console.log(`[next] ${d}`));
  serverProcess.stderr.on("data", (d) => console.error(`[next] ${d}`));
  serverProcess.on("exit", (code) => {
    if (code !== 0 && !app.isQuitting) {
      dialog.showErrorBox(
        "Resonance stopped",
        `The local server exited with code ${code}.`,
      );
    }
  });

  await waitForServer(serverPort);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1100,
    height: 820,
    minWidth: 760,
    backgroundColor: "#fafafa",
    title: "Resonance",
    webPreferences: {
      // No renderer needs Node here. The app is an ordinary web page talking
      // to a local HTTP server. Leaving these on would hand full filesystem
      // access to any script that made it into the page.
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  const origin = `http://127.0.0.1:${serverPort}`;

  // The no-egress guarantee has to hold for the SHELL too, not just the server.
  // Without these, one external link turns the window into a browser and the
  // claim quietly stops being true.
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(origin)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  win.loadURL(origin);
  return win;
}

function buildMenu() {
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      {
        label: "File",
        submenu: [
          {
            label: "Show data folder",
            // Surfaced deliberately: "your data stays here" is more convincing
            // when the user can open the folder and see for themselves.
            click: () => shell.openPath(app.getPath("userData")),
          },
          { type: "separator" },
          { role: "quit" },
        ],
      },
      { label: "Edit", submenu: [{ role: "copy" }, { role: "paste" }, { role: "selectAll" }] },
      {
        label: "View",
        submenu: [{ role: "reload" }, { role: "toggleDevTools" }, { role: "zoomIn" }, { role: "zoomOut" }],
      },
    ]),
  );
}

app.whenReady().then(async () => {
  buildMenu();
  try {
    await startServer();
  } catch (err) {
    dialog.showErrorBox("Resonance could not start", String(err));
    app.quit();
    return;
  }
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

// The Next server is a child process; without this it outlives the window.
app.on("before-quit", () => {
  app.isQuitting = true;
  if (serverProcess) serverProcess.kill();
});
