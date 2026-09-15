@echo off
rem Land a branch on develop the way workflow.md says to: bump, merge, tag,
rem delete -- one operation, so none of the four can be forgotten.
rem
rem   scripts\merge.bat feat/short-name              bump inferred from the prefix
rem   scripts\merge.bat fix/short-name patch         or said outright
rem   scripts\merge.bat docs/short-name none         docs only: no bump, no tag
rem   scripts\merge.bat feat/short-name 3.0.0        an exact version
rem   scripts\merge.bat feat/short-name minor --dry  say what it would do
rem
rem When a merge stops on conflicts it stays stopped, and these finish it:
rem
rem   scripts\merge.bat --continue                   resolve first, then this
rem   scripts\merge.bat --abort                      throw the whole merge away
rem
rem Paths come from this file's own location, so it does not matter which
rem folder you call it from.
setlocal enabledelayedexpansion
rem It matters for a second reason as well: an unresolved \.. runs perfectly
rem well right up until it is used inside a for /f, where the command is
rem handed to a nested cmd that will not have it.
for %%I in ("%~dp0..") do set "ROOT=%%~fI"

rem The project's own .venv wins if there is one, so a double-clicked script
rem uses the same packages as a shell where it had been activated. Otherwise
rem plain "python" -- same rule as scripts\_env.bat, repeated rather than
rem called because this script must keep working while git rewrites the
rem folder around it.
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set "PY=%ROOT%\.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

rem Finishing or abandoning a merge that stopped on conflicts. Both work on
rem the repo rather than on arguments, so they jump in once ROOT is resolved.
if /i "%~1"=="--continue" goto :resume
if /i "%~1"=="--abort"    goto :abandon

set BRANCH=%~1
set BUMP=%~2
set DRY=
if /i "%~2"=="--dry" (set BUMP=&set DRY=1)
if /i "%~3"=="--dry" set DRY=1

if "%BRANCH%"=="" (
    echo Usage: scripts\merge.bat ^<branch^> [major^|minor^|patch^|X.Y.Z^|none] [--dry]
    echo        scripts\merge.bat --continue ^| --abort
    exit /b 2
)

pushd "%ROOT%"

rem ---- 1. refuse to start from a state we cannot reason about --------------
rem Every step below is reversible only because the tree was clean when we
rem began: the rollback at the end is a hard reset, and a hard reset over
rem uncommitted work destroys it.
for /f "delims=" %%S in ('git status --porcelain') do (
    echo Working tree is not clean. Commit or stash first:
    git status --short
    popd
    exit /b 1
)

git rev-parse --verify --quiet "%BRANCH%" >nul
if errorlevel 1 (
    echo No such branch: %BRANCH%
    popd
    exit /b 1
)

if /i "%BRANCH%"=="develop" (
    echo Refusing to merge develop into itself.
    popd
    exit /b 1
)

rem ---- 2. work out the version -------------------------------------------
rem The prefix already says which number moves -- see the table in
rem workflow.md -- so an unstated bump is inferred and then printed loudly
rem rather than guessed at silently. major is never inferred: nothing about a
rem branch name can tell you a script written against the old flags has
rem stopped working.
if "%BUMP%"=="" (
    echo %BRANCH% | findstr /b /c:"feat/" >nul && set BUMP=minor
    echo %BRANCH% | findstr /b /c:"fix/" >nul && set BUMP=patch
    echo %BRANCH% | findstr /b /c:"chore/" >nul && set BUMP=patch
    echo %BRANCH% | findstr /b /c:"docs/" >nul && set BUMP=none
)
if "%BUMP%"=="" (
    echo Cannot tell what to bump for "%BRANCH%" -- say major, minor, patch, a version, or none.
    popd
    exit /b 2
)

