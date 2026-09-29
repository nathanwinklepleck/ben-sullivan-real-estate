$ErrorActionPreference = 'Stop'
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $RepoRoot

$Msys2Root = 'C:\msys64'
$PangoBin = Join-Path $Msys2Root 'mingw64\bin'

function Step($message) { Write-Host "`n==> $message" -ForegroundColor Cyan }

function Invoke-Checked {
    param([string]$File, [string[]]$Arguments)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $File $($Arguments -join ' ')" }
}

function Update-SessionPath {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

function Install-WingetPackage {
    param([string]$Id, [string]$Name)
    # Windows PowerShell 5.1 turns redirected native stderr into terminating errors under 'Stop'.
    $ErrorActionPreference = 'Continue'
    $installed = winget list --id $Id -e --accept-source-agreements 2>$null | Select-String -SimpleMatch $Id
    if ($installed) {
        Write-Host "$Name is already installed."
        return
    }
    Write-Host "Installing $Name..."
    winget install --id $Id -e --silent --accept-source-agreements --accept-package-agreements
    # -1978335189 means "already installed / no newer version".
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { throw "winget could not install $Name." }
}

try {
    Step 'Checking for winget'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'winget was not found. Install "App Installer" from the Microsoft Store, then run setup.bat again.'
    }

    Step 'Installing Python, Node.js, and MSYS2 (skips anything already installed)'
    Install-WingetPackage 'Python.Python.3.12' 'Python 3.12'
    Install-WingetPackage 'OpenJS.NodeJS.LTS' 'Node.js LTS'
    Install-WingetPackage 'MSYS2.MSYS2' 'MSYS2'
    Update-SessionPath

    Step 'Installing Pango (needed for PDF export)'
    $msysBash = Join-Path $Msys2Root 'usr\bin\bash.exe'
    if (-not (Test-Path $msysBash)) { throw "MSYS2 was not found at $Msys2Root." }
    Invoke-Checked $msysBash @('-lc', 'pacman -S --needed --noconfirm mingw-w64-x86_64-pango')
    [Environment]::SetEnvironmentVariable('WEASYPRINT_DLL_DIRECTORIES', $PangoBin, 'User')
    $env:WEASYPRINT_DLL_DIRECTORIES = $PangoBin

    Step 'Creating the Python environment (.venv)'
    $venvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            Invoke-Checked 'py' @('-3.12', '-m', 'venv', '.venv')
        } else {
            Invoke-Checked 'python' @('-m', 'venv', '.venv')
        }
    }
    Invoke-Checked $venvPython @('-m', 'pip', 'install', '--upgrade', 'pip')
    Invoke-Checked $venvPython @('-m', 'pip', 'install', '-e', '.[dev]')

    Step 'Installing frontend packages'
    Push-Location (Join-Path $RepoRoot 'frontend')
    try { Invoke-Checked 'npm.cmd' @('install') } finally { Pop-Location }

    Step 'Running tests'
    Invoke-Checked $venvPython @('-m', 'pytest', '-q')

    Write-Host "`nSetup complete. Double-click start.bat to run the app." -ForegroundColor Green
    exit 0
} catch {
    Write-Host "`nSetup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Fix the problem above, then run setup.bat again. It is safe to re-run.' -ForegroundColor Yellow
    exit 1
}
