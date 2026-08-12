/**
 * Capture full-page screenshots of the running app.
 *
 *   npm run dev              # in one terminal
 *   npx electron scripts/screenshot.js [--dark] [--out ../docs/screens]
 *
 * Why Electron rather than Playwright: Electron is already a dependency for the
 * desktop shell, so this needs no extra 300 MB of browser binaries, and it
 * renders with the same engine the desktop app ships with — which is the thing
 * whose appearance we actually care about.
 *
 * Each page is measured first and the window resized to its full height, so the
 * capture is the whole document rather than a viewport crop.
 */

const { app, BrowserWindow, nativeImage } = require("electron");
const fs = require("node:fs/promises");
const path = require("node:path");

const args = process.argv.slice(2);
const DARK = args.includes("--dark");
const outIdx = args.indexOf("--out");
const OUT = path.resolve(
  __dirname,
  outIdx >= 0 ? args[outIdx + 1] : path.join("..", "..", "docs", "screens"),
);
const BASE = process.env.SHOT_BASE || "http://localhost:3000";
const WIDTH = 1280;

const PAGES = [
  ["home", "/"],
  ["compare", "/compare"],
  ["track", "/track"],
  ["analyse", "/analyse"],
  ["allocate", "/allocate"],
  ["methodology", "/methodology"],
];

async function main() {
  await fs.mkdir(OUT, { recursive: true });

  const win = new BrowserWindow({
    width: WIDTH,
    height: 900,
    show: false,
    webPreferences: { offscreen: false },
  });

  // Electron honours the OS theme by default; force the one we asked for so a
  // run is reproducible rather than dependent on whoever's laptop this is.
  const { nativeTheme } = require("electron");
  nativeTheme.themeSource = DARK ? "dark" : "light";

  for (const [name, route] of PAGES) {
    // Shrink back before measuring. scrollHeight is never less than the
    // viewport, so leaving the window at the previous (tall) page's height
    // makes every short page report that height and capture as mostly empty
    // space — which is exactly what the first run produced.
    win.setContentSize(WIDTH, 900);
    await win.loadURL(BASE + route);

    // Settle: fonts, the reveal observer, and any client fetch on mount.
    await win.webContents.executeJavaScript(
      "new Promise(r => setTimeout(r, 2500))",
    );

    const height = await win.webContents.executeJavaScript(
      "Math.min(document.documentElement.scrollHeight, 6000)",
    );
    win.setContentSize(WIDTH, Math.ceil(height));
    // Long enough for the reveal deadline (2.5s) plus the 600ms transition and
    // its stagger. Capturing at 900ms caught the page mid-fade and produced
    // screenshots that looked like the app was broken.
    await win.webContents.executeJavaScript(
      "new Promise(r => setTimeout(r, 4000))",
    );

    const image = await win.webContents.capturePage();
    const file = path.join(OUT, `${name}${DARK ? "-dark" : ""}.png`);
    await fs.writeFile(file, image.toPNG());
    const { width, height: h } = image.getSize();
    console.log(`${file}  ${width}x${h}`);
  }

  win.destroy();
  app.quit();
}

app.whenReady().then(() =>
  main().catch((err) => {
    console.error(err);
    app.exit(1);
  }),
);
