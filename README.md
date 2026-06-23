# Website Audit Tool

An AI-powered website audit tool that scrapes deterministic page metrics and uses Anthropic Claude to generate actionable SEO and UX insights — with a full LLM interaction audit trail committed back to this repository.

Live demo: **website-audit-tool-eosin.vercel.app**

---

## How It Works

```
  ┌─────────────┐
  │  User / UI  │  Paste a URL → click Analyze
  └──────┬──────┘
         │ POST /analyse
         ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                     FastAPI  (Vercel)                       │
  │                                                             │
  │   POST /scrape ──► PageScraper ──► PageMetrics (JSON)      │
  │                                         │                   │
  │   POST /analyse ────────────────────────┤                   │
  │                                         ▼                   │
  │                               AnthropicClient               │
  │                               (claude-haiku)                │
  │                                         │                   │
  │                               AnalysisResult                │
  │                            + LLMInteraction log             │
  │                                         │                   │
  │                            ┌────────────┴────────────┐      │
  │                            ▼                         ▼      │
  │                     GitHub  API               /tmp (local)  │
  │                  logs/ + scraped/            (fallback only) │
  └─────────────────────────────────────────────────────────────┘
         │
         ▼
  ┌─────────────┐
  │  Browser UI │  Shows metrics instantly, AI insights when ready
  └─────────────┘
```

**Key design choice:** The browser fires `/scrape` and `/analyse` simultaneously. Metrics appear immediately when scraping finishes. AI insights load in parallel — if they timeout or fail, the metrics panel still renders.

---

## Architecture

The project follows **Clean Architecture** — each layer knows only about the layer inside it.

```
  ╔══════════════════════════════════════════════════════════════╗
  ║               DELIVERY  (web + CLI)                         ║
  ║   web/app.py  (FastAPI)          main.py  (CLI)             ║
  ╠══════════════════════════════════════════════════════════════╣
  ║               USE CASES  (orchestration)                     ║
  ║                   AuditPageUseCase                           ║
  ║          scrape → analyse → save scraped + log               ║
  ╠══════════════════╦═══════════════════════════════════════════╣
  ║   ADAPTERS       ║            CORE  (pure domain)            ║
  ║                  ║                                           ║
  ║  PageScraper     ║   PageMetrics   (dataclass, no I/O)       ║
  ║  requests + BS4  ║   AuditResult   (dataclass, no I/O)       ║
  ║                  ║   LLMInteraction(dataclass, no I/O)       ║
  ║  AnthropicClient ║   AnalysisResult(Pydantic — tool schema)  ║
  ║  claude-haiku    ║   InsightSections                         ║
  ║                  ║   Recommendation                          ║
  ║  GitHubStorage   ║                                           ║
  ║  Contents API    ║                                           ║
  ╚══════════════════╩═══════════════════════════════════════════╝
```

### Layer responsibilities

| Layer | Files | Rule |
|---|---|---|
| Core | `core/models.py` | Pure Python dataclasses and Pydantic models. Zero I/O, zero imports from other layers. |
| Adapters | `adapters/scraper.py` `adapters/llm_client.py` `adapters/github_storage.py` | All network I/O lives here. Each adapter converts external data into core types. |
| Use Cases | `use_cases/audit_page.py` | Orchestrates adapters. Knows about core types, never about HTTP or HTML. |
| Delivery | `web/app.py` `main.py` | Wires dependencies, owns request/response format. |

---

## Data Flow

```
  URL (string)
      │
      ▼
  PageScraper.scrape()
      │   requests.get() + BeautifulSoup
      │   ─────────────────────────────
      │   word count       header counts
      │   CTA count        internal links
      │   external links   image alt gaps
      │   meta title       meta description
      │
      ▼
  PageMetrics  ◄── typed dataclass, no AI involved
      │
      ├──► saved to  scraped/<timestamp>_<domain>.json
      │
      ▼
  AnthropicClient.analyze()
      │
      │   ┌─ System Prompt ──────────────────────────────────────┐
      │   │  "You are an expert SEO and UX analyst…              │
      │   │   Every insight MUST cite a specific metric."        │
      │   └──────────────────────────────────────────────────────┘
      │   ┌─ User Prompt (constructed at runtime) ───────────────┐
      │   │  URL: https://example.com                            │
      │   │  Word count: 1 204                                   │
      │   │  Heading structure: h1: 1, h2: 6, h3: 4             │
      │   │  CTAs: 3   Internal links: 22   External links: 8   │
      │   │  Images: 14 total, 2 missing alt text (14.3%)        │
      │   │  Meta title: "…"   Meta description: "…"             │
      │   └──────────────────────────────────────────────────────┘
      │   ┌─ Tool schema (AnalysisResult as JSON Schema) ────────┐
      │   │  tool_choice: { "type": "tool",                      │
      │   │                 "name": "submit_analysis" }          │
      │   │  Forces structured JSON — no free-text response      │
      │   └──────────────────────────────────────────────────────┘
      │
      ▼
  Raw JSON from Claude  (tool_blocks[0].input)
      │
      ├──► Pydantic validates → AnalysisResult
      │
      ▼
  LLMInteraction  ◄── full audit trail captured here
      │   model, tokens, system_prompt, user_prompt, raw_output
      │
      ▼
  saved to  logs/<timestamp>_<domain>.json
      │
      │   via GitHubStorage (if GITHUB_TOKEN + GITHUB_REPO set)
      │   or /tmp fallback (local / unconfigured)
      │
      ▼
  AuditResult  ──► returned to browser / CLI
```

