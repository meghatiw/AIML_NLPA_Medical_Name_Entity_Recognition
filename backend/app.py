from flask import Flask, request, jsonify, send_file
from datetime import datetime
import re, os, io, csv, json

try:
    import yaml  # pyyaml
except Exception:
    yaml = None

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(APP_ROOT, 'rules', 'healthcare_rules.yml')
DATASET_PATH = os.path.join(APP_ROOT, 'data', 'demo_healthcare_notes.json')

app = Flask(__name__)

# ---------------------- Rules Loader ----------------------

def load_rules():
    if yaml is None:
        raise RuntimeError("pyyaml not installed. Please `pip install -r requirements.txt`.")
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        rules = yaml.safe_load(f)
    return rules

# Compile dictionary -> regex pattern with word boundaries
def dict_to_pattern(words, ignore_case=True):
    escaped = [re.escape(w) for w in sorted(set(words), key=lambda x: -len(x)) if w]
    if not escaped:
        return None
    patt = r"\b(?:" + "|".join(escaped) + r")\b"
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(patt, flags)

# Compile single regex pattern from string
def compile_pattern(patt, ignore_case=True):
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(patt, flags)

# --------------- Extraction Core (Entities & Events) ---------------

def extract_entities(text, rules, wanted_types=None):
    E = []
    ignore_case = rules.get('flags', {}).get('ignore_case', True)

    # Pre-compile entity patterns
    ents = rules.get('entities', {})
    pats = rules.get('patterns', {})

    compiled = {}
    for key, words in ents.items():
        compiled[key] = dict_to_pattern(words, ignore_case)

    compiled_patterns = {k: compile_pattern(v, ignore_case) for k, v in pats.items()}

    # Helper to push entity
    def push(_type, m):
        E.append({
            'type': _type,
            'text': m.group(0),
            'start': m.start(),
            'end': m.end()
        })

    # Dictionary-driven types
    dict_types = ['MEDICATIONS','DISEASES','SYMPTOMS','PROCEDURES','TREATMENTS','LAB_TESTS','PATIENT_TITLES','GENDERS']
    for t in dict_types:
        if compiled.get(t):
            for m in compiled[t].finditer(text):
                push(t[:-1] if t.endswith('S') else t, m)  # normalize: MEDICATIONS -> MEDICATION

    # Regex-driven types
    regex_map = {
        'AGE': compiled_patterns.get('AGE'),
        'DOSAGE': compiled_patterns.get('DOSAGE'),
        'FREQUENCY': compiled_patterns.get('FREQUENCY'),
        'ROUTE': compiled_patterns.get('ROUTE'),
        'DATE': compiled_patterns.get('DATE'),
    }
    for t, patt in regex_map.items():
        if patt:
            for m in patt.finditer(text):
                push(t, m)

    # Merge overlaps: prefer longer spans, then earlier
    E.sort(key=lambda x: (x['start'], -(x['end']-x['start'])))
    merged = []
    last_end = -1
    for e in E:
        if not merged:
            merged.append(e); last_end = e['end']; continue
        if e['start'] < last_end:  # overlap -> keep the longer (already sorted by length desc within same start)
            continue
        merged.append(e)
        last_end = e['end']

    # Filter by requested types
    if wanted_types:
        wanted = set(wanted_types)
        merged = [e for e in merged if e['type'] in wanted]

    return merged


