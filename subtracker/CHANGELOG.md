# Changelog

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
