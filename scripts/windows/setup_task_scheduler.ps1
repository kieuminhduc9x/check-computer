<#
.SYNOPSIS
    Dang ky PC Monitor Pro chay khi dang nhap (Windows Task Scheduler).

.HUONG DAN
    1. Cai Python, tick "Add python.exe to PATH".
    2. pip install -r requirements.txt
    3. Copy .env.example thanh .env, dien BOT_TOKEN va ALLOWED_CHAT_IDS.
    4. python main.py test
    5. python main.py install
       hoac chay script nay:
           Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
           .\setup_task_scheduler.ps1

.GO BO
    python main.py uninstall
    hoac: .\setup_task_scheduler.ps1 -Uninstall
#>

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path (Join-Path $ScriptDir "..\..")
$MainPy     = Join-Path $ProjectDir "main.py"

$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) { $PythonExe = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $PythonExe) {
    Write-Host "LOI: Khong tim thay python trong PATH." -ForegroundColor Red
    exit 1
}

$Action = if ($Uninstall) { "uninstall" } else { "install" }
& $PythonExe $MainPy $Action
exit $LASTEXITCODE
