
$py = (Get-Command python.exe).Source
$script = 'c:\vmfort\OneDrive - 중앙대학교 병원\Individual\hospital\Claude Code\radiology_worklog\backup_db.py'
$wdir = 'c:\vmfort\OneDrive - 중앙대학교 병원\Individual\hospital\Claude Code\radiology_worklog'
$action = New-ScheduledTaskAction -Execute $py -Argument ('\"' + $script + '\"') -WorkingDirectory $wdir
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName 'RadiologyWorklog_DB_Backup' -Action $action -Trigger $trigger -Settings $settings -Description '영상의학과 업무일지 DB 매일 백업' -Force
