# Deploying VERITENSOR

## Read this first: Vercel can host **half** of this project

VERITENSOR has three kinds of process. They have very different hosting needs,
and getting this wrong is the most common way a hackathon demo dies on stage.

| Part | What it is | Vercel? |
| --- | --- | --- |
| **Frontend** (`frontend/`) | Next.js dashboard | ✅ **Yes** — ideal |
| **Backend** (`backend/`) | FastAPI; holds the subnet in memory, streams live events, runs simulations in worker threads | ❌ **No** — needs a long-lived server |
| **Neurons** (`subnet/neurons/`) | Miner + validator programs that run for hours | ❌ **No** — run on a VM or locally |

**Why the backend can't be a Vercel function.** Serverless functions are
stateless, start fresh on each request, and are killed after seconds. Our
backend seeds a subnet on boot and keeps it in memory, holds open Server-Sent
Event streams for the live view, and runs simulations on background threads.
On serverless the leaderboard would reset constantly and the live feed would
never connect.

**The working setup:**

```
   Vercel  ──────────────►  Render / Railway / Fly.io / any VM
  (frontend)  /api/* proxy      (FastAPI backend, Docker)
```

The frontend already proxies `/api/*` to whatever `BACKEND_URL` you give it, so
the browser only ever talks to your Vercel domain. No CORS problems, no API
keys in the browser.

---

## Step 1 — Push to GitHub (Git Bash on Windows)

Nothing secret gets committed: `.gitignore` already excludes `.env`,
`.wallets-dev/` (which contains **real private keys**), `evidence/`,
`node_modules/` and databases. There is also an automated test
(`tests/test_security.py::test_no_secrets_in_repository`) that fails the build
if a key-shaped string appears anywhere in the tree.

```bash
# 1. one-time identity setup (skip if you've done this before)
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"

# 2. go to the project
cd /c/Users/YOU/path/to/veritensor

# 3. initialise and make the first commit
git init
git add -A
git status                 # ← LOOK at this list before committing
git commit -m "VERITENSOR: decentralized AI verification subnet"

# 4. verify nothing sensitive slipped in
git ls-files | grep -iE "wallet|hotkey|\.env$|secret"
#    → should print nothing except subnet/chain/wallets.py (that's source code)

# 5. create an EMPTY repo on github.com (no README, no .gitignore),
#    then connect and push
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/veritensor.git
git push -u origin main
```

If GitHub asks for a password, it wants a **Personal Access Token**, not your
account password: GitHub → Settings → Developer settings → Personal access
tokens → Tokens (classic) → Generate new token → tick `repo`. Paste the token
as the password.

Later updates:

```bash
git add -A
git commit -m "what changed"
git push
```

---

## Step 2 — Deploy the backend (do this BEFORE Vercel)

The frontend is useless without an API to talk to, so the backend goes first.
A `Dockerfile.backend` and a `render.yaml` blueprint are already in the repo.

### Option A — Render (easiest, free tier works)

