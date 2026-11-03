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
  const model = { anthropic: opts.anthropic_model, openai: opts.openai_model, ollama: opts.ollama_model, ha_ai_task: opts.ha_ai_task_entity }[
    settings.data?.ai_provider ?? ""] as string | undefined;

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
      <PageHeader title="Settings" description="Country is set here. AI, email and the dashboard card are set in Home Assistant: Settings → Add-ons → SubTracker → Configuration." />
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
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Provider</dt><dd>{PROVIDER_LABEL[s.ai_provider] ?? s.ai_provider}</dd>
              {model && <><dt className="text-muted-foreground">Model</dt><dd className="font-mono text-xs leading-5">{model}</dd></>}
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
