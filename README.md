# SubTracker — Home Assistant add-on

Track household subscriptions, contracts, utility bills and medicines inside Home Assistant.
Get reminders before renewal and notice deadlines, and let an AI look for better deals before you roll over.

Status: in development. See [PLAN.md](PLAN.md) for the build checklist.

## Install (once released)
Add this repository URL in **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, then install **SubTracker**.

## Local development
```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -r subtracker/requirements.txt pytest pytest-asyncio
.venv/bin/pytest
```
