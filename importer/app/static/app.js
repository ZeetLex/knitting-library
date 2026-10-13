/* Pattern importer. Three stages: get the pattern, check the details, add it to the library.
   All page text is set with textContent, never as HTML, so nothing from a pattern can run as code. */
(() => {
  "use strict";

  // ------------------------------------------------------------------ small helpers
  const KEY = "knit-import-draft";
  const store = {
    get() { try { return localStorage.getItem(KEY); } catch { return null; } },
    set(v) { try { localStorage.setItem(KEY, v); } catch { /* private window: fine */ } },
    clear() { try { localStorage.removeItem(KEY); } catch { /* ignore */ } },
  };

  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, v);
    }
    const add = (kid) => {
      if (kid === null || kid === undefined || kid === false) return;
      if (Array.isArray(kid)) kid.forEach(add);
      else el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    };
    kids.forEach(add);
    return el;
  }

  const ICONS = {
    tick: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    cross: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    warn: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.2v.1"/></svg>',
    info: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 7.8v.1"/></svg>',
    dot: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
    spin: '<svg class="spin" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9" /></svg>',
    close: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    big_tick: '<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  };
  function icon(name) {
    const span = document.createElement("span");
    span.className = "ico";
    span.innerHTML = ICONS[name]; // fixed strings above, never data
    return span;
  }

  async function api(method, path, body, opts = {}) {
    const init = { method, headers: { "X-Requested-With": "knit-import" } };
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(path, init);
    } catch {
      throw new Error("Could not reach the importer. Check your connection and try again.");
    }
    if (opts.raw) return res;
    let data = null;
    try { data = await res.json(); } catch { /* not JSON */ }
    if (!res.ok) {
      let msg = data && data.detail;
      if (Array.isArray(msg)) msg = "Something in that request was not right.";
      throw new Error(msg || `Something went wrong (error ${res.status}).`);
    }
    return data;
  }

  // ------------------------------------------------------------------ state
  const S = {
    draft: null,
    status: null,
    suggestions: { categories: [], tags: [] },
    ui: { url: "", urlError: "", busy: false, continued: false, backToDetails: false, rejected: [], problem: "", uploading: false, textPreview: null },
    timer: null,
    lastStage: 0,
    saveTimers: {},
  };
  const main = document.getElementById("main");
  const rail = document.getElementById("rail");
  const statusEl = document.getElementById("status");

  // ------------------------------------------------------------------ stage logic
  function stageOf(d) {
    if (!d) return 1;
    const pub = d.publish;
    if (pub && ["running", "done", "duplicate", "error"].includes(pub.state) && !S.ui.backToDetails) return 3;
    if (d.status === "ready" && S.ui.continued) return 2;
    if (d.status === "published") return 3;
    return 1;
  }

  function renderRail(stage) {
    const names = ["Get pattern", "Check details", "Add to library"];
    const nodes = [];
    names.forEach((name, i) => {
      const n = i + 1;
      const state = n < stage ? "done" : n === stage ? "current" : "";
      const finished = n === 3 && S.draft && S.draft.publish && S.draft.publish.state === "done";
      const cls = finished ? "done" : state;
      nodes.push(
        h("div", { class: `node ${cls}`, "aria-current": n === stage && !finished ? "step" : null },
          h("div", { class: "bubble" }, cls === "done" ? icon("tick") : String(n)),
          h("div", { class: "label" }, name)),
      );
      if (n < 3) nodes.push(h("div", { class: `stitch ${n < stage || finished ? "done" : ""}`, "aria-hidden": "true" }));
    });
    rail.replaceChildren(...nodes);
  }

  function renderStatus() {
    const st = S.status;
    const back = document.getElementById("back");
    if (back) {
      if (st && st.library_url) { back.href = st.library_url; back.hidden = false; } else { back.hidden = true; }
    }
    if (!st) { statusEl.className = "status"; statusEl.replaceChildren(); return; }
    const lib = st.library || {};
    let text, cls;
    if (lib.reachable && lib.logged_in) { text = "Library connected"; cls = "ok"; }
    else if (lib.reachable) { text = "Library sign-in needed"; cls = "warn"; }
    else { text = "Library not reachable"; cls = "warn"; }
    statusEl.className = `status ${cls}`;
    statusEl.title = lib.detail || "";
    statusEl.replaceChildren(h("span", { class: "dot" }), text);
  }

  // ------------------------------------------------------------------ shared pieces
  const PAST = {
    page: "Read the pattern page", print: "Read the print view", pdf: "Made the PDF", read: "Read the pattern",
    check: "Checked your library", recipe: "Added the pattern and PDF", text: "Saved the instructions as text",
    cover: "Chose the cover picture", yarn: "Added the yarns to your yarn list",
  };
  function stepList(steps) {
    return h("ol", { class: "steps", "aria-live": "polite" },
      steps.map((s) => {
        const mark = s.state === "done" ? icon("tick") : s.state === "active" ? icon("spin")
          : s.state === "failed" ? icon("cross") : s.state === "skipped" ? icon("warn") : icon("dot");
        return h("li", { class: s.state },
          h("span", { class: "mark" }, mark),
          h("div", {}, h("div", { class: "t" }, s.state === "done" && PAST[s.key] ? PAST[s.key] : s.label), s.detail ? h("div", { class: "d" }, s.detail) : null));
      }));
  }

  function checkList(checks) {
    return h("ul", { class: "checks" }, (checks || []).map((c) =>
      h("li", { class: c.state },
        h("span", { class: "ci" }, icon(c.state === "ok" ? "tick" : c.state === "warn" ? "warn" : "cross")),
        h("div", {}, c.label, c.detail ? h("span", { class: "cd" }, ` ${c.detail}`) : null))));
  }

  function note(kind, title, body, extra) {
    return h("div", { class: `note ${kind}`, role: kind === "bad" ? "alert" : null },
      icon(kind === "good" ? "tick" : kind === "bad" ? "cross" : kind === "warn" ? "warn" : "info"),
      h("div", { class: "body" }, title ? h("p", { class: "strong" }, title) : null, body ? h("p", {}, body) : null, extra));
  }

  function technical(text) {
    if (!text) return null;
    return h("details", { class: "tech" }, h("summary", {}, "Details for whoever looks after the server"), h("pre", {}, text));
  }

  // ------------------------------------------------------------------ stage 1
  function viewStart() {
    const lib = S.status && S.status.library;
    const input = h("input", {
      class: `input${S.ui.urlError ? " bad" : ""}`, type: "text", id: "url", name: "url", inputmode: "url",
      autocomplete: "off", spellcheck: "false", placeholder: "https://www.garnstudio.com/pattern.php?id=…",
      value: S.ui.url, "aria-describedby": "url-help url-error",
      oninput: (e) => { S.ui.url = e.target.value; },
    });
    const submit = async (e) => {
      e.preventDefault();
      S.ui.url = input.value;
      S.ui.urlError = "";
      S.ui.busy = true; render();
      try {
        const d = await api("POST", "api/drafts", { url: S.ui.url });
        setDraft(d);
      } catch (err) {
        S.ui.urlError = err.message;
      }
      S.ui.busy = false; render();
    };
    return h("div", { class: "stack" },
      h("div", { class: "stage-head" },
        h("h1", { tabindex: "-1" }, "Which pattern would you like?"),
        h("p", { class: "lede" }, "Paste the link to a pattern on the DROPS website. The importer fetches it, makes the PDF and reads the instructions for you.")),
      lib && !lib.reachable ? note("warn", "Knitting Library cannot be reached", "You can still get a pattern ready, but it cannot be added until the library is back.") : null,
      lib && lib.reachable && !lib.logged_in ? note("warn", "The importer cannot sign in to Knitting Library", lib.detail || "Ask whoever looks after the server to check the importer account.") : null,
      h("form", { onsubmit: submit },
        h("label", { class: "field", for: "url" },
          h("span", { class: "field-name" }, "Pattern link"),
          h("span", { class: "field-hint", id: "url-help" }, "Open the pattern on garnstudio.com, then copy the link from the address bar.")),
        h("div", { class: "getform" }, input,
          h("button", { class: "btn", type: "submit", disabled: S.ui.busy }, S.ui.busy ? "Starting…" : "Get pattern")),
        h("div", { id: "url-error", class: "field-error", role: "alert" }, S.ui.urlError)),
      h("div", { class: "actions" },
        h("span", { class: "lede" }, "Already saved the files yourself?"),
        h("button", { class: "linklike", type: "button", onclick: startManual }, "Add them by hand")),
    );
  }

  async function startManual() {
    try {
      const d = await api("POST", "api/drafts/manual");
      setDraft(d);
      render();
    } catch (err) {
      S.ui.urlError = err.message; render();
    }
  }

  function viewWorking(d) {
    return h("div", { class: "stack" },
      h("div", { class: "stage-head" },
        h("h1", { tabindex: "-1" }, "Getting your pattern"),
        h("p", { class: "lede" }, "The importer asks DROPS for one page at a time, so this takes about half a minute.")),
      stepList(d.progress),
      h("p", { class: "patience" }, "You can leave this page open. It carries on by itself."),
      h("div", { class: "actions" }, h("button", { class: "btn quiet", type: "button", onclick: startAgain }, "Cancel")),
    );
  }

  function viewError(d) {
    const e = d.error || { message: "Something went wrong." };
    return h("div", { class: "stack" },
      h("div", { class: "stage-head" }, h("h1", { tabindex: "-1" }, "That did not work")),
      note("bad", e.message, null),
      stepList(d.progress),
      h("div", { class: "actions" }, h("button", { class: "btn", type: "button", onclick: startAgain }, "Try another link")),
    );
  }

  const MANUAL_WHY = {
    refused: "DROPS did not hand the pattern to the importer.",
    challenge: "DROPS wanted a human check, which the importer cannot do.",
    rate: "DROPS asked for a pause.",
    unavailable: "DROPS is not answering at the moment.",
    network: "The importer could not reach DROPS.",
    unexpected: "DROPS answered in an unexpected way.",
    host: "The importer was sent somewhere it is not allowed to go.",
    no_renderer: "This server cannot make the PDF itself.",
    unreadable: "The pages came back, but the pattern could not be read from them.",
    interrupted: "The importer was restarted part way through.",
    disabled: "Fetching from DROPS is switched off on this server.",
  };

  function viewManual(d) {
    const m = d.manual || {};
    const pdfV = d.verification.pdf;
    const pageV = d.verification.main_html;
    const canContinue = d.status === "ready";
    const patternLink = d.links && d.links.pattern;

    const openStep = patternLink
      ? h("li", {}, h("a", { href: patternLink, target: "_blank", rel: "noopener noreferrer" }, "Open the pattern on DROPS"), " in a new tab.")
      : h("li", {}, "Open the pattern on garnstudio.com.");

    const pdfTask = h("section", { class: `task${pdfV ? " done" : ""}`, "aria-labelledby": "t-pdf" },
      h("div", { class: "task-head" },
        h("span", { class: "task-mark" }, pdfV ? icon("tick") : "A"),
        h("h3", { id: "t-pdf" }, "Save the pattern as a PDF"),
        h("span", { class: "pill need" }, "Needed")),
      pdfV
        ? h("div", {}, h("p", { class: "file-line" }, pdfV.filename), checkList(pdfV.checks))
        : h("ol", { class: "how" },
          openStep,
          h("li", {}, "Press the ", h("strong", {}, "Print"), " button on the pattern page."),
          h("li", {}, "In the print window, set the destination to ", h("strong", {}, "Save as PDF"), ", then press Save."),
          h("li", {}, "Drop the saved file into the box below.")),
    );

    const pageTask = h("section", { class: `task${pageV ? " done" : ""}`, "aria-labelledby": "t-page" },
      h("div", { class: "task-head" },
        h("span", { class: "task-mark" }, pageV ? icon("tick") : "B"),
        h("h3", { id: "t-page" }, "Save the pattern page"),
        h("span", { class: "pill" }, "Recommended")),
      pageV
        ? h("div", {}, h("p", { class: "file-line" }, pageV.filename), checkList(pageV.checks))
        : h("div", {},
          h("ol", { class: "how" },
            h("li", {}, "Go back to the pattern page, not the print window."),
            h("li", {}, "Press ", h("strong", {}, "Ctrl+S"), " (", h("strong", {}, "Cmd+S"), " on a Mac)."),
            h("li", {}, "Choose ", h("strong", {}, "Webpage, HTML only"), " as the format. On Safari, choose ", h("strong", {}, "Page Source"), "."),
            h("li", {}, "Drop the saved file into the box below.")),
          h("p", { class: "why" }, "This adds the tags, categories and tutorial videos. You can skip it and add those by hand.")),
    );

    const fileInput = h("input", {
      type: "file", multiple: true, hidden: true, accept: ".pdf,.html,.htm,application/pdf,text/html",
      onchange: (e) => { upload([...e.target.files]); e.target.value = ""; },
    });
    const drop = h("button", {
      class: "drop", type: "button", "aria-busy": S.ui.uploading ? "true" : null,
      onclick: () => fileInput.click(),
      ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); },
      ondragleave: () => drop.classList.remove("over"),
      ondrop: (e) => { e.preventDefault(); drop.classList.remove("over"); upload([...e.dataTransfer.files]); },
    },
      h("span", { class: "big" }, S.ui.uploading ? "Checking your file…" : "Drop your files here"),
      h("span", { class: "small" }, S.ui.uploading ? "One moment." : "or choose them from your computer. You can drop both at once."));

    const rejects = S.ui.rejected.length
      ? h("div", { class: "rejects", role: "alert" }, S.ui.rejected.map((r) => {
        const v = r.verdict;
        return h("div", { class: "reject" },
          h("div", { class: "fname" }, r.filename),
          h("h3", {}, v.headline || "That file cannot be used"),
          checkList(v.checks),
          v.advice ? h("p", { class: "advice" }, v.advice) : null);
      }))
      : null;
    const problem = S.ui.problem ? note("bad", "The PDF was accepted, but the pattern could not be read from it", S.ui.problem) : null;

    const reason = MANUAL_WHY[m.code];
    const intro = m.code === "chosen"
      ? h("p", { class: "lede" }, "Save two files from the DROPS website, drop them below, and the importer checks each one for you.")
      : h("p", { class: "lede" }, "Nothing is wrong with your link. This way takes two minutes and works every time.");

    return h("div", { class: "stack" },
      h("div", { class: "stage-head" },
        h("h1", { tabindex: "-1" }, m.code === "chosen" ? "Add your own files" : "Let's get it the other way"),
        intro),
      reason ? note("warn", reason, null, technical(m.technical)) : (m.message ? note("warn", m.message, null, technical(m.technical)) : null),
      h("div", { class: "tasks" }, pdfTask, pageTask),
      fileInput, drop, rejects, problem,
      h("div", { class: "footer-actions" },
        h("div", { class: "actions" },
          h("button", { class: "btn quiet", type: "button", onclick: startAgain }, "Start again"),
          d.url ? h("button", { class: "btn ghost", type: "button", onclick: retryLink }, "Try the link again") : null),
        h("div", { class: "actions" },
          canContinue && !pageV ? h("span", { class: "lede" }, "Without the page, tags and videos are left out.") : null,
          h("button", { class: "btn", type: "button", disabled: !canContinue, onclick: () => { S.ui.continued = true; render(); } }, "Continue"))),
    );
  }

  async function upload(files) {
    if (!files.length || S.ui.uploading) return;
    S.ui.uploading = true; S.ui.rejected = []; S.ui.problem = ""; render(false);
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
    try {
      const d = await api("POST", `api/drafts/${S.draft.id}/files`, fd);
      S.ui.rejected = d.rejected || [];
      S.ui.problem = d.problem || "";
      setDraft(d);
    } catch (err) {
      S.ui.rejected = [{ filename: "", verdict: { headline: err.message, checks: [], advice: "" } }];
    }
    S.ui.uploading = false; render(false);
  }

  async function retryLink() {
    try { setDraft(await api("POST", `api/drafts/${S.draft.id}/retry`)); S.ui.rejected = []; S.ui.problem = ""; render(); }
    catch (err) { S.ui.rejected = [{ filename: "", verdict: { headline: err.message, checks: [], advice: "" } }]; render(false); }
  }

  async function startAgain() {
    const id = S.draft && S.draft.id;
    S.draft = null; store.clear();
    S.ui = { url: "", urlError: "", busy: false, continued: false, backToDetails: false, rejected: [], problem: "", uploading: false, textPreview: null };
    render();
    if (id) { try { await api("DELETE", `api/drafts/${id}`); } catch { /* it will be tidied up later */ } }
  }

  // ------------------------------------------------------------------ stage 2
  function chipField({ title, hint, kind, values, suggestions, onChange }) {
    const id = `f-${kind}`;
    let current = [...values];
    const input = h("input", { id, type: "text", autocomplete: "off", "aria-describedby": `${id}-hint`, placeholder: kind === "cat" ? "Add a category" : "Add a tag" });
    const wrap = h("div", { class: "chipfield", onclick: () => input.focus() });
    const sugg = h("div", { class: "suggest" });

    function commit(raw) {
      const parts = raw.split(",").map((s) => s.trim().replace(/\s+/g, " ")).filter(Boolean);
      if (!parts.length) return;
      for (const p of parts) if (!current.some((c) => c.toLowerCase() === p.toLowerCase())) current.push(p.slice(0, 60));
      input.value = "";
      changed();
    }
    function remove(value) { current = current.filter((c) => c !== value); changed(); }
    function changed() { onChange(current); paint(); }
    function paint() {
      wrap.replaceChildren(
        ...current.map((v) => h("span", { class: `chip ${kind}` }, v,
          h("button", { type: "button", "aria-label": `Remove ${v}`, onclick: (e) => { e.stopPropagation(); remove(v); } }, icon("close")))),
        input);
      const left = (suggestions || []).filter((s) => !current.some((c) => c.toLowerCase() === s.toLowerCase())).slice(0, 8);
      sugg.replaceChildren(...(left.length ? [h("span", {}, "In your library:"), ...left.map((s) => h("button", { type: "button", onclick: () => { commit(s); input.focus(); } }, s))] : []));
    }
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commit(input.value); }
      else if (e.key === "Backspace" && !input.value && current.length) { current = current.slice(0, -1); changed(); input.focus(); }
    });
    input.addEventListener("blur", () => commit(input.value));
    paint();
    return h("div", { class: "field" },
      h("label", { class: "field-name", for: id }, title),
      h("span", { class: "field-hint", id: `${id}-hint` }, hint),
      wrap, sugg);
  }

  function saveSoon(patch, delay = 500) {
    const key = Object.keys(patch)[0];
    clearTimeout(S.saveTimers[key]);
    Object.assign(S.draft.edits, patch);
    S.saveTimers[key] = setTimeout(() => flush(patch), delay);
  }
  async function flush(patch) {
    try { const d = await api("PATCH", `api/drafts/${S.draft.id}`, patch); S.draft.edits = d.edits; }
    catch { /* the next change or the Add button will send it again */ }
  }
  async function flushAll() {
    Object.values(S.saveTimers).forEach(clearTimeout);
    S.saveTimers = {};
    const e = S.draft.edits;
    await flush({ title: e.title, description: e.description, categories: e.categories, tags: e.tags, cover_page: e.cover_page });
  }

  function foundList(d) {
    const p = d.pattern, e = d.edits;
    const items = [];
    items.push({ state: "ok", label: "PDF saved", detail: `${p.page_count} page${p.page_count === 1 ? "" : "s"}` });
    const lines = p.sections.reduce((n, s) => n + s.lines, 0);
    items.push(lines > 15 ? { state: "ok", label: "Instructions read", detail: `${p.sections.length} sections` }
      : { state: "warn", label: "Instructions look short", detail: "Check the PDF to be sure nothing is missing." });
    items.push(p.sizes.length ? { state: "ok", label: "Sizes", detail: p.sizes.join(", ") } : { state: "warn", label: "No sizes found" });
    const yarnNames = [...new Set(p.yarn_options.flatMap((o) => o.components.map((c) => c.name)))];
    items.push(yarnNames.length ? { state: "ok", label: "Yarn", detail: yarnNames.join(", ") } : { state: "warn", label: "No yarn found" });
    if (p.diagram_pages.length) items.push({ state: "ok", label: "Charts and diagrams", detail: `page ${p.diagram_pages.join(", ")}` });
    else if (p.has_diagram_note) items.push({ state: "warn", label: "The pattern mentions diagrams, but none were found in the PDF" });
    if (p.has_main_page) {
      items.push({ state: p.videos.length ? "ok" : "warn", label: p.videos.length ? "Tutorial videos" : "No tutorial videos", detail: p.videos.length ? `${p.videos.length} linked` : "" });
      items.push({ state: e.tags.length ? "ok" : "warn", label: e.tags.length ? "Tags and categories" : "No tags found", detail: e.tags.length ? `${e.tags.length} tags, ${e.categories.length} categories` : "" });
    } else {
      items.push({ state: "warn", label: "No pattern page, so no video links", detail: "Tags were taken from the PDF only." });
    }
    (p.warnings || []).forEach((w) => items.push({ state: "warn", label: w }));
    (p.notes || []).forEach((n) => items.push({ state: "info", label: n }));
    const bad = items.filter((i) => i.state === "warn").length;
    return h("section", { class: "found", "aria-labelledby": "found-h" },
      h("h2", { id: "found-h" }, bad ? `Read, with ${bad} thing${bad === 1 ? "" : "s"} to look at` : "Everything was read"),
      h("ul", { class: "checks" }, items.map((i) => h("li", { class: i.state },
        h("span", { class: "ci" }, icon(i.state === "ok" ? "tick" : i.state === "warn" ? "warn" : "info")),
        h("div", {}, i.label, i.detail ? h("span", { class: "cd" }, ` ${i.detail}`) : null)))));
  }

  function viewCheck(d) {
    const p = d.pattern, e = d.edits;
    const cover = h("img", { alt: `Page ${e.cover_page} of the PDF`, src: `api/drafts/${d.id}/pages/${e.cover_page}.jpg`, width: 300, height: 424 });
    const caption = h("p", { class: "cover-cap" }, `Cover picture: page ${e.cover_page} of ${p.page_count}`);
    const thumbs = h("div", { class: "thumbs", role: "group", "aria-label": "Choose the cover picture" });
    const paintThumbs = () => thumbs.replaceChildren(...Array.from({ length: p.page_count }, (_, i) => {
      const n = i + 1;
      return h("button", { type: "button", "aria-pressed": String(n === e.cover_page), "aria-label": `Page ${n}`,
        onclick: () => { e.cover_page = n; cover.src = `api/drafts/${d.id}/pages/${n}.jpg`; cover.alt = `Page ${n} of the PDF`; caption.textContent = `Cover picture: page ${n} of ${p.page_count}`; paintThumbs(); saveSoon({ cover_page: n }, 200); } },
        h("img", { src: `api/drafts/${d.id}/pages/${n}.jpg`, alt: "", loading: "lazy", width: 54, height: 76 }));
    }));
    paintThumbs();

    const yarnNames = [...new Set(p.yarn_options.flatMap((o) => o.components.map((c) => c.name)))];
    const fact = (k, v) => (v ? h("div", {}, h("dt", {}, k), h("dd", {}, v)) : null);
    const side = h("aside", { class: "side", "aria-label": "Pattern pictures and facts" },
      h("div", { class: "cover-frame" }, cover), caption, thumbs,
      h("dl", { class: "facts" },
        fact("Pattern", [p.number, p.designer_id].filter(Boolean).join(", ")),
        fact("Sizes", p.sizes.join(", ")),
        fact("Yarn", yarnNames.join(", ")),
        fact("Needles", (p.needles || []).slice(0, 2).join(" ")),
        fact("Tension", (p.tension || [])[0]),
        fact("Videos", p.videos.length ? `${p.videos.length} tutorial videos` : "")));

    const title = h("input", { class: "input", id: "f-title", type: "text", value: e.title, maxlength: 200,
      oninput: (ev) => saveSoon({ title: ev.target.value }), onblur: (ev) => flush({ title: ev.target.value }) });
    const desc = h("textarea", { class: "input", id: "f-desc", maxlength: 2000,
      oninput: (ev) => saveSoon({ description: ev.target.value }), onblur: (ev) => flush({ description: ev.target.value }) });
    desc.value = e.description;

    const textBox = h("pre", {}, "Loading…");
    const peek = h("details", { class: "peek", ontoggle: async (ev) => {
      if (!ev.target.open || S.ui.textPreview) { if (S.ui.textPreview) textBox.textContent = S.ui.textPreview; return; }
      try { S.ui.textPreview = (await api("GET", `api/drafts/${d.id}/text`)).markdown; } catch (err) { S.ui.textPreview = err.message; }
      textBox.textContent = S.ui.textPreview;
    } }, h("summary", {}, "Preview the instructions text"), textBox);

    const form = h("div", { class: "stack" },
      S.ui.publishError ? note("bad", "It could not be added", S.ui.publishError) : null,
      foundList(d),
      h("div", { class: "field" },
        h("label", { class: "field-name", for: "f-title" }, "Title"), title),
      h("div", { class: "field" },
        h("label", { class: "field-name", for: "f-desc" }, "Description"),
        h("span", { class: "field-hint" }, "Shown at the top of the pattern in your library."), desc),
      chipField({ title: "Categories", kind: "cat", values: e.categories, suggestions: S.suggestions.categories,
        hint: "Broad groups that sort your library, like Women or Jumpers.", onChange: (v) => saveSoon({ categories: v }, 150) }),
      chipField({ title: "Tags", kind: "tag", values: e.tags, suggestions: S.suggestions.tags,
        hint: "Details you may want to search for, like raglan or English rib. Press Enter after each one.", onChange: (v) => saveSoon({ tags: v }, 150) }),
      peek,
      h("div", { class: "footer-actions" },
        h("button", { class: "btn quiet", type: "button", onclick: startAgain }, "Start again"),
        h("button", { class: "btn", type: "button", onclick: addToLibrary }, "Add to library")),
    );
    return h("div", {},
      h("div", { class: "stage-head" },
        h("h1", { tabindex: "-1" }, p.title || "Check the details"),
        h("p", { class: "lede" }, "Look over what the importer found. Change anything that is not right, then add it to your library.")),
      h("div", { class: "two" }, side, form));
  }

  async function addToLibrary(allowDuplicate = false) {
    const allow = allowDuplicate === true;
    try {
      await flushAll();
      S.ui.backToDetails = false;
      const d = await api("POST", `api/drafts/${S.draft.id}/publish`, { allow_duplicate: allow });
      setDraft(d);
    } catch (err) {
      S.ui.backToDetails = true;
      S.ui.publishError = err.message;
    }
    render();
  }

  // ------------------------------------------------------------------ stage 3
  function viewAdd(d) {
    const pub = d.publish || { steps: [], state: "running" };
    const title = (d.edits && d.edits.title) || (d.pattern && d.pattern.title) || "your pattern";
    if (pub.state === "duplicate") {
      const dups = pub.duplicates || { content: [], title: [] };
      const names = [...dups.content, ...dups.title].map((x) => x.title || x.id);
      return h("div", { class: "stack" },
        h("div", { class: "stage-head" }, h("h1", { tabindex: "-1" }, "You may already have this one")),
        note("warn", "Knitting Library found a match",
          dups.content.length ? "A pattern with the same file is already in your library." : "A pattern with the same title is already in your library.",
          h("ul", { class: "dupes" }, [...new Set(names)].map((n) => h("li", {}, n)))),
        h("div", { class: "footer-actions" },
          h("button", { class: "btn quiet", type: "button", onclick: backToDetails }, "Back to the details"),
          h("button", { class: "btn", type: "button", onclick: () => addToLibrary(true) }, "Add it anyway")));
    }
    if (pub.state === "error") {
      const e = pub.error || {};
      return h("div", { class: "stack" },
        h("div", { class: "stage-head" }, h("h1", { tabindex: "-1" }, "It stopped part way")),
        note("bad", e.message || "Something went wrong.", "What was already added is kept. Trying again carries on from where it stopped.", technical(e.technical)),
        stepList(pub.steps),
        h("div", { class: "footer-actions" },
          h("button", { class: "btn quiet", type: "button", onclick: backToDetails }, "Back to the details"),
          h("button", { class: "btn", type: "button", onclick: () => addToLibrary(false) }, "Try again")));
    }
    if (pub.state === "done") {
      return h("div", { class: "stack" },
        h("div", { class: "stage-head" },
          h("div", { class: "done-mark" }, icon("big_tick")),
          h("h1", { tabindex: "-1" }, "Added to your library"),
          h("p", { class: "lede" }, `${title} is ready to read.`)),
        stepList(pub.steps),
        h("div", { class: "actions" },
          h("a", { class: "btn", href: d.library_url || (S.status && S.status.library_url) || "/", target: "_blank", rel: "noopener noreferrer" }, "Open Knitting Library"),
          h("button", { class: "btn ghost", type: "button", onclick: startAgain }, "Add another pattern")));
    }
    return h("div", { class: "stack" },
      h("div", { class: "stage-head" },
        h("h1", { tabindex: "-1" }, "Adding to your library"),
        h("p", { class: "lede" }, "The PDF, the instructions and the cover picture all go in together.")),
      stepList(pub.steps));
  }

  function backToDetails() { S.ui.backToDetails = true; render(); }

  // ------------------------------------------------------------------ render and poll
  function setDraft(d) {
    const was = S.draft && S.draft.status;
    S.draft = { ...d };
    delete S.draft.accepted; delete S.draft.rejected; delete S.draft.problem;
    store.set(d.id);
    if (was === "working" && d.status === "ready" && d.mode === "auto" && !S.ui.continued) {
      setTimeout(() => { if (S.draft && S.draft.status === "ready") { S.ui.continued = true; render(); } }, 900);
    }
  }

  function busy(d) {
    return d && (d.status === "working" || (d.publish && d.publish.state === "running"));
  }

  function schedulePoll() {
    clearTimeout(S.timer);
    if (!busy(S.draft)) return;
    S.timer = setTimeout(async () => {
      try {
        const d = await api("GET", `api/drafts/${S.draft.id}`);
        const before = JSON.stringify([S.draft.status, S.draft.progress, S.draft.publish]);
        const wasEdits = S.draft.edits;
        setDraft(d);
        if (wasEdits && S.draft.status === "ready") S.draft.edits = wasEdits;
        const after = JSON.stringify([S.draft.status, S.draft.progress, S.draft.publish]);
        if (before !== after) render(false);
      } catch { /* try again on the next tick */ }
      schedulePoll();
    }, 1000);
  }

  function render(moveFocus = true) {
    const d = S.draft;
    const stage = stageOf(d);
    let view;
    if (stage === 3) view = viewAdd(d);
    else if (stage === 2) view = viewCheck(d);
    else if (!d) view = viewStart();
    else if (d.status === "working") view = viewWorking(d);
    else if (d.status === "manual" || d.status === "ready") view = viewManual(d);
    else if (d.status === "error") view = viewError(d);
    else view = viewStart();

    main.className = stage === 2 ? "wide" : "";
    main.replaceChildren(view);
    renderRail(stage);
    const changed = stage !== S.lastStage || (moveFocus && S.lastKey !== viewKey(d));
    S.lastStage = stage; S.lastKey = viewKey(d);
    if (moveFocus && changed) {
      const heading = main.querySelector("h1");
      if (heading) { heading.focus({ preventScroll: true }); window.scrollTo({ top: 0 }); }
    }
    schedulePoll();
  }
  function viewKey(d) { return d ? `${d.status}|${d.publish ? d.publish.state : ""}|${S.ui.continued}|${S.ui.backToDetails}` : "start"; }

  // ------------------------------------------------------------------ boot
  async function boot() {
    render(false);
    try { S.status = await api("GET", "api/status"); } catch { S.status = null; }
    renderStatus();
    api("GET", "api/suggestions").then((s) => { S.suggestions = s; }).catch(() => {});
    const id = store.get();
    if (id) {
      try {
        const d = await api("GET", `api/drafts/${id}`);
        if (d.status === "published" || (d.publish && d.publish.state === "done")) { store.clear(); }
        else { S.ui.continued = d.status === "ready"; setDraft(d); }
      } catch { store.clear(); }
    }
    if (S.status) renderStatus();
    render(false);
    setInterval(async () => {
      try { S.status = await api("GET", "api/status"); renderStatus(); } catch { /* ignore */ }
    }, 60000);
  }
  boot();
})();
