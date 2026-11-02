let LOCALE = "en-IE";

/** Date/number style chosen on the profile page (stored in the profile's date_format). */
export const DATE_STYLES: Record<string, string> = {
  "en-IE": "2 Nov 2026 (Ireland)",
  "en-GB": "2 Nov 2026 (UK)",
  "en-US": "Nov 2, 2026 (US)",
  "de-DE": "2. Nov. 2026 (Germany)",
  "fr-FR": "2 nov. 2026 (France)",
};
export const setLocale = (locale: string) => {
  LOCALE = locale in DATE_STYLES ? locale : "en-IE";
};

export const money = (n: number | null | undefined, currency = "EUR") =>
  new Intl.NumberFormat(LOCALE, { style: "currency", currency }).format(n ?? 0);

export const day = (iso: string | null | undefined) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(LOCALE, { day: "numeric", month: "short", year: "numeric" }) : "—";

export const dateTime = (iso: string | undefined) =>
  !iso ? "—" : new Date(iso).toLocaleString(LOCALE, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export const inDays = (days: number) => (days === 0 ? "today" : days === 1 ? "tomorrow" : `in ${days} days`);

export const EVENT_LABEL: Record<string, string> = {
  notice_deadline: "Notice deadline",
  renewal: "Renews",
  contract_end: "Contract ends",
  contract_expired: "Contract ended",
  refill: "Refill",
  script_expiry: "Prescription expires",
};

export const KIND_LABEL: Record<string, string> = {
  fixed: "Fixed price",
  contract: "Contract",
  usage: "Usage bills",
  refill: "Refill (medicine)",
};

export const CYCLE_LABEL: Record<string, string> = {
  week: "Weekly",
  month: "Monthly",
  quarter: "Quarterly",
  year: "Yearly",
  custom: "Custom",
};

/** Badge tone for how close a deadline is. */
export const urgency = (days: number | undefined) =>
  days === undefined ? "outline" : days <= 7 ? "destructive" : days <= 30 ? "default" : "secondary";

export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
