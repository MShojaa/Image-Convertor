@echo off
rem Runs the built exe. Pass "onedir" if that is how it was built.
rem To run from source instead, use dev.bat.

call "%~dp0_env.bat"

set "NAME=Image-Convertor"
if /i "%~1"=="onedir" (
    set "EXE=%ROOT%\dist\%NAME%\%NAME%.exe"
) else (
    set "EXE=%ROOT%\dist\%NAME%.exe"
)

if not exist "%EXE%" (
    echo Not built: %EXE%
    echo Run scripts\build.bat first.
    exit /b 1
)

rem From dist\, so the input\ and output\ folders the app uses are the ones
rem beside the exe rather than in scripts\.
pushd "%ROOT%\dist"
"%EXE%"
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%
