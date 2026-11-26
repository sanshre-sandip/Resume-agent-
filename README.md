# Nhyapu Craft

A local resume builder. Open it in your browser, edit resumes, preview them, and export files. There are no accounts or sign-in screens. Resume data is stored as JSON files on the computer running the app.

## Run locally

Python 3.12+ is recommended. From the project folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --app-dir resume_creator/backend --reload --host 127.0.0.1 --port 8001
```

Open <http://127.0.0.1:8001/>. The workspace is also available at `/workspace`; API documentation is at `/docs`. Resume records are written to `DATA_DIR` and generated files to `GENERATED_DIR`; both can be set in `.env`. Keep the server bound to `127.0.0.1` for a private local app.

PDF export uses `pdflatex` or LibreOffice when installed. Word export is available when the document renderer is installed. Manual editing, saving, and preview do not need an AI provider. AI options are optional and may send selected resume text to the provider you choose.

## What it includes

- Multiple locally saved resumes with create, reopen, rename, duplicate, and delete actions.
- Resume templates, live preview, PDF preview/download, and Word export where supported.
- Optional AI editing and layout suggestions.
- JSON file storage; no database or account setup is needed.

For a quick syntax check, run `node --check resume_creator/frontend/static/app.js`.
