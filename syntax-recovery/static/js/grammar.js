(async function () {
  try {
    const g = await api("/api/grammar");
    document.getElementById("productions").textContent = g.productions.join("\n");
    const nulls = new Set(g.nullable);
    document.querySelector("#ff tbody").innerHTML = g.nonterminals.map(a =>
      `<tr><td class="mono">${esc(a)}</td><td>${nulls.has(a) ? "yes" : "no"}</td>` +
      `<td class="mono">${g.first[a].map(esc).join("  ")}</td><td class="mono">${g.follow[a].map(esc).join("  ")}</td></tr>`).join("");
    const t = g.table;
    document.getElementById("ll1").innerHTML =
      `<thead><tr><th></th>${t.terminals.map(x => `<th>${esc(x)}</th>`).join("")}</tr></thead><tbody>` +
      g.nonterminals.map(a => `<tr><td>${esc(a)}</td>${t.terminals.map(x => {
        const v = t.rows[a][x];
        return v === undefined ? "<td></td>" : v === "synch" ? `<td class="synch">synch</td>` : `<td>${esc(v)}</td>`;
      }).join("")}</tr>`).join("") + "</tbody>";
    if (t.resolved.length) {
      document.getElementById("resolved").textContent =
        "Conflict resolved by rule: " + t.resolved.map(r => `M[${r.nonterminal}, ${r.token}] takes the non-empty production (dangling else attaches to the nearest if)`).join("; ") + ".";
    }
  } catch (e) {
    document.getElementById("productions").textContent = e.message;
  }
})();
