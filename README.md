# Website Audit Tool

An AI-powered website audit tool that scrapes deterministic page metrics and uses a large language model (Anthropic Claude) to generate actionable SEO and UX insights.

---

## Architecture Overview

The project follows **Clean Architecture** principles with three concentric layers:

```
┌────────────────────────────────────────────────────────┐
│                      main.py (CLI)                     │
├────────────────────────────────────────────────────────┤
│               Use Cases  (orchestration)               │
│                   AuditPageUseCase                     │
├──────────────────────┬─────────────────────────────────┤
│  Adapters / Infra    │         Core / Entities         │
│  ┌──────────────┐    │    ┌──────────────────────────┐ │
│  │ PageScraper  │    │    │      PageMetrics          │ │
│  │ (requests +  │◄───┼───►│      AuditResult          │ │
│  │  BS4)        │    │    └──────────────────────────┘ │
│  └──────────────┘    │                                 │
│  ┌──────────────┐    │                                 │
│  │ Anthropic    │    │                                 │
│  │ LLMClient    │    │                                 │
│  └──────────────┘    │                                 │
└──────────────────────┴─────────────────────────────────┘
```

**Data flow:**
```
URL → PageScraper → PageMetrics → AnthropicClient → insights
                                                  ↓
                                         logs/<ts>_<domain>.json
                                                  ↓
                                            AuditResult
```

---

## Project Structure

```
website_audit_tool/
├── .env.example                        # API key template
├── .gitignore
├── README.md
├── requirements.txt
├── pyproject.toml
├── logs/
│   └── .gitkeep                        # Directory tracked; *.json files are gitignored
├── src/
│   └── website_audit_tool/
│       ├── __init__.py
│       ├── main.py                     # CLI entry point
│       ├── core/                       # Pure domain entities (no I/O)
│       │   ├── __init__.py
│       │   └── models.py               # PageMetrics, AuditResult
│       ├── adapters/                   # Infrastructure — network / API
│       │   ├── __init__.py
│       │   ├── scraper.py              # BeautifulSoup-based deterministic scraper
│       │   └── llm_client.py           # Anthropic API client (claude-opus-4-8)
│       └── use_cases/                  # Orchestration layer
│           ├── __init__.py
│           └── audit_page.py           # AuditPageUseCase
└── tests/
    ├── __init__.py
    ├── test_models.py
    └── test_scraper.py
```

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Clean Architecture layers | The scraper (deterministic, testable) is fully decoupled from the LLM (probabilistic, costly to test). Each layer can evolve independently. |
| `requests` + `BeautifulSoup` | Lightweight, synchronous, zero-browser-overhead. Playwright can be layered in later for JS-rendered pages without touching the `PageMetrics` contract. |
| Dependency injection in `AuditPageUseCase` | The use case accepts `PageScraper` and `AnthropicClient` via constructor, making both swappable in tests without mocking at import time. |
| JSON prompt logs in `logs/` | Every API interaction is persisted as a structured JSON file. This satisfies the "Prompt Logs" audit trail requirement and aids debugging. |
| `AnthropicClient` with adaptive thinking | Using `claude-opus-4-8` with `thinking: {type: "adaptive"}` and streaming. The system prompt + structured user prompt yield consistent five-section Markdown reports. |

---

## Trade-offs

| Trade-off | Decision |
|---|---|
| `requests` vs `httpx` | `requests` chosen for simplicity; switch to `httpx` if async support is required later. |
| Synchronous I/O | Sufficient for a single-URL tool. A batch auditing feature would warrant `asyncio`. |
| `BeautifulSoup` vs `lxml` | `html.parser` (stdlib) used by default — no C dependency. `lxml` can be swapped in via `BeautifulSoup(html, "lxml")` for speed. |
| CTA detection via keywords | Heuristic approach; avoids an extra ML model. False positives/negatives can be tuned by editing `_CTA_KEYWORDS`. |

---

## How to Run

### 1. Set up the environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure API key

```bash
cp .env.example .env
# Edit .env and set your Anthropic API key
```

### 3. Run an audit

```bash
# Install the package in editable mode first
pip install -e .

# Using the installed entry point
audit --url https://example.com

# Or directly via Python module
python -m website_audit_tool.main --url https://example.com --timeout 15
```

### 4. Run tests

```bash
pytest
```

### 5. Type-check

```bash
mypy src/
```

---

## Prompt Logs

Every LLM interaction is saved to `logs/` as a JSON file:

```
logs/20260623T120000Z_example_com.json
```

Structure:
```json
{
  "url": "https://example.com",
  "scraped_at": "20260623T120000Z",
  "metrics": {
    "word_count": 412,
    "header_counts": {"h1": 1, "h2": 4},
    "cta_count": 3,
    "internal_links_count": 12,
    "external_links_count": 5
  },
  "insights": "..."
}
```

---

## Roadmap

- [x] Finalise prompt schema — free-form Markdown, five standard sections
- [x] Implement `AnthropicClient.analyze()` — `claude-opus-4-8` with adaptive thinking + streaming
- [ ] Add Playwright adapter for JS-rendered pages
- [ ] Batch URL auditing (CSV input)
- [ ] HTML / Markdown report export
