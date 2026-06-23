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
  ║  claude-haiku-   ║   InsightSections                         ║
  ║  4-5-20251001    ║   InsightSection  (analysis + score)      ║
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
      │
      ├─── Call 1: submit_recommendations ───────────────────────┐
      │         schema: _inline_refs(_RecsResult.model_json_schema())
      │         tool_blocks[0].input → Pydantic → list[Recommendation]
      │
      └─── Call 2: submit_insights ──────────────────────────────┐
               schema: _FlatInsights.model_json_schema()
               (flat — 10 top-level fields, no nesting)
               tool_blocks[0].input → Pydantic → assembled InsightSections
      │
      ▼
  AnalysisResult assembled from both tool outputs
      │
      ▼
  LLMInteraction  ◄── audit trail: prompts, summed token counts, serialised result
      │   model, tokens (recs + insights), system_prompt, user_prompt, raw_output
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
    "recommendations": [
      { "priority": 1, "severity": "critical", "title": "Add alt text to 2 images",
        "reasoning": "14.3% of images have no alt attribute…" },
      { "priority": 2, "severity": "warning",  "title": "Add meta description",
        "reasoning": "Meta description not set — Google will auto-generate…" },
      { "priority": 3, "severity": "suggestion", "title": "Add a second CTA",
        "reasoning": "Only 3 CTAs detected; 1–3 is standard but a secondary…" }
    ],
    "insights": {
      "seo_structure":     { "analysis": "The page has 1 H1 and 6 H2 tags…", "score": 72 },
      "messaging_clarity": { "analysis": "The meta description at 23 words…", "score": 58 },
      "cta_usage":         { "analysis": "With only 3 CTAs detected…",        "score": 65 },
      "content_depth":     { "analysis": "1 204 words is above average…",     "score": 80 },
      "ux_concerns":       { "analysis": "2 of 14 images (14.3%) lack alt…",  "score": 28 }
    }
  },
  "llm": {
    "model": "claude-haiku-4-5-20251001",
    "input_tokens": 741,
    "output_tokens": 498,
    "system_prompt": "You are an expert SEO and UX analyst for a web agency…",
    "user_prompt": "Audit this web page. Call `submit_analysis`…",
    "raw_output": "{ \"recommendations\": [ ... ], \"insights\": { ... } }"
  }
}
```

The `llm` block is the complete audit trail — the prompts sent, the token counts (summed across both tool calls), and the assembled `AnalysisResult` serialised as JSON.

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
  AnthropicClient  (two focused tool calls — same system + user prompt each time)
       │
       ├── Call 1 ── tool_choice = { "type": "tool", "name": "submit_recommendations" }
       │              input_schema = _inline_refs(_RecsResult.model_json_schema())
       │                             ↳ $defs/$ref resolved — flat, self-contained schema
       │              ▼
       │          _RecsResult
       │              └── recommendations: list[Recommendation]  (3–5 items)
       │                      ├── priority   int   (1 = highest)
       │                      ├── severity   str   ("critical" | "warning" | "suggestion")
       │                      ├── title      str   (≤ 10 words)
       │                      └── reasoning  str   (must cite at least one metric number)
       │
       └── Call 2 ── tool_choice = { "type": "tool", "name": "submit_insights" }
                      input_schema = _FlatInsights.model_json_schema()
                                     ↳ already flat — no $defs generated, no _inline_refs needed
                      ▼
                  _FlatInsights  (10 top-level fields — no nesting)
                      ├── seo_structure            str   (analysis — must cite exact metrics)
                      ├── seo_structure_score      int   (0–100)
                      ├── messaging_clarity        str
                      ├── messaging_clarity_score  int   (0–100)
                      ├── cta_usage                str
                      ├── cta_usage_score          int   (0–100)
                      ├── content_depth            str
                      ├── content_depth_score      int   (0–100)
                      ├── ux_concerns              str
                      └── ux_concerns_score        int   (0–100)

  _FlatInsights output is assembled post-call into InsightSections / InsightSection objects.
  Token counts from both calls are summed into LLMInteraction.
```

**Key design details:**

