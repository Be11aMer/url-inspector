# URL Inspector

[![CI](https://github.com/Be11aMer/url-inspector/actions/workflows/ci.yml/badge.svg)](https://github.com/Be11aMer/url-inspector/actions/workflows/ci.yml)

A personal tool for inspecting URL metadata: HTTP status, redirect chain, page title, Open Graph tags, Twitter Card tags, and canonical URL.

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
