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

## Building for a specific platform
Home Assistant builds the add-on for its own architecture during install (bases in `subtracker/build.yaml`).
To build one platform yourself, or publish ready-made images so devices don't have to build:

```bash
scripts/build.sh aarch64          # Raspberry Pi 4/5 and other 64-bit ARM
scripts/build.sh amd64            # Intel/AMD machines and VMs
scripts/build.sh all --push       # both, pushed to ghcr.io/cyberjithu/{arch}-subtracker
```

On GitHub: **Actions → Build add-on images → Run workflow**, then choose `all`, `aarch64` or `amd64`.
Pushing a `v*` tag builds both. Once the images for a version are published (and public), add
`image: ghcr.io/cyberjithu/{arch}-subtracker` to `subtracker/config.yaml`; Home Assistant then pulls the
image for its architecture instead of building it on the device.
