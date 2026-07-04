/* Фабрика гипотез — SPA поверх gateway API. */
const API = (window.HF_API || `http://${location.hostname}:8000`) + "/api/v1";

const $ = (sel) => document.querySelector(sel);
let plants = [];        // [{plant, engine, summary, project, hypotheses_count}]
let current = null;     // выбранная фабрика
let network = null;     // vis.Network
let graphEdit = false;  // режим правки графа
const fmtT = (v) => (v == null ? "—" : Math.round(v).toLocaleString("ru-RU"));

async function api(path, opts = {}) {
  // разграничение доступа: ключ хранится локально, спрашивается при 401
  const key = localStorage.getItem("hf_api_key");
  opts.headers = { ...(opts.headers || {}), ...(key ? { "X-API-Key": key } : {}) };
  let r = await fetch(API + path, opts);
  if (r.status === 401) {
    const entered = prompt("API-ключ (HF_API_KEY):");
    if (entered) {
      localStorage.setItem("hf_api_key", entered);
      opts.headers["X-API-Key"] = entered;
      r = await fetch(API + path, opts);
    }
  }
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}
const postJSON = (path, body, method = "POST") => api(path, {
  method, headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function projectOptions() {
  const kpi = $("#kpi-input").value.trim();
  const constraints = $("#constraints-input").value.split("\n")
    .map((s) => s.trim()).filter(Boolean);
  return kpi || constraints.length
    ? { target_kpi: kpi || null, constraints } : null;
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
  await withStatus("#run-btn", async () => {
    const useLlm = $("#use-llm").checked;
    const opts = projectOptions();
    await api(`/runs?use_llm=${useLlm}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: opts ? JSON.stringify(opts) : "{}",
    });
  });
}

async function uploadReport() {
  const f = $("#file-input").files[0];
  if (!f) { $("#run-status").textContent = "Выберите .xlsx файл"; return; }
  await withStatus("#upload-btn", async () => {
    const fd = new FormData();
    fd.append("file", f);
    fd.append("target_kpi", $("#kpi-input").value.trim());
    fd.append("constraints", $("#constraints-input").value);
    const res = await api(`/reports?use_llm=${$("#use-llm").checked}`,
      { method: "POST", body: fd });
    current = res.plant;
  });
}

async function withStatus(btnSel, fn) {
  const btn = $(btnSel);
  btn.disabled = true;
  $("#run-status").textContent = "Конвейер работает (парсинг → диагностика → генерация)…";
  try {
    await fn();
    $("#run-status").textContent = "Готово";
    await loadPlants();
  } catch (e) {
    $("#run-status").textContent = "Ошибка: " + e.message;
  } finally {
    btn.disabled = false;
  }
}

async function vote(category, v) {
  await postJSON("/feedback", { category, vote: v });
  await renderPlant(); // приоритеты пересчитаны на сервере
}

async function setStatus(hypId, status) {
  await postJSON(`/plants/${encodeURIComponent(current)}/hypotheses/${encodeURIComponent(hypId)}`,
    { status }, "PATCH");
  await renderPlant();
}

async function removeHyp(hypId) {
  await api(`/plants/${encodeURIComponent(current)}/hypotheses/${encodeURIComponent(hypId)}`,
    { method: "DELETE" });
  await renderPlant();
}

async function applyWeights() {
  await postJSON("/weights", {
    impact: +$("#w-impact").value, feasibility: +$("#w-feas").value,
    risk: +$("#w-risk").value, novelty: +$("#w-nov").value,
  }, "PUT");
  await renderPlant();
}

async function runWhatIf() {
  const signal = $("#wi-signal").value;
  const pct = +$("#wi-pct").value;
  const r = await api(`/plants/${encodeURIComponent(current)}/whatif` +
    `?signal=${signal}&reduction_pct=${pct}`);
  $("#wi-result").textContent =
    `адресуемо Ni ${fmtT(r.addressable_t.ni)} т / Cu ${fmtT(r.addressable_t.cu)} т → ` +
    `при устранении ${pct}%: −${fmtT(r.kpi_delta_t.ni)} т Ni, −${fmtT(r.kpi_delta_t.cu)} т Cu ` +
    `(остаток потерь: Ni ${fmtT(r.losses_after_t.ni)} т)`;
}

async function addHypothesis() {
  const text = $("#new-hyp-text").value.trim();
  if (!text) return;
  $("#add-hyp-btn").disabled = true;
  try {
    await postJSON(`/plants/${encodeURIComponent(current)}/hypotheses`, {
      text,
      title: $("#new-hyp-title").value.trim() || null,
      category: $("#new-hyp-cat").value || null,
    });
    await renderPlant();
  } catch (e) {
    alert("Ошибка: " + e.message);
    $("#add-hyp-btn").disabled = false;
  }
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

const STATUS_BADGE = {
  llm: `<span class="badge llm">LLM</span>`,
  "llm-new": `<span class="badge llm">LLM</span>`,
  expert_added: `<span class="badge expert">гипотеза эксперта</span>`,
  confirmed: `<span class="badge ok">✔ подтверждена</span>`,
  rejected: `<span class="badge bad">✖ отклонена</span>`,
};

function hypCard(h) {
  const s = h.scores, eff = h.expected_effect;
  const ev = h.evidence.map((e) =>
    `<li>${e.fact}<div class="src">— ${e.source}</div></li>`).join("");
  return `<div class="hyp ${h.status === "rejected" ? "rejected" : ""}">
    <div class="head"><h3>${h.rank}. ${h.title}</h3>
      <span class="prio">приоритет ${s.priority}</span></div>
    <div class="badges">
      <span class="badge">${h.category_ru}</span>${STATUS_BADGE[h.status] || ""}
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
      <button class="ghost ok" onclick="setStatus('${h.id}','confirmed')">✔ подтвердить</button>
      <button class="ghost bad" onclick="setStatus('${h.id}','rejected')">✖ отклонить</button>
      ${h.status === "expert_added"
        ? `<button class="ghost" onclick="removeHyp('${h.id}')">🗑 удалить</button>` : ""}
      <span>фидбэк сдвигает приоритет категории «${h.category_ru}»
        (adj: ${s.feedback_adj ?? 0})</span>
    </div>
  </div>`;
}

// ---------------------------------------------------------------- граф знаний
const GRAPH_GROUPS = {
  kpi: { color: "#ffd166", shape: "box" },
  class: { color: "#93a1b8", shape: "box" },
  finding: { color: "#e3486d", shape: "box" },
  hyp: { color: "#4da3ff", shape: "box" },
};

async function renderGraph() {
  const g = await api(`/plants/${encodeURIComponent(current)}/graph`);
  const edges = g.edges.map((e) =>
    e.expert ? { ...e, color: "#38c172", width: 2, dashes: true } : e);
  network = new vis.Network($("#graph"), { nodes: g.nodes, edges }, {
    groups: GRAPH_GROUPS,
    nodes: { font: { color: "#0f1420", size: 13 }, margin: 8 },
    edges: { color: "#2c3a55" },
    physics: { barnesHut: { springLength: 140 } },
    interaction: { multiselect: true },
  });
  const patched = g.patch.removed_nodes.length + g.patch.removed_edges.length
    + g.patch.added_edges.length;
  $("#graph-info").textContent = patched
    ? `правок эксперта: ${patched} (зелёные пунктирные рёбра — добавленные)` : "";
}

async function graphDeleteSelected() {
  const sel = network.getSelection();
  if (!sel.nodes.length && !sel.edges.length) {
    $("#graph-info").textContent = "Выделите узлы или рёбра (клик, ctrl+клик)"; return;
  }
  await postJSON(`/plants/${encodeURIComponent(current)}/graph/patch`,
    { removed_nodes: sel.nodes, removed_edges: sel.edges });
  await renderGraph();
}

async function graphLinkSelected() {
  const sel = network.getSelection().nodes;
  if (sel.length !== 2) {
    $("#graph-info").textContent = "Выделите ровно 2 узла (ctrl+клик)"; return;
  }
  await postJSON(`/plants/${encodeURIComponent(current)}/graph/patch`,
    { added_edges: [{ from: sel[0], to: sel[1] }] });
  await renderGraph();
}

async function graphReset() {
  await api(`/plants/${encodeURIComponent(current)}/graph/patch`,
    { method: "DELETE" });
  await renderGraph();
}

// ------------------------------------------------------------------- страница
async function renderPlant() {
  const result = await api(`/plants/${encodeURIComponent(current)}`);
  const weights = await api("/weights");
  const s = result.summary;
  const signals = [...new Set(result.findings
    .filter((f) => !f.informational).map((f) => f.signal))];
  const findings = result.findings.slice(0, 8).map((f) =>
    `<li class="${f.informational ? "info" : ""}">${f.informational ? "(справочно) " : ""}
     <b>${f.title}</b> — ${fmtT(f.tons)} т (${f.share_of_losses_pct}% потерь потока)</li>`
  ).join("");
  const proj = result.project;
  const projHtml = proj ? `
    <div class="project-info">
      <b>Задача:</b> ${proj.target_kpi || "—"}
      ${(proj.constraints || []).length
        ? `<br><b>Ограничения:</b> ${proj.constraints.join(" · ")}` : ""}
    </div>` : "";

  $("#content").innerHTML = `
    <p class="engine">движок: ${result.engine}</p>
    ${projHtml}
    <div class="cards-row">
      ${statCard("Потери Ni, т", fmtT(s.losses_ni_t))}
      ${statCard("Потери Cu, т", fmtT(s.losses_cu_t))}
      ${statCard("Извлекаемый Ni", fmtT(s.recoverable_ni_t) + " т · " + s.recoverable_ni_pct + "%")}
      ${statCard("Извлекаемый Cu", fmtT(s.recoverable_cu_t) + " т · " + s.recoverable_cu_pct + "%")}
    </div>
    <h2>Матрица потерь</h2>${heatmap(result.cells)}
    <h2>Находки диагностики</h2><ul class="findings">${findings}</ul>
    <div class="add-hyp">
      <h3>🔮 Что-если (контрфактуальный анализ)</h3>
      <div class="pf-row">
        <select id="wi-signal">${signals.map((x) =>
          `<option value="${x}">${x}</option>`).join("")}</select>
        <label class="llm-label">устранить <input id="wi-pct" type="number"
          value="50" min="0" max="100" style="width:60px"> % потерь сигнала</label>
        <button class="ghost" onclick="runWhatIf()">Посчитать</button>
      </div>
      <span id="wi-result" class="engine"></span>
    </div>
    <h2>Граф знаний: класс → диагноз → гипотеза → KPI</h2>
    <div class="graph-tools">
      <button class="ghost" onclick="graphDeleteSelected()">🗑 Удалить выбранное</button>
      <button class="ghost" onclick="graphLinkSelected()">🔗 Связать 2 узла</button>
      <button class="ghost" onclick="graphReset()">↺ Сбросить правки</button>
      <span id="graph-info" class="engine"></span>
    </div>
    <div id="graph"></div>
    <h2>Гипотезы (${result.hypotheses.length})</h2>
    <div class="add-hyp">
      <h3>⚖️ Настройки эксперта: веса ранжирования</h3>
      <div class="pf-row">
        <label class="llm-label">эффект <input id="w-impact" type="number" step="0.05"
          min="0" value="${weights.impact}" style="width:70px"></label>
        <label class="llm-label">реализуемость <input id="w-feas" type="number" step="0.05"
          min="0" value="${weights.feasibility}" style="width:70px"></label>
        <label class="llm-label">риск <input id="w-risk" type="number" step="0.05"
          min="0" value="${weights.risk}" style="width:70px"></label>
        <label class="llm-label">новизна <input id="w-nov" type="number" step="0.05"
          min="0" value="${weights.novelty}" style="width:70px"></label>
        <button class="ghost" onclick="applyWeights()">Применить и переранжировать</button>
      </div>
    </div>
    <div class="add-hyp">
      <h3>➕ Своя гипотеза</h3>
      <p class="engine">Система сама определит категорию, адресуемый металл по ячейкам
      отчёта, обоснование из базы знаний и место в ранжировании.</p>
      <input id="new-hyp-title" type="text" placeholder="Название (опционально)">
      <textarea id="new-hyp-text" rows="2"
        placeholder="Если установить дополнительный контактный чан перед контрольной флотацией, то потери раскрытого металла снизятся…"></textarea>
      <div class="pf-row">
        <select id="new-hyp-cat">
          <option value="">категория: авто</option>
          <option value="GRIND">Измельчение</option>
          <option value="CLASSIFY">Классификация</option>
          <option value="REGRIND">Доизмельчение/сепарация</option>
          <option value="FLOT">Флотация</option>
          <option value="REAGENT">Реагентный режим</option>
          <option value="CRUSH">Дробление</option>
          <option value="TAILS">Переработка хвостов</option>
          <option value="AUTO">Автоматизация</option>
        </select>
        <button id="add-hyp-btn" onclick="addHypothesis()">Добавить и оценить</button>
      </div>
    </div>
    ${result.hypotheses.map(hypCard).join("")}
    <h2>Экспорт</h2>
    <p class="exports">
      <a href="${API}/plants/${encodeURIComponent(current)}/export?fmt=json">JSON</a>
      <a href="${API}/plants/${encodeURIComponent(current)}/export?fmt=csv">CSV</a>
      <a href="${API}/plants/${encodeURIComponent(current)}/export?fmt=md">Markdown</a>
      <a href="${API}/plants/${encodeURIComponent(current)}/export?fmt=docx">DOCX</a>
      <a href="${API}/plants/${encodeURIComponent(current)}/export?fmt=md&lang=en">MD·EN</a>
      <a href="${API}/plants/${encodeURIComponent(current)}/export?fmt=md&lang=zh">MD·中文</a>
      <span class="engine">(EN/中文 — через LLM-слой; PDF — печать MD/DOCX)</span>
    </p>`;
  await renderGraph();
}

$("#run-btn").onclick = runPipeline;
$("#upload-btn").onclick = uploadReport;
Object.assign(window, { vote, setStatus, removeHyp, addHypothesis,
  graphDeleteSelected, graphLinkSelected, graphReset, applyWeights, runWhatIf });
loadPlants().catch(() => {}); // при пустом состоянии остаётся подсказка