rem `if errorlevel` is no use here: the findstr calls above leave it at 1
rem whenever the last prefix tested did not match, and a for /f does not
rem clear it. What is actually being asked is whether the value arrived.
rem
rem usebackq and backticks, with the script path RELATIVE: a for /f command
rem holding two quoted tokens ("python" "C:\...\script.py") loses its outer
rem quotes to the nested cmd that runs it and fails. One quoted token and a
rem relative path -- which the pushd above makes safe -- does not.
set CURRENT=
for /f "usebackq delims=" %%V in (`"%PY%" scripts\bump_version.py --show`) do set CURRENT=%%V
if not defined CURRENT (
    echo Could not read __version__ from image_convertor\__init__.py.
    popd
    exit /b 1
)

set NEXT=
if /i "%BUMP%"=="none" (
    set NEXT=
) else if /i "%BUMP%"=="major" (
    for /f "usebackq delims=" %%V in (`"%PY%" scripts\bump_version.py --next major`) do set NEXT=%%V
) else if /i "%BUMP%"=="minor" (
    for /f "usebackq delims=" %%V in (`"%PY%" scripts\bump_version.py --next minor`) do set NEXT=%%V
) else if /i "%BUMP%"=="patch" (
    for /f "usebackq delims=" %%V in (`"%PY%" scripts\bump_version.py --next patch`) do set NEXT=%%V
) else (
    set NEXT=%BUMP%
)
if /i not "%BUMP%"=="none" if not defined NEXT (
    echo Could not work out the next version from "%BUMP%".
    popd
    exit /b 1
)

rem An explicit version is checked HERE rather than where it is written. It
rem is written after the bump has been committed, and "1.2" getting that far
rem would mean failing with a commit already made.
rem Flat on purpose: a multi-line `|| ( ... )` nested inside another
rem parenthesised block confuses cmd's parser, and what it does with the
rem confusion is run half of a later line as a command.
set VERSION_OK=
if not defined NEXT set VERSION_OK=1
if defined NEXT echo !NEXT!| findstr /r /c:"^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$" >nul && set VERSION_OK=1
if not defined VERSION_OK (
    echo "!NEXT!" is not a version -- three dotted numbers, e.g. 1.2.0
    popd
    exit /b 2
)

rem The merge commit says what landed, not just that something did. The
rem branch's own last subject is the nearest thing to a summary that already
rem exists, so it is used rather than asking for one that would get skipped.
set SUBJECT=
for /f "delims=" %%M in ('git log -1 --format^=%%s "%BRANCH%"') do set SUBJECT=%%M

echo.
echo   branch   %BRANCH%
echo   summary  !SUBJECT!
echo   version  %CURRENT%
if defined NEXT (echo   becomes  !NEXT!   ^(tag v!NEXT!^)) else (echo   becomes  unchanged -- docs only, no bump and no tag)
echo.

if defined DRY (
    echo --dry: nothing was changed.
    popd
    exit /b 0
)

rem ---- 3. the branch has to pass on its own before it lands ---------------
git checkout --quiet "%BRANCH%"
if errorlevel 1 (popd & exit /b 1)
echo Running the tests on %BRANCH% ...
call "%ROOT%\scripts\check.bat" -q >nul 2>&1
if errorlevel 1 (
    echo.
    echo %BRANCH% does not pass its own tests. Nothing was merged.
    echo Run scripts\check.bat to see which.
    git checkout --quiet develop
    popd
    exit /b 1
)
echo   ok.

rem The graph, for the branch, while the branch is still what is checked
rem out. If the merge below conflicts, this is the graph you will be reading
rem to work out why, and a stale one is worse than none.
call :refresh_graph

rem ---- 4. bump, merge, tag ------------------------------------------------
git checkout --quiet develop
if errorlevel 1 (popd & exit /b 1)

rem Where to put develop back if the merged result does not pass. Taken before
rem anything is written, which is what makes the rollback exact.
for /f "delims=" %%S in ('git rev-parse HEAD') do set BEFORE=%%S

if defined NEXT (
    "%PY%" scripts\bump_version.py --set !NEXT! >nul
    if errorlevel 1 (echo Could not write the version. & popd & exit /b 1)
    git add image_convertor/__init__.py
    git commit --quiet -m "Version !NEXT!"
    if errorlevel 1 (echo Could not commit the version bump. & popd & exit /b 1)
)

