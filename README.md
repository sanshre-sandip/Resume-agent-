# AI Resume Creator

AI-powered resume generation platform built with FastAPI, LangGraph, LangChain, a responsive HTML/CSS/JavaScript interface, and local JSON file storage.

## Architecture

Web UI -> FastAPI -> LangGraph Workflow -> Local JSON files

### LangGraph Nodes
1. User Profile Validation
2. Role context retrieval for resume tailoring
3. Resume Optimization
4. Resume Structuring
5. LaTeX Rendering
6. Export (PDF/DOCX)

### Data Flow Diagram

```mermaid
flowchart TD
    subgraph Frontend["Web Frontend"]
        FORM[User Form Fields]
        SUBMIT[POST /api/resume/create]
    end

    subgraph FastAPI["FastAPI Backend"]
        ROUTER[Router<br/>resumes.py]
        VALIDATE[Pydantic Validation<br/>CreateResumeRequest]
    end

    subgraph Graph["LangGraph Workflow"]
        N1[Node 1: Validate<br/>validate_node]
        N2[Node 2: Research<br/>research_node]
        N3[Node 3: Optimize<br/>optimize_node]
        N4[Node 4: Structure<br/>structure_node]
        N5[Node 5: Render<br/>render_node]
        N6[Node 6: Export<br/>export_node]
    end

    subgraph Agents["Agent Layer"]
        RA[Research Agent]
        OA[Optimization Agent]
        SA[Structuring Agent]
        RDA[LaTeX Renderer]
        EA[Export Agent]
    end

    subgraph LLM["LLM Providers"]
        LLMF[llm_providers.py<br/>OpenAI | Anthropic | Google | Ollama | OpenRouter]
    end

    subgraph Services["Services"]
        RS[Research Service]
        RSCache[(Local JSON cache)]
    end

    subgraph Storage["Storage"]
        DB[(JSON files<br/>users, resumes, research cache)]
        TEX[.tex Template]
        FS[Generated Files<br/>.tex / .pdf / .docx]
    end

    subgraph Response["Response"]
        OUT[ResumeDetailResponse<br/>structured_data, latex, pdf, docx]
        DL[Download Buttons<br/>Web UI]
    end

    FORM --> SUBMIT --> ROUTER
    ROUTER --> VALIDATE
    ROUTER --> DB
    VALIDATE --> N1 --> N2 --> N3 --> N4 --> N5 --> N6

    N2 --> RA --> LLMF
    N2 --> RS --> RSCache

    N3 --> OA --> LLMF
    N4 --> SA --> LLMF
    N5 --> RDA --> TEX
    N6 --> EA --> FS

    N6 --> ROUTER
    ROUTER --> DB
    ROUTER --> OUT --> DL
```

## Project Structure

```
resume_creator/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI application
│       ├── config.py            # Settings and environment configuration
│       ├── database/
│       │   └── file_store.py    # JSON file persistence
│       ├── schemas/
│       │   └── schemas.py       # Pydantic request/response schemas
│       ├── routers/
│       │   ├── resumes.py       # Resume endpoints
│       ├── agents/
│       │   ├── research_agent.py
│       │   ├── optimization_agent.py
│       │   ├── structuring_agent.py
│       │   ├── rendering_agent.py
│       │   └── export_agent.py
│       ├── graph/
│       │   └── resume_graph.py  # LangGraph workflow
│       ├── services/
│       │   ├── research_service.py
│       │   └── resume_service.py
│       ├── templates/           # LaTeX templates (*.tex)
│       └── utils/
│           ├── llm_providers.py # OpenAI, Anthropic, Google, Ollama, OpenRouter
│           ├── renderer.py
│           └── latex_utils.py
├── frontend/
│   └── static/                  # HTML, CSS, and JavaScript UI
├── generated/                   # Generated PDFs and DOCX
├── uploads/                     # User uploads
└── logs/                        # Application logs
```

## Prerequisites

- Python 3.11+
- Ollama (for local LLM) or API keys for OpenAI/Anthropic/Google/OpenRouter
- TeX Live (for PDF generation) or pandoc (for DOCX conversion)

## Setup

1. Clone the repository and navigate to the project directory:
```bash
cd /home/sandip/Resume_Agent
```

2. Create a virtual environment:
```bash
python3 -m venv res
source res/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment:
```bash
cp .env.example .env
# Edit .env with your LLM credentials (DATA_DIR selects local JSON storage)
```

5. Create required directories:
```bash
mkdir -p generated uploads logs
```

## Running the Application

### Start the application

```bash
uvicorn resume_creator.backend.app.main:app --host 127.0.0.1 --port 8001 --reload
```

Open `http://127.0.0.1:8001` for the resume builder or `http://127.0.0.1:8001/docs` for the API docs.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/resume/create` | Create a new resume |
| GET | `/api/resume/{id}` | Get resume details |
| GET | `/api/resume/{id}/pdf` | Download PDF |
| GET | `/api/resume/{id}/docx` | Download DOCX |
| GET | `/api/templates` | List available templates |

## LLM Providers

Supported providers (configure in `.env`):
- **Ollama** (default, local)
- **OpenAI** (GPT-4o)
- **Anthropic** (Claude)
- **Google** (Gemini)
- **OpenRouter**

## LaTeX Templates

Place `.tex` templates in `resume_creator/backend/app/templates/`:
- `modern.tex`
- `professional.tex`
- `simple.tex`

## Environment Variables

See `.env.example` for all available configuration options.

## Tech Stack

- **Frontend**: Responsive HTML, CSS, and JavaScript
- **Backend**: FastAPI
- **Agent Framework**: LangChain, LangGraph
- **Storage**: Local JSON files in `data/`
- **LLM**: Provider abstraction (OpenAI, Gemini, Claude, Ollama, OpenRouter)
- **Rendering**: Jinja2, LaTeX, pdflatex, Pandoc

## License

MIT
