# SubTracker

Keep track of everything the household pays for regularly: broadband, energy, bins, streaming, software and AI
subscriptions, and monthly medicines. SubTracker reminds you before renewals and notice deadlines, shows what you
spend each month, and can ask an AI to look for a better deal before you roll over.

## Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add this repository's URL.
2. Install **SubTracker**, start it, and turn on **Show in sidebar**.
3. Open **Subscriptions** from the sidebar. The first person to open it becomes the admin; everyone after that joins
   as a member. Admins can change roles under **Users**.

## Roles

| Role | Can |
| --- | --- |
| Admin | everything, plus settings, the provider catalog, AI suggestions and user roles |
| Member | add and edit household and own subscriptions, run deal searches |
| Viewer | look only |

Each person can also keep a **personal list** ("Keep on my own list only" when adding). Personal items are only
shown to their owner (and admins), their reminders only go to the owner, and they are never published as Home
Assistant sensors or bell notifications, because those are visible to every Home Assistant user.

## Configuration

| Option | Default | What it does |
| --- | --- | --- |
| `ai_provider` | `none` | `anthropic`, `openai`, `ollama`, `ha_ai_task` or `none` |
| `anthropic_api_key`, `anthropic_model` | `claude-opus-5-5` | Claude, with web search |
| `openai_api_key`, `openai_model` | `gpt-5` | OpenAI, with web search |
| `ollama_url`, `ollama_model` | `llama3.1` | A local model; no web search, it reads the catalog's price pages instead |
| `ha_ai_task_entity` | | The AI Task entity configured in Home Assistant (leave empty for HA's default) |
| `discovery_interval_days` | `30` | How often the AI looks for providers missing from the catalog (`0` = off) |
| `deal_search_lead_days` | `45` | How many days before a notice deadline the automatic deal search runs |
| `resend_api_key`, `resend_from` | | Send email reminders through [Resend](https://resend.com) |
| `email_notify_service` | | Or send email through a Home Assistant notify service (e.g. `notify.smtp`) |
| `install_lovelace_card` | `true` | Copy the dashboard card to `/config/www/subtracker-card.js` on start |

The AI provider, model and API key can also be set by an admin in the SubTracker panel under **Settings → AI
assistant**, without restarting the add-on. Values set there override the add-on configuration. Keys entered in the
panel are encrypted before they are stored (the encryption key is a separate file in the add-on's private data
folder), are never shown again (only their last four characters), and are never written to the log.
Use **Settings → Test AI connection** to check the key and model.

## Reminders and notifications

Every person sets their own channels under **Profile**:

- **Phone push**: pick your `notify.mobile_app_…` service (Home Assistant companion app).
- **Home Assistant bell**: persistent notifications, shared items only.
- **Inbox**: always kept in SubTracker.
- **Email**: needs Resend or an email notify service in the configuration.

Quiet hours hold notifications until the window ends. Your own reminder days override the per-subscription days.
Reminders are checked every morning at 08:00 and when the add-on starts.

## Sensors

| Entity | State | Attributes |
| --- | --- | --- |
| `sensor.subtracker_monthly_total` | monthly total | `by_category`, `count`, `panel_url` |
| `sensor.subtracker_next_deadline` | date of the next event | `subscription`, `event`, `days`, `upcoming` (next 10) |
| `sensor.subtracker_<id>` | days to the next event | price, monthly cost, notice deadline, contract end… |

Sensors are refreshed every 10 minutes, so they come back shortly after Home Assistant restarts.

## Dashboard card

With `install_lovelace_card` on, add the resource once: **Settings → Dashboards → ⋮ → Resources → Add resource**,
URL `/local/subtracker-card.js`, type **JavaScript module**. Then add the **SubTracker** card to any dashboard:

```yaml
type: custom:subtracker-card
title: Subscriptions
show_total: true
max_items: 5
```

Tapping the total opens the SubTracker panel.

## AI and privacy

The AI is used for two things, and only when you set up a provider:

- **Provider suggestions** for the catalog. They go to **Suggestions** for an admin to accept or reject; nothing is
  added to the catalog without that.
- **Deal searches** before a renewal, and **reading bills** you upload.

What a deal search sends is shown under **Better deals → Exactly what is sent**: the category, country, current
provider and plan, what it costs, the contract end and notice period, and the catalog's providers. Your yearly usage
and your Eircode are only included when you switch them on for that subscription. Notes, account links, names and
anything about medicines are never sent. AI prices can be wrong or out of date: check on the provider's site before
you switch.

## Your data

Everything is stored in the add-on's own data folder (`/data`: a SQLite database and uploaded documents) and is
included in Home Assistant backups. Uninstalling the add-on deletes it.

## Troubleshooting

- **"Open SubTracker from the Home Assistant sidebar"**: the panel only works through Home Assistant's sidebar
  (Ingress), not on a direct port.
- **No sensors**: check the add-on log for "Sensor push failed".
- **AI errors** (rate limits, no credit, wrong key) are shown where they happen and in the add-on log.
