(function () {
  const pct = v => (v === undefined || v === null ? "–" : v + "%");
  function renderCases(d) {
    const s = d.summary;
    document.getElementById("caseSummary").textContent =
      `${s.passed} of ${s.count} programs give the expected result. ${s.detected} errors found, ${s.expected} expected; ` +
      `recovery rate ${pct(s.recovery_rate)}, false errors ${s.false_errors}, mean time ${s.mean_ms} ms.`;
    document.querySelector("#cases tbody").innerHTML = d.cases.map(c => {
      const r = c.result;
      return `<tr><td>${esc(c.name)}${c.note ? `<br><span class="note">${esc(c.note)}</span>` : ""}</td>` +
        `<td class="num">${r.detected}</td><td class="num">${r.expected}</td>` +
        `<td class="${r.passed ? "pass" : "fail"}">${r.passed ? "pass" : "fail"}${r.passed ? "" : "<br><span class='note'>" + esc(r.problems.join("; ")) + "</span>"}</td></tr>`;
    }).join("");
  }
  function renderSplit(e) {
    if (!e.available && e.available !== undefined) {
      document.getElementById("splitNote").textContent = "No evaluation has been run yet. Run python -m compiler.evaluation.";
      return;
    }
    const a = e.test.baseline.overall, b = e.test.isolation_forest.overall;
    document.getElementById("splitNote").textContent =
      `${a.cases} programs with one injected error (one token deleted, added, replaced or duplicated). ` +
      `The programs were not used for training or tuning. The original program is the correct answer.`;
    const rows = [
      ["Fixed automatically and correctly", a.auto_restored, b.auto_restored],
      ["Best-ranked suggestion is correct", a.top1, b.top1],
      ["Correct fix within the top 3", a.top3, b.top3],
      ["Flagged ambiguous (nothing applied)", a.ambiguous, b.ambiguous],
      ["Applied, but not the original", a.wrong_apply, b.wrong_apply],
    ];
    document.querySelector("#splitTable tbody").innerHTML = rows.map(r =>
      `<tr><td>${r[0]}</td><td class="num">${pct(r[1])}</td><td class="num">${pct(r[2])}</td></tr>`).join("") +
      `<tr><td>Extra errors reported per program</td><td class="num">${a.mean_cascading}</td><td class="num">${b.mean_cascading}</td></tr>`;
    const kinds = { insert: "Extra token", delete: "Deleted token", replace: "Wrong token", duplicate: "Duplicated token", swap: "Two tokens swapped" };
    const ra = e.test.baseline.by_kind, rb = e.test.isolation_forest.by_kind;
    document.querySelector("#kindTable tbody").innerHTML = Object.keys(kinds).filter(k => rb[k]).map(k =>
      `<tr><td>${kinds[k]}</td><td class="num">${rb[k].cases}</td><td class="num">${pct(ra[k].auto_restored)}</td><td class="num">${pct(rb[k].auto_restored)}</td></tr>`).join("");
    document.getElementById("kindNote").textContent =
      "Swapped tokens take two edits to undo, which insert, delete, replace and skip cannot do in one step, so they are shown here but left out of the figures above. " +
      `Isolation Forest settings: temperature = ${e.params.isolation_forest.temperature}, tau = ${e.params.isolation_forest.tau}, delta = ${e.params.isolation_forest.delta}, edit-cost adjustment = ${e.params.isolation_forest.cost_weight}.`;
  }
  async function load() {
    try { renderCases(await api("/api/testcases")); } catch (e) { document.getElementById("caseSummary").textContent = e.message; }
    try { renderSplit(await api("/api/evaluation")); } catch (e) { document.getElementById("splitNote").textContent = e.message; }
  }
  document.getElementById("rerun").addEventListener("click", async () => {
    const st = document.getElementById("rerunStatus"), btn = document.getElementById("rerun");
    btn.disabled = true; st.textContent = "Running…";
    try { renderSplit(await api("/api/evaluate", {})); await load(); st.textContent = "Done."; }
    catch (e) { st.textContent = e.message; }
    btn.disabled = false;
  });
  load();
})();
