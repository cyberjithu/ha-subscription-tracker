/**
 * SubTracker Lovelace card. Reads only the sensors the add-on publishes (no API calls):
 *   sensor.subtracker_monthly_total  -> state = monthly total, attributes.by_category / count / panel_url, unit = currency
 *   sensor.subtracker_next_deadline  -> attributes.upcoming = [{ name, event, title, date, days }]
 * Personal subscriptions are never published as sensors, so this card only ever shows household items.
 */
import { LitElement, css, html, nothing } from "lit";

type Upcoming = { name: string; event: string; title: string; date: string; days: number };
type HassEntity = { state: string; attributes: Record<string, unknown> };
type Hass = { states: Record<string, HassEntity | undefined>; locale?: { language?: string } };
type Config = { type: string; title?: string; show_total?: boolean; max_items?: number; panel_path?: string };

const TOTAL = "sensor.subtracker_monthly_total";
const NEXT = "sensor.subtracker_next_deadline";
const EVENT_LABEL: Record<string, string> = {
  notice_deadline: "Notice deadline",
  renewal: "Renews",
  contract_end: "Contract ends",
  contract_expired: "Contract ended",
  refill: "Refill",
  script_expiry: "Prescription expires",
};

class SubTrackerCard extends LitElement {
  static properties = { hass: { attribute: false }, config: { state: true } };
  hass?: Hass;
  config: Config = { type: "custom:subtracker-card" };

  setConfig(config: Config) {
    const max = config.max_items ?? 5;
    if (!Number.isInteger(max) || max < 1 || max > 20) throw new Error("max_items must be a whole number from 1 to 20");
    this.config = { show_total: true, ...config, max_items: max };
  }

  getCardSize() {
    return 2 + Math.min(this.config.max_items ?? 5, this.upcoming().length);
  }

  // HA 2024.11+: visual editor built from this schema, no custom editor element needed
  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "show_total", selector: { boolean: {} } },
        { name: "max_items", selector: { number: { min: 1, max: 20, mode: "box" } } },
        { name: "panel_path", selector: { text: {} } },
      ],
      computeLabel: (s: { name: string }) =>
        ({ title: "Title", show_total: "Show monthly total", max_items: "Upcoming items to show",
           panel_path: "SubTracker panel path (if not the default)" })[s.name],
    };
  }

  static getStubConfig() {
    return { title: "Subscriptions", show_total: true, max_items: 5 };
  }

  private upcoming(): Upcoming[] {
    const list = this.hass?.states[NEXT]?.attributes.upcoming;
    return Array.isArray(list) ? (list as Upcoming[]) : [];
  }

  private money(value: number, currency: string) {
    try {
      return new Intl.NumberFormat(this.hass?.locale?.language, { style: "currency", currency }).format(value);
    } catch {
      return `${value.toFixed(2)} ${currency}`;
    }
  }

  private openPanel() {
    // the add-on panel lives under the Ingress path; HA routes in-app navigation through location-changed
    const published = this.hass?.states[TOTAL]?.attributes.panel_url;
    const path = this.config.panel_path || (typeof published === "string" ? published : "/hassio/ingress/local_subtracker");
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  render() {
    if (!this.hass) return nothing;
    const total = this.hass.states[TOTAL];
    if (!total) {
      return html`<ha-card .header=${this.config.title}>
        <div class="empty">SubTracker sensors not found. Is the SubTracker add-on running?</div>
      </ha-card>`;
    }
    const items = this.upcoming().slice(0, this.config.max_items);
    const currency = String(total.attributes.unit_of_measurement ?? "EUR");
    return html`<ha-card .header=${this.config.title}>
      ${this.config.show_total
        ? html`<button class="total" @click=${this.openPanel} aria-label="Open SubTracker">
            <span class="amount">${this.money(Number(total.state), currency)}</span>
            <span class="label">a month · ${total.attributes.count ?? 0} subscriptions</span>
          </button>`
        : nothing}
      ${items.length === 0
        ? html`<div class="empty">Nothing coming up.</div>`
        : html`<ul>
            ${items.map((u) => html`<li>
              <span class="dot ${u.days <= 7 ? "soon" : u.days <= 30 ? "near" : ""}" aria-hidden="true"></span>
              <span class="what"><span class="name">${u.name}</span> <span class="event">${EVENT_LABEL[u.event] ?? u.event}</span></span>
              <span class="when">${u.days === 0 ? "today" : u.days === 1 ? "tomorrow" : `in ${u.days} days`}</span>
            </li>`)}
          </ul>`}
    </ha-card>`;
  }

  static styles = css`
    ha-card { padding-bottom: 8px; }
    .total {
      display: flex; flex-direction: column; align-items: flex-start; gap: 2px; width: 100%;
      padding: 0 16px 12px; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer;
    }
    .total:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; border-radius: 8px; }
    .amount { font-size: 2em; font-weight: 500; line-height: 1.2; }
    .label { color: var(--secondary-text-color); font-size: 0.9em; }
    ul { list-style: none; margin: 0; padding: 0 16px; }
    li { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-top: 1px solid var(--divider-color); }
    .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--disabled-text-color, #9e9e9e); }
    .dot.near { background: var(--primary-color); }
    .dot.soon { background: var(--error-color, #db4437); }
    .what { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .name { font-weight: 500; }
    .event, .when { color: var(--secondary-text-color); }
    .when { flex: none; font-variant-numeric: tabular-nums; }
    .empty { padding: 0 16px 12px; color: var(--secondary-text-color); }
  `;
}

if (!customElements.get("subtracker-card")) customElements.define("subtracker-card", SubTrackerCard);

const w = window as unknown as { customCards?: { type: string; name: string; description: string; preview?: boolean }[] };
w.customCards = w.customCards ?? [];
w.customCards.push({
  type: "subtracker-card",
  name: "SubTracker",
  description: "Monthly subscription spend and upcoming renewals, notice deadlines and refills.",
  preview: true,
});
