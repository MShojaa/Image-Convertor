# graphify

A knowledge graph of this repo, built from the source itself. Ask it what calls
what, where something lives, or what a change touches, **before** reading files
one by one. A question about the architecture is a graphify query first.

The graph lives in `graphify-out/`. **None of it is committed** -- see
[Nothing is committed](#nothing-is-committed) for why, and what that costs.

> This project is not classified (`workflow.md` says so outright), so nothing
> here is a disclosure rule. The commands at the bottom that call out to a model
> are still not to be run, for a plainer reason: they cost money and buy nothing
> this repo needs. Everything else runs locally and needs no API key.

## Getting it in place

Already done here -- `graphify hook status` answers, and `graphify-out/` is in
`.gitignore`. This section is for a fresh clone, or another machine.

**Once per machine.** The PyPI package is `graphifyy` -- two y's, and the command
it installs is `graphify`:

```bash
pipx install graphifyy
graphify install --platform claude     # the /graphify skill + a CLAUDE.md section
```

That skill and its CLAUDE.md section are global, so a second project does not
need them again. `--platform` also takes `codex`, `cursor`, `opencode`, `gemini`
and others; `graphify --help` lists them.

**Once per repo**, from the repo root:

```bash
graphify hook install    # post-commit + post-checkout, this repo only
graphify update .        # the first build -- AST only, no API call, no cost
```

`.gitignore` already carries `graphify-out/`, with the reasoning beside it. In a
new repo, add it **before the first commit that would catch it** -- it is much
easier to ignore the folder than to untrack it later.

`hook install` also writes a `.gitattributes` in the repo root:

```gitattributes
graphify-out/graph.json merge=graphify
```

**Delete it.** It registers a driver to union-merge a *tracked* `graph.json`, and
nothing in `graphify-out/` is tracked, so it can never fire. Left alone it gets
committed and reads as though the graph were shared. (If the repo already has a
`.gitattributes`, delete just that line.) The driver stays registered in the
local git config either way; that is harmless and costs nothing.

Check the result:

```bash
graphify hook status
graphify god-nodes --top 5
git status --short       # graphify-out must not appear
```

`hook status` says this, and it is the correct outcome, not a problem:

```
post-commit: installed
post-checkout: installed
merge driver: partially registered (git config set, .gitattributes line missing)
```

"Partially registered" is what deleting `.gitattributes` looks like from
graphify's side. It is measuring against a setup where the graph is committed.
Do not fix it by putting the line back.

`god-nodes` is the useful one: it prints the most connected nodes, so if the
names coming back are the real hubs, extraction worked. **Here that is
`Monochrome`, `load()`, `convert_image()`, `Settings` and `Size`.**

They are the right ones: the effect every conversion ends with, the settings
read at startup, the function the whole app exists to call, and the two values
that cross every boundary in it. The tests are extracted alongside the app and
are the larger half of the repo, so a hub from `tests/` appearing here is not a
fault -- it means a fixture that nearly every test in its file reaches.

The size is worth knowing too -- the point of it is to notice a *collapse*, not
to match a figure. It was 480 nodes and 898 edges over 25 files at the time of
writing, and a number in prose goes out of date immediately: committing this file
adds nodes for it. Read the current one instead of trusting the sentence:

```bash
python -c "import json;g=json.load(open('graphify-out/graph.json'));print(len(g['nodes']),'nodes',len(g['links']),'edges')"
```

A fraction of that -- lookups answering *no node matching* for names that
certainly exist -- is the failure worth catching.

## Asking it things

```bash
graphify query "what happens to a transparent pixel?"
graphify explain "fit_into_box"
graphify affected "to_monochrome" --depth 2
graphify god-nodes --top 10
graphify path "image_convertor_cli_run" "convert_image()"
```

| command | what it answers |
|---|---|
| `query "..."` | scopes a subgraph from a plain-language question -- the general way in |
| `explain "X"` | one node's relationships and metadata |
| `affected "X"` | reverse traversal -- what breaks if X changes |
| `god-nodes` | the most connected nodes, i.e. the architectural hubs |
| `path "A" "B"` | the route between two things -- see the warning below |

Node names are the symbol or file names in the graph. Functions carry their
parentheses (`convert_image()`, `fit_into_box()`); classes and modules do not
(`Size`, `Converted`, `cli.py`).

### What it is built from

Every `.py`, `.md`, `.txt`, `.html` and `.js` in the repo, tests and README
included.
`manifest.json` lists them, which is the fastest way to answer "is this file in
the graph at all":

```bash
python -c "import json;print('\n'.join(sorted(json.load(open('graphify-out/manifest.json')))))"
```

**The `.bat` scripts are not in it**, and neither is `UI/style.css` or
`Image-Convertor.spec` -- there is no extractor for any of them. So `scripts\merge.bat`, `scripts\check.bat` and
the rest of the workflow are invisible to the graph: a question about what a
script does is a question for `workflow.md` and the comments in the file itself.
That is most of `scripts/`, which is the one real blind spot here.

### The graph stops at the bridge

**Not one edge in this graph connects `UI/` to `image_convertor/`.** Measured,
not assumed: 22 nodes from `UI/`, 377 from the Python, and zero edges between
the two groups. The window
reaches Python through pywebview's `js_api` -- `window.pywebview.api.start_conversion(...)`
in `app.js` arriving at `Api.start_conversion` in `webapi.py` -- and that is a
string lookup at runtime, which an AST extractor cannot see and does not invent.

So `path` and `affected` **never cross from a JS symbol to a Python one**, and a
"no path found" between the two halves means nothing at all. `query` still
returns both sides of a question, because it seeds from name matches rather than
by traversing.

Within either half the traversal is real: `main.py` to `webapi.py` to
`converter.py` to `effects.py` is one process with no lookup in the middle, and
`affected "to_monochrome"` genuinely lists everything that would break.

For anything that crosses the bridge, `docs/design-system.md` and the module
docstring in `webapi.py` are the map -- the latter is deliberately explicit
about what may cross and in what shape, because the graph cannot be.

### When a lookup does not answer

Three things trip up lookups, and each says so rather than failing silently:

- **No node matching.** The name is wrong, **or the graph is stale or broken** --
  check [When answers look wrong](#when-answers-look-wrong) before assuming it is
  the name. Constants are a common miss: `DEFAULT_THRESHOLD` and
  `SUPPORTED_SUFFIXES` are not nodes, because the extractor graphs callables and
  files, not every module-level name.
- **Ambiguous: matches N nodes.** A name that exists in more than one file. It
  prints the candidate ids; pass the one you meant instead of the bare name:

      graphify explain "image_convertor_cli_main"

  `main()` is the live example here -- there are three, in `cli.py`, `main.py`
  and `build.py`. `explain` refuses and lists them, but **`path` and `affected`
  guess**, printing a one-line `warning: source match was ambiguous` and then
  answering about whichever node they picked. `path "main()" "convert_image()"`
  reports no path at all that way, which is wrong; with the id it is one hop. If
  a traversal surprises you, check that warning line first.
- **No directed path found.** `path` follows edge direction by default. Re-run
  with `--undirected`, but read the result: an undirected path can route through
  something incidental the two ends merely share. A path is a hint to go and read
  the code, not a finding.

`query` truncates to a ~2000-token budget and says so when it does. Raise it with
`--budget N`, or narrow the question rather than trusting a truncated answer.

There are two ways in and they are not the same thing. `/graphify` is the skill,
through the assistant; the `graphify` CLI is what runs headless, where there is
no assistant to invoke the skill.

## Keeping it current

```bash
graphify update .        # seconds, AST only, no API call, no cost
```

`post-commit` and `post-checkout` rebuild in the background, so ordinary work
keeps the graph fresh on its own. Because `graphify-out/` is ignored, a rebuild
can never leave the working tree dirty and can never block a checkout or a merge.

**The hooks do not cover a pull or a merge.** After either, run
`graphify update .` by hand. That matters every time a branch lands: a merge
commit is not a commit the post-commit hook rebuilds from, so the graph is stale
until it is run -- and in this repo every branch lands by `--no-ff` merge, so it
is *every* time. `scripts\merge.bat` does it for you at each of the three points
that matter; doing it by hand is for the pulls and the merges that bypass it.

A full rebuild is cheap enough that when in doubt, just run it.

### The hooks live in .git, so a clone has none

```bash
graphify hook status     # post-commit / post-checkout installed
graphify hook install    # if either is missing
```

Worth checking after a fresh clone or a recreated `.git`. Without the hooks the
graph simply stops moving while still looking like an answer, which is worse than
having none. The background rebuild logs to `~/.cache/graphify-rebuild.log`.

`hook status` also reports the **merge driver** as *partially registered*. That is
expected here and needs no action -- see [Getting it in
place](#getting-it-in-place).

## When answers look wrong

A graph that is stale or partial still answers confidently. Two failures look
different and are worth telling apart.

**Stale** -- the answer describes code as it was. The fix is the same as the
check, costs seconds, and cannot be wrong:

```bash
graphify update .
```

If you want to know *whether* it was behind rather than just fixing it, do not
compare commit hashes. `graph.json` records `built_at_commit`, but that is the
commit HEAD stood at during the last **rebuild**, and a rebuild only happens when
an extracted file's content changes. So the stamp legitimately lags HEAD after
any commit that changed nothing the graph is built from -- which includes **every
merge commit in this repo**, since a merge of a branch that develop has not moved
past introduces no new content at all. Comparing hashes reports a perfectly
current graph as behind, every time a branch lands.

Ask whether any *extracted* file changed instead:

```bash
STAMP=$(python -c "import json;print(json.load(open('graphify-out/graph.json'))['built_at_commit'])")
git diff --stat $STAMP HEAD -- '*.py' '*.md' '*.txt' '*.html' '*.js'
```

Empty means the graph is current whatever the two hashes say. Note the globs:
the `.bat` files, `UI/style.css` and the PyInstaller spec are **not**
extracted, so a commit touching only `scripts/` or the stylesheet never dates
the graph either.

**Collapsed** -- the graph has lost most of its nodes, and lookups start answering
*no node matching* for names that certainly exist. Check the size:

```bash
python -c "import json;print(len(json.load(open('graphify-out/graph.json'))['nodes']))"
```

This happens when two background rebuilds overlap -- switching branches several
times in quick succession launches a detached rebuild per switch, and one can
write a partial graph over a complete one. It is a race, not a repeatable bug.

Either way the fix is the same, and graphify keeps a dated backup of the last
good graph next to it:

```bash
graphify update .                   # rebuilds in full; this is the authoritative fix
ls graphify-out/2026-*/             # the backup taken before the bad write
```

**Believe the code over the graph.** If an answer looks wrong or dated, rebuild
and ask again before acting on it.

## Nothing is committed

The whole of `graphify-out/` is ignored. Tracking it is tempting -- a clone would
start with the map already built -- and it is a bad trade, for two reasons that
compound:

- **A `post-commit` hook cannot be in the commit it follows.** It writes its
  output *after* the commit, so the rebuild is never inside the commit that
  triggered it. The tree goes dirty the instant any commit finishes, by
  construction, and those dirty files then block the next checkout or merge. No
  hook ordering fixes this -- it is what *post* means. In this repo it would also
  collide with `merge.bat`, which refuses to start on a dirty tree.
- **`manifest.json` changes on its own.** It records an mtime per file beside the
  content hash, and a checkout rewrites every mtime without changing a byte, so
  switching branches is enough to dirty it.

  The mtime is not what triggers work, though: the manifest carries both `mtime`
  and `ast_hash`, and it is the *hash* that decides whether anything is
  re-extracted. So the mtime churn dirties the manifest without ever causing a
  needless rebuild. It is a reason not to track the folder, not a reason the
  graph is unreliable.

Against that, a cold rebuild takes seconds, costs no API call, and regenerates
the community labels just as well -- they come from hub node names, not a model,
which is why the report says `Token cost: 0`.

So: the graph is a derived artifact. Rebuild it, do not carry it. A fresh clone
has no graph until `graphify update .` is run, which is the one thing given up
here.

`.gitignore` carries this reasoning too, for whoever reads it there first.

## Commands that send code off the machine

Everything above is local. `graphify update .` uses an AST extractor that needs
no API key and no network, and the graph, the report and the community labels all
come out of it -- which is why the report says `Token cost: 0`.

These are the exceptions:

| command | what leaves |
|---|---|
| `graphify extract` | source chunks, to an LLM provider, for semantic extraction |
| `graphify label` | community contents, to an LLM provider, for naming |
| `graphify cluster-only` *without* `--no-label` | the same as `label` |
| `graphify add <url>` | fetches a URL into `./raw` and indexes it |
| `graphify global add` | merges this repo's nodes into `~/.graphify/global-graph.json`, outside the project |

**Do not run any of them here.** Not for secrecy -- this project is not
classified -- but because they cost real money per run and nothing above needs
them. Ten files of straightforward Python is exactly the case where the AST
extractor already gets it right. The `Tip: set GEMINI_API_KEY ...` line printed
after every update is graphify's own advertising for these; ignore it.

`global add` is the one to be careful with for a different reason: it writes
outside the repo, into a shared graph that later sessions in *other* projects
read. Nothing here would be harmed by leaking, but a global graph carrying
several projects' `main()` and `Size` nodes makes every one of them ambiguous.
