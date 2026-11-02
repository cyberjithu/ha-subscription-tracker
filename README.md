# SubTracker — Home Assistant add-on

Track household subscriptions, contracts, utility bills and medicines inside Home Assistant.
Get reminders before renewal and notice deadlines, and let an AI look for better deals before you roll over.

Status: in development. See [PLAN.md](PLAN.md) for the build checklist.

## Install (once released)
Add this repository URL in **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, then install **SubTracker**.

## Local development
Backend (Python 3.12):
```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -r subtracker/requirements.txt pytest pytest-asyncio
.venv/bin/pytest
cd subtracker && SUBTRACKER_DATA=../.data ../.venv/bin/alembic upgrade head
SUBTRACKER_DATA=../.data ../.venv/bin/uvicorn app.main:app --port 8099
```
Without `SUPERVISOR_TOKEN` the app runs in dev mode: Home Assistant calls are only logged and you are the `dev` user.

Frontend (Node 24, see `subtracker/frontend/.nvmrc`):
```bash
cd subtracker/frontend && npm ci
npm run dev        # Vite on :5173, proxies /api to :8099
npm run build      # outputs to subtracker/app/static, served by FastAPI
npm run gen:api    # regenerate TypeScript API types after backend changes
```
