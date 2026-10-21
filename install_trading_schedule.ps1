$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pipeline = Join-Path $projectRoot 'trading_pipeline.py'
$overnightPipeline = Join-Path $projectRoot 'overnight_pipeline.py'
if (-not (Test-Path -LiteralPath $python) -or
    -not (Test-Path -LiteralPath $pipeline) -or
    -not (Test-Path -LiteralPath $overnightPipeline)) {
    throw 'Virtual environment atau pipeline riset tidak ditemukan.'
}
if ([TimeZoneInfo]::Local.GetUtcOffset([DateTime]::Now).TotalHours -ne 7) {
    throw 'Jadwal 18:30 mengasumsikan zona waktu komputer UTC+7 (WIB).'
}

$taskName = 'Saham-Trading-Research-EOD'
$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $pipeline + '" --skip-if-current-eod') -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '18:30'
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 25)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Riset sinyal saham IDX EOD setelah candle selesai' -Force | Out-Null
$overnightTaskName = 'Saham-Overnight-Research'
$overnightAction = New-ScheduledTaskAction -Execute $python -Argument ('"' + $overnightPipeline + '"') -WorkingDirectory $projectRoot
$overnightTriggers = @(
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '14:45'),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '18:45')
)
Register-ScheduledTask -TaskName $overnightTaskName -Action $overnightAction -Trigger $overnightTriggers -Principal $principal -Settings $settings -Description 'Arsip 5 menit dan riset beli sore jual pagi' -Force | Out-Null

Get-ScheduledTask -TaskName $taskName,$overnightTaskName | Select-Object TaskName,State
