# Nhyapu Craft

Nhyapu Craft is a private, account-based resume builder. The Phase 1 app uses FastAPI and a responsive HTML/CSS/JavaScript frontend. Manual editing and resume export do not require an AI provider. It supports five templates, multiple resumes per account, live preview, PDF preview/download, and Word export when the host has the required document renderer.

## Current architecture

```text
Browser (same-origin UI)
  ├── Public landing page and authentication screens
  └── Authenticated workspace
        ├── Editor, template preview, autosave, chat cache
        └── FastAPI JSON API
              ├── Signed session + CSRF checks
              ├── Per-user resume/layout ownership checks
              ├── Atomic JSON record files in DATA_DIR
              └── Private generated .tex/.docx/.pdf in GENERATED_DIR
```

The project intentionally retains file-based storage. On Linux, collection writes use a process lock and atomic replacement. This is suitable for local development or a single application host with persistent disks and backups. It is not a horizontally scalable database: keep a single application instance for writes, mount persistent storage, and back it up. A hosted deployment that needs multiple application instances should migrate the data-store interface to PostgreSQL before enabling scale-out.

## Local development (no Docker)

Python 3.12+ is recommended. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --app-dir resume_creator/backend --reload --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/`, register a test account, then use the workspace. API docs are at `/docs`; `/workspace` serves the editor UI and redirects signed-out users to login in the browser.

Run automated checks:

```bash
PYTHONPATH=resume_creator/backend python -m unittest discover -s resume_creator/backend/tests -v
node --check resume_creator/frontend/static/app.js
node --check resume_creator/frontend/static/auth.js
node --check resume_creator/frontend/static/account.js
```

PDF export tries `pdflatex` first and then headless LibreOffice to convert the generated Word document. Install either renderer on the host. In restricted containers where neither renderer can write its runtime profile, PDF generation reports unavailable; Word export remains available. The PDF text should be selectable/searchable when the renderer is available.

## Features in this release

- Landing page, FAQ, privacy and service-information pages.
- Email/password registration and login; optional email verification and password recovery through SMTP.
- Google OpenID Connect sign-in when credentials are configured.
- Expiring signed session cookies, CSRF checks, auth attempt throttling, and server-side ownership checks.
- Create, reopen, autosave, rename, duplicate, and delete multiple resumes per user.
- Five templates: ATS-Friendly Standard, Modern Minimalist, Student & Fresh Graduate, Technical Developer, and AI/ML Research.
- Resume sections for profile, headline, summary, skills, work, education, projects, certifications, awards, languages, and extra links.
- A4 and US Letter sizing, live preview, PDF preview/download, and Word export when the renderer is available.
- AI assistance is optional. Users can enter their own provider key in AI Settings; it stays in that browser tab's session storage and is sent to the app only for an AI action. It is excluded from resume data and persistent account files. Server-configured provider keys remain supported as a fallback.

The UI includes a layout/chat assistant. Cloud AI operations require a user-entered key or a server-configured provider. No AI feature is needed to manually create, edit, save, preview, or export a resume. Users must review AI suggestions; the assistant is instructed not to invent qualifications or achievements.

## Environment configuration

Copy `.env.example` to `.env` for local use. The example contains placeholders only. For production, set a randomly generated `SESSION_SECRET` of at least 32 characters, `APP_ENV=production`, and the public URL. Do not commit `.env` or place provider secrets in frontend code.

- Email verification and password recovery use Brevo SMTP (`smtp-relay.brevo.com:587` with STARTTLS). Configure `SMTP_USERNAME` with the SMTP login shown by Brevo, `SMTP_PASSWORD` with the Brevo SMTP key (not its API key), and `SMTP_FROM_EMAIL` with a verified sender. Keep `REQUIRE_EMAIL_VERIFICATION=true` for production after these values are set; registration fails safely if verification is required but email delivery is not configured.
- Google OAuth needs a Google OAuth web client. Set the exact callback to `https://craft.nhyapu.space/api/auth/google/callback` in the provider console and in `GOOGLE_REDIRECT_URI`.
- Server-side AI provider secrets are optional fallbacks: OpenAI, Anthropic, Google AI, OpenRouter, or Groq. Users can instead provide their own key in AI Settings. Ollama can point to a local service. A cloud AI edit sends the selected resume text to that provider after the user requests the edit and confirms the disclosure.
- `DATA_DIR` and `GENERATED_DIR` must point to persistent, private storage. `GENERATED_DIR` contains private resume artifacts. Restrict file permissions and back up both locations.

## Deployment at craft.nhyapu.space (single-host, no Docker)

1. Provision a Linux VM or platform that supports FastAPI/Uvicorn, persistent disk, and the chosen PDF renderer. Create a dedicated unprivileged service account.
2. Install Python and project requirements. Install `pdflatex` or LibreOffice on that host if PDF generation is required. LibreOffice must be able to create a headless user profile and write in the generated directory.
3. Create a persistent data volume outside the checkout. Set `DATA_DIR` and `GENERATED_DIR` to directories on it, owned by the service account. Use private permissions (for example, directory mode `0700`). Example service and Caddy reverse-proxy configuration are in `deploy/`.
4. Create a production `.env` from `.env.example`, set a strong `SESSION_SECRET`, `APP_ENV=production`, `PUBLIC_BASE_URL=https://craft.nhyapu.space`, CORS origin, OAuth callback, and SMTP values. Add provider keys only if the AI assistant will be enabled.
5. Run Uvicorn behind a TLS-terminating reverse proxy such as Caddy. The sample Caddyfile obtains TLS automatically. Route `craft.nhyapu.space` to the FastAPI process, preserve the `Host` header, enforce HTTPS, and configure trusted proxy handling if applicable. Do not expose the Uvicorn port publicly.
6. Point the domain DNS record to the host and provision an HTTPS certificate before allowing sign-in. The session cookie is marked Secure in production.
7. Start with one Uvicorn worker while using JSON files. Configure a system service/supervisor for restart-on-failure. Check `/health` after deployment.
8. Schedule encrypted backups of `DATA_DIR` and `GENERATED_DIR`, test restore procedures, and define how long backup copies remain after account deletion.

There is no database migration step in the current file-storage implementation. Do not run multiple independent app instances against separate local disks: users would see different data. This deployment target has not been deployed or DNS-verified by this repository task.

## Security and data notes

- Resume IDs are identifiers, not authorization. API methods check the authenticated owner before read, write, delete, and export.
- The server does not return internal file paths for download; artifact paths are constrained to the owner's generated directory.
- Resume content and credentials are not intentionally logged. Keep application and proxy logs access-controlled.
- Browser local storage is used for layout-assistant conversation/undo cache and AI model preferences. User-entered provider keys are held separately in tab-scoped session storage and are not included in the authoritative resume record.
- Account deletion removes the account, resume/layout records, and that account's generated files from active storage. Operator backups may persist until their documented expiry.
- `privacy.html` and `terms.html` are implementation summaries and need jurisdiction-specific review before public launch.

## Useful routes

| Route | Purpose |
| --- | --- |
| `/` | Public landing page |
| `/register`, `/login` | Authentication UI |
| `/workspace` | Protected resume workspace UI |
| `/account` | Account settings and deletion |
| `/health` | Basic health check |
| `/docs` | FastAPI API documentation |
