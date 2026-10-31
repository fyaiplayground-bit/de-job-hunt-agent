@echo off
rem Daily run, called by the Windows scheduled task "de-job-hunt-agent daily" (decision #27).
rem Runs from the repo root; output is appended to output\daily\daily.log (gitignored).
cd /d "%~dp0.."
if not exist output\daily mkdir output\daily
"%USERPROFILE%\.local\bin\uv.exe" run python -m pipeline.daily >> output\daily\daily.log 2>&1
exit /b %ERRORLEVEL%