- Each `InsightSection.score` uses the same 0–100 scale (0–39 poor, 40–69 fair, 70–89 good, 90–100 excellent), letting the UI render an at-a-glance verdict alongside the text analysis.
- Two focused tool calls keep each schema small enough for Haiku to complete without truncation — recommendations in call 1, all insight text and scores in call 2.
- `_inline_refs()` is applied only to `_RecsResult`'s schema, which contains `$defs`/`$ref` cross-references from the nested `Recommendation` model. `_FlatInsights` has no nested models so Pydantic generates no `$defs` — `_inline_refs()` is not needed for call 2.
- Each field `description` in the Pydantic model doubles as a prompt instruction — the schema enforces structure and guides output quality simultaneously.

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
pip install -r requirements.txt   # includes pydantic, which pyproject.toml omits
pip install -e .                  # installs the package and registers the `audit` CLI

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
       ├── Reads pyproject.toml  →  Python 3.11, installs deps
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
| Tool-use forced output | Two `tool_choice: { "type": "tool" }` calls (`submit_recommendations` then `submit_insights`) make unstructured LLM responses architecturally impossible. Pydantic validates each result. |
| Pydantic schema as prompt | Field `description` strings serve double duty — they define the JSON schema sent to the model AND instruct the model to cite specific metric numbers. |
| `_inline_refs()` schema flattening | `_RecsResult`'s schema contains Pydantic-generated `$defs`/`$ref` cross-references. `_inline_refs()` resolves these before sending so Haiku sees every field inline. `_FlatInsights` uses no nested models so no `$defs` are generated and `_inline_refs()` is not needed. |
| Two focused tool calls | Splitting recommendations and insights into separate calls keeps each schema small enough for Haiku to complete reliably. A single large schema caused truncation of later fields; two focused calls eliminate that failure mode. |
| Per-category scores (0–100) | Each `InsightSection` carries a `score` alongside its `analysis` text. Scores give an at-a-glance signal without requiring the reader to parse every paragraph. The scale (0–39 poor → 90–100 excellent) is defined in the field description so the model applies it consistently. |
| Severity tiers on recommendations | `critical` / `warning` / `suggestion` lets an agency immediately triage blockers from nice-to-haves without reading all reasoning text. The enum is enforced by the tool schema — the model cannot return an invalid value. |
| Industry benchmarks in system prompt | Word count ranges, H1 rules, CTA and link counts, meta tag length standards are injected into the system prompt so insights say "below the 500–900 word standard" rather than just citing the raw number. |
| Few-shot examples in system prompt | One good and one bad example of an insight are included to anchor Haiku against generic, uncited advice — especially important on edge-case pages with unusual metric profiles. |
| CTA detection covers buttons and inputs | `_count_ctas` checks `<a>` (keyword match), `<button>` (keyword match), `<input type="submit/image">` (always a CTA), and `<input type="button">` (keyword match on `value`). Anchor-only detection missed the most common CTA pattern on modern pages. |
| CTA detection via keywords | Deterministic heuristic over an ML classifier — fast, auditable, zero cost, tunable by editing `_CTA_KEYWORDS`. |
| Parallel frontend requests | `/scrape` and `/analyse` fire simultaneously. Metrics render immediately; AI insights load without blocking the UI. |
| GitHub Contents API for logs | Serverless functions have no persistent filesystem. The GitHub API turns each audit run into a repo commit, making the audit trail permanent and publicly inspectable. |
| GitHubStorage failures non-fatal | If the token or repo is misconfigured, the analysis still completes and falls back to `/tmp`. The error is logged but does not surface to the user. |

---

## Trade-offs

| Trade-off | Decision |
|---|---|
| `claude-haiku-4-5-20251001` vs `claude-opus-4-8` | Haiku fits inside Vercel Hobby's 10s function timeout. Opus produces richer reasoning but reliably times out on the free tier. Switch by passing `model="claude-opus-4-8"` to `AnthropicClient.__init__`. On a paid Vercel plan (300 s limit), Opus or Sonnet (`claude-sonnet-4-6`) are viable. |
| `requests` (sync) vs `httpx` (async) | Sync is sufficient for a single-URL tool. Switch to `httpx` if batch auditing is added. |
| `html.parser` vs `lxml` | stdlib parser used — no C dependency. Swap to `lxml` in `BeautifulSoup(html, "lxml")` for a ~3× speed improvement on large pages. |
| File storage vs database | GitHub API commits are human-readable and require no extra infrastructure. A database (e.g. Supabase) would be needed for querying or pagination at scale. |
| No auth on API endpoints | Acceptable for a demo tool. Rate-limiting or an API key header should be added before public exposure at scale. |

---

## What Would You Improve With More Time

### 1. Persistent Audit Storage With Query Support

Logs are committed to GitHub as flat JSON files, which is fine for a demo. Replacing `GitHubStorage` with a Supabase adapter (one concrete implementation behind the same interface) would enable querying audit history, comparing re-audits before and after fixes, and building a simple trend dashboard — without touching the use case or domain layers.

### 2. Progress Monitoring Over Time

Re-auditing the same URL on a schedule and tracking how metrics change would let agencies verify that implemented recommendations actually moved the needle. Each re-audit would be stored alongside previous runs, and the LLM would receive the current metrics plus the delta from the prior audit — e.g., "CTA count increased from 2 to 5, alt-text gaps closed from 4 to 0" — and generate a progress-aware insight: what improved, what is still outstanding, and what impact the changes likely had. This requires replacing flat-file storage with a queryable database (Supabase is a natural fit given the existing architecture).

### 3. Competitor Comparison

Accepting a second URL alongside the primary audit target and running the same scrape-and-analyse pipeline on both would let agencies benchmark a client's page directly against a competitor. The LLM would receive both sets of metrics and produce a side-by-side comparative insight — highlighting where the client leads, where they lag, and which gaps are worth closing first. The existing architecture already supports this cleanly: it is a second call to the same use case plus a new comparative insight field in `InsightSections`.
