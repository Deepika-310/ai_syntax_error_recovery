(function () {
  const $ = id => document.getElementById(id);
  const ta = $("source"), backdrop = $("backdrop"), gutter = $("gutter");
  const S = { result: null, applied: {}, step: -1, stepMode: false, src: "", jump: {} };

  /* ---------- editor ---------- */
  function lineStarts(text) {
    const starts = [0];
    for (let i = 0; i < text.length; i++) if (text[i] === "\n") starts.push(i + 1);
    return starts;
  }
  function offsetOf(text, line, col) {
    const st = lineStarts(text);
    return (st[line - 1] ?? text.length) + col - 1;
  }
  // The range to underline for an error reported at line:col.
  function errorRange(text, e) {
    const off = offsetOf(text, e.line, e.col);
    const tok = e.current_token === "$" ? "" : e.current_token;
    if (tok && text.substr(off, tok.length) === tok) return [off, off + tok.length];
    return off > 0 ? [off - 1, off] : [0, Math.min(1, text.length)];
  }
  function finalKind(e) {
    if (e.status === "unrecoverable") return "bad";
    if (e.ambiguous || e.status === "recovered by panic mode") return "warn";
    return "ok";
  }
  const GLYPH = { err: "●", ok: "✓", warn: "▲", bad: "✕" };

  // Which marks to show right now (all final marks, or only those reached in step mode).
  function currentMarks() {
    const r = S.result;
    if (!r) return [];
    const marks = [];
    r.errors.forEach(e => {
      let kind = finalKind(e);
      if (S.stepMode) {
        const j = S.jump[e.id];
        if (!j || S.step < j.error) return;
        if (S.step < j.recovery) kind = "err";
      }
      marks.push({ id: e.id, line: e.line, range: errorRange(S.src, e), kind, title: `Error ${e.id}: ${e.problem}` });
    });
    (r.lexical_errors || []).forEach(l => {
      const off = offsetOf(S.src, l.line, l.col);
      marks.push({ id: null, line: l.line, range: [off, off + 1], kind: "err", title: l.message });
    });
    return marks;
  }

  function render() {
    const text = ta.value;
    const marks = S.result && text === S.src ? currentMarks() : [];
    let cur = null;
    if (S.stepMode && S.result && text === S.src && S.step >= 0) {
      const row = S.result.trace[S.step];
      const first = (row.input.split(" ")[0] || "");
      const off = offsetOf(text, row.line, row.col);
      cur = { range: [off, off + Math.max(first === "$" ? 0 : first.length, 0)], line: row.line };
    }
    // backdrop: text with underline marks
    const spans = marks.map(m => ({ s: m.range[0], e: Math.max(m.range[1], m.range[0] + 1), cls: m.kind }))
      .concat(cur && cur.range[1] > cur.range[0] ? [{ s: cur.range[0], e: cur.range[1], cls: "cur" }] : [])
      .sort((a, b) => a.s - b.s);
    let html = "", pos = 0;
    spans.forEach(sp => {
      if (sp.s < pos) return;
      html += esc(text.slice(pos, sp.s)) + `<mark class="${sp.cls}">${esc(text.slice(sp.s, sp.e))}</mark>`;
      pos = sp.e;
    });
    html += esc(text.slice(pos)) + "\n";
    backdrop.innerHTML = html;
    // gutter: line numbers and markers
    const n = text.split("\n").length;
    const byLine = {};
    marks.forEach(m => { (byLine[m.line] = byLine[m.line] || []).push(m); });
    let g = "";
    for (let i = 1; i <= n; i++) {
      const btns = (byLine[i] || []).map(m =>
        `<button type="button" class="mk-${m.kind}" data-err="${m.id ?? ""}" title="${esc(m.title)}" aria-label="${esc(m.title)}">${GLYPH[m.kind]}</button>`).join("");
      g += `<div class="gl${cur && cur.line === i ? " cur" : ""}">${btns}<span>${i}</span></div>`;
    }
    gutter.innerHTML = g;
    syncScroll();
  }
  function syncScroll() {
    backdrop.scrollTop = ta.scrollTop; backdrop.scrollLeft = ta.scrollLeft;
    gutter.scrollTop = ta.scrollTop;
  }
  ta.addEventListener("scroll", syncScroll);
  ta.addEventListener("input", () => {
    if (S.result && ta.value !== S.src) {
      S.result = null; S.applied = {}; S.stepMode = false; S.step = -1;
      $("summary").textContent = "The source changed. Press Analyze to see the results.";
      clearPanels();
    }
    render();
  });
  gutter.addEventListener("click", ev => {
    const b = ev.target.closest("button[data-err]");
    if (b && b.dataset.err) jumpToError(Number(b.dataset.err));
  });

  function jumpToError(id) {
    const e = S.result && S.result.errors.find(x => x.id === id);
    if (!e) return;
    const [s, en] = errorRange(S.src, e);
    ta.focus();
    ta.setSelectionRange(s, en);
    const line = e.line - 1;
    ta.scrollTop = Math.max(0, line * 21 - ta.clientHeight / 2);
    syncScroll();
    selectTab("errors");
    const card = $("err-" + id);
    if (card) card.scrollIntoView({ block: "nearest" });
  }

  /* ---------- tabs ---------- */
  const TABS = ["errors", "tokens", "trace", "recovered", "tree", "compare", "metrics"];
  function selectTab(name) {
    TABS.forEach(t => {
      $("tab-" + t).setAttribute("aria-selected", String(t === name));
      $("panel-" + t).hidden = t !== name;
    });
  }
  TABS.forEach((t, i) => {
    const b = $("tab-" + t);
    b.addEventListener("click", () => selectTab(t));
    b.addEventListener("keydown", ev => {
      const d = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
      if (!d) return;
      const next = TABS[(i + d + TABS.length) % TABS.length];
      selectTab(next); $("tab-" + next).focus();
    });
  });
  function clearPanels() {
    TABS.forEach(t => { $("panel-" + t).innerHTML = ""; });
  }

  /* ---------- results ---------- */
  function sourceLine(e) {
    const line = S.src.split("\n")[e.line - 1] ?? "";
    return `<pre class="srcline">${esc(line)}\n${" ".repeat(Math.max(0, e.col - 1))}^</pre>`;
  }
  function statusClass(e) {
    return { ok: "status-ok", warn: "status-warn", bad: "status-bad" }[finalKind(e)];
  }
  function renderSummary(r) {
    const m = r.metrics;
    let t = m.detected === 0 ? "No syntax errors." :
      `${m.detected} error${m.detected === 1 ? "" : "s"} · ${m.recovered} recovered · ${m.panic_recoveries} by panic mode · ${m.unrecoverable} unrecoverable`;
    if (m.ambiguous) t += ` · ${m.ambiguous} ambiguous`;
    if (r.lexical_errors.length) t += ` · ${r.lexical_errors.length} illegal character${r.lexical_errors.length === 1 ? "" : "s"}`;
    $("summary").textContent = t;
  }
  function candidateTable(e) {
    const valid = e.candidates.filter(c => c.valid);
    const failed = e.candidates.length - valid.length;
    const maxCont = Math.max(...valid.map(c => c.continuation), 0);
    const rows = valid.map(c => {
      const act = c.chosen ? (e.forced ? "chosen by you" : (e.ambiguous ? "applied" : "applied")) :
        `<button type="button" data-apply="${esc(c.key)}" data-err="${e.id}">Use this</button>`;
      return `<tr class="${c.chosen ? "chosen" : ""}"><td>${esc(c.label)}${c.suggestion_only ? ' <span class="tag">needs a value</span>' : ""}</td>` +
        `<td class="num">${c.cost}</td><td class="num">${c.anomaly_score === null ? "–" : c.anomaly_score}</td><td class="num">${c.rank_score}</td><td class="num">${c.prob === null ? "–" : (c.prob * 100).toFixed(1) + "%"}</td>` +
        `<td class="num">${c.continuation >= 12 ? "12+" : c.continuation}${c.continuation === maxCont && valid.length > 1 ? " ★" : ""}</td><td>${act}</td></tr>`;
    }).join("");
    return `<details${e.ambiguous ? " open" : ""}><summary>Candidates (${valid.length})</summary>` +
      `<div class="scroll"><table><thead><tr><th>Fix</th><th class="num">Edit cost</th><th class="num">Anomaly score</th><th class="num">Rank score</th><th class="num">Relative confidence</th><th class="num">Parses on for</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` +
      `<p class="note">Lower rank scores win; rank combines the Isolation Forest anomaly score with the edit-cost adjustment. Confidence compares candidates for this error only and is not calibrated. ★ parses the furthest. ${failed} other candidate${failed === 1 ? "" : "s"} failed the grammar check. "Needs a value" fixes insert an identifier or number, so they are never applied automatically.</p></details>`;
  }
  function errorCard(e) {
    const modelTag = e.model_changed ? ' <span class="tag model" title="The Isolation Forest ranked this fix above the edit-cost baseline">Isolation Forest changed the pick</span>' : "";
    return `<article class="err" id="err-${e.id}"><h3>Error ${e.id} <span class="where">line ${e.line}, column ${e.col}</span> ${esc(e.problem)}${modelTag}</h3>` +
      sourceLine(e) +
      `<dl class="kv"><dt>Found</dt><dd class="mono">${esc(e.unexpected)}</dd>` +
      `<dt>Expected</dt><dd class="mono">${e.expected.map(esc).join(" / ")}</dd>` +
      (e.also_valid.length ? `<dt>Also valid</dt><dd class="mono">${e.also_valid.map(esc).join(" ")}</dd>` : "") +
      `<dt>Action</dt><dd>${esc(e.detail)}</dd>` +
      `<dt>Status</dt><dd class="${statusClass(e)}">${esc(e.status)}</dd></dl>` +
      (e.ambiguous ? `<p class="ambig">Several fixes fit and none is clearly best, so none was applied. Choose one below to apply it.</p>` : "") +
      (e.candidates.length ? candidateTable(e) : "") +
      `<details><summary>Recovery log</summary><dl class="kv">` +
      `<dt>Parser state</dt><dd class="mono">${esc(e.parser_state)}${e.synch_entry ? " (synch entry)" : ""} on top of the stack</dd>` +
      `<dt>Stack (top first)</dt><dd class="mono">${esc(e.stack.join(" "))}</dd>` +
      `<dt>Strategy</dt><dd>${esc(e.strategy || "none")}${e.fell_back ? " (fell back to panic mode)" : ""}</dd>` +
      `<dt>Inserted</dt><dd class="mono">${e.tokens_inserted.map(esc).join(" ") || "none"}</dd>` +
      `<dt>Deleted or skipped</dt><dd class="mono">${e.tokens_deleted.map(esc).join(" ") || "none"}</dd>` +
      `<dt>Replaced</dt><dd class="mono">${e.tokens_replaced.map(t => esc(t.from) + " → " + esc(t.to)).join(", ") || "none"}</dd>` +
      `<dt>Sync token</dt><dd class="mono">${esc(e.sync_token || "none")}</dd>` +
      `<dt>Resumes at</dt><dd>${e.resume ? `line ${e.resume.line}, column ${e.resume.col} (${esc(e.resume.token)})` : "not resumed"}</dd>` +
      `<dt>Decision model</dt><dd>${e.candidates.some(c => c.anomaly_score !== null) ? "Isolation Forest anomaly ranking" : "Edit-cost fallback (model not trained)"}</dd>` +
      `<dt>Edit cost</dt><dd>${e.cost}</dd></dl></details></article>`;
  }
  function renderErrors(r) {
    let h = r.lexical_errors.map(l => `<p class="err status-warn">Line ${l.line}, column ${l.col}: ${esc(l.message)} (ignored by the lexer)</p>`).join("");
    h += r.errors.length ? r.errors.map(errorCard).join("") : `<p>The program is valid. The parser accepted it without any recovery.</p>`;
    if (!r.completed) h += `<p class="note">The parser stopped before the end of the program.</p>`;
    $("panel-errors").innerHTML = h;
  }
  function renderTokens(r) {
    $("panel-tokens").innerHTML = `<div class="scroll tall"><table><thead><tr><th>Lexeme</th><th>Token</th><th>Line</th><th>Col</th></tr></thead><tbody>` +
      r.tokens.map(t => `<tr><td class="mono">${esc(t.lexeme)}</td><td class="mono">${esc(t.text)}</td><td class="num">${t.line}</td><td class="num">${t.col}</td></tr>`).join("") +
      `</tbody></table></div>`;
  }
  function renderTrace(r) {
    $("panel-trace").innerHTML =
      `<div class="stepbar"><button type="button" id="prev">Previous</button><button type="button" id="next">Next</button>` +
      `<span id="stepinfo"></span></div>` +
      `<div class="scroll tall" id="tracebox"><table class="trace"><thead><tr><th class="num">Step</th><th>Stack (bottom → top)</th><th>Remaining input</th><th>Action</th></tr></thead><tbody>` +
      r.trace.map((t, i) => `<tr class="${t.kind}" id="tr-${i}"><td class="num">${t.step}</td><td class="mono stack">${esc(t.stack)}</td><td class="mono">${esc(t.input)}</td><td>${esc(t.action)}</td></tr>`).join("") +
      `</tbody></table></div>`;
    $("prev").onclick = () => gotoStep(S.step - 1);
    $("next").onclick = () => gotoStep(S.step + 1);
    updateStepUI();
  }
  function updateStepUI() {
    const r = S.result;
    if (!r || !$("stepinfo")) return;
    $("stepinfo").textContent = S.stepMode ? `Step ${S.step + 1} of ${r.trace.length}` : `${r.trace.length} steps`;
    $("prev").disabled = !S.stepMode || S.step <= 0;
    $("next").disabled = !S.stepMode || S.step >= r.trace.length - 1;
    r.trace.forEach((_, i) => {
      const tr = $("tr-" + i);
      tr.classList.toggle("current", S.stepMode && i === S.step);
      tr.classList.toggle("future", S.stepMode && i > S.step);
    });
    if (S.stepMode && $("tr-" + S.step)) $("tr-" + S.step).scrollIntoView({ block: "nearest" });
  }
  function buildJumps(r) {
    S.jump = {};
    let n = 0;
    r.trace.forEach((t, i) => {
      if (t.kind === "error") { n++; S.jump[n] = { error: i, recovery: i + 1 }; }
      if (t.kind === "recovery" && S.jump[n]) S.jump[n].recovery = i;
    });
    r.errors.forEach(e => { if (!S.jump[e.id]) S.jump[e.id] = { error: 0, recovery: 0 }; });
  }
  function gotoStep(i) {
    const r = S.result;
    if (!r) return;
    S.step = Math.max(0, Math.min(r.trace.length - 1, i));
    updateStepUI();
    render();
  }
  function enterStep() {
    S.stepMode = true; S.step = 0;
    selectTab("trace");
    updateStepUI(); render();
    $("step").textContent = "Exit step-through";
  }
  function exitStep() {
    S.stepMode = false; S.step = -1;
    $("step").textContent = "Step through";
    updateStepUI(); render();
  }

  function diffPanes(src, edits) {
    const ops = edits.map((e, i) => ({ ...e, i })).sort((a, b) => a.offset - b.offset || a.i - b.i);
    let o = "", n = "", cur = 0;
    for (const op of ops) {
      if (op.offset < cur) continue;
      const plain = esc(src.slice(cur, op.offset));
      o += plain; n += plain;
      const t = src.substr(op.offset, op.length || 0);
      if (op.kind === "insert") { o += '<span class="at"></span>'; n += `<ins>${esc(op.text)}</ins>`; cur = op.offset; }
      else if (op.kind === "delete") { o += `<del>${esc(t)}</del>`; cur = op.offset + op.length; }
      else if (op.kind === "replace") { o += `<del>${esc(t)}</del>`; n += `<ins class="rep">${esc(op.text)}</ins>`; cur = op.offset + op.length; }
      else { o += `<span class="skip">${esc(t)}</span>`; n += `<span class="skip">${esc(t)}</span>`; cur = op.offset + op.length; }
    }
    const rest = esc(src.slice(cur));
    return [o + rest, n + rest];
  }
  function renderRecovered(r) {
    const [o, n] = diffPanes(S.src, r.edits);
    $("panel-recovered").innerHTML =
      `<div class="cols"><div><h3>Original</h3><pre class="code">${o}</pre></div><div><h3>Recovered</h3><pre class="code">${n}</pre></div></div>` +
      `<p class="keyline"><ins style="background:var(--ins-bg);text-decoration:none">inserted</ins> · <ins style="background:var(--rep-bg);text-decoration:none">replaced</ins> · <del style="background:var(--del-bg)">removed</del> · <span style="background:var(--rep-bg)">skipped by panic mode, left as written</span></p>` +
      `<p class="note">The parser never invents an identifier or a number. A statement it could not fix locally is skipped, not rewritten, so the recovered code can still contain it.</p>`;
  }
  function treeHtml(n) {
    const skipped = n.skipped ? ` <span class="miss">skipped: ${esc(n.skipped.join(" "))}</span>` : "";
    if (n.error) return `<li><span class="miss">${esc(n.label || "<missing>")}</span>${skipped}</li>`;
    if (!n.children.length) {
      if (n.text !== undefined) {
        const shown = (n.sym === "id" || n.sym === "num") ? `${n.sym}: ${n.text}` : n.sym;
        const note = n.inserted ? ' <span class="ins">(inserted)</span>' : n.replaced_from ? ` <span class="ins">(replaced ${esc(n.replaced_from)})</span>` : "";
        return `<li><span class="t">${esc(shown)}</span>${note}${skipped}</li>`;
      }
      if (n.prod === "ε") return "";
      return skipped ? `<li>${esc(n.sym)}${skipped}</li>` : "";
    }
    const kids = n.children.map(treeHtml).join("");
    return `<li>${esc(n.sym)}${skipped}${kids ? `<ul>${kids}</ul>` : ""}</li>`;
  }
  function renderTree(r) {
    $("panel-tree").innerHTML = `<div class="treebox"><ul class="tree">${treeHtml(r.tree)}</ul></div>` +
      `<p class="note">Amber entries mark where recovery removed or skipped part of the program.</p>`;
  }
  function renderMetrics(r) {
    const m = r.metrics;
    $("panel-metrics").innerHTML = `<dl class="kv">` +
      [["Errors detected", m.detected], ["Recovered", m.recovered], ["Recovery rate", fmt(m.recovery_rate, "%")],
       ["Recovered by panic mode", m.panic_recoveries], ["Ambiguous (nothing applied)", m.ambiguous],
       ["Edits (inserted, deleted, replaced)", m.edit_count], ["Tokens skipped before resuming", m.resume_distance],
       ["Parsed to the end", m.parse_completed ? "yes" : "no"], ["Response time", m.response_ms + " ms"]]
        .map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("") + `</dl>` +
      `<p class="note">Detection rate, false-error counts and parse completion over the stored programs are on the <a href="/evaluation">Evaluation</a> page.</p>`;
  }
  function renderCompareIdle() {
    $("panel-compare").innerHTML = `<p>Run every recovery strategy on the current program and compare them.</p><button type="button" id="runCompare">Compare strategies</button><div id="cmpOut"></div>`;
    $("runCompare").onclick = async () => {
      const out = $("cmpOut");
      out.textContent = "Running…";
      try {
        const d = await api("/api/compare", { source: ta.value });
        out.innerHTML = `<div class="scroll"><table><thead><tr><th>Strategy</th><th class="num">Errors</th><th class="num">Recovered</th><th class="num">Edits</th><th class="num">Skipped</th><th class="num">Extra</th><th>Parsed to end</th></tr></thead><tbody>` +
          d.rows.map(x => `<tr><td>${esc(x.label)}</td><td class="num">${x.errors}</td><td class="num">${x.recovered}</td><td class="num">${x.edits}</td><td class="num">${x.skipped}</td><td class="num">${x.extra_errors}</td><td>${x.completed ? "yes" : "no"}</td></tr>`).join("") +
          `</tbody></table></div><p class="note">Extra = errors reported beyond the lowest count any strategy reports for this program. Extra errors usually come from one mistake setting off later ones.</p>`;
      } catch (e) { out.textContent = e.message; }
    };
  }

  /* ---------- actions ---------- */
  async function run(keepApplied) {
    if (!keepApplied) S.applied = {};
    const src = ta.value;
    $("status").textContent = "";
    $("analyze").disabled = true;
    try {
      const r = await api("/api/analyze", { source: src, strategy: $("strategy").value, apply: S.applied });
      S.result = r; S.src = src; S.stepMode = false; S.step = -1;
      $("step").textContent = "Step through";
      buildJumps(r);
      renderSummary(r); renderErrors(r); renderTokens(r); renderTrace(r);
      renderRecovered(r); renderTree(r); renderMetrics(r); renderCompareIdle();
      render();
    } catch (e) {
      $("status").textContent = e.message;
    }
    $("analyze").disabled = false;
  }
  $("analyze").addEventListener("click", () => run(false));
  $("step").addEventListener("click", async () => {
    if (S.stepMode) return exitStep();
    if (!S.result || ta.value !== S.src) await run(false);
    if (S.result) enterStep();
  });
  $("reset").addEventListener("click", () => loadExample(true));
  $("panel-errors").addEventListener("click", ev => {
    const b = ev.target.closest("button[data-apply]");
    if (!b) return;
    S.applied[b.dataset.err] = b.dataset.apply;
    run(true);
  });
  $("panel-errors").addEventListener("click", ev => {
    const card = ev.target.closest(".err");
    if (card && !ev.target.closest("button, summary, a, table")) jumpToError(Number(card.id.replace("err-", "")));
  });

  /* ---------- setup ---------- */
  let examples = [];
  function loadExample(reset) {
    const idx = reset ? 0 : Number($("example").value);
    if (reset) $("example").value = "0";
    ta.value = (examples[idx] || { source: "" }).source;
    S.result = null; S.applied = {}; S.stepMode = false; S.step = -1;
    $("step").textContent = "Step through";
    $("summary").textContent = "Press Analyze to see the results.";
    $("status").textContent = "";
    clearPanels(); render();
  }
  $("example").addEventListener("change", () => loadExample(false));
  (async function init() {
    try {
      const [ex, st] = await Promise.all([api("/api/examples"), api("/api/strategies")]);
      examples = ex;
      $("example").innerHTML = ex.map((e, i) => `<option value="${i}">${esc(e.name)}</option>`).join("");
      $("strategy").innerHTML = st.map(s => `<option value="${s.key}">${esc(s.label)}</option>`).join("");
      // start on the four-error example
      const start = ex.findIndex(e => e.name === "Four errors");
      $("example").value = String(start >= 0 ? start : 0);
      loadExample(false);
      await run(false);
    } catch (e) { $("status").textContent = e.message; }
  })();
})();