def extract_events(text, rules, entities=None, wanted_types=None, window=100):
    """Very simple event extraction: look for triggers, then collect nearby arguments
       by reusing already-detected entities.
    """
    events_cfg = rules.get('events', {})
    ignore_case = rules.get('flags', {}).get('ignore_case', True)
    flags = re.IGNORECASE if ignore_case else 0

    # Index entities by span to fetch arguments near triggers
    ent_list = entities or extract_entities(text, rules)

    # Build quick lookup of entities within any character window
    def ents_near(idx, w=window):
        left, right = idx - w, idx + w
        return [e for e in ent_list if e['start'] >= left and e['end'] <= right]

    out = []
    for ev_type, cfg in events_cfg.items():
        if wanted_types and ev_type not in wanted_types:
            continue
        triggers = cfg.get('triggers', [])
        if not triggers:
            continue
        trig_re = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in triggers) + r")\b", flags)
        for m in trig_re.finditer(text):
            args_spec = cfg.get('args', {})
            nearby = ents_near(m.start())
            args = {}
            # Simple arg selection: pick the closest matching entity per role
            for role, ref in args_spec.items():
                if ref.startswith('@'):
                    key = ref[1:]
                    # Map dictionary keys to entity type names used above
                    # e.g., MEDICATIONS -> MEDICATION
                    entity_name = key[:-1] if key.endswith('S') else key
                    # Regex shortcuts like @DOSAGE map directly
                    if key in ['DOSAGE','ROUTE','FREQUENCY','DATE','AGE']:
                        entity_name = key
                    # pick nearest entity of that type
                    candidates = [e for e in nearby if e['type'].upper() == entity_name.upper()]
                    if candidates:
                        # closest center distance
                        candidates.sort(key=lambda e: abs((e['start']+e['end'])/2 - m.start()))
                        args[role] = candidates[0]['text']
            out.append({
                'type': ev_type,
                'trigger': m.group(0),
                'start': m.start(),
                'end': m.end(),
                'arguments': args
            })

    return out


def analyze(entities, events):
    from collections import Counter
    ec = Counter(e['type'] for e in entities)
    top_mentions = Counter(e['text'].lower() for e in entities).most_common(10)
    evc = Counter(e['type'] for e in events)
    return {
        'entity_counts': dict(ec),
        'top_mentions': top_mentions,
        'event_counts': dict(evc)
    }

# ---------------------- API Routes ----------------------

@app.route('/', methods=['GET'])
def root():
    return jsonify({"service": "healthcare-ner-events", "status": "ok"})

@app.route('/extract', methods=['POST'])
def api_extract():
    data = request.get_json(force=True)
    text = data.get('text', '')
    want_entities = data.get('entity_types') or []
    want_events = data.get('event_types') or []

    rules = load_rules()
    entities = extract_entities(text, rules, wanted_types=want_entities or None)
    events = extract_events(text, rules, entities=entities, wanted_types=want_events or None)
    stats = analyze(entities, events)

    return jsonify({
        'entities': entities,
        'events': events,
        'analytics': stats
    })

@app.route('/upload', methods=['POST'])
def api_upload():
    files = request.files.getlist('files')
    rules = load_rules()
    bundle = []
    all_entities, all_events = [], []

    for f in files:
        raw = f.read()
        try:
            text = raw.decode('utf-8', errors='ignore')
        except Exception:
            text = raw.decode('latin-1', errors='ignore')
        entities = extract_entities(text, rules)
        events = extract_events(text, rules, entities=entities)
        all_entities.extend([{**e, 'file': f.filename} for e in entities])
        all_events.extend([{**e, 'file': f.filename} for e in events])
        bundle.append({'file': f.filename, 'text': text, 'entities': entities, 'events': events, 'analytics': analyze(entities, events)})

    return jsonify({'files': bundle, 'totals': analyze(all_entities, all_events)})

@app.route('/export/entities', methods=['POST'])
def export_entities():
    payload = request.get_json(force=True)
    entities = payload.get('entities', [])
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['file','type','text','start','end'])
    for e in entities:
        w.writerow([e.get('file',''), e['type'], e['text'], e['start'], e['end']])
    mem = io.BytesIO(out.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=f'entities_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')

@app.route('/export/events', methods=['POST'])
def export_events():
    payload = request.get_json(force=True)
    events = payload.get('events', [])
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['file','type','trigger','start','end','arguments_json'])
    for e in events:
        w.writerow([e.get('file',''), e['type'], e['trigger'], e['start'], e['end'], json.dumps(e.get('arguments', {}))])
    mem = io.BytesIO(out.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=f'events_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')

@app.route('/dataset', methods=['GET'])
def dataset():
    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
