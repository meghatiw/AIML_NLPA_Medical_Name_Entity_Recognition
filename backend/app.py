from flask import Flask, request, jsonify, send_file
from datetime import datetime
import re, os, io, csv, json, hashlib

# Optional ML stage (safe fallback if not installed)
try:
    from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
    HF_AVAILABLE = True
except Exception:
    HF_AVAILABLE = False
try:
    import yaml
except Exception:
    yaml = None

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(APP_ROOT, 'rules', 'healthcare_rules.yml')
DATASET_PATH = os.path.join(APP_ROOT, 'data', 'demo_healthcare_notes.json')

# MTSamples config & cache path
MTSAMPLES_CSV_URL = os.getenv(
    "MTSAMPLES_CSV_URL",
    "https://raw.githubusercontent.com/NinaFatehi/Medical-Transcriptions-Preprocessing/refs/heads/main/mtsamples.csv"
)
MTSAMPLES_CSV_PATH = os.getenv(
    "MTSAMPLES_CSV_PATH",
    os.path.join(APP_ROOT, "data", "mtsamples", "mtsamples.csv")
)

app = Flask(__name__)

# ---------------- Rules ----------------
def load_rules():
    if yaml is None:
        raise RuntimeError("pyyaml is not installed. Run: pip install -r requirements.txt")
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

def rules_hash():
    try:
        with open(RULES_PATH, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        return "no_rules"

# --------------- Regex helpers ---------------
def _rx_from_words(words, ignore_case=True):
    words = [w for w in (words or []) if w]
    if not words: return None
    words = sorted(set(words), key=lambda x: -len(x))  # longest first
    patt = r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b"
    return re.compile(patt, re.IGNORECASE if ignore_case else 0)

def _rx_compile(patt, ignore_case=True):
    if not patt: return None
    return re.compile(patt, re.IGNORECASE if ignore_case else 0)

# --------------- Extraction core ---------------
def extract_entities(text, rules):
    """
    Auto-discovers all dictionaries under rules['entities'] and all regexes under rules['patterns'].
    """
    E = []
    ignore_case = (rules.get('flags') or {}).get('ignore_case', True)
    ents = (rules.get('entities') or {})
    pats = (rules.get('patterns') or {})

    dict_res = {k: _rx_from_words(v, ignore_case) for k, v in ents.items()}
    patt_res = {k: _rx_compile(v, ignore_case) for k, v in pats.items()}

    def push(_type, m):
        E.append({'type': _type, 'text': m.group(0), 'start': m.start(), 'end': m.end()})

    # dictionaries
    for key, rx in dict_res.items():
        if not rx: continue
        label = key[:-1] if key.endswith('S') else key  # MEDICATIONS -> MEDICATION
        for m in rx.finditer(text):
            push(label, m)

    # patterns (AGE/DATE/WEIGHT/BP/GLUCOSE…)
    for key, rx in patt_res.items():
        if not rx: continue
        for m in rx.finditer(text):
            push(key, m)

    # merge overlaps: prefer longer span
    E.sort(key=lambda x: (x['start'], -(x['end'] - x['start'])))
    merged, last_end = [], -1
    for e in E:
        if not merged:
            merged.append(e); last_end = e['end']; continue
        if e['start'] < last_end:
            continue
        merged.append(e); last_end = e['end']
    return merged

def extract_events(text, rules, entities=None, wanted_types=None, window=100):
    events_cfg = (rules.get('events') or {})
    ignore_case = (rules.get('flags') or {}).get('ignore_case', True)
    flags = re.IGNORECASE if ignore_case else 0
    ent_list = entities or extract_entities(text, rules)

    def ents_near(idx, w=window):
        L, R = idx - w, idx + w
        return [e for e in ent_list if e['start'] >= L and e['end'] <= R]

    out = []
    for ev_type, cfg in events_cfg.items():
        if wanted_types and ev_type not in wanted_types:
            continue
        trig_words = cfg.get('triggers', [])
        if not trig_words: continue
        trig_re = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in trig_words) + r")\b", flags)
        for m in trig_re.finditer(text):
            nearby = ents_near(m.start())
            args = {}
            for role, ref in (cfg.get('args') or {}).items():
                if isinstance(ref, str) and ref.startswith('@'):
                    key = ref[1:]                # e.g. MEDICATIONS
                    label = key[:-1] if key.endswith('S') else key
                    for cand in sorted(nearby, key=lambda e: abs((e['start']+e['end'])/2 - m.start())):
                        if cand['type'].upper() == label.upper():
                            args[role] = cand['text']; break
            out.append({'type': ev_type, 'trigger': m.group(0), 'start': m.start(),
                        'end': m.end(), 'arguments': args})
    return out

