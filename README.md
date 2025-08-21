# Healthcare NER + Event Extraction — Flask API + React UI

Rule-based Named Entity Recognition (NER) & Event Extraction for the **Healthcare** domain.  
**No spaCy/NLTK NER** — dictionaries + regex + YAML config. React frontend talks to Flask API.

## Project Layout
```
healthcare-ner-event-extraction/
├─ backend/                  # Flask API + rules + demo dataset
│  ├─ app.py
│  ├─ requirements.txt
│  ├─ rules/
│  │  └─ healthcare_rules.yml
│  └─ data/
│     └─ demo_healthcare_notes.json
└─ frontend-react/           # React (Vite) frontend
   ├─ index.html
   ├─ vite.config.js
   ├─ package.json
   └─ src/
      ├─ main.jsx
      ├─ App.jsx
      ├─ api.js
      └─ styles.css
```

---

## 1) Prerequisites
- **Python 3.10+**
- **Node.js 18+** & **npm 9+** (or Node 20/22 is fine)

---

## 2) Backend Setup (Flask)
```bash
cd backend
python -m venv .venv
# mac/linux
source .venv/bin/activate
# windows powershell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python app.py
```
Flask runs at **http://127.0.0.1:5000**.

---

## 3) Frontend Setup (React + Vite)
Open a new terminal:
```bash
cd frontend-react
npm install
npm run dev
```
Vite runs at **http://127.0.0.1:5173** and **proxies** API calls to Flask (see `vite.config.js`).

---

## 4) Use the App
1. Open **http://127.0.0.1:5173** in your browser.
2. Load a demo note from the dropdown (or paste your own text).
3. Toggle **Entity** & **Event** type chips to filter.
4. See **highlighted** entities in real time.
5. Try **.txt** batch upload; check console for totals.
6. Click **Export Entities/Events** to download CSVs.

---

## 5) Customize Rules
Edit `backend/rules/healthcare_rules.yml`:
- Add diseases/medications/etc. under `entities:`
- Tweak regex under `patterns:` (e.g., `DOSAGE`, `DATE`)
- Update `events:` triggers & argument bindings

Restart Flask if needed.

---

## 6) Optional: Build for Production
Build the React app:
```bash
cd frontend-react
npm run build
```
This outputs a `/dist` folder. You can serve it with any static server (Nginx, Netlify, etc.) and keep Flask as a separate API service.

---

## 7) Notes
- Proxy avoids CORS during dev. If you skip Vite proxy and call Flask directly from a different origin, enable CORS on Flask.
- This is **rule-based** and intentionally simple. Extend YAML dictionaries for better coverage.

Enjoy! 🚀
