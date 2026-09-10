@echo off
if not exist "%~dp0python\pythonw.exe" (
    echo Dossier incomplet : extraire tout le ZIP portable.
    echo Incomplete folder: extract the entire portable ZIP.
    pause
    exit /b 1
)
start "" "%~dp0python\pythonw.exe" -I -B "%~dp0run_qt.py"