rem What --continue needs to know, written before the merge rather than
rem after it: a conflicted merge is exactly the case where this script is not
rem around to remember anything. BEFORE is already the pre-bump commit, so
rem abandoning takes the version bump with it.
for /f "usebackq delims=" %%G in (`git rev-parse --absolute-git-dir`) do set "GITDIR=%%G"
set "STATE=%GITDIR%\image-convertor-merge.state"

git merge --no-ff --quiet "%BRANCH%" -m "Merge %BRANCH%: !SUBJECT!"
if errorlevel 1 (
    >"!STATE!"  echo BRANCH=%BRANCH%
    >>"!STATE!" echo NEXT=!NEXT!
    >>"!STATE!" echo BEFORE=%BEFORE%
    >>"!STATE!" echo SUBJECT=!SUBJECT!
    echo.
    echo The merge stopped on conflicts. develop is left mid-merge on purpose.
    echo.
    git --no-pager diff --name-only --diff-filter=U
    echo.
    echo Resolve those, "git add" each one, then:
    echo    scripts\merge.bat --continue     finishes it -- tests first, and it
    echo                                     only completes if they pass
    echo    scripts\merge.bat --abort        throws the merge and the bump away
    popd
    exit /b 1
)

rem ---- 5. the merged result has to pass too -------------------------------
rem This is the check that matters. Two branches that each pass alone can
rem still fail together, and the only place that shows is here.
echo Running the tests on the merged develop ...
call "%ROOT%\scripts\check.bat" -q >nul 2>&1
if errorlevel 1 (
    echo.
    echo The merged result fails its tests. Rolling develop back to %BEFORE%.
    echo %BRANCH% is untouched -- fix it there and run this again.
    git reset --hard --quiet %BEFORE%
    popd
    exit /b 1
)
echo   ok.

if defined NEXT (
    git tag "v!NEXT!"
    if errorlevel 1 (
        echo.
        echo Merged, but the tag v!NEXT! could not be created -- it may already exist.
        echo The branch has NOT been deleted.
        popd
        exit /b 1
    )
)

rem ---- 6. the branch has landed; drop it ----------------------------------
rem -d, not -D: it refuses on anything unmerged, which after the merge above
rem can only mean something went wrong worth stopping for.
git branch -d "%BRANCH%"
if errorlevel 1 (
    echo.
    echo Merged and tagged, but %BRANCH% could not be deleted. Left in place.
    popd
    exit /b 1
)

rem ---- 7. the graph, now that develop is what it will be ------------------
rem The reasoning lives with the routine at the bottom of this file.
call :refresh_graph

if exist "!STATE!" del "!STATE!"

echo.
echo Merged %BRANCH% into develop.
if defined NEXT (echo Tagged v!NEXT!.) else (echo No version change -- docs only.)
echo Branch deleted.
git --no-pager log --oneline -3
popd
exit /b 0


rem ========================================================================
rem  Finishing a merge that stopped on conflicts.
rem
rem  The order here is the point, and it is not the order the plain path
rem  uses. There, the merge commit is made and then tested, and a failure
rem  rolls develop back with a hard reset. That cannot happen here: the reset
rem  would destroy the conflict resolution, which is the one part of this
rem  nobody can redo cheaply. So the tests run on the resolved tree BEFORE
rem  the merge is committed, and a failure leaves everything exactly where it
rem  was -- still mid-merge, resolutions intact, ready to try again.
rem ========================================================================
:resume
pushd "%ROOT%"
for /f "usebackq delims=" %%G in (`git rev-parse --absolute-git-dir`) do set "GITDIR=%%G"
set "STATE=%GITDIR%\image-convertor-merge.state"
if not exist "!STATE!" (
    echo No merge is waiting to be finished.
    echo    --continue only follows a merge that stopped on conflicts.
    popd
    exit /b 2
)
for /f "usebackq tokens=1,* delims==" %%A in ("!STATE!") do set "%%A=%%B"

