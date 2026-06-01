# JobPilot Intelligence Layer

Job application automation platform — scrapes 250+ companies, scores relevancy, auto-fills applications.

```
project/
├── frontend/          # Next.js app → Vercel (hire.shreevaidya.com)
├── backend/           # FastAPI API → Fly.io (jobs.shreevaidya.com)
├── CONTEXT.md         # Architecture deep-dive
├── KNOWLEDGE_GRAPH.md # System diagrams
└── PLAYBOOK.md        # Day-to-day workflow guide
```

---

## Quick Start (Local Development)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your keys
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local    # fill in your keys
npm run dev                   # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local` for local development.

---

## Deployment

### 1. Supabase Setup

1. Create a new project at [supabase.com](https://supabase.com)
2. Open **SQL Editor** and paste the schema from `backend/scripts/migrate.py`
3. Copy your project credentials:
   - **Project URL** → `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL`
   - **anon key** → `NEXT_PUBLIC_SUPABASE_ANON_KEY` (frontend only)
   - **service_role key** → `SUPABASE_SERVICE_ROLE_KEY` (backend only, never expose)

### 2. Deploy Backend to Fly.io

1. Install the Fly CLI: `curl -L https://fly.io/install.sh | sh`
2. Authenticate: `fly auth login`
3. From the `backend/` directory:

```bash
cd backend
fly launch          # creates app, picks region (default: sea)
```

4. Set secrets (never committed to git):

```bash
fly secrets set \
  SUPABASE_URL=https://xxx.supabase.co \
  SUPABASE_SERVICE_ROLE_KEY=eyJ... \
  OPENAI_API_KEY=sk-... \
  CLAUDE_API=sk-ant-... \
  APIFY_TOKEN=apify_api_...
```

5. Deploy:

```bash
fly deploy
```

6. Note your Fly hostname (e.g., `intelligence-layer.fly.dev`)

### 3. Deploy Frontend to Vercel

1. Go to [vercel.com](https://vercel.com) → **Import Project**
2. Connect your GitHub repo
3. Settings:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Next.js
4. Add environment variables:
   | Variable | Value |
   |----------|-------|
   | `NEXT_PUBLIC_API_URL` | `https://jobs.shreevaidya.com` |
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://xxx.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJ...` |
5. Deploy

### 4. Custom Domain DNS Records

Vercel controls your nameservers. Add these records in the **Vercel DNS dashboard**:

#### `shreevaidya.com` → Vercel frontend

This is configured automatically when you add the domain in Vercel project settings.

| Type | Name | Value | TTL |
|------|------|-------|-----|
| `A` | `@` | `76.76.21.21` | Auto |
| `CNAME` | `www` | `cname.vercel-dns.com` | Auto |

#### `jobs.shreevaidya.com` → Fly.io backend

| Type | Name | Value | TTL |
|------|------|-------|-----|
| `CNAME` | `jobs` | `intelligence-layer.fly.dev` | Auto |

> Replace `intelligence-layer.fly.dev` with your actual Fly app hostname.

Then add the custom domain to your Fly app:

```bash
fly certs add jobs.shreevaidya.com
```

### 5. Chrome Extension

1. Open `chrome://extensions`
2. Enable Developer Mode
3. Click "Load unpacked" → select `frontend/extension/`
4. The extension calls `https://intelligence-layer.fly.dev/api/profile`

---

## Architecture

| Layer | Tech | Host |
|-------|------|------|
| Frontend | Next.js 15, React 19 | Vercel |
| Backend | FastAPI, Python 3.13 | Fly.io (Docker) |
| Database | PostgreSQL | Supabase |
| Scraping | httpx (async), Apify | Backend process |
| Extension | Chrome Manifest V3 | Local |

### Why this split?

- **Vercel** for the frontend: instant deploys, edge CDN, zero config for Next.js
- **Fly.io** for the backend: persistent VMs (scraping takes minutes), Docker support (Puppeteer needs system libs), WebSocket support, auto-suspend to save cost, global edge deployment
- **Supabase** for the database: managed PostgreSQL, real-time subscriptions available, row-level security when needed, generous free tier

### Security

- `SUPABASE_SERVICE_ROLE_KEY` only on the backend, never exposed to the browser
- `NEXT_PUBLIC_*` variables are the only ones the frontend sees
- CORS restricts API access to `shreevaidya.com` and the Chrome extension
- Apify token and AI keys live only in Fly.io secrets (encrypted at rest)
