/* Фабрика гипотез — SPA поверх gateway API. */
const API = (window.HF_API || `http://${location.hostname}:8000`) + "/api/v1";

const $ = (sel) => document.querySelector(sel);
let plants = [];        // [{plant, engine, summary, hypotheses_count}]
let current = null;     // выбранная фабрика
const fmtT = (v) => (v == null ? "—" : Math.round(v).toLocaleString("ru-RU"));

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

async function loadPlants() {
  plants = await api("/plants");
  renderTabs();
  if (plants.length && !plants.find((p) => p.plant === current))
    current = plants[0].plant;
  if (current) renderPlant();
}

function renderTabs() {
  const nav = $("#tabs");
  nav.innerHTML = "";
  for (const p of plants) {
    const b = document.createElement("button");
    b.className = "tab" + (p.plant === current ? " active" : "");
    b.textContent = p.plant;
    b.onclick = () => { current = p.plant; renderTabs(); renderPlant(); };
    nav.appendChild(b);
  }
}

async function runPipeline() {
  const btn = $("#run-btn");
  btn.disabled = true;
  $("#run-status").textContent = "Конвейер работает (парсинг → диагностика → генерация)…";
  try {
    const useLlm = $("#use-llm").checked;
    await api(`/runs?use_llm=${useLlm}`, { method: "POST" });
    $("#run-status").textContent = "Готово";
    await loadPlants();
  } catch (e) {
    $("#run-status").textContent = "Ошибка: " + e.message;
  } finally {
    btn.disabled = false;
  }
}

async function vote(category, v) {
  await api("/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category, vote: v }),
  });
  await renderPlant(); // приоритеты пересчитаны на сервере
}

function statCard(label, value) {
  return `<div class="stat"><div class="v">${value}</div><div class="l">${label}</div></div>`;
}

function heatmap(cells) {
  if (!cells || !cells.length) return "";
  const classes = [...new Set(cells.map((c) => c.cls))];
  const streams = [...new Set(cells.map((c) => c.stream))];
  const sum = (st, cls) => cells.filter((c) => c.stream === st && c.cls === cls)
    .reduce((a, c) => a + c.tons, 0);
  const max = Math.max(...streams.flatMap((st) => classes.map((cl) => sum(st, cl))), 1);
  let html = `<table class="heat"><tr><th>Поток \\ класс, мкм</th>` +
    classes.map((c) => `<th>${c}</th>`).join("") + "</tr>";
  for (const st of streams) {
    html += `<tr><th style="text-align:left">${st}</th>` + classes.map((cl) => {
      const v = sum(st, cl);
      const a = v / max;
      return `<td style="background:rgba(227,72,109,${(0.65 * a).toFixed(2)})">${fmtT(v)}</td>`;
    }).join("") + "</tr>";
  }
  return html + "</table><p class='engine'>Потери Ni+Cu, т (по ячейкам отчёта)</p>";
}

function hypCard(h) {
  const s = h.scores, eff = h.expected_effect;
  const ev = h.evidence.map((e) =>
    `<li>${e.fact}<div class="src">— ${e.source}</div></li>`).join("");
  const llm = h.status.startsWith("llm") ? `<span class="badge llm">LLM</span>` : "";
  return `<div class="hyp">
    <div class="head"><h3>${h.rank}. ${h.title}</h3>
      <span class="prio">приоритет ${s.priority}</span></div>
    <div class="badges">
      <span class="badge">${h.category_ru}</span>${llm}
      <span class="badge">эффект ${fmtT(s.impact_t)} т</span>
      <span class="badge">реализуемость ${s.feasibility}/5</span>
      <span class="badge">новизна ${s.novelty}/5</span>
      <span class="badge">риск ${s.risk}/5</span>
      ${h.streams.map((x) => `<span class="badge">${x}</span>`).join("")}
    </div>
    <p class="statement">${h.hypothesis}</p>
    <p><b>Механизм.</b> ${h.mechanism}</p>
    <details open><summary>Обоснование и источники (${h.evidence.length})</summary>
      <ul class="evidence">${ev}</ul></details>
    <details><summary>Ожидаемый KPI</summary>
      <p>Ni −${fmtT(eff.kpi_delta_t.ni[0])}…${fmtT(eff.kpi_delta_t.ni[1])} т,
         Cu −${fmtT(eff.kpi_delta_t.cu[0])}…${fmtT(eff.kpi_delta_t.cu[1])} т.
         ${eff.assumption}</p></details>
    <details><summary>Риски</summary>
      <ul class="risks">${h.risks.map((r) => `<li>${r}</li>`).join("")}</ul></details>
    <details><summary>Дорожная карта проверки</summary>
      <ol class="roadmap">${h.roadmap.map((r) => `<li>${r}</li>`).join("")}</ol></details>
    <div class="fb">
      <button class="ghost" onclick="vote('${h.categories[0]}','up')">👍</button>
      <button class="ghost" onclick="vote('${h.categories[0]}','down')">👎</button>
      <span>оценка эксперта сдвигает приоритет категории «${h.category_ru}»
        (feedback_adj: ${s.feedback_adj ?? 0})</span>
    </div>
  </div>`;
}

