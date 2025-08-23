# Healthcare NER + Event Extraction — Flask + React (MIMIC-IV Ready)

Rule-based NER & Event extraction for **Healthcare** with optional ML and **MIMIC-IV-Note** integration.

## Run Locally
Backend:
```bash
cd backend
python -m venv .venv
# mac/linux: source .venv/bin/activate
# windows:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Frontend:
```bash
cd frontend-react
npm install
npm run dev
```
Open http://127.0.0.1:5173

## Load MIMIC-IV Discharge Notes (Local Only)
1. Obtain **MIMIC-IV-Note v2.2** via PhysioNet (credentialed access/DUA required).
2. Place the file at:
```
backend/data/mimic-iv-note/note/discharge.csv.gz
```
   or set an env var:
```
MIMIC_DISCHARGE_PATH=/absolute/path/to/discharge.csv.gz
```
3. In the UI click **"Load MIMIC-IV Notes"** (loads up to 10 notes by default).

> **Compliance:** Do not commit or redistribute any MIMIC text. Keep it local and follow the PhysioNet DUA.

## Endpoints
- `POST /extract` — run extraction on text
- `POST /upload` — batch upload `.txt` files
- `GET  /dataset` — demo synthetic dataset
- `GET  /mimic/notes?limit=10&subject_id=&hadm_id=` — stream MIMIC-IV discharge notes

## Sources
- MIMIC-IV (project): https://physionet.org/content/mimiciv/
- MIMIC-IV-Note (notes): https://physionet.org/content/mimic-iv-note/
- License/DUA: https://physionet.org/about/licenses/ and project-specific DUA on PhysioNet

## Accessibility
White theme + **Okabe–Ito** colorblind-safe palette with underlined entity spans.
