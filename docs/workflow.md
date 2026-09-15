# Working rules

How changes get made in this repo. These are the standing rules, not
suggestions: they apply to every change unless I say otherwise in the moment.

## The other files in here

Read these; do not restate them. This file is the rules, they are the detail.

| file | read it before |
|---|---|
| `design-system.md` | adding or changing anything the user sees -- the palette, the type, the metrics, the components. |
| `graphify.md` | asking the knowledge graph anything, or when its answers look wrong. |
| `TODO.md` | starting something new -- it may already be written down, specified, and parked. |

`README.md` in the repo root is the user-facing one: what the app does, the
flags, and how to run it. It is not a design document and does not try to be.

When one of them turns out to be wrong, fix it in the same change as the code.
A stale note is worse than no note.

## graphify

The repo builds a knowledge graph of itself in `graphify-out/`. Ask it what calls
what, where something lives, or what a change touches, **before** reading files
one by one. A question about the architecture is a graphify query first.

```bash
graphify query "what happens when a conversion is started?"
graphify update .        # after a pull or a merge -- the hooks do not cover those
```

**The graph is not committed**, and two things are outside it. The `.bat`
scripts and `UI/style.css` have no extractor, so a question about `scripts\` or
the stylesheet is not one the graph can answer. And **it stops at the bridge**:
no edge connects `UI/` to `image_convertor/`, because pywebview's `js_api` is a
runtime string lookup an AST extractor cannot see. Within either half the
traversal is real.

`graphify.md` is the rest of it: the other commands, keeping it current, what to
do when an answer looks wrong, why none of it is committed, and which commands
must never be run on this project.

## A branch per change

Every feature or fix gets its own branch off `develop`:

```bash
git checkout develop
git checkout -b feat/short-name    # or fix/short-name
```

- `feat/...` for something new, `fix/...` for something broken, `docs/...` for
  documentation, `chore/...` for the rest.
- **Never commit on `develop` directly.** `develop` only ever moves by a merge.
- Commit on the branch once the change has been tested successfully, not before.
- **Never push.** Branches stay local until I explicitly ask for a push, and
  then it is exactly what I asked for -- no merging along the way.
- Merging is my call, made branch by branch. Don't merge unprompted.

## Tests

Tests live in `tests/`, one file per area, run by pytest through the wrapper:

```bat
scripts\check.bat
```

`tests/test_converter.py` covers the conversion rules -- transparency onto
white, the aspect-ratio fit and its centring, shrink-only resizing.
`test_effects.py` and `test_formats.py` cover the effects and the containers,
`test_settings.py` what is remembered and every way the file can be wrong, and
`test_webapi.py` covers the app around all of it: what the window may ask for,
what a batch does with a file that fails, and what it warns about.

**`UI/` is not covered**, and that is a real gap rather than an oversight:
there is no JavaScript runner in this project. Everything `app.js` is allowed
to ask for is tested through `webapi.py`, and the page itself is checked by
running the app.

**Run the built exe before calling a window change done.** Two bugs have
shipped that every test passed through: one only happens frozen, and the other
only happens against a real pywebview window rather than the fake one the
tests use. Both showed as a window that opened and then said Not Responding.
`scriptsuild-and-run.bat`, click the thing that changed. A new feature or fix adds its
checks to whichever of those it belongs in, or to a new `tests/test_*.py`, which
is picked up by being put there -- pytest globs the folder and `pytest.ini`
points at it.

A branch is not ready to commit until the whole run passes.

This is the one command `scripts\merge.bat` runs, twice: on the branch, and
again on the merged result. So "the tests pass" is not a suggestion -- a branch
that fails cannot land.

## Versions belong to the merge

A feature branch **never touches `__version__`** in `image_convertor/__init__.py`.
The version identifies a build that shipped, and nothing ships from a branch --
if each branch bumped it, several branches in flight would all claim the same
next version and whichever merged last would silently win.

So the bump, the merge, the tag and the delete are one operation, done **when I
ask for the merge** and not when a branch is finished. **Do not do it by hand** --
there is a script, and it is the script because four steps done by hand are four
steps one of which eventually gets skipped:

```bat
scripts\merge.bat feat/short-name
```

That is the whole thing. It works out the bump from the branch prefix, says what
it is about to do, and then does it.

```bat
scripts\merge.bat feat/short-name --dry     say what it would do, change nothing
scripts\merge.bat fix/short-name patch      when the prefix is not the whole story
scripts\merge.bat docs/short-name none      docs only: no bump, no tag
scripts\merge.bat feat/short-name 3.0.0     an exact version
```

Which number moves, and what the prefix infers:

| Bump | For | Inferred from |
|---|---|---|
| major | a change that breaks how the app is driven -- a flag, or an answer a script relies on | never -- say it |
| minor | a feature | `feat/` |
| patch | a fix | `fix/`, `chore/` |
| none | documentation only: no bump, no tag | `docs/` |

**major is never inferred.** Nothing about a branch name can tell you that a
script someone wrote against the old flags has stopped working, so that one is
always said out loud.

**A branch that changes nothing that ships takes `none`.** The prefix says what kind
of change it is, not whether anything shipped -- a `feat/` branch touching only
`scripts/` or `docs/` would infer a minor and claim a build that behaves exactly
like the last one. `--dry` is the guard: it prints what it is about to do and
changes nothing.

### What the script refuses to do

The order is the point. Each step is there because of something that can go wrong:

- **It will not start on a dirty tree.** Its rollback is a hard reset, and a hard
  reset over uncommitted work destroys it.
- **It runs `scripts\check.bat` on the branch first.** A branch that does not pass
  alone is not merged at all.
- **It runs it again on the merged result**, and this is the check that matters:
  two branches that each pass alone can still fail together, and here is the only
  place that shows. If the merged result fails, `develop` is reset to exactly where
  it was and the branch is left untouched.
- **It tags only after the merged result passes**, and deletes the branch only after
  the tag exists. `git branch -d`, never `-D`: a refusal there means something went
  wrong worth stopping for.
- **It refreshes the knowledge graph three times**, at each point the hooks leave it
  stale: on the branch once its own tests pass, on a resolved conflict once its
  tests pass, and on `develop` once the merge has landed. That last one is the
  moment `graphify.md` calls out -- `post-commit` does not fire for a merge commit
  -- and the first is there so that a graph you reach for *because* the merge
  conflicted is the branch's, not whatever was last built.

  It never refreshes from a tree the tests have rejected, and never in a repo that
  has no graph already (building one there would leave the tree dirty, which this
  script would then refuse to start on).

If it stops, it says what state it left behind and how to finish or undo it.
Nothing is left half-done silently.

### When the merge conflicts

It stops, and it stays stopped. `develop` is left mid-merge on purpose, with the
conflicted files listed, and two ways out:

```bat
scripts\merge.bat --continue    once the conflicts are resolved and git add-ed
scripts\merge.bat --abort       throw the merge away, bump included
```

`--continue` runs the tests **on the resolved tree, before committing the merge**.
That ordering is the whole point and it is deliberately not the one the plain path
uses. There, a failure rolls `develop` back with a hard reset; here that reset would
destroy the conflict resolution, which is the one part of this nobody can redo
cheaply. So if the tests fail, nothing is committed and nothing is lost -- the
resolutions are still there, `develop` has not moved, and the fix-and-rerun loop is
`--continue` again.

It refuses while anything is still unmerged, and says which files. `--abort` puts
`develop` back exactly where it started, version bump included, and leaves the
branch untouched.

### It cannot land a change to itself

cmd reads a batch file as it runs it, a line at a time, from disk. `merge.bat`
checks out the branch and then checks out `develop` -- so a run that is landing a
change to `merge.bat` is reading the file while git is rewriting it underneath, and
what happens next is undefined.

**Land a change to `scripts\merge.bat` or `scripts\bump_version.py` by hand**, the
steps below. It is the one case, and it does not come up otherwise.

```bash
git checkout develop
# 1. bump __version__ in image_convertor/__init__.py, commit it
# 2. merge with a real merge commit
git merge --no-ff feat/short-name
# 3. tag the merge commit with the new version
git tag v1.2.0
# 4. the branch has landed; drop it
git branch -d feat/short-name
# 5. the hooks do not rebuild for a merge commit
graphify update .
```

### The version itself

`__version__` in `image_convertor/__init__.py` is the one place the number is
written -- `--version` on the command line reads it from there.
`scripts/bump_version.py` owns it, and is usable on its own:

```bat
python scripts\bump_version.py --show
python scripts\bump_version.py --next minor
```

`tests/test_version.py` asserts only the shape -- three dotted numbers, and that
`--version` prints that same number -- so it needs no edit per bump.

## main is the release branch

Two long-lived branches, and they answer different questions:

- **`develop`** is the latest work. Every branch lands here, and it moves
  several times between releases.
- **`main`** is the latest released build. It moves only at a release, and it
  only ever fast-forwards.

So `main` is what to check out to get the last thing that shipped, and the
question "what is actually released?" has an answer that is a branch name rather
than an archaeology exercise over tags.

A release is a deliberate act, not a side effect of merging:

```bash
git checkout main
git merge --ff-only develop    # refuses if develop is not ahead -- see below
git checkout develop           # get back before doing anything else
```

**`--ff-only`, always.** A plain `git merge` here would happily make a merge
commit, and a merge commit on `main` means `main` has content `develop` does not
-- at which point the two branches have diverged and every later release needs a
real merge with real conflicts. The flag refuses instead of doing that, and a
refusal means something has been committed to `main` directly, which is the thing
to go and find out about.

**Never commit on `main`.** It has no commits of its own, by construction. It is
a pointer that follows `develop`.

**The tag is made by the merge, not by the release.** `scripts\merge.bat` tags
`v1.2.0` on `develop` when the feature lands, so by the time `main` fast-forwards
the tag is already in the history it is picking up. Releasing does not tag
anything -- if it did, the same build would carry two.

Which is also why `main` is normally *behind* by the merges that carried no
version: a docs branch bumps nothing, so there is nothing new to release and
`main` stays where it is until the next feature or fix lands.

## Reporting back

If the tests passed, don't narrate the work. A brief is enough -- what branch it
was committed to, that the tests pass -- plus anything I actually have to act
on: warnings, or a choice only I can make.

## This project is not classified

Nothing here is sensitive. It converts image files; there is no protected format,
no customer data, nothing under an agreement. That is worth saying plainly rather
than leaving unsaid, because an absent rule reads as an unanswered question, and
the answer here is simply no.

So: normal open-source hygiene, and nothing beyond it.

- **Reusing it elsewhere is fine** -- in another project, as a starting point, in
  part or adapted. `LICENSE` is the only thing that governs that.
- **Pasting a file into an assistant is fine**, which is why graphify's
  model-backed commands are a cost decision here rather than a disclosure one.
  `graphify.md` still says not to run them, for the reason given there: they cost
  money and buy nothing this repo needs.

The one thing that does not belong in the repo is the obvious one: **whatever is
in `input/` and `output/`** is the user's own material, not the project's. Both
are in `.gitignore` and stay there.
