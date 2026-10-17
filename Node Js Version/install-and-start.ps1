# Retail Genie - One-Click Installer and Starter
# This script installs dependencies, builds the standalone app, 
# removes source code for IP protection, and starts the production server.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

# 1. Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Cyan
npm install --silent

# 2. Build application (standalone mode)
Write-Host "Building application (standalone)..." -ForegroundColor Cyan
npm run build

# 3. Create a temporary deployment folder
$DeployRoot = Join-Path $ProjectRoot "deploy"
if (Test-Path $DeployRoot) { Remove-Item -Recurse -Force $DeployRoot }
New-Item -ItemType Directory -Path $DeployRoot | Out-Null

# 4. Copy standalone output
Write-Host "Copying standalone output..." -ForegroundColor Cyan
Copy-Item -Recurse ".next/standalone/*" $DeployRoot

# 5. Copy static assets (required for client-side)
$DeployStatic = Join-Path $DeployRoot ".next/static"
New-Item -ItemType Directory -Path $DeployStatic -Force | Out-Null
Copy-Item -Recurse ".next/static/*" $DeployStatic

# 6. Copy public assets (Logo, etc)
if (Test-Path "public") {
    $DeployPublic = Join-Path $DeployRoot "public"
    Copy-Item -Recurse "public" $DeployPublic
}

# 7. Preserve User Data (DO NOT DELETE)
if (Test-Path "uploads") {
    Copy-Item -Recurse "uploads" $DeployRoot
}
if (Test-Path "netpos.db") {
    Copy-Item "netpos.db" $DeployRoot
}

# 8. IP PROTECTION: Remove all original source code
# We delete everything except our temporary "deploy" folder
Write-Host "Removing original source code for protection..." -ForegroundColor Cyan
Get-ChildItem $ProjectRoot -Exclude "deploy" | ForEach-Object {
    Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
}

# 9. Finalize structure: Move deployment files to root
Move-Item "$DeployRoot\*" $ProjectRoot -Force
Remove-Item $DeployRoot

# 10. Start the server
Write-Host "Starting the application..." -ForegroundColor Green
# Start Node.js server in the background
Start-Process -NoNewWindow -FilePath "node" -ArgumentList "server.js" -WorkingDirectory $ProjectRoot

Write-Host "Success! Access the app at http://localhost:3000" -ForegroundColor Green
