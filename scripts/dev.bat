@echo off
rem The app from source. Arguments pass through, e.g. dev.bat --size 128x64.
rem
rem Runs from the project root, so the input\ and output\ folders it uses are
rem the ones in the project rather than in scripts\.

call "%~dp0_env.bat"
pushd "%ROOT%"
"%PY%" main.py %*
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%
