@echo off
rem Freezes the app to dist\Image-Convertor.exe. Pass "onedir" for a folder build
rem instead of one file -- it starts faster and lets you see what landed beside
rem the exe, which is what to reach for when a frozen build misbehaves.
rem
rem build.py runs a preflight first and refuses to build in an environment that
rem would produce a broken exe. Every PyInstaller flag lives there, not here.

call "%~dp0_env.bat"

set "EXTRA="
if /i "%~1"=="onedir" set "EXTRA=--onedir"

pushd "%ROOT%"
"%PY%" build.py %EXTRA%
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%
