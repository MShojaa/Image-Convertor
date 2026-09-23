/* The window's behaviour. Everything it can ask the app to do is a method on
   window.pywebview.api -- see image_convertor/webapi.py, which is the only
   Python that knows this page exists.

   Two rules this file follows throughout:

   - Nothing crosses the bridge except strings, numbers and plain objects. A
     Path or a tuple arrives here as an empty object, silently.
   - Every api call returns {ok: true, ...} or {ok: false, error: "..."}, and
     the error is a sentence written to be shown. So failures are shown, never
     swallowed and never turned into a generic message of our own. */

const state = {
  settingColumns: 0,
  folder: "",
  outputFolder: "",
  defaultOutputFolder: "",
  theme: "system",
  effects: [],      // what the app told us exists, in the order they run
  formats: [],
  running: false,
  total: 0,
};

const el = (id) => document.getElementById(id);

/* pywebview injects its api object asynchronously; the event is how you know
   it is there. Reading window.pywebview.api before it fires is the classic
   way to get "undefined is not a function" on a page that is otherwise fine. */
window.addEventListener("pywebviewready", start);

async function start() {
  const info = await window.pywebview.api.describe_app();
  if (!info.ok) {
    return fail(info.error);
  }

  state.effects = info.effects;
  state.formats = info.formats;

  applyTheme(info.settings.theme);
  buildFormats(info.formats, info.settings.output_format);
  buildEffects(info.effects, info.settings.effects);

  el("size").value = info.settings.size || "";

  if (info.input_folder) {
    setFolder(info.input_folder, info.has_folder_beside);
  } else {
    el("folder-status").textContent =
      "No input folder beside the app. Choose one with Browse.";
  }

  state.defaultOutputFolder = info.default_output_folder;
  setOutputFolder(info.output_folder);

  watchWindowState();

  wire();
}

function wire() {
  el("browse").addEventListener("click", () => browse("input"));
  el("browse-output").addEventListener("click", () => browse("output"));
  el("reset-output").addEventListener("click", () => setOutputFolder(state.defaultOutputFolder));
  el("output-folder").addEventListener("change", (event) => setOutputFolder(event.target.value));
  el("convert").addEventListener("click", convert);
  el("cancel").addEventListener("click", () => window.pywebview.api.cancel_conversion());
  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    button.addEventListener("click", () => chooseTheme(button.dataset.themeChoice));
  }
  el("theme-switcher").addEventListener("keydown", themeKeys);
  el("reveal").addEventListener("click", revealOutput);

  captionButton("window-minimize", () => window.pywebview.api.window_minimize());
  captionButton("window-maximize", toggleMaximize);
  captionButton("window-close", () => window.pywebview.api.window_close());

  document.querySelector(".titlebar-grip").addEventListener("mousedown", grabTitlebar);
  el("format").addEventListener("change", showFormatNote);

  /* Validated as it is typed, by the same parser the conversion uses, so the
     message here and the message a run would give cannot drift apart. */
  el("size").addEventListener("change", async (event) => {
    const answer = await window.pywebview.api.check_size(event.target.value);
    el("size-hint").dataset.kind = answer.ok ? "" : "bad";
    el("size-hint").textContent = answer.ok
      ? "Aspect ratio kept, centred on white in the box, never enlarged."
      : answer.error;
  });

  el("folder").addEventListener("change", async (event) => {
    const answer = await window.pywebview.api.inspect_folder(event.target.value);
    if (!answer.ok) return fail(answer.error);
    setFolder(answer.folder, false, answer.count);
  });
}

/* -- building the controls from what the app knows ---------------------- */

function buildFormats(formats, chosen) {
  const select = el("format");
  select.innerHTML = "";

  /* "Same as the input" is the default and has to be an option rather than an
     empty value, or nobody can get back to it after picking something. */
  select.append(new Option("Same as the input", ""));
  for (const format of formats) {
    select.append(new Option(format.name, format.name));
  }
  select.value = chosen || "";
  showFormatNote();
}

function showFormatNote() {
  const chosen = state.formats.find((f) => f.name === el("format").value);
  el("format-note").textContent = chosen && chosen.note ? `${chosen.name}: ${chosen.note}` : "";
}

