@echo off
rem Runs the test suite. Everything has to pass before a commit -- that is what
rem this is for, and it is why it is one command with nothing to remember.
rem
rem Arguments pass through to pytest, so scripts\check.bat -k hard_cut runs
rem just the hard cut tests and scripts\check.bat -x stops at the first failure.

call "%~dp0_env.bat"

pushd "%ROOT%"
"%PY%" -m pytest %*
set "CODE=%ERRORLEVEL%"
popd

if not "%CODE%"=="0" (
    echo.
    echo CHECK FAILED -- do not commit.
)
exit /b %CODE%
