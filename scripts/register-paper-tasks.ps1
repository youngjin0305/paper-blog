[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$WeeklyTime = '08:00',
    [string]$DailyTime = '09:00',
    [ValidateSet('Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')]
    [string]$WeeklyDay = 'Monday',
    [string]$TaskPrefix = 'PaperGarden',
    [string]$PythonPath = ''
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $PythonPath) { $PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$PipelinePath = Join-Path $ProjectRoot 'paper_pipeline.py'
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 6)
foreach ($Kind in @('weekly', 'daily')) {
    $Action = New-ScheduledTaskAction -Execute $PythonPath -Argument ('-B "' + $PipelinePath + '" ' + $Kind) -WorkingDirectory $ProjectRoot
    if ($Kind -eq 'weekly') {
        $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $WeeklyDay -At $WeeklyTime
    } else {
        $Trigger = New-ScheduledTaskTrigger -Daily -At $DailyTime
    }
    $TaskName = "$TaskPrefix-$Kind"
    if ($PSCmdlet.ShouldProcess($TaskName, 'Register scheduled paper pipeline')) {
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
        Write-Output "Registered $TaskName ($PythonPath)"
    }
}
