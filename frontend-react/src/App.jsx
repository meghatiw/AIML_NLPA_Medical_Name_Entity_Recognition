import React, { useEffect, useMemo, useState } from 'react'
import { extract, uploadFiles, exportEntities, exportEvents, getDataset, getMTSpecialties, getMTNotes } from './api'

const E_TYPES = [
  'PATIENT','MEDICATION','DISEASE','TREATMENT','PROCEDURE','SYMPTOM','LAB_TEST',
  'AGE','DOSAGE','ROUTE','FREQUENCY','DATE','WEIGHT','BP','GLUCOSE','PROGRAM','VITAL_SIGN','MEASUREMENT_UNIT'
]
const EVENT_TYPES = ['MedicationAdministration','Diagnosis','Procedure','Admission','Discharge']

function Chipbar({items, selected, onToggle}){
  return (
    <div className="chipbar">
      {items.map(it=>{
        const isOn = selected.has(it)
        return (
          <label key={it} className={`chip ${isOn?'active':''}`}>
            <input type="checkbox" checked={isOn} onChange={e=>onToggle(it, e.target.checked)} /> {it}
          </label>
        )
      })}
    </div>
  )
}

export default function App(){
  const [text,setText]=useState('')
  const [entities,setEntities]=useState([])
  const [events,setEvents]=useState([])
  const [analytics,setAnalytics]=useState({})
  const [selectedE,setSelectedE]=useState(new Set(E_TYPES))
  const [selectedEv,setSelectedEv]=useState(new Set(EVENT_TYPES))
  const [dataset,setDataset]=useState([])
  const [noteIdx,setNoteIdx]=useState(0)
  const [batch,setBatch]=useState({files:[],totals:null})
  const [useML,setUseML]=useState(false)

  const [sourceInfo,setSourceInfo]=useState({name:'demo',extra:'',count:0})
  const [mtSpecialties,setMtSpecialties]=useState([])
  const [chosenSpec,setChosenSpec]=useState('')

  useEffect(()=>{
    getDataset().then(ds=>{ setDataset(ds); setSourceInfo({name:'demo',extra:'',count:ds.length}) })
    getMTSpecialties().then(d=>setMtSpecialties(d.specialties||[])).catch(()=>{})
  },[])

  const filteredEntities = useMemo(()=>entities.filter(e=>selectedE.has(e.type)), [entities,selectedE])
  const filteredEvents = useMemo(()=>events.filter(e=>selectedEv.has(e.type)), [events,selectedEv])

  useEffect(()=>{
    const t=setTimeout(()=>{
      if(!text.trim()){ setEntities([]); setEvents([]); setAnalytics({}); return }
      extract({ text, use_ml: useML })
        .then(({entities,events,analytics})=>{ setEntities(entities||[]); setEvents(events||[]); setAnalytics(analytics||{}) })
        .catch(console.error)
    },300)
    return ()=>clearTimeout(t)
  },[text,useML])

  const toggleSet=(setter)=>(key,on)=>setter(prev=>{ const next=new Set(prev); if(on) next.add(key); else next.delete(key); return next })

function highlight(){
  const spans=[...filteredEntities].sort((a,b)=>a.start-b.start||b.end-a.end)
  let out='', cursor=0
  const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
  for(const s of spans){
    if(s.start < cursor) continue
    out += esc(text.slice(cursor, s.start))
    const neg = s.negated ? ' negated' : ''
    const tip = s.negated ? `${s.type} (negated)` : s.type
    out += `<span class="entity tag-${s.type}${neg}" title="${tip}">${esc(text.slice(s.start, s.end))}</span>`
    cursor = s.end
  }
  out += esc(text.slice(cursor))
  return {__html: out || '<em class="muted">(No text)</em>'}
}


  async function doUpload(ev){
    const files = ev.target.files
    if(!files?.length) return
    const data = await uploadFiles(files, { use_ml: useML })
    setBatch(data)
  }

  async function downloadEntities(){
    const blob = await exportEntities(entities)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'entities.csv'; a.click(); URL.revokeObjectURL(url)
  }
  async function downloadEvents(){
    const blob = await exportEvents(events)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'events.csv'; a.click(); URL.revokeObjectURL(url)
  }

  function loadBatchFile(idx){
    const f = batch.files[idx]; if(!f) return
    setText(f.text||''); setEntities(f.entities||[]); setEvents(f.events||[]); setAnalytics(f.analytics||{})
    setTimeout(()=>document.querySelector('.highlighted')?.scrollIntoView({behavior:'smooth', block:'start'}),0)
  }

  const entityCountSum = a => !a || !a.entity_counts ? 0 : Object.values(a.entity_counts).reduce((x,y)=>x+y,0)

  return (
    <div>
      <header>
        <h1>Healthcare NER & Event Extraction</h1>
        <span className="badge">Data: {sourceInfo.name}{sourceInfo.extra?` / ${sourceInfo.extra}`:''} — {sourceInfo.count} notes</span>
        <p className="muted">React UI · Rule-based backend · Edit rules in <code>backend/rules/healthcare_rules.yml</code></p>
      </header>

      <main className="grid">
        <section className="card">
          <h2>Input</h2>

          <div className="row">
            <label htmlFor="noteSelect">Load demo note:</label>
            <select id="noteSelect" value={noteIdx} onChange={e=>setNoteIdx(+e.target.value)}>
              {dataset.map((d,i)=>(<option key={i} value={i}>{i+1}. {d.title}</option>))}
            </select>
            <button onClick={()=>{ setText(dataset[noteIdx]?.text||''); setSourceInfo(si=>({...si,name:'demo',extra:'',count:1})) }}>Load</button>
          </div>

          <div className="row">
            <label>MT Specialty:</label>
            <select value={chosenSpec} onChange={e=>setChosenSpec(e.target.value)}>
              <option value="">(All specialties)</option>
              {mtSpecialties.map((s,i)=>(<option key={i} value={s}>{s}</option>))}
            </select>
            <button className="ghost" onClick={async()=>{
              try{ const d=await getMTSpecialties(); setMtSpecialties(d.specialties||[]) }catch(e){ alert(e.message) }
            }}>Refresh List</button>
            <button onClick={async()=>{
              try{
                const items = await getMTNotes(10, chosenSpec ? { specialty: chosenSpec } : {})
                setDataset(items); setNoteIdx(0)
                if(items[0]?.text) setText(items[0].text)
                setSourceInfo({name:'MTSamples', extra: chosenSpec || 'All', count: items.length})
              }catch(e){ alert(`MTSamples load error: ${e.message}`) }
            }}>Load MTSamples</button>
          </div>

          <textarea value={text} onChange={e=>setText(e.target.value)} placeholder="Paste clinical note or load MTSamples..." />

          <h3>Entity Types</h3>
          <Chipbar items={E_TYPES} selected={selectedE} onToggle={toggleSet(setSelectedE)} />

          <h3>Event Types</h3>
          <Chipbar items={EVENT_TYPES} selected={selectedEv} onToggle={toggleSet(setSelectedEv)} />

          <h3>Options</h3>
          <label className="chip"><input type="checkbox" checked={useML} onChange={e=>setUseML(e.target.checked)} /> Use ML stage (if installed)</label>

          <div className="row"><button onClick={()=>setText('')} className="ghost">Clear</button></div>

          <h3>Batch Upload (.txt)</h3>
          <input type="file" multiple accept=".txt" onChange={doUpload} />

          {batch.files.length > 0 && (
            <div style={{ marginTop: '12px' }}>
              <h3>Batch Results</h3>
              <table>
                <thead><tr><th>#</th><th>File</th><th>Entities</th><th>Events</th><th></th></tr></thead>
                <tbody>
                  {batch.files.map((f,i)=>(
                    <tr key={i}>
                      <td>{i+1}</td>
                      <td>{f.file}</td>
                      <td>{entityCountSum(f.analytics)}</td>
                      <td>{Object.values(f.analytics?.event_counts||{}).reduce((a,b)=>a+b,0)}</td>
                      <td><button onClick={()=>loadBatchFile(i)}>Load to Viewer</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card">
          <h2>Highlighted Text</h2>
          <div className="highlighted" dangerouslySetInnerHTML={highlight()} />

          <div className="row spaced">
            <button onClick={downloadEntities}>Export Entities CSV</button>
            <button onClick={downloadEvents}>Export Events CSV</button>
          </div>

          <div className="grid two">
            <div>
              <h3>Entities</h3>
              <table>
                <thead><tr><th>Type</th><th>Text</th><th>Pos</th></tr></thead>
                <tbody>
                  {filteredEntities.map((e,i)=>(
                    <tr key={i}><td>{e.type}</td><td>{e.text}</td><td>{e.start}-{e.end}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h3>Events</h3>
              <table>
                <thead><tr><th>Type</th><th>Trigger</th><th>Arguments</th></tr></thead>
                <tbody>
                  {filteredEvents.map((ev,i)=>{
                    const args = Object.entries(ev.arguments||{}).map(([k,v])=>`${k}: ${v}`).join(', ')
                    return (<tr key={i}><td>{ev.type}</td><td>{ev.trigger}</td><td>{args}</td></tr>)
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </main>

      <footer><small>For academic demo. Avoid real PHI.</small></footer>
    </div>
  )
}
