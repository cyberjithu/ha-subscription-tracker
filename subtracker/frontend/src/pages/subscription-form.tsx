import { useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";
import { Field, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { type Provider, type SubIn, api, unwrap, useProviders, useSubscription, useSubscriptions } from "@/lib/api";
import { CYCLE_LABEL, KIND_LABEL, errorText } from "@/lib/format";

const BLANK: SubIn = {
  name: "", category: "", kind: "fixed", country: "IE", plan_name: "", price: 0, currency: "EUR", cycle: "month",
  cycle_days: null, start_date: null, next_renewal: null, contract_end: null, auto_renew: true, notice_days: null,
  reminder_days: [30, 14, 7, 1], ai_enabled: true, ai_share_usage: false, ai_share_location: false,
  annual_usage: null, usage_unit: "", location: "", account_url: "", notes: "", status: "active", personal: false,
};

const SUGGESTED_CATEGORIES = ["broadband", "mobile", "electricity", "gas", "bins", "streaming", "software", "insurance", "medicine"];

export function SubscriptionFormPage() {
  const params = useParams({ strict: false }) as { id?: string };
  const id = params.id ? Number(params.id) : undefined;
  const existing = useSubscription(id ?? 0);
  const search = useSearch({ strict: false }) as { kind?: SubIn["kind"] };
  if (id && existing.isPending) return null;
  if (id && existing.isError) return <p className="text-sm text-destructive">{errorText(existing.error)}</p>;
  const fresh = search.kind === "refill" ? { ...BLANK, kind: "refill" as const, category: "medicine", reminder_days: [3, 1] } : BLANK;
  return <SubscriptionForm id={id} initial={id && existing.data ? { ...BLANK, ...existing.data } : fresh} />;
}

function SubscriptionForm({ id, initial }: { id?: number; initial: SubIn }) {
  const [f, setF] = useState<SubIn>(initial);
  const [days, setDays] = useState((initial.reminder_days ?? []).join(", "));
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const all = useSubscriptions();
  const set = <K extends keyof SubIn>(key: K, value: SubIn[K]) => setF((prev) => ({ ...prev, [key]: value }));
  const num = (v: string) => (v === "" ? null : Number(v));
  const categories = [...new Set([...SUGGESTED_CATEGORIES, ...(all.data ?? []).map((s) => s.category)])].sort();

  useEffect(() => {
    // medicines default to short reminders; only while the user hasn't typed their own
    if (!id && f.kind === "refill" && days === "30, 14, 7, 1") setDays("3, 1");
  }, [f.kind, id, days]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const reminder_days = days.split(/[,\s]+/).filter(Boolean).map(Number);
    if (reminder_days.some((d) => !Number.isInteger(d) || d < 0 || d > 365)) {
      toast.error("Reminder days must be whole numbers between 0 and 365");
      return;
    }
    setSaving(true);
    try {
      const body = { ...f, reminder_days };
      const saved = id
        ? unwrap(await api.PUT("/api/subscriptions/{sub_id}", { params: { path: { sub_id: id } }, body }))
        : unwrap(await api.POST("/api/subscriptions", { body }));
      await qc.invalidateQueries({ queryKey: ["subscriptions"] });
      toast.success(id ? "Saved" : `${saved.name} added`);
      navigate({ to: "/subscriptions/$id", params: { id: String(saved.id) } });
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setSaving(false);
    }
  };

  const k = f.kind;
  return (
    <form onSubmit={submit} className="max-w-3xl">
      <PageHeader
        title={id ? `Edit ${initial.name}` : "Add subscription"}
        actions={<>
          <Button type="button" variant="outline" onClick={() => history.back()}>Cancel</Button>
          <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
        </>}
      />
      <div className="grid gap-4">
        <Section title="What is it?">
          <Field label="Name" htmlFor="name">
            <Input id="name" required maxLength={120} value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="eir Fibre 500" />
          </Field>
          <Field label="Category" htmlFor="category">
            <Input id="category" required list="categories" value={f.category} onChange={(e) => set("category", e.target.value.toLowerCase())} placeholder="broadband" />
            <datalist id="categories">{categories.map((c) => <option key={c} value={c} />)}</datalist>
          </Field>
          <ProviderPicker category={f.category} country={f.country} value={f.provider_id ?? null}
            onPick={(p) => setF((prev) => {
              const notice = (p?.switching as { notice_days?: number | null } | undefined)?.notice_days;
              return {
                ...prev,
                provider_id: p?.id ?? null,
                name: prev.name || p?.name || "",
                account_url: prev.account_url || p?.url || "",
                notice_days: prev.notice_days ?? (notice || null),
              };
            })} />
          <Field label="How is it billed?">
            <Select value={k} onValueChange={(v) => set("kind", v as SubIn["kind"])}>
              <SelectTrigger aria-label="Billing type" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(KIND_LABEL).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Plan" htmlFor="plan">
            <Input id="plan" value={f.plan_name} onChange={(e) => set("plan_name", e.target.value)} placeholder="Optional" />
          </Field>
          {!id && (
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <Checkbox aria-label="Keep on my own list only" checked={!!f.personal} onCheckedChange={(v) => set("personal", v === true)} />
              Keep on my own list only (other household members won't see it)
            </label>
          )}
          {id && (
            <Field label="Status">
              <Select value={f.status} onValueChange={(v) => set("status", v as SubIn["status"])}>
                <SelectTrigger aria-label="Status" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="switching">Switching provider</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          )}
        </Section>

        {k !== "refill" && (
          <Section title="Cost" description={k === "usage" ? "Bills drive the monthly cost once you add them; the price here is an estimate until then." : undefined}>
            <Field label={k === "usage" ? "Estimated price per cycle" : "Price per cycle"} htmlFor="price">
              <Input id="price" type="number" min={0} step="0.01" inputMode="decimal" value={f.price} onChange={(e) => set("price", Number(e.target.value))} />
            </Field>
            <Field label="Currency" htmlFor="currency">
              <Input id="currency" maxLength={3} value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} />
            </Field>
            <Field label="Billing cycle">
              <Select value={f.cycle} onValueChange={(v) => set("cycle", v as SubIn["cycle"])}>
                <SelectTrigger aria-label="Billing cycle" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(CYCLE_LABEL).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            {f.cycle === "custom" && (
              <Field label="Every how many days?" htmlFor="cycle_days">
                <Input id="cycle_days" type="number" min={1} required value={f.cycle_days ?? ""} onChange={(e) => set("cycle_days", num(e.target.value))} />
              </Field>
            )}
          </Section>
        )}

        <Section title="Dates & reminders">
          <Field label="Started" htmlFor="start_date">
            <Input id="start_date" type="date" value={f.start_date ?? ""} onChange={(e) => set("start_date", e.target.value || null)} />
          </Field>
          {k === "contract" ? (
            <>
              <Field label="Contract ends" htmlFor="contract_end">
                <Input id="contract_end" type="date" value={f.contract_end ?? ""} onChange={(e) => set("contract_end", e.target.value || null)} />
              </Field>
              <label className="flex items-center gap-2 text-sm">
                <Switch aria-label="Rolls over automatically" checked={f.auto_renew} onCheckedChange={(v) => set("auto_renew", v)} /> Rolls over automatically
              </label>
            </>
          ) : k !== "refill" && (
            <Field label="Next renewal / bill date" htmlFor="next_renewal" hint="Later renewals are worked out from the cycle.">
              <Input id="next_renewal" type="date" value={f.next_renewal ?? ""} onChange={(e) => set("next_renewal", e.target.value || null)} />
            </Field>
          )}
          {k !== "refill" && (
            <Field label="Notice period (days)" htmlFor="notice_days" hint="Leave empty if you can cancel any time.">
              <Input id="notice_days" type="number" min={0} value={f.notice_days ?? ""} onChange={(e) => set("notice_days", num(e.target.value))} />
            </Field>
          )}
          <Field label="Remind me (days before)" htmlFor="reminder_days" hint="Comma separated. You are always reminded on the day.">
            <Input id="reminder_days" value={days} onChange={(e) => setDays(e.target.value)} />
          </Field>
          {k === "refill" && (
            <p className="text-sm text-muted-foreground sm:col-span-2">Stock, dose and prescription dates are set on the medicine's page after saving.</p>
          )}
        </Section>

        {k !== "refill" && (
          <Section title="Better-deal search" description="Before renewal an AI can look for cheaper offers. Nothing personal is shared unless you switch it on here.">
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <Switch aria-label="Look for better deals before renewal" checked={f.ai_enabled} onCheckedChange={(v) => set("ai_enabled", v)} /> Look for better deals before renewal
            </label>
            {f.ai_enabled && (
              <>
                <label className="flex items-center gap-2 text-sm sm:col-span-2">
                  <Switch aria-label="Share my usage" checked={f.ai_share_usage} onCheckedChange={(v) => set("ai_share_usage", v)} /> Share my usage (kWh, GB…)
                </label>
                {f.ai_share_usage && (
                  <>
                    <Field label="Yearly usage" htmlFor="annual_usage">
                      <Input id="annual_usage" type="number" min={0} value={f.annual_usage ?? ""} onChange={(e) => set("annual_usage", num(e.target.value))} />
                    </Field>
                    <Field label="Unit" htmlFor="usage_unit">
                      <Input id="usage_unit" value={f.usage_unit} onChange={(e) => set("usage_unit", e.target.value)} placeholder="kWh" />
                    </Field>
                  </>
                )}
                <label className="flex items-center gap-2 text-sm sm:col-span-2">
                  <Switch aria-label="Share my Eircode or area" checked={f.ai_share_location} onCheckedChange={(v) => set("ai_share_location", v)} /> Share my Eircode / area (coverage checks)
                </label>
                {f.ai_share_location && (
                  <Field label="Eircode or county" htmlFor="location">
                    <Input id="location" value={f.location} onChange={(e) => set("location", e.target.value)} />
                  </Field>
                )}
              </>
            )}
          </Section>
        )}

        <Section title="Notes">
          <Field label="Account / portal link" htmlFor="account_url">
            <Input id="account_url" type="url" value={f.account_url} onChange={(e) => set("account_url", e.target.value)} placeholder="https://" />
          </Field>
          <Field label="Notes" htmlFor="notes" className="sm:col-span-2">
            <Textarea id="notes" value={f.notes} onChange={(e) => set("notes", e.target.value)} />
          </Field>
        </Section>
      </div>
    </form>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">{children}</CardContent>
    </Card>
  );
}

const NONE = "none";

function ProviderPicker({ category, country, value, onPick }: {
  category: string; country: string; value: number | null; onPick: (p: Provider | null) => void;
}) {
  const providers = useProviders({ country, category: category || undefined });
  const list = category ? providers.data ?? [] : [];
  return (
    <Field label="Provider" hint={category && !list.length ? "No catalog providers for this category yet." : "Fills in the name, account link and notice period."}>
      <Select value={value ? String(value) : NONE} disabled={!list.length}
        onValueChange={(v) => onPick(list.find((p) => String(p.id) === v) ?? null)}>
        <SelectTrigger aria-label="Provider" className="w-full"><SelectValue placeholder="Pick a category first" /></SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>Other / not listed</SelectItem>
          {list.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
        </SelectContent>
      </Select>
    </Field>
  );
}
