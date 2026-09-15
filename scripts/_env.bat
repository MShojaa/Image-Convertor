@echo off
rem Shared setup: puts the project root in ROOT and the interpreter to use in
rem PY. Not meant to be run directly -- every other script calls it first.
rem
rem The project's own .venv wins if there is one, so a double-clicked script
rem uses the same packages as a shell where you had activated it. Otherwise
rem plain "python", which is what a global install leaves you with -- and
rem which is where a wrong Python version or a missing Pillow comes from, so
rem build.py checks both before it builds anything.

set "ROOT=%~dp0.."
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set "PY=%ROOT%\.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
