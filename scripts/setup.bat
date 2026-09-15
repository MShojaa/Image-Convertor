@echo off
rem Creates the project's own Python environment in .venv and installs
rem everything into it. Run this once, first; every other script finds .venv by
rem itself afterwards.
rem
rem Safe to run again: it reuses an existing .venv and just reinstalls into it,
rem which is also how you pick up a change to requirements.txt.
rem
rem The environment is a folder inside the project, ignored by git. It does not
rem touch the Python on your PATH and nothing outside this folder can see it.

setlocal
set "ROOT=%~dp0.."

rem py.exe is the launcher that ships with python.org builds; -3 asks it for
rem the newest Python 3 it knows about. The build needs 3.10 or newer --
rem build.py checks that properly, so all this has to do is find something.
set "BOOTSTRAP=py -3"
where py >nul 2>&1 || set "BOOTSTRAP=python"

if exist "%ROOT%\.venv\Scripts\python.exe" (
    echo Reusing the existing .venv
) else (
    echo Creating .venv
    %BOOTSTRAP% -m venv "%ROOT%\.venv"
    if errorlevel 1 (
        echo.
        echo Could not create the environment. Install Python 3.10 or newer from
        echo https://www.python.org/downloads/windows/ and tick "Add python.exe
        echo to PATH", then run this again.
        exit /b 1
    )
)

set "PY=%ROOT%\.venv\Scripts\python.exe"

echo.
echo Installing packages
"%PY%" -m pip install --upgrade pip --quiet
if errorlevel 1 goto :failed

rem Pillow, pywebview, pytest and PyInstaller -- everything the other scripts
rem in this folder need. requirements-dev.txt pulls in requirements.txt.
"%PY%" -m pip install -r "%ROOT%\requirements-dev.txt" pyinstaller
if errorlevel 1 goto :failed

echo.
echo == checking it can actually build ================================
rem The same preflight the build runs: the wrong Python or a package that did
rem not install produces an exe that dies on launch, and this is what says so.
"%PY%" "%ROOT%\build.py" --check
if errorlevel 1 goto :failed

echo.
echo Ready. Run scripts\dev.bat to start the app from source,
echo scripts\check.bat to run the tests, or
echo scripts\build-and-run.bat to build the exe and run it.
exit /b 0

:failed
echo.
echo SETUP FAILED.
exit /b 1
