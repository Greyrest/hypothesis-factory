"""Генерация интерактивного дашборда: index + страница по каждой фабрике.

Каждая страница самодостаточна (данные инлайн), граф знаний — vis-network (CDN).
Обратная связь эксперта: 👍/👎 по гипотезе, хранится в localStorage,
экспортируется в feedback.json (его читает generate.py при переранжировании).
"""
from __future__ import annotations

import json
from pathlib import Path

CLS_ORDER = ["+125", "-125+71", "+71", "-71+45", "-45+20", "-20+10", "-10"]
FORM_ORDER = ["Раскрытый Pnt/Cp", "Закрытый Pnt/Cp", "Миллерит",
              "Примесь в пирротине", "Силикатная форма/Валлериит", "Пирит/Другие"]

PAGE = """<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Фабрика гипотез</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
:root {{ --blue:#0077C8; --dark:#0B2D4E; --bg:#F4F7FA; --card:#fff; --line:#E2E9F0;
        --ok:#1D9A6C; --warn:#E8A13C; --bad:#D64550; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ font:15px/1.55 -apple-system,'Segoe UI',Roboto,sans-serif; background:var(--bg); color:#1c2b3a; }}
header {{ background:linear-gradient(100deg,var(--dark),var(--blue)); color:#fff; padding:26px 36px; }}
header h1 {{ font-size:24px; }} header a {{ color:#BFE0F8; text-decoration:none; font-size:13px; }}
header .sub {{ opacity:.85; margin-top:4px; font-size:14px; }}
main {{ max-width:1280px; margin:0 auto; padding:26px 24px 80px; }}
h2 {{ margin:34px 0 14px; font-size:19px; color:var(--dark); }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; }}
.card .v {{ font-size:26px; font-weight:700; color:var(--dark); }}
.card .l {{ font-size:12.5px; color:#5b6c7d; margin-top:2px; }}
.card .s {{ font-size:12px; color:var(--ok); }}
table.matrix {{ border-collapse:collapse; background:#fff; border-radius:10px; overflow:hidden;
               font-size:12.5px; width:100%; }}
.matrix th,.matrix td {{ border:1px solid var(--line); padding:6px 8px; text-align:right; min-width:74px; }}
.matrix th {{ background:#EDF3F8; color:var(--dark); text-align:center; }}
.matrix td.name {{ text-align:left; font-weight:600; background:#F8FBFD; }}
.matrix td.rec {{ box-shadow: inset 3px 0 0 var(--ok); }}
.legend {{ font-size:12.5px; color:#5b6c7d; margin:8px 0 0; }}
#graph {{ height:560px; background:#fff; border:1px solid var(--line); border-radius:12px; }}
.gwrap {{ position:relative; }}
#ginfo {{ position:absolute; top:12px; right:12px; width:320px; max-height:520px; overflow:auto;
         background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 14px;
         box-shadow:0 6px 24px rgba(11,45,78,.12); font-size:13px; display:none; }}
.hyp {{ background:#fff; border:1px solid var(--line); border-radius:12px; margin-bottom:14px; overflow:hidden; }}
.hyp>summary {{ list-style:none; cursor:pointer; padding:14px 18px; display:flex; gap:14px; align-items:center; }}
.hyp>summary::-webkit-details-marker {{ display:none; }}
.badge {{ min-width:52px; height:52px; border-radius:10px; background:var(--dark); color:#fff;
         display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.badge b {{ font-size:17px; }} .badge span {{ font-size:9.5px; opacity:.8; }}
.hyp .t {{ flex:1; }} .hyp .t b {{ font-size:15.5px; color:var(--dark); }}
.tags {{ margin-top:4px; display:flex; flex-wrap:wrap; gap:6px; }}
.tag {{ font-size:11px; padding:2px 9px; border-radius:20px; background:#E8F1F9; color:var(--blue); }}
.tag.st-catalog {{ background:#E7F6EF; color:var(--ok); }}
.tag.st-llm,.tag.st-llm-new {{ background:#F3EDFB; color:#7A4FD1; }}
.tag.st-generated {{ background:#FCF3E3; color:#B07817; }}
.body {{ padding:0 18px 18px; border-top:1px dashed var(--line); }}
.body h4 {{ margin:14px 0 6px; font-size:13px; text-transform:uppercase; letter-spacing:.4px; color:#5b6c7d; }}
.body ul,.body ol {{ padding-left:20px; }} .body li {{ margin:4px 0; }}
.ev {{ background:#F8FBFD; border-left:3px solid var(--blue); padding:8px 12px; border-radius:6px; margin:6px 0; }}
.ev .src {{ display:block; font-size:11.5px; color:#5b6c7d; margin-top:3px; }}
.scorebar {{ display:flex; gap:18px; flex-wrap:wrap; font-size:13px; margin-top:10px; }}
.scorebar div b {{ color:var(--dark); }}
.fb {{ display:flex; gap:8px; align-items:center; }}
.fb button {{ border:1px solid var(--line); background:#fff; border-radius:8px; padding:6px 10px;
             cursor:pointer; font-size:15px; }}
.fb button.on {{ background:var(--blue); border-color:var(--blue); color:#fff; }}
.toolbar {{ display:flex; gap:10px; flex-wrap:wrap; margin:12px 0 4px; }}
.toolbar a,.toolbar button {{ font-size:13px; padding:8px 14px; border-radius:8px; border:1px solid var(--line);
      background:#fff; color:var(--dark); text-decoration:none; cursor:pointer; }}
.findings li {{ margin:6px 0; }}
.note {{ font-size:12.5px; color:#5b6c7d; }}
</style></head><body>
<header>
  <a href="index.html">← все фабрики</a>
  <h1>{title}</h1>
  <div class="sub">Автоматическая диагностика потерь и генерация гипотез · движок: {engine}</div>
</header>
<main>
  <div class="cards" style="margin-top:6px">
    <div class="card"><div class="v">{ni_loss}</div><div class="l">потери Ni с хвостами, т</div>
      <div class="s">извлекаемо {ni_rec} т ({ni_rec_pct}%)</div></div>
    <div class="card"><div class="v">{cu_loss}</div><div class="l">потери Cu с хвостами, т</div>
      <div class="s">извлекаемо {cu_rec} т ({cu_rec_pct}%)</div></div>
    <div class="card"><div class="v">{n_hyp}</div><div class="l">гипотез сгенерировано</div>
      <div class="s">{n_findings} диагностических находок</div></div>
    <div class="card"><div class="v">{kpi_range}</div><div class="l">потенциал топ-3 гипотез, т Ni</div>
      <div class="s">оценка до испытаний</div></div>
  </div>

  <h2>Диагностика: где теряется металл</h2>
  <ul class="findings">{findings_html}</ul>

  <h2>Матрица потерь (классы крупности × формы), тонны</h2>
  {matrices_html}
  <p class="legend">◧ зелёная кромка — извлекаемые формы для данного элемента (по справке института).</p>

  <h2>Граф знаний: класс крупности → диагноз → гипотеза</h2>
  <div class="gwrap"><div id="graph"></div><div id="ginfo"></div></div>
  <p class="legend">Размер узла ~ тонны металла. Клик по узлу — детали. Синие — классы/потоки, оранжевые — диагнозы, зелёные — гипотезы.</p>

  <h2>Гипотезы (ранжированы: эффект · реализуемость · риск · новизна)</h2>
  <div class="toolbar">
    <a href="{json_name}" download>⬇ JSON</a>
    <a href="{csv_name}" download>⬇ CSV</a>
    <a href="{md_name}" download>⬇ Отчёт (MD)</a>
    <button onclick="exportFeedback()">⬇ feedback.json (оценки эксперта)</button>
    <span class="note" style="align-self:center">👍/👎 — обратная связь: попадает в переранжирование при следующем запуске</span>
  </div>
  <div id="hyps">{hyps_html}</div>
</main>
<script>
const DATA = {data_json};
// ---- граф знаний ----
(function() {{
  const nodes = [], edges = [];
  const seen = new Set();
  function add(n) {{ if (!seen.has(n.id)) {{ seen.add(n.id); nodes.push(n); }} }}
  const F = DATA.findings.filter(f => !f.informational);
  for (const f of F) {{
    add({{id:'f:'+f.id, label:wrap(f.title,22), group:'finding',
         value:Math.max(f.tons,50), payload:f}});
    for (const c of (f.classes||[])) {{
      add({{id:'c:'+f.stream+c, label:c+'\\n'+shortStream(f.stream), group:'cls', value:60}});
      edges.push({{from:'c:'+f.stream+c, to:'f:'+f.id}});
    }}
  }}
  for (const h of DATA.hypotheses) {{
    add({{id:'h:'+h.id, label:wrap(h.title,24), group:'hyp',
         value:Math.max(h.scores.impact_t,80), payload:h}});
    for (const fid of (h.finding_ids||[])) {{
      if (seen.has('f:'+fid)) edges.push({{from:'f:'+fid, to:'h:'+h.id, arrows:'to'}});
    }}
  }}
  function shortStream(s) {{ return s.replace('Хвосты ','').slice(0,10); }}
  function wrap(t,w) {{ const words=t.split(' '); let line='',out=[];
    for (const wd of words) {{ if ((line+wd).length>w) {{ out.push(line); line=''; }} line+=wd+' '; }}
    out.push(line); return out.join('\\n').trim(); }}
  const net = new vis.Network(document.getElementById('graph'),
    {{nodes:new vis.DataSet(nodes), edges:new vis.DataSet(edges)}},
    {{nodes: {{shape:'dot', font:{{size:11, multi:false}}, scaling:{{min:8,max:34}}}},
     groups: {{cls:{{color:'#5B9BD5'}}, finding:{{color:'#E8A13C'}}, hyp:{{color:'#1D9A6C'}}}},
     edges: {{color:{{color:'#B8C9D9'}}, smooth:{{type:'continuous'}}}},
     physics: {{barnesHut:{{gravitationalConstant:-2600, springLength:120}}, stabilization:{{iterations:120}}}}}});
  const info = document.getElementById('ginfo');
  net.on('click', p => {{
    if (!p.nodes.length) {{ info.style.display='none'; return; }}
    const n = nodes.find(x => x.id===p.nodes[0]);
    if (!n || !n.payload) {{ info.style.display='none'; return; }}
    const d = n.payload;
    info.innerHTML = d.hypothesis
      ? `<b>${{d.title}}</b><br><br>${{d.hypothesis}}<br><br><i>${{d.mechanism||''}}</i>`
      : `<b>${{d.title}}</b><br><br>${{d.detail}}<br><br><b>${{d.tons}}</b> т (${{d.share_of_losses_pct}}% потерь потока)`;
    info.style.display='block';
  }});
}})();
// ---- обратная связь ----
const FB_KEY = 'fabrika-feedback-' + DATA.plant;
function fbState() {{ try {{ return JSON.parse(localStorage.getItem(FB_KEY)||'{{}}'); }} catch(e) {{ return {{}}; }} }}
function vote(id, dir) {{
  const st = fbState(); st[id] = (st[id]===dir) ? null : dir;
  localStorage.setItem(FB_KEY, JSON.stringify(st)); paint();
}}
function paint() {{
  const st = fbState();
  document.querySelectorAll('.fb').forEach(el => {{
    const id = el.dataset.id;
    el.querySelector('.up').classList.toggle('on', st[id]==='up');
    el.querySelector('.down').classList.toggle('on', st[id]==='down');
  }});
}}
function exportFeedback() {{
  const st = fbState(), agg = {{}};
  for (const h of DATA.hypotheses) {{
    const v = st[h.id]; if (!v) continue;
    for (const c of h.categories) {{
      agg[c] = agg[c]||{{up:0,down:0}}; agg[c][v]++;
    }}
  }}
  const blob = new Blob([JSON.stringify(agg,null,2)], {{type:'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'feedback.json'; a.click();
}}
paint();
</script>
</body></html>"""

