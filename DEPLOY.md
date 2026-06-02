# Deployment: url-inspector

**Platform:** Render (free tier)  
**Deploy method:** Docker container  
**Public URL:** https://url-inspector-t6tm.onrender.com

---

## Public Render URL

```
https://url-inspector-t6tm.onrender.com
```

---

## render.yaml

`render.yaml` is committed at the repository root. It defines the service as code:

```yaml
services:
  - type: web
    name: url-inspector
    env: docker
    plan: free
    healthCheckPath: /health
    dockerfilePath: ./Dockerfile
```

---

## PM Steps to Deploy

These steps require access to the Render dashboard. They cannot be automated from this repository.

### 1. Confirm CI is green on main

Before creating the Render service, verify the GitHub Actions CI badge in README.md shows passing.
The CI runs `ruff check .` and `pytest tests/` on every push.

### 2. Create the Render Web Service

1. Log in to [render.com](https://render.com)
2. Click **New** → **Web Service**
3. Connect your GitHub account if not already connected
4. Select the `url-inspector` repository
5. Configure the service:
   - **Name:** `url-inspector`
   - **Region:** Choose nearest to you
   - **Branch:** `main`
   - **Runtime:** Docker
   - **Dockerfile path:** `./Dockerfile`
   - **Plan:** Free
6. Under **Advanced**:
   - **Health Check Path:** `/health`
7. Click **Create Web Service**

### 3. Wait for first build

- Render will pull the repo, build the Docker image, and start the container.
- Build typically takes 2–5 minutes on first run.
- Watch the build log in the Render dashboard for any errors.
- The service is ready when the status shows **Live**.

---

## Post-Deployment Verification

Run each check after the service is live. All must pass before marking TASK-008 done.

### Health check

```bash
curl -s https://url-inspector-t6tm.onrender.com/health
# Expected: {"status":"ok"}
```

### Frontend

Open `https://url-inspector-t6tm.onrender.com/` in a browser. The URL Inspector page must load without errors.

### Metadata fetch (valid public URL)

```bash
curl -s -X POST https://url-inspector-t6tm.onrender.com/api/inspect \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}' | python3 -m json.tool
# Expected: HTTP 200, title field is non-null ("Example Domain")
```

### SSRF rejection

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST https://url-inspector-t6tm.onrender.com/api/inspect \
  -H "Content-Type: application/json" \
  -d '{"url": "http://127.0.0.1"}'
# Expected: 422

curl -s -X POST https://url-inspector-t6tm.onrender.com/api/inspect \
  -H "Content-Type: application/json" \
  -d '{"url": "http://127.0.0.1"}' | python3 -m json.tool
# Expected: {"error": "Forbidden Target", "error_detail": "..."}
```

---

## Known Limitations

| Limitation | Impact |
|---|---|
| Cold starts | Render free tier spins down after ~15 min of inactivity. First request may take up to 30 s. |
| Bot-blocking | Sites that detect automated clients return 403 or a bot-detection page. The tool returns what the server returns. |
| JS-rendered metadata | Metadata injected by JavaScript is not captured. Raw HTML fetch only. Affects SPAs. |
| 5 MB body cap | Pages larger than 5 MB are rejected with `Response Too Large`. |

---

## Redeployment

Render auto-deploys on every push to the tracked branch (configured in the Render dashboard).
No manual action required for subsequent deploys after initial service creation.

To trigger a manual redeploy: **Render dashboard → url-inspector → Manual Deploy → Deploy latest commit**.
