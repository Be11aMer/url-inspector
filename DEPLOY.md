# Deployment: url-inspector

**Platform:** DigitalOcean App Platform
**Deploy method:** Docker container, built from the repository `Dockerfile`
**Spec:** [`.do/app.yaml`](.do/app.yaml)

The application is a standard container listening on `$PORT` (default `8000`).
Nothing in it is DigitalOcean-specific — see [Self-hosting](#self-hosting)
to run the identical image anywhere Docker runs.

> **Public URL:** _set after the first deploy._ App Platform assigns a
> `*.ondigitalocean.app` hostname; record it here, or replace it with your own
> domain once DNS is pointed (see [Custom domain](#custom-domain-via-cloudflare)).

---

## Prerequisites

- A DigitalOcean account
- [`doctl`](https://docs.digitalocean.com/reference/doctl/how-to/install/)
  installed and authenticated (`doctl auth init`)
- The GitHub repository connected to DigitalOcean, so App Platform can pull
  source and redeploy on push

---

## Deploying

`.do/app.yaml` is the source of truth for the service definition. Prefer
applying it over configuring the app by hand in the control panel — panel edits
that are not mirrored back into the file drift silently.

### First deploy

```bash
doctl apps create --spec .do/app.yaml
```

The command returns an app ID. The first build takes roughly 3–5 minutes:
DigitalOcean clones the repository, builds the `Dockerfile`, and starts the
container. Watch progress with:

```bash
doctl apps logs <app-id> --type build --follow
```

The app is ready when `doctl apps get <app-id>` reports the active deployment
phase as `ACTIVE`.

### Subsequent deploys

`deploy_on_push: true` is set in the spec, so every push to `main` triggers an
automatic rebuild. No manual step is needed.

To force a redeploy without a new commit:

```bash
doctl apps create-deployment <app-id>
```

### Changing the spec

Edit `.do/app.yaml`, commit it, then apply:

```bash
doctl apps update <app-id> --spec .do/app.yaml
```

To pull the live spec back down and check for drift:

```bash
doctl apps spec get <app-id>
```

---

## Post-deployment verification

Run every check against the deployed URL. Substitute `$APP_URL` for the
hostname App Platform assigned.

```bash
export APP_URL="https://your-app.ondigitalocean.app"
```

### Health check

```bash
curl -s "$APP_URL/health"
# Expected: {"status":"ok"}
```

This is the same path App Platform polls (`health_check.http_path` in the
spec), so a failure here means the platform will also be restarting the
container.

### Frontend

Open `$APP_URL/` in a browser. The URL Inspector page must load without
console errors.

### Metadata fetch (valid public URL)

```bash
curl -s -X POST "$APP_URL/api/inspect" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}' | python3 -m json.tool
# Expected: HTTP 200, "title": "Example Domain"
```

### SSRF rejection

The single most important check — this is the app's main security control, and
it must hold on the deployed instance, not just in tests.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$APP_URL/api/inspect" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://127.0.0.1"}'
# Expected: 422

curl -s -X POST "$APP_URL/api/inspect" \
  -H "Content-Type: application/json" \
  -d '{"url": "http://169.254.169.254"}' | python3 -m json.tool
# Expected: {"error": "Forbidden Target", ...}
```

The second URL is the cloud metadata endpoint. On a container platform, a
successful fetch of that address would be a credential-disclosure bug, so
confirm it is rejected before announcing the deployment.

---

## Custom domain (via Cloudflare)

App Platform serves a `*.ondigitalocean.app` hostname with TLS by default. To
front it with a domain hosted on Cloudflare:

1. In the DO control panel, open the app → **Settings** → **Domains** → **Add
   Domain**, and enter the hostname. Choose **"You manage your domain"** so DO
   does not take over the nameservers.
2. In Cloudflare DNS, add a `CNAME` record pointing the hostname at the
   `*.ondigitalocean.app` target DigitalOcean shows.
3. Set the record to **DNS only** (grey cloud) for the initial certificate
   issuance. DigitalOcean needs to reach the origin directly to complete the
   ACME challenge; proxying before issuance will stall it.
4. Once the certificate is issued and the domain shows as active in DO, switch
   the record to **Proxied** (orange cloud) if you want Cloudflare's caching
   and WAF in front.
5. Set the Cloudflare SSL/TLS mode to **Full (strict)**. App Platform presents
   a valid certificate, so anything weaker downgrades a working chain for no
   benefit.

---

## Self-hosting

The image has no dependency on any hosting provider. To run it anywhere:

```bash
docker build -t url-inspector .
docker run --rm -p 8000:8000 url-inspector
```

Then open `http://localhost:8000`.

To bind a different port, set `PORT`:

```bash
docker run --rm -e PORT=3000 -p 3000:3000 url-inspector
```

The container runs as an unprivileged user (uid `10001`), needs no volumes, no
environment configuration, and no network access beyond outbound HTTPS to the
sites being inspected.

---

## Operational notes

| Note | Detail |
|---|---|
| No rate limiting | `/api/inspect` performs an outbound fetch per request with no throttle. A public instance can be used as a fetch relay. Put a rate limit in front of it (Cloudflare WAF, or an app-level limiter) before advertising the URL widely. |
| DNS rebinding | `validate_url()` resolves and checks the target, then `httpx` resolves again independently. A hostile DNS server can answer differently across those two lookups. The blocked-range check still stops the common cases. |
| Bot-blocking | Sites that detect automated clients return 403 or a challenge page. The tool reports what the server returns. |
| JS-rendered metadata | Metadata injected by JavaScript is not captured — this is a raw HTML fetch. Affects SPAs. |
| 5 MB body cap | Larger responses are rejected with `Response Too Large`. |
| Single worker | The container runs `--workers 1`. Scale with `instance_count` in the spec rather than in-container workers, so health checks and restarts stay granular. |

---

## Migrating from Render

This project previously deployed to Render's free tier via `render.yaml`, which
has been removed. Points of difference worth knowing:

- **No cold starts.** App Platform's paid instances stay warm. Render's free
  tier spun down after ~15 minutes, making the first request take up to 30 s.
  That limitation no longer applies.
- **Health check path is unchanged** (`/health`), so external monitors keep
  working.
- **Decommission the old service** in the Render dashboard once the DO
  deployment is verified, so pushes to `main` stop triggering builds there and
  the stale URL stops serving an outdated copy.