function buildEffects(effects, remembered) {
  const list = el("effects");
  list.innerHTML = "";

  /* What was remembered arrives as the text it would be typed as --
     "blur:2", "monochrome" -- so the name is up to the first colon and the
     rest are that effect's settings in order. */
  const chosen = new Map();
  for (const text of remembered || []) {
    const [name, ...values] = text.split(":");
    chosen.set(name, values);
  }

  effects.forEach((effect, index) => {
    list.append(effectRow(effect, chosen.get(effect.name), index + 1));
  });

  for (const effect of effects) updateDependents(effect);
  showChain();
}

function effectRow(effect, values, step) {
  const row = document.createElement("li");
  row.className = "effect";
  row.dataset.name = effect.name;
  row.dataset.on = values ? "true" : "false";

  /* The step number is the effect's place in the pipeline, not its place in
     this list -- they happen to be the same because the list is built in
     that order, and that is the point of showing it. */
  const number = document.createElement("span");
  number.className = "effect-step";
  number.textContent = step;
  number.setAttribute("aria-hidden", "true");

  const toggle = document.createElement("label");
  toggle.className = "effect-name";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = Boolean(values);
  box.addEventListener("change", () => {
    row.dataset.on = box.checked ? "true" : "false";
    showChain();
  });
  toggle.append(number, box, document.createTextNode(effect.name));

  const settings = document.createElement("div");
  settings.className = "effect-settings";
  row.append(toggle, settings);

  /* Each setting is its own label and input placed directly in the row's
     grid, rather than wrapped in a box of its own. The wrapper was what
     stopped the inputs lining up: every row sized its own, so "radius" and
     "threshold" pushed their boxes to different places. */
  effect.settings.forEach((setting, index) => {
    const pair = document.createElement("div");
    pair.className = "setting";

    const label = document.createElement("label");
    label.className = "setting-label";
    /* The title, not the name: the name is the field the effect declares and
       is sometimes a Python identifier rather than something to read. */
    label.textContent = setting.title || setting.name;

    const control = settingControl(effect, setting, values && values[index]);
    label.htmlFor = control.id;

    pair.append(label, control);
    settings.append(pair);
  });

  return row;
}

/* One control per setting, chosen by what the setting is. A dropdown for a
   fixed set of words, a checkbox for a yes/no, a box to type in otherwise --
   rather than a text field for everything and a user left to guess that
   "soft" wants the word "yes". Every one of them still produces the same
   text the effect would be typed as, so the two ways in cannot drift. */
function settingControl(effect, setting, value) {
  const id = `setting-${effect.name}-${setting.name}`;

  const remembered = String(setting.default === null ? "" : setting.default);

  if (setting.kind === "choice") {
    const select = document.createElement("select");
    select.id = id;
    select.className = "setting-input";
    select.dataset.setting = setting.name;
    select.dataset.default = remembered;
    for (const option of setting.options) {
      select.append(new Option(option, option));
    }
    select.value = value || setting.default;
    select.addEventListener("change", () => {
      showChain();
      updateDependents(effect);
    });
    return select;
  }

  if (setting.kind === "flag") {
    const box = document.createElement("input");
    box.type = "checkbox";
    box.id = id;
    box.className = "setting-flag";
    box.dataset.setting = setting.name;
    box.dataset.default = remembered;
    box.checked = value ? value === "yes" : setting.default === "yes";
    box.addEventListener("change", showChain);
    return box;
  }

  const input = document.createElement("input");
  input.type = "text";
  input.id = id;
  input.className = "setting-input";
  input.dataset.setting = setting.name;
  input.dataset.default = remembered;
  input.value = value || "";
  /* The placeholder is the effect's own default, so an empty box is not a
     question -- it says what will happen if it is left alone. */
  input.placeholder = setting.default === null ? "dither" : String(setting.default);
  input.addEventListener("input", showChain);
  return input;
}

/* A setting the chosen mode does not use is greyed rather than hidden: a row
   that changes shape when you use it moves everything below it. The one case
   today is the tolerance, which an exact match ignores. */
