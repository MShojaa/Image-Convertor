@echo off
rem The app from source, with the webview's devtools on right-click -- which
rem is where the page and its styling are meant to be edited.
rem Arguments pass through.
rem
rem Runs from the project root, so the input\ and output\ folders it uses are
rem the ones in the project rather than in scripts\.

call "%~dp0_env.bat"
pushd "%ROOT%"
"%PY%" main.py --debug %*
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%
