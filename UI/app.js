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

  wire();
}

function wire() {
  el("browse").addEventListener("click", () => browse("input"));
  el("browse-output").addEventListener("click", () => browse("output"));
  el("reset-output").addEventListener("click", () => setOutputFolder(state.defaultOutputFolder));
  el("output-folder").addEventListener("change", (event) => setOutputFolder(event.target.value));
  el("convert").addEventListener("click", convert);
  el("cancel").addEventListener("click", () => window.pywebview.api.cancel_conversion());
  el("theme-toggle").addEventListener("click", toggleTheme);
  el("format").addEventListener("change", showFormatNote);

  /* Validated as it is typed, by the same parser the conversion uses, so the
     message here and the message a run would give cannot drift apart. */
  el("size").addEventListener("change", async (event) => {
    const answer = await window.pywebview.api.check_size(event.target.value);
    el("size-hint").dataset.kind = answer.ok ? "" : "bad";
    el("size-hint").textContent = answer.ok
      ? "Width x height. Images keep their aspect ratio and are centred on white in the box; nothing is enlarged."
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

  for (const effect of effects) {
    const values = chosen.get(effect.name);
    list.append(effectRow(effect, values));
  }
}

function effectRow(effect, values) {
  const row = document.createElement("li");
  row.className = "effect";
  row.dataset.name = effect.name;
  row.dataset.on = values ? "true" : "false";

  const toggle = document.createElement("label");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = Boolean(values);
  box.addEventListener("change", () => {
    row.dataset.on = box.checked ? "true" : "false";
  });
  toggle.append(box, document.createTextNode(effect.name));

  const settings = document.createElement("div");
  settings.className = "effect-settings";

  effect.settings.forEach((setting, index) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "text";
    input.dataset.setting = setting.name;
    input.value = (values && values[index]) || "";
    /* The placeholder is the effect's own default, so an empty box is not a
       question -- it says what will happen if it is left alone. */
    input.placeholder = setting.default === null ? "dither" : String(setting.default);
    label.append(document.createTextNode(setting.name), input);
    settings.append(label);
  });

  row.append(toggle, settings);
  return row;
}

function chosenEffects() {
  const chosen = [];
  for (const row of document.querySelectorAll(".effect")) {
    if (row.dataset.on !== "true") continue;

    const values = [...row.querySelectorAll("[data-setting]")].map((i) => i.value.trim());
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
  const answer = await window.pywebview.api.choose_folder(which);
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

  const label = state.theme === "system"
    ? `System (${resolveTheme(state.theme)})`
    : state.theme[0].toUpperCase() + state.theme.slice(1);
  el("theme-label").textContent = label;
  el("theme-toggle").setAttribute("aria-label", `Theme: ${label}. Click to change.`);
}

/* Only while the choice is "system" -- someone who picked dark deliberately
   does not want it reverting at sunrise. */
LIGHT_QUERY.addEventListener("change", () => {
  if (state.theme === "system") applyTheme("system");
});

async function toggleTheme() {
  const next = THEMES[(THEMES.indexOf(state.theme) + 1) % THEMES.length];
  applyTheme(next);
  await window.pywebview.api.save_theme(next);
}
