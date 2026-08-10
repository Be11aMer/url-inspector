# URL Inspector

[![CI](https://github.com/Be11aMer/url-inspector/actions/workflows/ci.yml/badge.svg)](https://github.com/Be11aMer/url-inspector/actions/workflows/ci.yml)

A tool for inspecting URL metadata: HTTP status, redirect chain, page title, Open Graph tags, Twitter Card tags, and canonical URL.

**Built by [`alpha`](https://github.com/Be11aMer/alpha)** — an experimental autonomous software delivery team: four AI agents (Architect, Dev, Reviewer, Explainer) coordinated through a JSON task board and a structured handoff process. This project was the bootstrap test for that system. Every line of application code was written by the Dev agent, reviewed by the Reviewer agent, and merged on approval — no human wrote application code. The Architect designed the stack and SSRF strategy before a line was written. The Explainer produced all technical documentation at sprint close.

What the system got right: honest handoffs, real security findings caught at review, no hidden technical debt. What it got wrong: PM-gated tasks burned review cycles before a `blocked` state was introduced; a transitive dependency CVE required understanding fastapi's starlette version constraint before it could be fixed; task numbering broke when the sprint structure was refactored mid-run. All of it is documented in the [write-ups](https://github.com/Be11aMer/alpha/tree/main/write-ups).

## Stack

- **Backend:** FastAPI + httpx + BeautifulSoup4
- **Frontend:** Vanilla HTML/CSS/JS (single `index.html`)
- **Container:** Docker (python:3.12-slim)
- **Hosting:** DigitalOcean App Platform — though the container is
  provider-agnostic and runs anywhere Docker does

## Run it

The whole application is one container with no external services, no database,
and no configuration:

```bash
docker build -t url-inspector .
docker run --rm -p 8000:8000 url-inspector
```

Open `http://localhost:8000`. Set `-e PORT=3000` to bind a different port.

## Local development

```bash
pip install -r requirements-dev.txt   # includes requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

Runtime and development dependencies are split deliberately:
`requirements.txt` holds only what the production image needs, so test and lint
tooling never ships to production.

## Tests

```bash
pytest tests/
```

## Lint

```bash
ruff check .
```

## Deployment

See [DEPLOY.md](DEPLOY.md) for the DigitalOcean App Platform procedure, the
post-deploy verification checklist, custom domains via Cloudflare, and
self-hosting notes.

## Security

SSRF mitigation is applied to every URL and every redirect hop. Private IP ranges, loopback addresses, link-local addresses, and CGNAT space are all rejected before any HTTP request is made.

The production image installs runtime dependencies only and runs as an
unprivileged user (uid `10001`).

Two limitations are worth stating plainly, because a public instance inherits
both:

- **No rate limiting.** `/api/inspect` makes one outbound request per call with
  no throttle, so an open instance can be used as a fetch relay. Put a limiter
  in front of it before advertising the URL.
- **DNS rebinding.** The validator resolves the hostname and checks the
  addresses, then `httpx` resolves it again for the actual request. A hostile
  DNS server can answer differently between those two lookups. The blocked-range
  check still stops every case that does not involve an attacker-controlled
  resolver.

Both are tracked in [DEPLOY.md](DEPLOY.md#operational-notes).
