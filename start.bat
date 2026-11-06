@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw znote_app.py
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    start "" python znote_app.py
  ) else (
    py znote_app.py
  )
)