1. Go to [render.com](https://render.com) → **New** → **Blueprint**.
2. Connect your GitHub repo. Render reads `render.yaml` automatically.
3. It creates a web service (`veritensor-api`) plus a PostgreSQL database.
4. Wait for the build, then open the service URL and check:
   ```
   https://veritensor-api.onrender.com/health
   → {"status":"ok","mode":"LOCAL_SIMULATION"}
   ```
5. **Copy that URL** — you need it in Step 3.

> Free-tier Render sleeps after inactivity, and the first request afterwards
> takes ~30s while the subnet re-seeds. For a live demo, hit the URL once a
> few minutes beforehand, or use the paid starter plan.

### Option B — Railway / Fly.io / any VPS

Any host that can run a Docker container works:

```bash
docker build -f Dockerfile.backend -t veritensor-api .
docker run -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e CORS_ORIGINS=https://your-app.vercel.app \
  -e ADMIN_API_KEY="$(openssl rand -hex 24)" \
  -e VERITENSOR_COMMIT_SECRET="$(openssl rand -hex 24)" \
  veritensor-api
```

### Backend environment variables that matter

| Variable | Set it to | Why |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | disables debug endpoints automatically |
| `CORS_ORIGINS` | your Vercel URL | refuses requests from other sites |
| `ADMIN_API_KEY` | a long random string | without it, admin routes return 503 in production |
| `VERITENSOR_COMMIT_SECRET` | a long random string | signs the hidden-answer commitments |
| `SEED_TASKS` | `260` (or `120` if RAM is tight) | how much demo history to generate on boot |
| `DATABASE_URL` | provided by the host | leave unset to use SQLite |

---

## Step 3 — Deploy the frontend to Vercel

1. [vercel.com](https://vercel.com) → **Add New** → **Project** → import your repo.
2. **Set Root Directory to `frontend`.** This is the step people miss — the repo
   is a monorepo and Vercel must be pointed at the Next.js app.
3. Framework preset: **Next.js** (auto-detected via `frontend/vercel.json`).
4. Add one environment variable:

   | Name | Value |
   | --- | --- |
   | `BACKEND_URL` | `https://veritensor-api.onrender.com` (your Step 2 URL, **no trailing slash**) |

5. Deploy.

If you forget `BACKEND_URL`, the build prints a loud warning and every page
will load but show "Backend unavailable" — that's the app being honest rather
than showing fake numbers.

6. Go back to Render and set `CORS_ORIGINS` to your new Vercel URL, then
   redeploy the backend.

### Verify the deployment

```
https://your-app.vercel.app/                → landing page
https://your-app.vercel.app/dashboard       → live numbers, banner reads LOCAL SIMULATION
https://your-app.vercel.app/demo            → press RUN FULL DEMO, watch 8 stages
https://your-app.vercel.app/api/network/stats → raw JSON from your backend
```

---

## Step 4 — The neurons (optional, for the video)

The miner and validator programs cannot run on Vercel or Render's free tier —
they are long-lived and need ~95 MB of RAM each. Run them **locally** and record
the terminal for your demo video:

```bash
./scripts/setup_testnet.sh      # creates 13 unfunded local wallets
./scripts/start_miners.sh       # 10 miner processes, real signed transport
VT_ROUNDS=15 ./scripts/start_validators.sh
tail -f evidence/logs/validator-00.log
./scripts/stop_all.sh
```

On a laptop with limited RAM, close the frontend dev server first or use
`VT_MINERS=4`. The script checks memory and tells you before it starts.

---

## What judges will see, and what's honest about it

* The dashboard banner says **LOCAL SIMULATION** because that's the truth: the
  hosted backend runs the mechanism in memory, not on a blockchain.
* The **Bittensor status panel** performs a genuine read-only chain query. On
  the deployed backend it will show the live block number and honestly list the
  prerequisites that are *not* met (no wallet, no netuid, not registered).
* Nothing shows a fabricated token price, transaction, or subnet ID.

That is the correct posture for a hackathon: **a working mechanism, honestly
labelled**, beats a fake blockchain demo that a knowledgeable judge will see
through in thirty seconds.

---

## Quick troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every page shows "Backend unavailable" | `BACKEND_URL` unset or wrong | set it in Vercel → Settings → Environment Variables → **redeploy** |
| Vercel build fails: "No Next.js version detected" | Root Directory not set | set it to `frontend` |
| Dashboard blank on first load after idle | free-tier backend was asleep | wait ~30s and refresh, or upgrade the plan |
| `git push` rejected | remote has commits you don't | `git pull --rebase origin main`, then push |
| Backend restarts and the leaderboard resets | expected | state is in memory and re-seeds on boot; deterministic, so numbers are similar |
| `RUN FULL DEMO` returns 429 | rate limit (12/min on demo routes) | wait a minute |