---

## Prompt Log Structure

Every audit run produces two JSON files committed to this repo.

### `scraped/<timestamp>_<domain>.json`

Raw deterministic data — no AI involved.

```json
{
  "url": "https://example.com",
  "scraped_at": "20260623T120000Z",
  "word_count": 1204,
  "header_counts": { "h1": 1, "h2": 6, "h3": 4 },
  "cta_count": 3,
  "internal_links": ["https://example.com/about", "..."],
  "external_links": ["https://partner.com", "..."],
  "images_count": 14,
  "images_missing_alt": 2,
  "meta_title": "Example Domain",
  "meta_description": "This domain is for use in examples."
}
```

### `logs/<timestamp>_<domain>.json`

Full LLM audit trail — everything the model received and returned.

```json
{
  "url": "https://example.com",
  "scraped_at": "20260623T120000Z",
  "metrics": { "...": "same numeric fields as above" },
  "analysis": {
    "insights": {
      "seo_structure":     "The page has 1 H1 and 6 H2 tags…",
      "messaging_clarity": "The meta description at 23 words…",
      "cta_usage":         "With only 3 CTAs detected…",
      "content_depth":     "1 204 words is above average…",
      "ux_concerns":       "2 of 14 images (14.3%) lack alt text…"
    },
    "recommendations": [
      { "priority": 1, "title": "Add alt text to 2 images",
        "reasoning": "14.3% of images have no alt attribute…" },
      "..."
    ]
  },
  "llm": {
    "model": "claude-haiku-4-5-20251001",
    "input_tokens": 541,
    "output_tokens": 312,
    "system_prompt": "You are an expert SEO and UX analyst…",
    "user_prompt": "Audit this web page. Call `submit_analysis`…",
    "raw_output": "{ \"insights\": { ... }, \"recommendations\": [ ... ] }"
  }
}
```

The `llm` block is the complete AI interaction record — what went in, what came out, before any Python processing.

---

## Project Structure

```
website_audit_tool/
│
├── api/
│   └── index.py                    # Vercel entry point — adds src/ to path, imports app
│
├── src/
│   └── website_audit_tool/
│       ├── core/
│       │   └── models.py           # PageMetrics, AuditResult, LLMInteraction,
│       │                           # AnalysisResult, InsightSections, Recommendation
│       │
│       ├── adapters/
│       │   ├── scraper.py          # requests + BeautifulSoup → PageMetrics
│       │   ├── llm_client.py       # Anthropic tool-use API → (AnalysisResult, LLMInteraction)
│       │   └── github_storage.py   # GitHub Contents API → commits files to repo
│       │
│       ├── use_cases/
│       │   └── audit_page.py       # Orchestrates scrape → analyse → save
│       │
│       ├── web/
│       │   ├── app.py              # FastAPI: GET /, POST /scrape /analyse /audit
│       │   └── static/
│       │       └── index.html      # Single-page UI (Tailwind CDN)
│       │
│       └── main.py                 # CLI entry point
│
├── tests/
│   ├── test_models.py              # Domain model unit tests
│   └── test_scraper.py             # Scraper unit tests (mocked HTTP)
│
├── logs/                           # Prompt logs — committed by GitHubStorage on each run
├── scraped/                        # Raw scraped data — committed by GitHubStorage on each run
│
├── vercel.json                     # Routing + 60s function timeout
├── pyproject.toml                  # Package config, deps, pytest/mypy settings
└── requirements.txt                # Pip-installable deps for Vercel
```

---

## Structured Output Design

The LLM is never asked for free text. It is forced to call a tool with a strict JSON schema.

```
  AnthropicClient
       │
       │  tool_choice = { "type": "tool", "name": "submit_analysis" }
       │
       ▼
  AnalysisResult  (Pydantic model used directly as tool input_schema)
       │
       ├── insights: InsightSections
       │       ├── seo_structure      (must cite H-tag counts, meta tags)
       │       ├── messaging_clarity  (must cite word count, meta description)
       │       ├── cta_usage          (must cite exact CTA count)
       │       ├── content_depth      (must cite word count, heading structure)
       │       └── ux_concerns        (must cite link counts, alt-text gaps)
       │
       └── recommendations: list[Recommendation]  (3–5 items)
               ├── priority   int  (1 = highest)
               ├── title      str  (≤ 10 words)
               └── reasoning  str  (must cite at least one metric number)
```