INDEX = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Фабрика гипотез — Норникель</title>
<style>
:root { --blue:#0077C8; --dark:#0B2D4E; --line:#E2E9F0; }
* { box-sizing:border-box; margin:0; }
body { font:15px/1.55 -apple-system,'Segoe UI',Roboto,sans-serif; background:#F4F7FA; color:#1c2b3a; }
header { background:linear-gradient(100deg,var(--dark),var(--blue)); color:#fff; padding:44px 36px; }
header h1 { font-size:30px; } header p { opacity:.9; margin-top:8px; max-width:760px; }
main { max-width:1100px; margin:0 auto; padding:30px 24px 80px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:18px; margin-top:10px; }
a.plant { display:block; background:#fff; border:1px solid var(--line); border-radius:14px;
          padding:22px; text-decoration:none; color:inherit; transition:.15s; }
a.plant:hover { box-shadow:0 8px 28px rgba(11,45,78,.13); transform:translateY(-2px); }
a.plant h3 { color:var(--dark); font-size:19px; }
a.plant .num { font-size:13px; color:#5b6c7d; margin-top:8px; }
a.plant .top { margin-top:10px; font-size:13.5px; color:var(--blue); }
.how { background:#fff; border:1px solid var(--line); border-radius:14px; padding:22px; margin-top:34px; }
.how h2 { color:var(--dark); font-size:18px; margin-bottom:10px; }
.how ol { padding-left:22px; } .how li { margin:6px 0; }
</style></head><body>
<header>
  <h1>Фабрика гипотез</h1>
  <p>Прототип: автоматическая генерация и приоритизация технологических гипотез
     снижения потерь цветных металлов с хвостами флотации — по отчётам института,
     базе знаний и каталогу проверенных практик. Хакатон Норникеля, Задача 1.</p>
</header>
<main>
  <div class="grid">__PLANTS__</div>
  <div class="how">
    <h2>Как это работает</h2>
    <ol>
      <li><b>Парсинг</b> xlsx-отчёта о хвостах: потоки, классы крупности, минеральные формы, извлекаемый металл (устойчив к #REF! и пропускам).</li>
      <li><b>Диагностика</b>: правила физики обогащения находят, где и почему теряется металл (недоизмельчение, шламы, проскок классификации…).</li>
      <li><b>База знаний</b>: справка института + каталог из 27 практик экспертов (4 фабрики) + правила с привязкой к литературе.</li>
      <li><b>Генерация</b>: rule-based сопоставление + опциональное LLM-усиление (Claude Opus 4.8) — карточки с обоснованием, цитатами, KPI и дорожной картой.</li>
      <li><b>Приоритизация</b>: 0.40·эффект + 0.30·реализуемость + 0.20·(1−риск) + 0.10·новизна + обратная связь эксперта.</li>
    </ol>
  </div>
</main></body></html>"""


def _fmt(v, nd=0):
    if v is None:
        return "—"
    return f"{v:,.{nd}f}".replace(",", " ")


def _matrix_html(parsed: dict) -> str:
    from parse_tailings import RECOVERABLE_FORMS
    out = []
    for stream in parsed["streams"]:
        if stream.get("aggregate"):
            continue
        classes = {c["cls"]: c for c in stream["size_classes"]}
        cols = [c for c in CLS_ORDER if c in classes]
        for el, el_name in (("ni", "Ni (эл. 28)"), ("cu", "Cu (эл. 29)")):
            if not stream["totals"][f"{el}_t"]:
                continue
            rows = []
            vals_all = [(classes[c]["forms"].get(f) or {}).get(f"{el}_t") or 0
                        for c in cols for f in FORM_ORDER]
            vmax = max(vals_all) or 1
            for form in FORM_ORDER:
                cells, nonzero = [], 0
                rec = form in RECOVERABLE_FORMS[el]
                for c in cols:
                    v = (classes[c]["forms"].get(form) or {}).get(f"{el}_t")
                    nonzero += bool(v)
                    alpha = min(0.85, (v or 0) / vmax)
                    style = f' style="background:rgba(0,119,200,{alpha:.2f});color:{"#fff" if alpha>0.45 else "#1c2b3a"}"'
                    cells.append(f"<td{style}>{_fmt(v)}</td>")
                if not nonzero:
                    continue
                cls_attr = ' class="name rec"' if rec else ' class="name"'
                rows.append(f"<tr><td{cls_attr}>{form}</td>{''.join(cells)}</tr>")
            head = "".join(f"<th>{c}</th>" for c in cols)
            out.append(
                f"<h3 style='margin:18px 0 8px;font-size:15px;color:#0B2D4E'>"
                f"{stream['name']} — {el_name}, потери {_fmt(stream['totals'][f'{el}_t'])} т</h3>"
                f"<table class='matrix'><tr><th>Форма \\ Класс, мкм</th>{head}</tr>"
                f"{''.join(rows)}</table>")
    return "\n".join(out)


def _hyp_html(h: dict) -> str:
    eff, sc = h["expected_effect"], h["scores"]
    ev = "".join(f"<div class='ev'>{e['fact']}<span class='src'>— {e['source']}</span></div>"
                 for e in h["evidence"])
    risks = "".join(f"<li>{r}</li>" for r in h["risks"])
    road = "".join(f"<li>{r}</li>" for r in h["roadmap"])
    tags = (f"<span class='tag'>{h['category_ru']}</span>"
            + (f"<span class='tag'>{h['equipment']}</span>" if h["equipment"] else "")
            + f"<span class='tag st-{h['status']}'>{ {'catalog':'практика экспертов','generated':'генерация по правилам','llm':'доработано Claude','llm-new':'новая (Claude)'}.get(h['status'],h['status']) }</span>")
    kpi = (f"Ni −{_fmt(eff['kpi_delta_t']['ni'][0])}…{_fmt(eff['kpi_delta_t']['ni'][1])} т · "
           f"Cu −{_fmt(eff['kpi_delta_t']['cu'][0])}…{_fmt(eff['kpi_delta_t']['cu'][1])} т")
    return f"""<details class="hyp" {'open' if h['rank'] == 1 else ''}>
<summary>
  <div class="badge"><b>{sc['priority']:.0f}</b><span>приоритет</span></div>
  <div class="t"><b>{h['rank']}. {h['title']}</b>
    <div class="tags">{tags}</div></div>
  <div class="fb" data-id="{h['id']}" onclick="event.preventDefault()">
    <button class="up" onclick="vote('{h['id']}','up')">👍</button>
    <button class="down" onclick="vote('{h['id']}','down')">👎</button>
  </div>
</summary>
<div class="body">
  <h4>Гипотеза</h4><p>{h['hypothesis']}</p>
  <h4>Механизм влияния</h4><p>{h['mechanism']}</p>
  <h4>Обоснование и источники</h4>{ev}
  <h4>Ожидаемый эффект на KPI</h4>
  <p><b>{kpi}</b></p><p class="note">{eff['assumption']}</p>
  <div class="scorebar">
    <div>эффект (адресуемо): <b>{_fmt(sc['impact_t'])} т</b></div>
    <div>реализуемость: <b>{sc['feasibility']}/5</b></div>
    <div>новизна: <b>{sc['novelty']}/5</b></div>
    <div>риск: <b>{sc['risk']}/5</b></div>
    <div>поправка эксперта: <b>{sc.get('feedback_adj',0):+}</b></div>
  </div>
  <h4>Риски</h4><ul>{risks}</ul>
  <h4>Дорожная карта проверки</h4><ol>{road}</ol>
</div>
</details>"""


def build_plant_page(result: dict, parsed: dict, out_dir: Path, export_paths: dict):
    s = result["summary"]
    findings_html = "".join(
        f"<li>{'<span class=note>(справочно)</span> ' if f.get('informational') else ''}"
        f"<b>{f['title']}</b> — {_fmt(f['tons'])} т ({f['share_of_losses_pct']}% потерь потока)."
        f" <span class='note'>{f['detail']}</span></li>"
        for f in result["findings"][:9])
    top3 = result["hypotheses"][:3]
    kpi_lo = sum(h["expected_effect"]["kpi_delta_t"]["ni"][0] for h in top3)
    kpi_hi = sum(h["expected_effect"]["kpi_delta_t"]["ni"][1] for h in top3)

    html = PAGE.format(
        title=f"Фабрика {result['plant']}",
        engine=result["engine"],
        ni_loss=_fmt(s["losses_ni_t"]), cu_loss=_fmt(s["losses_cu_t"]),
        ni_rec=_fmt(s["recoverable_ni_t"]), cu_rec=_fmt(s["recoverable_cu_t"]),
        ni_rec_pct=s["recoverable_ni_pct"], cu_rec_pct=s["recoverable_cu_pct"],
        n_hyp=len(result["hypotheses"]), n_findings=len(result["findings"]),
        kpi_range=f"−{_fmt(kpi_lo)}…{_fmt(kpi_hi)}",
        findings_html=findings_html,
        matrices_html=_matrix_html(parsed),
        hyps_html="".join(_hyp_html(h) for h in result["hypotheses"]),
        json_name=Path(export_paths["json"]).name,
        csv_name=Path(export_paths["csv"]).name,
        md_name=Path(export_paths["md"]).name,
        data_json=json.dumps(
            {"plant": result["plant"], "findings": result["findings"],
             "hypotheses": result["hypotheses"]}, ensure_ascii=False),
    )
    page = out_dir / f"{result['plant'].replace(' ', '_')}.html"
    page.write_text(html, encoding="utf-8")
    return page


def build_index(entries: list[dict], out_dir: Path):
    cards = []
    for e in entries:
        s = e["summary"]
        top = e["hypotheses"][0]["title"] if e["hypotheses"] else "—"
        cards.append(
            f"<a class='plant' href='{e['page']}'><h3>{e['plant']}</h3>"
            f"<div class='num'>Потери: Ni {_fmt(s['losses_ni_t'])} т · Cu {_fmt(s['losses_cu_t'])} т<br>"
            f"Извлекаемо: Ni {s['recoverable_ni_pct']}% · Cu {s['recoverable_cu_pct']}%<br>"
            f"Гипотез: {len(e['hypotheses'])}</div>"
            f"<div class='top'>№1: {top}</div></a>")
    (out_dir / "index.html").write_text(
        INDEX.replace("__PLANTS__", "".join(cards)), encoding="utf-8")
