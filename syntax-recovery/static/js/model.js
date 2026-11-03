(async function () {
  const intro = document.getElementById("intro");
  try {
    const m = await api("/api/model");
    if (!m.trained) {
      intro.textContent = "The Isolation Forest has not been trained. Run python -m compiler.train before using model-assisted recovery.";
      return;
    }
    const s = m.summary, meta = s.meta;
    intro.textContent =
      "An Isolation Forest is trained on local token windows from valid programs. At a syntax error, the parser proposes grammar-valid repairs and the forest ranks them by how typical each repaired window looks. The grammar validity gate remains authoritative; operands are never invented.";
    const show = id => document.getElementById(id).hidden = false;
    document.getElementById("facts").innerHTML = [
      ["Valid training programs", meta.train_programs],
      ["Generated programs", meta.generated_programs],
      ["Hand-written programs", meta.hand_written_programs],
      ["Training token windows", s.training_windows],
      ["Features per window", s.features],
      ["Isolation trees", s.n_estimators],
      ["Held-out programs", `${meta.dev_programs} reserved for validation, ${meta.test_programs} for testing`],
    ].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
    show("stats");
    document.getElementById("params").innerHTML = Object.entries(m.params)
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
    show("parts");
  } catch (e) { intro.textContent = e.message; }
})();