function updateDependents(effect) {
  const row = document.querySelector(`.effect[data-name="${effect.name}"]`);
  if (!row) return;

  const match = row.querySelector('[data-setting="match"]');
  const tolerance = row.querySelector('[data-setting="tolerance"]');
  if (!match || !tolerance) return;

  tolerance.disabled = match.value === "exact";
  tolerance.title = tolerance.disabled ? "An exact match ignores the tolerance" : "";
}

/* The value a control holds, as the text the effect would be typed with.

   A value left at its default is written as nothing, which is the same rule
   the Python side follows when it describes an effect -- and the reason the
   line under the list reads "transparent" rather than
   "transparent::tolerance::no". Trailing nothings are dropped by the caller,
   so what is left is only what was actually chosen. */
function settingValue(control) {
  if (control.disabled) return "";

  const value = control.type === "checkbox"
    ? (control.checked ? "yes" : "no")
    : control.value.trim();

  return value === control.dataset.default ? "" : value;
}

/* What will actually run, in order, spelled the way the app would write it.
   The numbered list says where each effect sits; this says what the run is. */
function showChain() {
  const chosen = chosenEffects();
  el("effect-chain").textContent = chosen.length
    ? `Will run: ${chosen.join("  \u2192  ")}`
    : "No effects: images are resized and rewritten, nothing else.";
}

function chosenEffects() {
  const chosen = [];
  for (const row of document.querySelectorAll(".effect")) {
    if (row.dataset.on !== "true") continue;

    const values = [...row.querySelectorAll("[data-setting]")].map(settingValue);
    /* Trailing blanks are dropped so "monochrome" and "monochrome:" are the
       same thing, and a blank in the middle keeps its place -- "noise::7" is
       the default amount with a chosen seed. */
    while (values.length && values[values.length - 1] === "") values.pop();

    chosen.push([row.dataset.name, ...values].join(":"));
  }
  return chosen;
}

/* -- the folder --------------------------------------------------------- */

async function browse(which) {
  /* The folder comes back as a "folder_chosen" event, not as this call's
     result: the dialog cannot be opened from inside a js_api call without
     deadlocking the window. See choose_folder() in webapi.py. */
  browseButtons(true);
  /* Start the dialog where the box already points, rather than wherever
     Windows last left it. */
  const start = which === "output" ? state.outputFolder : state.folder;
  const answer = await window.pywebview.api.choose_folder(which, start);
  if (!answer.ok) {
    browseButtons(false);
    fail(answer.error);
  }
}

/* Both at once: the dialog is modal, so while one is open neither button can
   usefully be pressed. */
function browseButtons(disabled) {
  el("browse").disabled = disabled;
  el("browse-output").disabled = disabled;
}

function folderChosen(data) {
  browseButtons(false);
  if (!data.ok) return fail(data.error);
  if (!data.folder) return;            // cancelled, which is not a failure

  if (data.which === "output") {
    setOutputFolder(data.folder);
  } else {
    setFolder(data.folder, false, data.count);
  }
}

function setOutputFolder(folder) {
  state.outputFolder = folder;
  el("output-folder").value = folder;
  el("output-status").textContent =
    folder === state.defaultOutputFolder ? "The output folder beside the app." : "";
}

function setFolder(folder, beside, count) {
  state.folder = folder;
  el("folder").value = folder;

  if (count === undefined) {
    el("folder-status").textContent = beside ? "The input folder beside the app." : "";
    return;
  }
  el("folder-status").textContent =
    count === 1 ? "1 image" : `${count} images`;
}

/* -- running ------------------------------------------------------------ */

async function convert() {
  if (state.running) return;

  clearLog();
  const answer = await window.pywebview.api.start_conversion(
    state.folder,
    el("size").value,
    el("format").value,
    chosenEffects(),
    true,
    state.outputFolder
  );

  if (!answer.ok) return fail(answer.error);

  state.running = true;
  state.total = answer.count;
  el("convert").disabled = true;
  el("cancel").hidden = false;
  setSummary("", "");
  log(`Converting ${answer.count} image(s) with ${answer.effects}.`, "");
  progress(0, answer.count);
}

/* The one entry point the worker thread calls into. Everything the run has to
   say arrives here, which is why it is a single function with a switch rather
   than a handful of globals the Python side has to remember the names of. */