rem Anything still unmerged means the conflicts are not resolved, whatever
rem the files look like. Saying which ones is more use than saying that.
set UNRESOLVED=
for /f "delims=" %%U in ('git diff --name-only --diff-filter=U') do set UNRESOLVED=1
if defined UNRESOLVED (
    echo These are still conflicted:
    git --no-pager diff --name-only --diff-filter=U
    echo.
    echo Resolve them and "git add" each one, then run this again.
    popd
    exit /b 1
)

echo Running the tests on the resolved merge ...
call "%ROOT%\scripts\check.bat" -q >nul 2>&1
if errorlevel 1 (
    echo.
    echo The tests fail on the resolved merge, so it has NOT been committed.
    echo Nothing is lost -- the resolutions are still here and develop has not
    echo moved. Fix them, "git add" what you changed, and run this again.
    echo Run scripts\check.bat to see which.
    popd
    exit /b 1
)
echo   ok.

rem The resolved tree, before it becomes a commit. The merge is what changed
rem the code here, and this is the first moment the result is both complete
rem and known good.
call :refresh_graph

rem A resolved merge may already have been committed by hand; only commit if
rem git still says one is in progress.
git rev-parse -q --verify MERGE_HEAD >nul 2>&1
if not errorlevel 1 (
    git commit --quiet --no-edit
    if errorlevel 1 (echo Could not commit the merge. & popd & exit /b 1)
)

if defined NEXT (
    git tag "v!NEXT!"
    if errorlevel 1 (
        echo.
        echo Merged, but the tag v!NEXT! could not be created -- it may already exist.
        echo The branch has NOT been deleted.
        popd
        exit /b 1
    )
)

git branch -d "!BRANCH!"
if errorlevel 1 (
    echo.
    echo Merged and tagged, but !BRANCH! could not be deleted. Left in place.
    popd
    exit /b 1
)

call :refresh_graph

del "!STATE!"
echo.
echo Merged !BRANCH! into develop.
if defined NEXT (echo Tagged v!NEXT!.) else (echo No version change -- docs only.)
echo Branch deleted.
git --no-pager log --oneline -3
popd
exit /b 0

rem ========================================================================
rem  Throwing the whole thing away. BEFORE was taken before the version bump,
rem  so this takes the bump with it and leaves develop exactly as it was.
rem ========================================================================
:abandon
pushd "%ROOT%"
for /f "usebackq delims=" %%G in (`git rev-parse --absolute-git-dir`) do set "GITDIR=%%G"
set "STATE=%GITDIR%\image-convertor-merge.state"
if not exist "!STATE!" (
    echo No merge is waiting to be abandoned.
    popd
    exit /b 2
)
for /f "usebackq tokens=1,* delims==" %%A in ("!STATE!") do set "%%A=%%B"

git merge --abort >nul 2>&1
git reset --hard --quiet !BEFORE!
if errorlevel 1 (echo Could not put develop back to !BEFORE!. & popd & exit /b 1)
del "!STATE!"
echo.
echo Merge abandoned. develop is back at !BEFORE!, version bump included.
echo !BRANCH! is untouched.
popd
exit /b 0

rem ========================================================================
rem  The knowledge graph, refreshed wherever the hooks will not do it.
rem
rem  post-commit does not fire for a merge commit and neither hook fires for
rem  a pull, so the graph goes stale at exactly the moments this script runs.
rem  Called three times: on the branch once its tests pass, on a resolved
rem  conflict once its tests pass, and on develop once the merge has landed.
rem
rem  Best-effort throughout: no graphify on the PATH is not a reason to stop
rem  a merge. Only where a graph already exists -- running it in a repo that
rem  has never had one BUILDS one, and in a repo that does not ignore
rem  graphify-out/ that leaves the tree dirty, which the check at the top of
rem  this script would then refuse to start on.
rem ========================================================================
:refresh_graph
if not exist "%ROOT%\graphify-out" exit /b 0
where graphify >nul 2>&1 || exit /b 0
echo Refreshing the knowledge graph ...
graphify update . >nul 2>&1
exit /b 0