Each field description in the Pydantic model instructs the AI to cite specific numbers — the schema doubles as a prompt reinforcement mechanism.

---

## Local Setup

```bash
# 1. Clone and create virtual environment
git clone https://github.com/samkdataanalytics/website_audit_tool.git
cd website_audit_tool
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -e .

# 3. Set environment variables
cp .env.example .env
# Edit .env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   GITHUB_TOKEN=ghp_...          (optional — enables log commits to repo)
#   GITHUB_REPO=owner/repo-name   (optional — required if GITHUB_TOKEN is set)

# 4. Run the CLI
audit --url https://example.com

# 5. Or start the web server
uvicorn website_audit_tool.web.app:app --reload
# Open http://localhost:8000

# 6. Run tests
pytest

# 7. Type-check
mypy src/
```

---

## Vercel Deployment

```
  GitHub (main branch)
       │
       │  git push origin main
       ▼
  Vercel  (auto-deploy on push)
       │
       ├── Reads pyproject.toml  →  Python 3.12, installs deps
       ├── Detects api/index.py  →  deploys as serverless function
       ├── vercel.json           →  routes all requests to api/index.py
       │                            maxDuration: 60s
       └── Environment Variables →  ANTHROPIC_API_KEY
                                    GITHUB_TOKEN
                                    GITHUB_REPO
```

### Required environment variables

| Variable | Where to get it | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com | Enables AI analysis |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → PAT (needs `repo` scope) | Commits audit logs to repo |
| `GITHUB_REPO` | `owner/repo-name` format, e.g. `samkdataanalytics/website_audit_tool` | Target repo for log commits |

### Storage behaviour

```
  Audit runs on Vercel
       │
       ├── GITHUB_TOKEN + GITHUB_REPO set?
       │       YES → GitHub Contents API → commits to logs/ and scraped/
       │              (permanent, visible in GitHub, survives redeploys)
       │
       └── Not set / API error?
               → falls back to /tmp on Lambda
                 (ephemeral — lost when function instance is recycled)
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves the web UI |
| `POST` | `/scrape` | Scrapes a URL and returns `PageMetrics`. No LLM involved. |
| `POST` | `/analyse` | Scrapes + runs LLM analysis. Returns `AnalysisResult` + log path. |
| `POST` | `/audit` | Combined endpoint. Falls back to metrics-only if LLM unavailable. |

All POST endpoints accept `{ "url": "https://..." }`.

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Clean Architecture layers | Scraper (deterministic, cheap) and LLM (probabilistic, costly) are fully decoupled. Each can be swapped or tested independently. |
| Tool-use forced output | `tool_choice: { "type": "tool", "name": "submit_analysis" }` makes unstructured LLM responses architecturally impossible. Pydantic validates the result. |
| Pydantic schema as prompt | Field `description` strings in `InsightSections` serve double duty — they define the JSON schema sent to the model AND instruct the model to cite specific numbers. |
| CTA detection via keywords | Deterministic heuristic over an ML classifier — fast, auditable, zero cost, tunable by editing `_CTA_KEYWORDS`. |
| Parallel frontend requests | `/scrape` and `/analyse` fire simultaneously. Metrics render immediately; AI insights stream in without blocking the UI. |
| GitHub Contents API for logs | Serverless functions have no persistent filesystem. The GitHub API turns each audit run into a repo commit, making the audit trail permanent and publicly inspectable. |
| GitHubStorage failures non-fatal | If the token or repo is misconfigured, the analysis still completes and falls back to `/tmp`. The error is logged but does not surface to the user. |

---

## Trade-offs

| Trade-off | Decision |
|---|---|
| `claude-haiku` vs `claude-opus` | Haiku fits inside Vercel Hobby's 10s function timeout. Opus produces marginally richer prose but reliably times out. Switch by changing the default in `AnthropicClient.__init__`. |
| `requests` (sync) vs `httpx` (async) | Sync is sufficient for a single-URL tool. Switch to `httpx` if batch auditing is added. |
| `html.parser` vs `lxml` | stdlib parser used — no C dependency. Swap to `lxml` in `BeautifulSoup(html, "lxml")` for a ~3× speed improvement on large pages. |
| File storage vs database | GitHub API commits are human-readable and require no extra infrastructure. A database (e.g. Supabase) would be needed for querying or pagination at scale. |
| No auth on API endpoints | Acceptable for a demo tool. Rate-limiting or an API key header should be added before public exposure at scale. |