window.onAppEvent = function (event, data) {
  if (event === "folder_chosen") {
    folderChosen(data);
  } else if (event === "file_converted") {
    log(`${data.name} -> ${data.written} (${data.size})`, "");
    if (data.warning) log(`  WARNING  ${data.warning}`, "warn");
    progress(data.index, data.total);
  } else if (event === "file_failed") {
    log(`FAILED  ${data.name}: ${data.error}`, "bad");
    progress(data.index, data.total);
  } else if (event === "conversion_cancelled") {
    finish();
    setSummary(`Cancelled after ${data.done} image(s).`, "warn");
  } else if (event === "conversion_finished") {
    finish();
    summarise(data);
  }
};

function summarise(data) {
  const parts = [`${data.converted} converted`];
  if (data.failed) parts.push(`${data.failed} failed`);

  let kind = data.failed ? "bad" : "good";
  let message = `${parts.join(", ")}. Written to ${data.output_folder}`;

  /* The warning repeated where it will still be on screen after a long batch.
     "nothing was shrunk" is its own sentence because it usually means the box
     is bigger than the source material, which is worth saying outright. */
  if (data.all_too_small) {
    message += `. Nothing was shrunk -- every image was already smaller than ${data.box}.`;
    kind = data.failed ? "bad" : "warn";
  } else if (data.not_shrunk.length) {
    message += `. ${data.not_shrunk.length} could not be shrunk (already smaller than ${data.box}).`;
    kind = data.failed ? "bad" : "warn";
  }

  setSummary(message, kind);
}

function finish() {
  state.running = false;
  el("convert").disabled = false;
  el("cancel").hidden = true;
}

function progress(done, total) {
  const percent = total ? Math.round((done / total) * 100) : 0;
  el("progress-bar").style.width = `${percent}%`;
  el("counter").textContent = total ? `${done} / ${total}` : "";
  document.querySelector(".progress").setAttribute("aria-valuenow", String(percent));
}

/* Show the results. The folder is created if it is not there yet, so the
   button works before the first run -- an empty window is a fair answer to
   "where do these go?". */
async function revealOutput() {
  const answer = await window.pywebview.api.reveal_folder(state.outputFolder);
  if (!answer.ok) fail(answer.error);
}

/* -- the log ------------------------------------------------------------ */

function log(text, kind) {
  const line = document.createElement("div");
  line.className = "log-line";
  if (kind) line.dataset.kind = kind;
  line.textContent = text;
  el("log").append(line);
  el("log").scrollTop = el("log").scrollHeight;
}

function clearLog() {
  el("log").innerHTML = "";
  progress(0, 0);
}

function setSummary(text, kind) {
  el("summary").textContent = text;
  el("summary").dataset.kind = kind;
}

function fail(message) {
  setSummary(message, "bad");
  log(message, "bad");
}

/* -- the window's own titlebar ------------------------------------------- */

/* Dragging the window, by the only means that gets Windows' own behaviour.

   pywebview's drag region works by moving the window from here: it watches
   mousemove and asks Python to put the window at the new position. Windows is
   never told a drag is happening, so everything it does for a real titlebar --
   snapping to an edge and previewing it, Snap Assist, the layouts grid,
   drag-to-the-top to maximize, shake -- simply does not happen. None of it can
   be imitated from this end either: they are not window positions, they are a
   modal loop inside Windows.

   So the grip is not a pywebview drag region any more. Mousedown asks Windows
   to take the gesture, and Windows runs the drag.

   Two things ride along:

   Double-click. Windows would normally maximize on a double-click of the
   caption, but it only sees the presses we forward, and the first one starts a
   move loop that swallows the second. `detail` counts the clicks, so the
   second press maximizes here instead of starting another drag.

   The fallback. If Windows will not take it -- another platform, or a backend
   with no handle -- the grip becomes a pywebview drag region again and the
   window moves the old way. pywebview reads the selector at mousedown, so
   adding the class now is enough for the very next drag.
*/
async function grabTitlebar(event) {
  if (event.button !== 0) return;

  if (event.detail === 2) {
    toggleMaximize();
    return;
  }

  const answer = await window.pywebview.api.window_drag();
  if (!answer.ok) {
    document.querySelector(".titlebar-grip").classList.add("pywebview-drag-region");
  }
}

