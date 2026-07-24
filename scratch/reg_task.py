import subprocess

ps_script = r"""
$py = (Get-Command python.exe).Source
$script = 'c:\vmfort\OneDrive - 중앙대학교 병원\Individual\hospital\Claude Code\radiology_worklog\backup_db.py'
$wdir = 'c:\vmfort\OneDrive - 중앙대학교 병원\Individual\hospital\Claude Code\radiology_worklog'
$action = New-ScheduledTaskAction -Execute $py -Argument ('\"' + $script + '\"') -WorkingDirectory $wdir
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName 'RadiologyWorklog_DB_Backup' -Action $action -Trigger $trigger -Settings $settings -Description '영상의학과 업무일지 DB 매일 백업' -Force
"""

with open('scratch/reg_task.ps1', 'w', encoding='utf-8') as f:
    f.write(ps_script)

res = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scratch/reg_task.ps1'], capture_output=True, text=True)
print('STDOUT:', res.stdout)
print('STDERR:', res.stderr)
print('Returncode:', res.returncode)
