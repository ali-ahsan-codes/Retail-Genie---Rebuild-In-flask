$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if (-not $PythonLauncher) {
    throw "Python 3.11 or newer is required. Install Python and enable the 'py' launcher, then run this installer again."
}

& py -3 --version
if ($LASTEXITCODE -ne 0) {
    throw "Could not find a Python 3 installation."
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    & py -3 -m venv (Join-Path $Root ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the Python virtual environment."
    }
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Could not upgrade pip."
}

& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the application requirements."
}

& $VenvPython (Join-Path $Root "scripts\setup_database.py")
if ($LASTEXITCODE -ne 0) {
    throw "Retail Genie database setup failed. No other database was targeted."
}

& $VenvPython (Join-Path $Root "seed_admin.py")
if ($LASTEXITCODE -ne 0) {
    throw "Initial administrator setup failed. After resolving the issue, run: .\.venv\Scripts\python.exe seed_admin.py"
}

Write-Host "Retail Genie is installed. Start it with: .\.venv\Scripts\python.exe run.py"