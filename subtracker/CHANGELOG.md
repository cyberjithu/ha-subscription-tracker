# Changelog

## 0.2.0

- Catalog: **Add** a provider to your subscriptions in one click. If you already track that category you can replace
  one (it is marked cancelled, history kept) or keep both, e.g. for a second internet connection.
- Germany provider catalog (internet, mobile, electricity, gas, streaming, software, Rundfunkbeitrag).
- Settings → Country: choose the household country from every available catalog, or add your own country.
  Replaces the `countries` add-on option.
- Settings → AI assistant: choose the AI provider and model and enter API keys in the panel. Keys are stored
  encrypted and never shown again.
- Fix: the add-on now receives Home Assistant's token inside the container (sensors, notifications and the
  sidebar-only access check work).

## 0.1.0

First release.

- Subscriptions of four kinds: fixed price, contract with notice period, usage bills (gas, electricity) and medicines
  (stock, dose, refill and prescription dates).
- Household list plus personal lists; admin, member and viewer roles from Home Assistant users.
- Reminders before renewals, notice deadlines, refills and prescription expiry: phone push, Home Assistant bell,
  inbox and email (Resend or an HA notify service), with quiet hours and per-person reminder days.
- Home Assistant sensors and a Lovelace card.
- Ireland provider catalog (broadband, mobile, electricity, gas, bins, streaming, software) with import/export.
- Pluggable AI (Claude, OpenAI, Ollama, Home Assistant AI Task): provider suggestions reviewed by an admin, deal
  searches before renewals with a preview of exactly what is sent, and bill reading.
- Cost dashboard with a 12-month trend, categories, personal/shared split and the next 30 days.
