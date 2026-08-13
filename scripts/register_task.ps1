# REQ-20260813-004 任务1：注册开机自启计划任务（PowerShell 路线）
$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction -Execute 'D:\乔一禾\项目工作区\多Agent学习导师\scripts\启动看板.bat'
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
try {
    Register-ScheduledTask -TaskName '学习导师看板' -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
    Write-Output "REGISTER_OK"
} catch {
    Write-Output ("REGISTER_FAIL: " + $_.Exception.Message)
}
Get-ScheduledTask -TaskName '学习导师看板' -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ("TASK_EXISTS: " + $_.TaskName + " | " + $_.State) }