/* A caption button, wired up and told to let go afterwards.

   Clicking maximize left the button focused, and the window coming back from
   the resize is enough for Chromium to call that focus visible -- so a bright
   ring sat on the button until something else was clicked. No other window on
   this desktop does that.

   `detail` is how the press arrived: a mouse click counts the clicks and a
   keyboard activation reports 0. So the pointer drops focus and the keyboard
   keeps it, which is the only way round that serves both.
*/
function captionButton(id, act) {
  const button = el(id);
  button.addEventListener("click", (event) => {
    if (event.detail > 0) button.blur();
    act();
  });
}

async function toggleMaximize() {
  const answer = await window.pywebview.api.window_toggle_maximize();
  if (!answer.ok) return fail(answer.error);
  showMaximized(answer.maximized);
}

/* Which picture the maximize button draws. Kept on <body> rather than on the
   button, because it is a fact about the window and the CSS reads better for
   it. */
function showMaximized(maximized) {
  document.body.dataset.maximized = String(Boolean(maximized));
  const button = el("window-maximize");
  const words = maximized ? "Restore" : "Maximize";
  button.title = words;
  button.setAttribute("aria-label", words);
}

/* The window can be maximized without going through this app at all -- Aero
   Snap, a drag to the top edge, Win+Up -- so the button follows the window
   rather than the click. A resize is the one event all of those share. */
async function watchWindowState() {
  const answer = await window.pywebview.api.window_state();
  if (answer.ok) showMaximized(answer.maximized);
}

let resizeSettling = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeSettling);
  resizeSettling = setTimeout(watchWindowState, 120);
});

/* -- theme --------------------------------------------------------------- */

/* Three choices, two looks. "system" is a stored choice like the other two,
   not the absence of one -- it is resolved against the OS every time it is
   applied, so a window left open follows the OS changing under it.

   Resolving here rather than in CSS is deliberate. A media query would need a
   second copy of the light tokens to cover the system case, and the whole
   design rests on there being exactly one block of values per theme. */

const THEMES = ["system", "dark", "light"];
const LIGHT_QUERY = window.matchMedia("(prefers-color-scheme: light)");

function resolveTheme(choice) {
  if (choice !== "system") return choice;
  return LIGHT_QUERY.matches ? "light" : "dark";
}

function applyTheme(choice) {
  state.theme = THEMES.includes(choice) ? choice : "system";
  document.documentElement.dataset.theme = resolveTheme(state.theme);

  /* A roving tabindex: the group is one stop on the way round the window,
     and the arrow keys move within it. Three separate tab stops for one
     setting would be three times the tabbing for no more choice. */
  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    const chosen = button.dataset.themeChoice === state.theme;
    button.setAttribute("aria-checked", String(chosen));
    button.tabIndex = chosen ? 0 : -1;
  }
}

/* Only while the choice is "system" -- someone who picked a theme
   deliberately does not want it reverting at sunrise. */
LIGHT_QUERY.addEventListener("change", () => {
  if (state.theme === "system") applyTheme("system");
});

/* Pick one of the three, and remember it. "system" is one of the three
   rather than the absence of a choice, so going back to following the
   desktop is a click like any other. */
async function chooseTheme(choice) {
  if (choice === state.theme) return;
  applyTheme(choice);
  await window.pywebview.api.save_theme(choice);
}

/* Arrow keys move through the group, which is what a radiogroup does and
   what the roving tabindex above is for. Home and End go to the ends. */
function themeKeys(event) {
  const order = ["system", "light", "dark"];
  const at = order.indexOf(state.theme);

  let wanted = null;
  if (event.key === "ArrowRight" || event.key === "ArrowDown") {
    wanted = order[(at + 1) % order.length];
  } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
    wanted = order[(at - 1 + order.length) % order.length];
  } else if (event.key === "Home") {
    wanted = order[0];
  } else if (event.key === "End") {
    wanted = order[order.length - 1];
  }

  if (wanted === null) return;
  event.preventDefault();
  chooseTheme(wanted);
  document.querySelector(`[data-theme-choice="${wanted}"]`).focus();
}
