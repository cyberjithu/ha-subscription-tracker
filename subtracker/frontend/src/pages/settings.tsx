import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2Icon, GlobeIcon, PlugZapIcon, XCircleIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/page-header";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useQuery } from "@tanstack/react-query";
import { KeyRoundIcon } from "lucide-react";
import { api, unwrap, useCountries, useSettings } from "@/lib/api";
import { errorText } from "@/lib/format";

const PROVIDER_LABEL: Record<string, string> = {
  none: "Off",
  anthropic: "Claude (Anthropic)",
  openai: "OpenAI",
  ollama: "Ollama (local)",
  ha_ai_task: "Home Assistant AI Task",
};

type TestResult = { ok: boolean; detail: string; provider?: string; ms?: number };

export function Settings() {
  const settings = useSettings();
  const [result, setResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const opts = (settings.data?.options ?? {}) as Record<string, unknown>;

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      setResult(unwrap(await api.POST("/api/settings/test-ai")) as TestResult);
    } catch (e) {
      setResult({ ok: false, detail: errorText(e) });
    } finally {
      setTesting(false);
    }
  };

  if (!settings.data) return null;
  const s = settings.data;
  return (
    <>
      <PageHeader title="Settings" description="Country and AI are set here. Schedules, email and the dashboard card are in Home Assistant: Settings → Add-ons → SubTracker → Configuration." />
      <div className="grid max-w-3xl gap-4">
        <CountryCard current={s.country} />
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              AI assistant
              <Badge variant={s.ai_ready ? "default" : "secondary"}>{s.ai_ready ? "Configured" : "Not set up"}</Badge>
            </CardTitle>
            <CardDescription>
              Used to suggest new providers for the catalog and to look for better deals before a renewal.
              Medicines are never sent, and personal details only when you allow it per subscription.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <AIForm onSaved={() => setResult(null)} />
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Provider suggestions</dt>
              <dd>{opts.discovery_interval_days ? `every ${opts.discovery_interval_days} days` : "off"}</dd>
              <dt className="text-muted-foreground">Deal search</dt><dd>{String(opts.deal_search_lead_days ?? "—")} days before the notice deadline</dd>
            </dl>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={test} disabled={testing || s.ai_provider === "none"}>
                <PlugZapIcon /> {testing ? "Testing…" : "Test AI connection"}
              </Button>
              {result && (
                <p role="status" className={`flex items-center gap-1.5 text-sm ${result.ok ? "text-primary" : "text-destructive"}`}>
                  {result.ok ? <CheckCircle2Icon className="size-4" /> : <XCircleIcon className="size-4" />}
                  {result.detail}{result.ms != null && ` (${(result.ms / 1000).toFixed(1)} s)`}
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Connections</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Home Assistant</dt>
              <dd>{s.ha_connected ? "Connected" : "Not connected (development mode: notifications are only logged)"}</dd>
              <dt className="text-muted-foreground">Email</dt>
              <dd>{opts.resend_api_key_set ? `Resend, from ${String(opts.resend_from || "—")}` : opts.email_notify_service ? String(opts.email_notify_service) : "Not set up"}</dd>
              <dt className="text-muted-foreground">Dashboard card</dt>
              <dd>{opts.install_lovelace_card ? "Installed to /local/subtracker-card.js" : "Off"}</dd>
            </dl>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

const OTHER = "__other";

function CountryCard({ current }: { current: string }) {
  const countries = useCountries();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const choose = async (code: string) => {
    if (code === OTHER) return setAdding(true);
    try {
      unwrap(await api.PUT("/api/settings/country", { body: { code } }));
      await qc.invalidateQueries(); // country changes defaults on most pages
      toast.success(`Household country: ${countries.data?.find((c) => c.code === code)?.name ?? code}`);
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  const here = countries.data?.find((c) => c.code === current);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><GlobeIcon className="size-4" aria-hidden /> Country</CardTitle>
        <CardDescription>
          Sets the provider catalog, the currency for new subscriptions and where AI looks for providers and deals.
          New countries appear here automatically when an update ships their catalog.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        <Select value={current} onValueChange={choose}>
          <SelectTrigger aria-label="Household country" className="w-full sm:w-96"><SelectValue /></SelectTrigger>
          <SelectContent>
            {(countries.data ?? []).map((c) => (
              <SelectItem key={c.code} value={c.code}>
                {c.name} <span className="text-muted-foreground">· {c.builtin ? "built-in catalog" : "your own catalog"}, {c.provider_count} providers</span>
              </SelectItem>
            ))}
            <SelectSeparator />
            <SelectItem value={OTHER}>Other country…</SelectItem>
          </SelectContent>
        </Select>
        {here && !here.builtin && (
          <p className="text-sm text-muted-foreground">
            No built-in catalog for {here.name} yet. Add providers in Catalog, import a catalog file, or use Suggestions to let the AI find them.
          </p>
        )}
      </CardContent>
      {adding && <AddCountryDialog onClose={() => setAdding(false)} onAdded={async (code) => { setAdding(false); await choose(code); }} />}
    </Card>
  );
}

function AddCountryDialog({ onClose, onAdded }: { onClose: () => void; onAdded: (code: string) => void }) {
  const [f, setF] = useState({ code: "", name: "", currency: "EUR" });
  const qc = useQueryClient();
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      unwrap(await api.POST("/api/catalog/countries", { body: f }));
      await qc.invalidateQueries({ queryKey: ["catalog"] });
      onAdded(f.code);
    } catch (err) {
      toast.error(errorText(err));
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={save} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Add your country</DialogTitle>
            <DialogDescription>For a country without a built-in catalog. It starts empty; fill it in Catalog or with AI suggestions.</DialogDescription>
          </DialogHeader>
          <Field label="Country name" htmlFor="c-name"><Input id="c-name" required minLength={2} maxLength={60} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="France" /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Country code" htmlFor="c-code" hint="Two letters, e.g. FR">
              <Input id="c-code" required pattern="[A-Za-z]{2}" maxLength={2} value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
            </Field>
            <Field label="Currency" htmlFor="c-cur" hint="Three letters, e.g. EUR, GBP">
              <Input id="c-cur" required pattern="[A-Za-z]{3}" maxLength={3} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} />
            </Field>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit">Add and use</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type KeyState = { set: boolean; source: "app" | "addon" | null; hint: string };
type AISettings = {
  ai_provider: string; anthropic_model: string; openai_model: string; ollama_url: string; ollama_model: string;
  ha_ai_task_entity: string; keys: Record<"anthropic_api_key" | "openai_api_key", KeyState>;
};

function AIForm({ onSaved }: { onSaved: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings", "ai"], queryFn: async () => unwrap(await api.GET("/api/settings/ai")) as AISettings });
  if (!q.data) return null;
  return <AIFormInner key={JSON.stringify(q.data)} data={q.data} onSaved={async () => { await qc.invalidateQueries({ queryKey: ["settings"] }); onSaved(); }} />;
}

function AIFormInner({ data, onSaved }: { data: AISettings; onSaved: () => void }) {
  type KeyName = "anthropic_api_key" | "openai_api_key";
  const [f, setF] = useState({ ...data });
  const [draft, setDraft] = useState<Partial<Record<KeyName, string>>>({}); // newly typed keys
  const [editing, setEditing] = useState<Partial<Record<KeyName, boolean>>>({});
  const [remove, setRemove] = useState<Partial<Record<KeyName, boolean>>>({});
  const [saving, setSaving] = useState(false);
  const p = f.ai_provider;
  const field = (k: keyof AISettings) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const plain = Object.fromEntries((["ai_provider", "anthropic_model", "openai_model", "ollama_url", "ollama_model", "ha_ai_task_entity"] as const)
        .filter((k) => f[k] !== data[k]).map((k) => [k, f[k]]));
      const secrets: Partial<Record<KeyName, string>> = {};
      for (const k of ["anthropic_api_key", "openai_api_key"] as KeyName[]) {
        if (remove[k]) secrets[k] = "";
        else if (draft[k]?.trim()) secrets[k] = draft[k]!.trim();
      }
      unwrap(await api.PUT("/api/settings/ai", { body: { ...plain, ...secrets } }));
      toast.success("AI settings saved");
      onSaved();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setSaving(false);
    }
  };

  const keyField = (name: KeyName, label: string, placeholder: string) => {
    const k = data.keys[name];
    if (k.set && !editing[name]) {
      return (
        <Field label={label}>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-xs"><KeyRoundIcon className="size-3.5" aria-hidden />saved {k.hint}</span>
            <span className="text-muted-foreground">{k.source === "addon" ? "from the add-on configuration" : "stored encrypted"}</span>
            <Button type="button" variant="outline" size="sm" onClick={() => setEditing({ ...editing, [name]: true })}>Replace</Button>
            {k.source === "app" && (
              <Button type="button" variant="ghost" size="sm" onClick={() => setRemove({ ...remove, [name]: !remove[name] })}>
                {remove[name] ? "Undo remove" : "Remove"}
              </Button>
            )}
          </div>
          {remove[name] && <p className="text-xs text-destructive">Will be removed when you save.</p>}
        </Field>
      );
    }
    return (
      <Field label={label} htmlFor={name} hint="Stored encrypted on your Home Assistant. It is never shown again after saving.">
        <Input id={name} type="password" autoComplete="off" spellCheck={false} placeholder={placeholder}
          value={draft[name] ?? ""} onChange={(e) => setDraft({ ...draft, [name]: e.target.value })} />
      </Field>
    );
  };

  return (
    <form onSubmit={save} className="grid gap-4 rounded-lg border p-4">
      <Field label="Provider">
        <Select value={p} onValueChange={(v) => setF({ ...f, ai_provider: v })}>
          <SelectTrigger aria-label="AI provider" className="w-full sm:w-72"><SelectValue /></SelectTrigger>
          <SelectContent>{Object.entries(PROVIDER_LABEL).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
        </Select>
      </Field>
      {p === "anthropic" && <>
        {keyField("anthropic_api_key", "Anthropic API key", "sk-ant-…")}
        <Field label="Model" htmlFor="am"><Input id="am" value={f.anthropic_model} onChange={field("anthropic_model")} /></Field>
      </>}
      {p === "openai" && <>
        {keyField("openai_api_key", "OpenAI API key", "sk-…")}
        <Field label="Model" htmlFor="om"><Input id="om" value={f.openai_model} onChange={field("openai_model")} /></Field>
      </>}
      {p === "ollama" && <>
        <Field label="Ollama URL" htmlFor="ou" hint="e.g. http://192.168.1.20:11434"><Input id="ou" type="url" value={f.ollama_url} onChange={field("ollama_url")} /></Field>
        <Field label="Model" htmlFor="olm"><Input id="olm" value={f.ollama_model} onChange={field("ollama_model")} /></Field>
      </>}
      {p === "ha_ai_task" && (
        <Field label="AI Task entity" htmlFor="ht" hint="Leave empty to use Home Assistant's default AI Task.">
          <Input id="ht" value={f.ha_ai_task_entity} onChange={field("ha_ai_task_entity")} placeholder="ai_task.openai" />
        </Field>
      )}
      <div><Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save AI settings"}</Button></div>
    </form>
  );
}
