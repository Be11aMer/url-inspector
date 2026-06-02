# URL Inspector

[![CI](https://github.com/Be11aMer/url-inspector/actions/workflows/ci.yml/badge.svg)](https://github.com/Be11aMer/url-inspector/actions/workflows/ci.yml)

A tool for inspecting URL metadata: HTTP status, redirect chain, page title, Open Graph tags, Twitter Card tags, and canonical URL.

**Built by [`alpha`](https://github.com/Be11aMer/alpha)** — an experimental autonomous software delivery team: four AI agents (Architect, Dev, Reviewer, Explainer) coordinated through a JSON task board and a structured handoff process. This project was the bootstrap test for that system. Every line of application code was written by the Dev agent, reviewed by the Reviewer agent, and merged on approval — no human wrote application code. The Architect designed the stack and SSRF strategy before a line was written. The Explainer produced all technical documentation at sprint close.

What the system got right: honest handoffs, real security findings caught at review, no hidden technical debt. What it got wrong: PM-gated tasks burned review cycles before a `blocked` state was introduced; a transitive dependency CVE required understanding fastapi's starlette version constraint before it could be fixed; task numbering broke when the sprint structure was refactored mid-run. All of it is documented in the [write-ups](https://github.com/Be11aMer/alpha/tree/main/write-ups).

## Stack

- **Backend:** FastAPI + httpx + BeautifulSoup4
- **Frontend:** Vanilla HTML/CSS/JS (single `index.html`)
- **Container:** Docker (python:3.12-slim)
- **Hosting:** Render free tier

## Local development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

## Tests

```bash
pytest tests/
```

## Lint

```bash
ruff check .
```

## Security

SSRF mitigation is applied to every URL and every redirect hop. Private IP ranges, loopback addresses, link-local addresses, and CGNAT space are all rejected before any HTTP request is made.
