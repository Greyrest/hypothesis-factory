import {FormEvent, useEffect, useMemo, useRef, useState} from 'react'
import {API, api} from './api'
import type {Graph, Hypothesis, ModelSelection, Project, Run} from './types'

type View = 'overview' | 'hypotheses' | 'graph' | 'settings'
type ModelInfo = {provider: string; model: string; label: string; available: boolean; unavailable_reason?: string}

const fmt = (value: number | undefined, digits = 0) => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: digits}).format(value || 0)
const stageLabel: Record<string, string> = {queued:'В очереди', ingestion:'Разбор данных', retrieval:'Поиск знаний', generation:'Генерация', graph:'Граф знаний', done:'Готово'}

function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [activeId, setActiveId] = useState<string | null>(localStorage.getItem('hf-project'))
  const [view, setView] = useState<View>('overview')
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([])
  const [graph, setGraph] = useState<Graph | null>(null)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [selected, setSelected] = useState<Hypothesis | null>(null)
  const [query, setQuery] = useState('')
  const [risk, setRisk] = useState(5)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const active = projects.find(p => p.id === activeId) || null
  const refreshProjects = async () => {
    const data = await api.get<{items: Project[]}>('/projects')
    setProjects(data.items)
    if (!activeId && data.items[0]) setActiveId(data.items[0].id)
  }
  const loadResults = async (projectId: string) => {
    try {
      const [h, g] = await Promise.all([
        api.get<{items: Hypothesis[]}>(`/projects/${projectId}/hypotheses`),
        api.get<Graph>(`/projects/${projectId}/graph`),
      ])
      setHypotheses(h.items); setGraph(g)
    } catch { setHypotheses([]); setGraph(null) }
  }

  useEffect(() => {
    Promise.all([refreshProjects(), api.get<{models: ModelInfo[]}>('/models').then(x => setModels(x.models)).catch(() => {})])
      .catch(e => setError(e.message))
  }, [])
  useEffect(() => {
    if (!activeId) return
    localStorage.setItem('hf-project', activeId); loadResults(activeId)
  }, [activeId])

  useEffect(() => {
    const run = active?.latest_run
    if (!run || !['queued', 'running'].includes(run.status)) return
    const timer = window.setInterval(async () => {
      await refreshProjects()
      const state = await api.get<Run>(`/runs/${run.id}`)
      if (state.status === 'done') { await loadResults(active.id); clearInterval(timer) }
      if (state.status === 'error') { setError(state.error || 'Ошибка конвейера'); clearInterval(timer) }
    }, 1600)
    return () => clearInterval(timer)
  }, [active?.latest_run?.id, active?.latest_run?.status])

  const filtered = useMemo(() => hypotheses.filter(h =>
    h.scores.risk <= risk && `${h.title} ${h.hypothesis} ${h.category_ru}`.toLowerCase().includes(query.toLowerCase())
  ), [hypotheses, query, risk])

  const createProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError(null)
    const data = new FormData(event.currentTarget)
    try {
      const created = await api.post<Project>('/projects', {
        title: data.get('title'), target_kpi: data.get('kpi'), domain: data.get('domain'),
        description: data.get('description') || null,
        constraints: String(data.get('constraints') || '').split('\n').map(x => x.trim()).filter(Boolean),
      })
      await refreshProjects(); setActiveId(created.id); event.currentTarget.reset()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const upload = async (file?: File) => {
    if (!active || !file) return
    setBusy(true); setError(null)
    try { await api.upload(`/projects/${active.id}/files`, file); await refreshProjects() }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const run = async () => {
    if (!active) return
    setBusy(true); setError(null)
    try { await api.post(`/projects/${active.id}/runs`, {use_llm: active.model.enabled}); await refreshProjects() }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const saveModel = async (selection: ModelSelection) => {
    if (!active) return
    await api.put(`/projects/${active.id}/model`, selection); await refreshProjects()
  }

  const vote = async (item: Hypothesis, value: 'up' | 'down') => {
    if (!active) return
    await api.put(`/hypotheses/${encodeURIComponent(item.id)}/feedback?project_id=${active.id}`, {vote: value, comment: null})
    await loadResults(active.id)
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">HF</span><div><b>Hypothesis</b><small>FACTORY / R&D</small></div></div>
      <nav>
        <button className={view==='overview'?'active':''} onClick={()=>setView('overview')}><span>⌂</span> Обзор</button>
        <button className={view==='hypotheses'?'active':''} onClick={()=>setView('hypotheses')}><span>◇</span> Гипотезы <em>{hypotheses.length}</em></button>
        <button className={view==='graph'?'active':''} onClick={()=>setView('graph')}><span>⌘</span> Граф знаний</button>
        <button className={view==='settings'?'active':''} onClick={()=>setView('settings')}><span>⚙</span> Настройки</button>
      </nav>
      <div className="sidebar-projects"><label>Проекты</label>{projects.map(p=><button key={p.id} className={p.id===activeId?'project active':''} onClick={()=>setActiveId(p.id)}><i className={`status ${p.status}`}/><span>{p.title}</span></button>)}</div>
      <a className="api-link" href="/docs" target="_blank">API / Swagger ↗</a>
    </aside>

    <main>
      <header>
        <div><p className="eyebrow">R&D INTELLIGENCE PLATFORM</p><h1>{active?.title || 'Новый исследовательский контур'}</h1></div>
        <div className="header-actions"><span className={`pill ${active?.status || 'new'}`}>{active?.status==='done'?'● Готово':active?.status==='running'?'◌ Выполняется':'○ Черновик'}</span>{active && <button className="primary" onClick={run} disabled={busy || !active.files.length}>Запустить анализ <span>→</span></button>}</div>
      </header>
      {error && <div className="error"><b>Ошибка</b><span>{error}</span><button onClick={()=>setError(null)}>×</button></div>}

      {!active ? <Empty createProject={createProject} busy={busy}/> : <>
        {active.latest_run && ['queued','running'].includes(active.latest_run.status) && <RunProgress run={active.latest_run}/>} 
        {view==='overview' && <Overview project={active} hypotheses={hypotheses} upload={upload} fileRef={fileRef} run={run} busy={busy}/>} 
        {view==='hypotheses' && <Hypotheses items={filtered} query={query} setQuery={setQuery} risk={risk} setRisk={setRisk} select={setSelected} vote={vote} project={active}/>} 
        {view==='graph' && <KnowledgeGraph graph={graph} onNode={(id)=>setSelected(hypotheses.find(h=>`hypothesis:${h.id}`===id)||null)}/>} 
        {view==='settings' && <Settings project={active} models={models} save={saveModel}/>} 
      </>}
    </main>
    {selected && <Detail item={selected} close={()=>setSelected(null)} vote={vote}/>} 
  </div>
}

function Empty({createProject,busy}:{createProject:(e:FormEvent<HTMLFormElement>)=>void;busy:boolean}) {
  return <section className="empty-state"><div className="empty-copy"><p className="eyebrow">01 / ПОСТАНОВКА ЗАДАЧИ</p><h2>Превратите данные в<br/><span>проверяемые решения.</span></h2><p>Задайте KPI, ограничения и загрузите источники. Система построит цепочку от факта до плана эксперимента.</p></div><form className="create-card" onSubmit={createProject}><h3>Создать проект</h3><label>Название<input name="title" required minLength={2} placeholder="Снижение потерь Ni/Cu"/></label><label>Целевой KPI<textarea name="kpi" required minLength={3} placeholder="Снизить потери металла с хвостами"/></label><div className="two"><label>Домен<select name="domain"><option value="mining_flotation">Обогащение руд</option><option value="generic">Универсальный R&D</option></select></label><label>Контекст<input name="description" placeholder="Фабрика / установка"/></label></div><label>Ограничения<textarea name="constraints" placeholder={'Каждое ограничение с новой строки\nБез остановки производства'}/></label><button className="primary" disabled={busy}>Создать проект <span>→</span></button></form></section>
}

function RunProgress({run}:{run:Run}) { return <div className="run-progress"><div><span className="spinner"/><b>{stageLabel[run.stage]||run.stage}</b><small>Сервисы обрабатывают данные и строят трассировку</small></div><strong>{run.progress_pct}%</strong><i style={{width:`${run.progress_pct}%`}}/></div> }

function Overview({project,hypotheses,upload,fileRef,run,busy}:{project:Project;hypotheses:Hypothesis[];upload:(f?:File)=>void;fileRef:any;run:()=>void;busy:boolean}) {
  const best = hypotheses[0]
  const addressed = hypotheses.reduce((sum,h)=>sum+(h.scores.impact_t||0),0)
  return <div className="overview-grid">
    <section className="goal-panel"><p className="eyebrow">ЦЕЛЕВОЙ KPI</p><h2>{project.target_kpi}</h2>{project.description&&<p>{project.description}</p>}<div className="constraint-list">{project.constraints.map((x,i)=><span key={i}>⊘ {x}</span>)}</div></section>
    <section className="metrics"><Metric value={hypotheses.length} label="гипотез" note="готовы к сравнению"/><Metric value={best?fmt(best.scores.priority,1):'—'} label="лучший приоритет" note={best?.title||'запустите анализ'}/><Metric value={addressed?fmt(addressed):'—'} label="т адресуемо" note="суммарный потенциал"/></section>
    <section className="source-panel"><div className="section-head"><div><p className="eyebrow">ИСТОЧНИКИ</p><h3>Данные проекта</h3></div><button className="ghost" onClick={()=>fileRef.current?.click()}>+ Добавить</button></div><input hidden ref={fileRef} type="file" onChange={e=>upload(e.target.files?.[0])}/><div className="files">{project.files.map(f=><div className="file" key={f.id}><span>{f.filename.endsWith('.xlsx')?'XLS':'DOC'}</span><div><b>{f.filename}</b><small>{fmt(f.size/1024,1)} КБ · {f.kind}</small></div><i>✓</i></div>)}{!project.files.length&&<button className="dropzone" onClick={()=>fileRef.current?.click()}>Перетащите отчет или выберите файл<small>XLSX, PDF, DOCX, CSV, JSON · до 100 МБ</small></button>}</div></section>
    <section className="next-panel"><p className="eyebrow">СЛЕДУЮЩИЙ ШАГ</p><h3>{hypotheses.length?'Изучите лидирующие гипотезы':'Запустите полный конвейер'}</h3><p>{hypotheses.length?'Сравните механизм, эффект, риски и доказательства. Затем скорректируйте приоритет экспертной оценкой.':'Ingestion → retrieval → генерация → ранжирование → граф.'}</p><button className="primary" onClick={run} disabled={busy||!project.files.length}>{hypotheses.length?'Перезапустить':'Начать анализ'} <span>→</span></button></section>
    {best&&<section className="leader" onClick={()=>{}}><div className="rank">01</div><div><p className="eyebrow">ЛИДИРУЮЩАЯ ГИПОТЕЗА</p><h3>{best.title}</h3><p>{best.hypothesis}</p></div><Score score={best.scores.priority}/></section>}
  </div>
}

function Metric({value,label,note}:{value:string|number;label:string;note:string}) { return <div className="metric"><strong>{value}</strong><span>{label}</span><small>{note}</small></div> }
function Score({score}:{score:number}) { return <div className="score" style={{'--score':`${Math.max(0,Math.min(100,score))*3.6}deg`} as any}><span>{fmt(score,1)}</span><small>/ 100</small></div> }

function Hypotheses({items,query,setQuery,risk,setRisk,select,vote,project}:{items:Hypothesis[];query:string;setQuery:(x:string)=>void;risk:number;setRisk:(x:number)=>void;select:(h:Hypothesis)=>void;vote:(h:Hypothesis,v:'up'|'down')=>void;project:Project}) {
  return <section className="hypotheses-view"><div className="toolbar"><div><p className="eyebrow">РАНЖИРОВАНИЕ</p><h2>Проверяемые гипотезы</h2></div><div className="filters"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Поиск по гипотезам…"/><label>Риск ≤ <b>{risk}</b><input type="range" min="1" max="5" value={risk} onChange={e=>setRisk(+e.target.value)}/></label><a className="ghost" href={`${API}/projects/${project.id}/export?format=md`}>Экспорт ↓</a></div></div><div className="hyp-list">{items.map(h=><article className="hyp-card" key={h.id} onClick={()=>select(h)}><div className="rank-col"><span>{String(h.rank).padStart(2,'0')}</span><i/></div><div className="hyp-main"><div className="tags"><span>{h.category_ru}</span><span>{h.status==='llm'?'MODEL + RULES':'RULE-BASED'}</span></div><h3>{h.title}</h3><p>{h.hypothesis}</p><div className="mini-scores"><span>Эффект <b>{fmt(h.scores.impact_t)} т</b></span><span>Реализуемость <b>{h.scores.feasibility}/5</b></span><span>Риск <b>{h.scores.risk}/5</b></span><span>Новизна <b>{h.scores.novelty}/5</b></span></div></div><div className="hyp-side"><Score score={h.scores.priority}/><div className="votes"><button onClick={e=>{e.stopPropagation();vote(h,'up')}}>↑</button><button onClick={e=>{e.stopPropagation();vote(h,'down')}}>↓</button></div></div></article>)}{!items.length&&<div className="no-results">Нет гипотез для выбранных фильтров.</div>}</div></section>
}

function KnowledgeGraph({graph,onNode}:{graph:Graph|null;onNode:(id:string)=>void}) {
  if (!graph) return <div className="no-results">Граф появится после завершения анализа.</div>
  const groups:Record<string,{x:number;y:number;color:string}>={goal:{x:50,y:12,color:'#d8ff45'},problem:{x:22,y:48,color:'#ff9b73'},hypothesis:{x:55,y:55,color:'#74d7c4'},evidence:{x:84,y:76,color:'#8aa39e'}}
  const positioned=graph.nodes.map((n,i)=>{const same=graph.nodes.filter(x=>x.group===n.group);const index=same.findIndex(x=>x.id===n.id);const g=groups[n.group]||groups.evidence;return {...n,x:g.x+(index-(same.length-1)/2)*Math.min(13,52/Math.max(1,same.length-1)),y:g.y+(index%2)*10,color:g.color}})
  const byId=Object.fromEntries(positioned.map(n=>[n.id,n]))
  return <section className="graph-view"><div className="toolbar"><div><p className="eyebrow">ТРАССИРОВКА</p><h2>Граф знаний</h2></div><div className="legend">{Object.entries(groups).map(([k,v])=><span key={k}><i style={{background:v.color}}/>{k}</span>)}</div></div><div className="graph-canvas"><svg viewBox="0 0 100 100" preserveAspectRatio="none">{graph.edges.map((e,i)=>byId[e.from]&&byId[e.to]?<line key={i} x1={byId[e.from].x} y1={byId[e.from].y} x2={byId[e.to].x} y2={byId[e.to].y}/>:null)}</svg>{positioned.map(n=><button key={n.id} className={`graph-node ${n.group}`} style={{left:`${n.x}%`,top:`${n.y}%`,'--node':n.color} as any} onClick={()=>onNode(n.id)} title={n.label}><i/>{n.label.slice(0,70)}</button>)}</div></section>
}

function Settings({project,models,save}:{project:Project;models:ModelInfo[];save:(m:ModelSelection)=>void}) {
  const [selection,setSelection]=useState(project.model)
  useEffect(()=>setSelection(project.model),[project.id,project.model.provider,project.model.model,project.model.enabled])
  const model=models.find(m=>m.provider===selection.provider&&m.model===selection.model)
  return <section className="settings"><div><p className="eyebrow">MODEL RUNTIME</p><h2>Модель генерации</h2><p>Rule-based контур работает всегда. Нейросеть улучшает формулировки только при явном включении и доступном провайдере.</p></div><div className="settings-card"><label className="switch-row"><div><b>LLM-усиление</b><small>Отправлять структурированный контекст в model-runtime</small></div><input type="checkbox" checked={selection.enabled} onChange={e=>setSelection({...selection,enabled:e.target.checked})}/></label><label>Провайдер<select value={selection.provider} onChange={e=>{const first=models.find(m=>m.provider===e.target.value);setSelection({...selection,provider:e.target.value,model:first?.model||''})}}>{[...new Set(models.map(m=>m.provider))].map(x=><option key={x}>{x}</option>)}</select></label><label>Модель<select value={selection.model} onChange={e=>setSelection({...selection,model:e.target.value})}>{models.filter(m=>m.provider===selection.provider).map(m=><option key={m.model} value={m.model}>{m.label}{m.available?'':' · недоступна'}</option>)}</select></label>{selection.provider==='ollama'&&<label>Base URL<input value={selection.base_url||''} onChange={e=>setSelection({...selection,base_url:e.target.value||null})} placeholder="http://host.docker.internal:11434"/></label>}{model&&!model.available&&<div className="warning">{model.unavailable_reason}</div>}<button className="primary" onClick={()=>save(selection)}>Сохранить конфигурацию</button></div><div className="security-note"><b>Контроль данных</b><p>API-ключи хранятся только в model-runtime. Внешние вызовы по умолчанию запрещены и включаются через <code>HF_ALLOW_EXTERNAL_MODELS=true</code>.</p></div></section>
}

function Detail({item,close,vote}:{item:Hypothesis;close:()=>void;vote:(h:Hypothesis,v:'up'|'down')=>void}) { return <div className="modal-backdrop" onMouseDown={close}><aside className="detail" onMouseDown={e=>e.stopPropagation()}><button className="close" onClick={close}>×</button><div className="tags"><span>{item.category_ru}</span><span>RANK {String(item.rank).padStart(2,'0')}</span></div><h2>{item.title}</h2><p className="hyp-statement">{item.hypothesis}</p><div className="detail-score"><Score score={item.scores.priority}/><div><span>Реализуемость <b>{item.scores.feasibility}/5</b></span><span>Риск <b>{item.scores.risk}/5</b></span><span>Новизна <b>{item.scores.novelty}/5</b></span></div></div><Section title="Механизм"><p>{item.mechanism}</p></Section><Section title="Обоснование">{item.evidence.map((e,i)=><div className="evidence" key={i}><p>{e.fact}</p><small>{e.source}</small></div>)}</Section><Section title="Риски"><ul>{item.risks.map((x,i)=><li key={i}>{x}</li>)}</ul></Section><Section title="План проверки"><ol className="roadmap">{item.roadmap.map((x,i)=><li key={i}><span>{i+1}</span>{x}</li>)}</ol></Section><div className="detail-actions"><button onClick={()=>vote(item,'up')}>↑ Поддержать</button><button onClick={()=>vote(item,'down')}>↓ Понизить</button></div></aside></div> }
function Section({title,children}:{title:string;children:any}) { return <section className="detail-section"><h4>{title}</h4>{children}</section> }

export default App

