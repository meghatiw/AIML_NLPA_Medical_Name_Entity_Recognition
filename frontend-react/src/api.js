export async function extract(payload){
  const res = await fetch('/extract', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})
  return res.json()
}

export async function uploadFiles(files){
  const fd = new FormData()
  ;[...files].forEach(f=>fd.append('files', f))
  const res = await fetch('/upload', {method:'POST', body: fd})
  return res.json()
}

export async function exportEntities(entities){
  const res = await fetch('/export/entities', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({entities})})
  return res.blob()
}

export async function exportEvents(events){
  const res = await fetch('/export/events', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({events})})
  return res.blob()
}

export async function getDataset(){
  const res = await fetch('/dataset')
  return res.json()
}