def analyze(entities, events):
    from collections import Counter
    ec = Counter(e['type'] for e in entities)
    evc = Counter(e['type'] for e in events)
    top_mentions = Counter(e['text'].lower() for e in entities).most_common(10)
    return {'entity_counts': dict(ec), 'event_counts': dict(evc), 'top_mentions': top_mentions}

# --------------- Optional ML ---------------
HF_MODEL_NAME = "d4data/biomedical-ner-all"
_hf_pipe = None
def ml_ready():
    global _hf_pipe
    if not HF_AVAILABLE: return False
    if _hf_pipe is None:
        try:
            tok = AutoTokenizer.from_pretrained(HF_MODEL_NAME)
            mdl = AutoModelForTokenClassification.from_pretrained(HF_MODEL_NAME)
            _hf_pipe = pipeline("token-classification", model=mdl, tokenizer=tok, aggregation_strategy="simple")
        except Exception:
            return False
    return True
def ml_entities(text):
    if not ml_ready(): return []
    MAP = {"DISEASE":"DISEASE","CHEMICAL":"MEDICATION","DRUG":"MEDICATION","MED":"MEDICATION",
           "SYMPTOM":"SYMPTOM","TEST":"LAB_TEST","PROC":"PROCEDURE"}
    spans = _hf_pipe(text); out=[]
    for s in spans:
        t = MAP.get((s.get("entity_group") or "").upper())
        if t:
            out.append({"type":t, "text":s["word"], "start":int(s["start"]), "end":int(s["end"]), "score":float(s.get("score",0))})
    return out

# --------------- MTSamples auto-download ---------------
_MTSAMPLES_CACHE = None
_MTSAMPLES_SPECIALTIES = None

def _download_mtsamples_to_disk():
    if os.path.exists(MTSAMPLES_CSV_PATH):
        return {"downloaded": False, "path": MTSAMPLES_CSV_PATH, "size": os.path.getsize(MTSAMPLES_CSV_PATH)}
    os.makedirs(os.path.dirname(MTSAMPLES_CSV_PATH), exist_ok=True)
    import urllib.request
    with urllib.request.urlopen(MTSAMPLES_CSV_URL) as resp:
        data = resp.read()
    with open(MTSAMPLES_CSV_PATH, "wb") as f:
        f.write(data)
    return {"downloaded": True, "path": MTSAMPLES_CSV_PATH, "size": len(data)}

def _ensure_mtsamples_loaded():
    global _MTSAMPLES_CACHE, _MTSAMPLES_SPECIALTIES
    if _MTSAMPLES_CACHE is not None: return
    _download_mtsamples_to_disk()
    with open(MTSAMPLES_CSV_PATH, 'r', encoding='utf-8', errors='ignore', newline='') as f:
        reader = csv.DictReader(f)
        rows, specs = [], set()
        for i, row in enumerate(reader):
            spec = (row.get('medical_specialty') or row.get('specialty') or '').strip()
            title = (row.get('sample_name') or row.get('title') or '').strip() or f"Note {i+1}"
            trans = (row.get('transcription') or row.get('clean_text') or row.get('text') or '').strip()
            if not trans: continue
            rows.append({'title': f"{title} — {spec}" if spec else title, 'text': trans, 'specialty': spec})
            if spec: specs.add(spec)
        _MTSAMPLES_CACHE = rows
        _MTSAMPLES_SPECIALTIES = sorted(specs)

def load_mtsamples(limit=10, specialty=None):
    _ensure_mtsamples_loaded()
    items = list(_MTSAMPLES_CACHE)
    if specialty:
        want = {s.strip().lower() for s in specialty.split('|') if s.strip()}
        if want:
            items = [r for r in items if (r.get('specialty','').lower() in want)]
    return items[:int(limit)]

