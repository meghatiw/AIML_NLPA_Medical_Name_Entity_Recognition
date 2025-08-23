export async function extract(payload){
  const res = await fetch('/extract', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  })
  return res.json()
}

export async function uploadFiles(files, opts = {}){
  const fd = new FormData()
  ;[...files].forEach(f=>fd.append('files', f))
  if (opts.use_ml != null) fd.append('use_ml', opts.use_ml ? '1' : '0')
  const res = await fetch('/upload', { method:'POST', body: fd })
  return res.json()
}

export async function exportEntities(entities){
  const res = await fetch('/export/entities', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({entities})
  })
  return res.blob()
}

export async function exportEvents(events){
  const res = await fetch('/export/events', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({events})
  })
  return res.blob()
}

export async function getDataset(){
  const res = await fetch('/dataset')
  return res.json()
}

export async function getMTSpecialties(){
  const res = await fetch('/mtsamples/specialties')
  const text = await res.text()
  let body; try{ body = JSON.parse(text) }catch{ body = text }
  if(!res.ok){ throw new Error(body?.error || 'Failed to load specialties') }
  return body
}

export async function getMTNotes(limit = 10, q = {}){
  const params = new URLSearchParams({ limit: String(limit), ...q })
  const res = await fetch(`/mtsamples/notes?${params.toString()}`)
  const text = await res.text()
  let body; try{ body = JSON.parse(text) }catch{ body = text }
  if(!res.ok){ throw new Error(body?.error || `MTSamples fetch failed: ${res.status}`) }
  return body // [{title, text, specialty}]
}