function knowledgeGraph(result) {
  const nodes = [], edges = [], seen = new Set();
  const add = (id, label, group) => {
    if (!seen.has(id)) { seen.add(id); nodes.push({ id, label, group }); }
  };
  for (const f of result.findings.filter((f) => !f.informational)) {
    add("f:" + f.id, f.title.slice(0, 40), "finding");
    for (const cls of f.classes) {
      add("c:" + cls, cls + " мкм", "class");
      edges.push({ from: "c:" + cls, to: "f:" + f.id });
    }
  }
  for (const h of result.hypotheses) {
    add("h:" + h.id, `${h.rank}. ${h.title.slice(0, 45)}`, "hyp");
    for (const fid of h.finding_ids || []) {
      if (seen.has("f:" + fid)) edges.push({ from: "f:" + fid, to: "h:" + h.id, arrows: "to" });
    }
  }
  new vis.Network($("#graph"), { nodes, edges }, {
    groups: {
      class: { color: "#93a1b8", shape: "box" },
      finding: { color: "#e3486d", shape: "box" },
      hyp: { color: "#4da3ff", shape: "box" },
    },
    nodes: { font: { color: "#0f1420", size: 13 }, margin: 8 },
    edges: { color: "#2c3a55" },
    physics: { barnesHut: { springLength: 140 } },
  });
}

async function renderPlant() {
  const result = await api(`/plants/${encodeURIComponent(current)}`);
  const s = result.summary;
  const findings = result.findings.slice(0, 8).map((f) =>
    `<li class="${f.informational ? "info" : ""}">${f.informational ? "(справочно) " : ""}
     <b>${f.title}</b> — ${fmtT(f.tons)} т (${f.share_of_losses_pct}% потерь потока)</li>`
  ).join("");

  $("#content").innerHTML = `
    <p class="engine">движок: ${result.engine}</p>
    <div class="cards-row">
      ${statCard("Потери Ni, т", fmtT(s.losses_ni_t))}
      ${statCard("Потери Cu, т", fmtT(s.losses_cu_t))}
      ${statCard("Извлекаемый Ni", fmtT(s.recoverable_ni_t) + " т · " + s.recoverable_ni_pct + "%")}
      ${statCard("Извлекаемый Cu", fmtT(s.recoverable_cu_t) + " т · " + s.recoverable_cu_pct + "%")}
    </div>
    <h2>Матрица потерь</h2>${heatmap(result.cells)}
    <h2>Находки диагностики</h2><ul class="findings">${findings}</ul>
    <h2>Граф знаний: класс крупности → диагноз → гипотеза</h2><div id="graph"></div>
    <h2>Гипотезы (${result.hypotheses.length})</h2>
    ${result.hypotheses.map(hypCard).join("")}
    <h2>Экспорт</h2>
    <p class="exports">
      <a href="${API}/plants/${encodeURIComponent(current)}/export?fmt=json">JSON</a>
      <a href="${API}/plants/${encodeURIComponent(current)}/export?fmt=csv">CSV</a>
      <a href="${API}/plants/${encodeURIComponent(current)}/export?fmt=md">Markdown</a>
    </p>`;
  knowledgeGraph(result);
}

$("#run-btn").onclick = runPipeline;
window.vote = vote;
loadPlants().catch(() => {}); // при пустом состоянии остаётся подсказка