# ---------------- Routes ----------------
@app.get("/")
def root():
    ok = os.path.exists(MTSAMPLES_CSV_PATH)
    size = os.path.getsize(MTSAMPLES_CSV_PATH) if ok else 0
    return jsonify({"status":"ok","rules_version":rules_hash(),"mtsamples_cached":ok,"bytes":size})

@app.get("/rules/debug")
def rules_debug():
    r = load_rules()
    return jsonify({
        "path": RULES_PATH,
        "has_entities": bool(r.get("entities")),
        "has_patterns": bool(r.get("patterns")),
        "entity_sections": sorted(list((r.get("entities") or {}).keys())),
        "pattern_names": sorted(list((r.get("patterns") or {}).keys()))
    })

@app.get("/mtsamples/specialties")
def mtsamples_specialties():
    _ensure_mtsamples_loaded()
    return jsonify({"count": len(_MTSAMPLES_CACHE), "specialties": _MTSAMPLES_SPECIALTIES})

@app.get("/mtsamples/notes")
def mtsamples_notes():
    limit = int(request.args.get("limit","10"))
    spec = request.args.get("specialty")
    return jsonify(load_mtsamples(limit=limit, specialty=spec))

@app.get("/dataset")
def dataset():
    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))

@app.post("/extract")
def api_extract():
    data = request.get_json(force=True)
    text = data.get('text','')
    use_ml = bool(data.get('use_ml', False))
    rules = load_rules()

    ents = extract_entities(text, rules)     # UI filters are client-side only
    if use_ml:
        try:
            ents = sorted(ents + ml_entities(text), key=lambda x: (x['start'], -(x['end']-x['start'])))
            # de-overlap simple
            merged, last = [], -1
            for e in ents:
                if not merged: merged.append(e); last = e['end']; continue
                if e['start'] < last: continue
                merged.append(e); last = e['end']
            ents = merged
        except Exception:
            pass

    evs = extract_events(text, rules, entities=ents)
    return jsonify({"entities": ents, "events": evs, "analytics": analyze(ents, evs)})

@app.post("/upload")
def api_upload():
    use_ml = request.form.get('use_ml', '0') in ('1','true','True')
    files = request.files.getlist('files')
    bundle, all_e, all_v = [], [], []
    for f in files:
        raw = f.read()
        try: text = raw.decode('utf-8', errors='ignore')
        except Exception: text = raw.decode('latin-1', errors='ignore')
        rules = load_rules()
        ents = extract_entities(text, rules)
        if use_ml:
            try:
                ents = sorted(ents + ml_entities(text), key=lambda x: (x['start'], -(x['end']-x['start'])))
                merged, last = [], -1
                for e in ents:
                    if not merged: merged.append(e); last = e['end']; continue
                    if e['start'] < last: continue
                    merged.append(e); last = e['end']
                ents = merged
            except Exception: pass
        evs = extract_events(text, rules, entities=ents)

        from collections import Counter
        an = {"entity_counts": dict(Counter(e['type'] for e in ents)),
              "event_counts": dict(Counter(e['type'] for e in evs))}
        all_e.extend([{**e, 'file': f.filename} for e in ents])
        all_v.extend([{**v, 'file': f.filename} for v in evs])
        bundle.append({'file': f.filename, 'text': text, 'entities': ents, 'events': evs, 'analytics': an})

    return jsonify({'files': bundle, 'totals': {}})

@app.post("/export/entities")
def export_entities():
    payload = request.get_json(force=True)
    entities = payload.get('entities', [])
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(['file','type','text','start','end'])
    for e in entities:
        w.writerow([e.get('file',''), e['type'], e['text'], e['start'], e['end']])
    mem = io.BytesIO(out.getvalue().encode('utf-8')); mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True,
                     download_name=f'entities_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')

@app.post("/export/events")
def export_events():
    payload = request.get_json(force=True)
    events = payload.get('events', [])
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(['file','type','trigger','start','end','arguments_json'])
    for e in events:
        w.writerow([e.get('file',''), e['type'], e['trigger'], e['start'], e['end'], json.dumps(e.get('arguments', {}))])
    mem = io.BytesIO(out.getvalue().encode('utf-8')); mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True,
                     download_name=f'events_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')

if __name__ == '__main__':
    app.run(debug=True)
