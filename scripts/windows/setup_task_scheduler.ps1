<#
.SYNOPSIS
    Cai dat 4 Scheduled Task tren Windows cho PC Monitor Pro.

.HUONG DAN
    1. Cai Python (https://python.org), nho tick "Add python.exe to PATH".
    2. Mo Command Prompt/PowerShell thuong, cd toi thu muc goc project
       (noi co main.py), chay:
           pip install -r requirements.txt
    3. Copy .env.example thanh .env va dien BOT_TOKEN, ALLOWED_CHAT_IDS...
    4. Test: python main.py test
    5. Mo PowerShell voi quyen Administrator, cd toi thu muc
       scripts\windows, chay:
           Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
           .\setup_task_scheduler.ps1

.GO BO
    .\setup_task_scheduler.ps1 -Uninstall
#>

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "LOI: Ban can chay PowerShell voi quyen Administrator." -ForegroundColor Red
    exit 1
}

# scripts\windows\setup_task_scheduler.ps1 -> thu muc goc project la ..\..
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path (Join-Path $ScriptDir "..\..")
$MainPy     = Join-Path $ProjectDir "main.py"
$EnvFile    = Join-Path $ProjectDir ".env"

$TaskStartup   = "PCMonitorPro_Startup"
$TaskShutdown  = "PCMonitorPro_Shutdown"
$TaskHeartbeat = "PCMonitorPro_Heartbeat"
$TaskListener  = "PCMonitorPro_Listener"

if ($Uninstall) {
    Write-Host "Dang go cac Scheduled Task..." -ForegroundColor Cyan
    foreach ($t in @($TaskStartup, $TaskShutdown, $TaskHeartbeat, $TaskListener)) {
        if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t -Confirm:$false
            Write-Host "  Da xoa task: $t" -ForegroundColor Green
        } else {
            Write-Host "  Task khong ton tai (bo qua): $t" -ForegroundColor DarkGray
        }
    }
    exit 0
}

if (-not (Test-Path $MainPy)) {
    Write-Host "LOI: Khong tim thay main.py tai $MainPy" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $EnvFile)) {
    Write-Host "LOI: Khong tim thay file .env tai $EnvFile" -ForegroundColor Red
    Write-Host "Hay copy .env.example thanh .env va dien thong tin truoc." -ForegroundColor Yellow
    exit 1
}

# --- Kiem tra da dien BOT_TOKEN / ALLOWED_CHAT_IDS chua ---
$EnvContent = Get-Content $EnvFile -Raw
$BotTokenValue = $null
$ChatIdsValue = $null
if ($EnvContent -match 'BOT_TOKEN\s*=\s*(.+)') { $BotTokenValue = $Matches[1].Trim() }
if ($EnvContent -match 'ALLOWED_CHAT_IDS\s*=\s*(.+)') { $ChatIdsValue = $Matches[1].Trim() }

if ([string]::IsNullOrWhiteSpace($BotTokenValue) -or $BotTokenValue -like 'DAN_*' -or
    [string]::IsNullOrWhiteSpace($ChatIdsValue) -or $ChatIdsValue -like 'DAN_*') {
    Write-Host "LOI: Ban chua dien BOT_TOKEN / ALLOWED_CHAT_IDS trong file .env" -ForegroundColor Red
    exit 1
}

$HeartbeatMinutes = 60
if ($EnvContent -match 'HEARTBEAT_MINUTES\s*=\s*(\d+)') { $HeartbeatMinutes = [int]$Matches[1] }

# --- Tim python.exe ---
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) { $PythonExe = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $PythonExe) {
    Write-Host "LOI: Khong tim thay python trong PATH." -ForegroundColor Red
    exit 1
}
Write-Host "Da tim thay Python tai: $PythonExe" -ForegroundColor Green

$PythonwExe = Join-Path (Split-Path $PythonExe) "pythonw.exe"
if (-not (Test-Path $PythonwExe)) { $PythonwExe = $PythonExe }

# ================= TASK 1: STARTUP =================
Write-Host "`nDang tao task: $TaskStartup ..." -ForegroundColor Cyan
$ActionStartup  = New-ScheduledTaskAction -Execute $PythonwExe -Argument "`"$MainPy`" startup" -WorkingDirectory $ProjectDir
$TriggerStartup = New-ScheduledTaskTrigger -AtLogOn
$TriggerStartup.Delay = "PT30S"
$Settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskStartup -Action $ActionStartup -Trigger $TriggerStartup -Settings $Settings -Principal $Principal -Force | Out-Null
Write-Host "  OK: $TaskStartup" -ForegroundColor Green

# ================= TASK 2: SHUTDOWN (Event ID 1074) =================
Write-Host "`nDang tao task: $TaskShutdown ..." -ForegroundColor Cyan
$ActionShutdown = New-ScheduledTaskAction -Execute $PythonwExe -Argument "`"$MainPy`" shutdown" -WorkingDirectory $ProjectDir
$CimQuery = @'
<QueryList>
  <Query Id="0" Path="System">
    <Select Path="System">*[System[Provider[@Name='User32'] and EventID=1074]]</Select>
  </Query>
</QueryList>
'@
$TriggerShutdown = New-ScheduledTaskTrigger -AtStartup
$CimTriggerClass = Get-CimClass -ClassName MSFT_TaskEventTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
$EventTrigger = New-CimInstance -CimClass $CimTriggerClass -ClientOnly -Property @{ Subscription = $CimQuery; Enabled = $true }
$Settings2  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
$Principal2 = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskShutdown -Action $ActionShutdown -Trigger $EventTrigger -Settings $Settings2 -Principal $Principal2 -Force | Out-Null
Write-Host "  OK: $TaskShutdown" -ForegroundColor Green

# ================= TASK 3: HEARTBEAT =================
Write-Host "`nDang tao task: $TaskHeartbeat ..." -ForegroundColor Cyan
$ActionHeartbeat  = New-ScheduledTaskAction -Execute $PythonwExe -Argument "`"$MainPy`" heartbeat" -WorkingDirectory $ProjectDir
$TriggerHeartbeat = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $HeartbeatMinutes) -RepetitionDuration ([TimeSpan]::MaxValue)
$Settings3  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
$Principal3 = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskHeartbeat -Action $ActionHeartbeat -Trigger $TriggerHeartbeat -Settings $Settings3 -Principal $Principal3 -Force | Out-Null
Write-Host "  OK: $TaskHeartbeat (moi $HeartbeatMinutes phut)" -ForegroundColor Green

# ================= TASK 4: LISTENER =================
Write-Host "`nDang tao task: $TaskListener ..." -ForegroundColor Cyan
$ActionListener  = New-ScheduledTaskAction -Execute $PythonwExe -Argument "`"$MainPy`" listen" -WorkingDirectory $ProjectDir
$TriggerListener = New-ScheduledTaskTrigger -AtLogOn
$TriggerListener.Delay = "PT30S"
$Settings4  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
$Principal4 = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskListener -Action $ActionListener -Trigger $TriggerListener -Settings $Settings4 -Principal $Principal4 -Force | Out-Null
Start-ScheduledTask -TaskName $TaskListener
Write-Host "  OK: $TaskListener (dang chay nen)" -ForegroundColor Green

Write-Host "`n=================================================" -ForegroundColor Cyan
Write-Host "HOAN TAT! Da tao 4 Scheduled Task (PCMonitorPro_*)." -ForegroundColor Green
Write-Host "Thu ngay tren Telegram: gui /help cho bot cua ban" -ForegroundColor Yellow
Write-Host "Go bo: .\setup_task_scheduler.ps1 -Uninstall" -ForegroundColor Yellow
