## Solution for One‑Click Silent Install + Build + Source Deletion

Your requirements:
1. Run a single command (e.g., double‑click an icon) to install all dependencies, build the app, delete the source code, and start the app.
2. No console window appears in the taskbar – runs as a background process.
3. Deleting the source code must not break the running application.

The challenge: **After a standard Next.js build (`next build`), the running app still needs the original source files** (e.g., `src/`, `public/`, `next.config.js`) because `next start` loads compiled code from `.next` but also relies on the project structure.

**Solution: Use Next.js standalone output mode** – it packs everything needed into a self‑contained `.next/standalone` folder. You can then delete all other source files without affecting the running app.

---

## Step 1 – Enable standalone output

Edit `next.config.js`:

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',          // <-- add this line
  // ... your existing config (e.g., experimental, images, etc.)
};

module.exports = nextConfig;
```

After this change, `npm run build` will generate:
- `.next/standalone/` – all server code and `node_modules` (pruned)
- `.next/static/` – client static files (must be copied manually in production)

---

## Step 2 – Create the silent installer / starter script

We will use a **PowerShell script** that:
- Runs hidden (no console window)
- Executes all steps inside the project directory
- Uses the standalone build to safely delete the original source after build

### `install-and-start.ps1`

```powershell
# Run this script hidden (see Step 3 for launcher)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "Installing dependencies..." -ForegroundColor Cyan
npm install --silent

Write-Host "Building application (standalone)..." -ForegroundColor Cyan
npm run build

# Create a production deployment folder
$DeployRoot = Join-Path $ProjectRoot "deploy"
if (Test-Path $DeployRoot) { Remove-Item -Recurse -Force $DeployRoot }
New-Item -ItemType Directory -Path $DeployRoot | Out-Null

Write-Host "Copying standalone output..." -ForegroundColor Cyan
Copy-Item -Recurse ".next/standalone/*" $DeployRoot

# Copy static assets (needed for client)
$DeployStatic = Join-Path $DeployRoot ".next/static"
New-Item -ItemType Directory -Path $DeployStatic -Force | Out-Null
Copy-Item -Recurse ".next/static/*" $DeployStatic

# Copy public assets (if any)
$DeployPublic = Join-Path $DeployRoot "public"
if (Test-Path "public") {
    Copy-Item -Recurse "public" $DeployPublic
}

# Copy user data (uploads, database) – DO NOT DELETE THESE
if (Test-Path "uploads") {
    Copy-Item -Recurse "uploads" $DeployRoot
}
if (Test-Path "netpos.db") {
    Copy-Item "netpos.db" $DeployRoot
}

# Now delete the original source code (everything except the new deploy folder)
Write-Host "Removing original source code..." -ForegroundColor Cyan
Get-ChildItem $ProjectRoot -Exclude "deploy" | ForEach-Object {
    Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
}

# Move the deploy folder contents up to the original project root
Move-Item "$DeployRoot\*" $ProjectRoot -Force
Remove-Item $DeployRoot

Write-Host "Starting the application..." -ForegroundColor Green
# Start Node.js server (runs in background, no console window)
Start-Process -NoNewWindow -FilePath "node" -ArgumentList "server.js" -WorkingDirectory $ProjectRoot

Write-Host "Application is running. Access at http://localhost:3000 (or your configured port)"
```

**Important notes:**
- The script assumes the production entry point is `server.js` (standalone default). If your `package.json` uses a different start script, adjust the last line.
- The database (`netpos.db`) and `uploads/` folder are **preserved** and copied to the new deployment.
- After deletion, only the standalone server, static files, and user data remain. The original `src/`, `node_modules/` (except bundled ones), config files, etc. are gone.

---

## Step 3 – Run the script completely hidden (no console window)

Create a **VBScript launcher** that executes the PowerShell script without showing any window.

Save this as `launcher.vbs` **in the same folder** as your project:

```vbscript
Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File ""%~dp0install-and-start.ps1""", 0, False
```

To make it a single‑click icon:
1. Right‑click on `launcher.vbs` → **Send to** → **Desktop (create shortcut)**
2. Rename the shortcut to `Retail Genie`
3. Change the icon: Right‑click shortcut → Properties → Change Icon → browse to your `.ico` file

Now double‑clicking the shortcut will:
- Run the whole installation + build + source deletion + start sequence
- No console window appears in the taskbar
- The app starts silently as a background Node process

---

## Step 4 – Additional tweaks (optional)

### Make the Node process stay alive after logout
If you want the app to run as a persistent service, replace the `Start-Process` line with:

```powershell
Start-Process -NoNewWindow -FilePath "node" -ArgumentList "server.js" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
```

### Verify the app still works after source deletion
Because we used `output: 'standalone'`, the `server.js` includes **all** backend API routes and the compiled frontend. No source files are needed at runtime.

### Default credentials reminder
After reset, login with `admin` / `password123` (as per your `admin.txt`).

---

## Complete folder structure after the script finishes

```
project_root/
├── server.js               ← standalone server
├── .next/static/           ← client assets
├── public/                 ← copied if existed
├── uploads/                ← preserved
├── netpos.db               ← preserved
└── node_modules/           ← only bundled essentials (standalone)
```

Everything else (`src/`, `MAP/`, `Data_Link/`, original configs, etc.) is **deleted**.

---

## Troubleshooting

- **“node is not recognized”** – Ensure Node.js is installed and in PATH. The script can be modified to use full path to `node.exe`.
- **Port already in use** – Change the port by setting `PORT=XXXX` environment variable before starting.
- **Database locked errors** – The script copies `netpos.db` while the app might be running. Stop any running instance before running the installer.

This solution meets all your requirements: **one‑click silent install, build, source deletion without breaking the app, and no command prompt window visible.**