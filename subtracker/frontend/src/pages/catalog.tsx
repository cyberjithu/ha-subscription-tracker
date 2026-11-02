import { useQueryClient } from "@tanstack/react-query";
import { BookOpenIcon, DownloadIcon, EyeOffIcon, ExternalLinkIcon, PencilIcon, PlusIcon, RotateCcwIcon, UploadIcon } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { toast } from "sonner";
import { EmptyState, Field, PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { type Provider, api, apiUrl, unwrap, useCategories, useCountries, useMe, useProviders } from "@/lib/api";
import { errorText, money } from "@/lib/format";

type Switching = { contract_lengths?: number[]; notice_days?: number | null; cancel_method?: string; switch_site?: string; regulator?: string };
type Settings = { dps_monthly_cap?: number; dps_url?: string; switch_sites?: { name: string; url: string }[]; regulators?: Record<string, { name: string; url: string }> };

export function Catalog() {
  const me = useMe();
  const admin = me.data?.role === "admin";
  const countries = useCountries();
  const categories = useCategories();
  const [country, setCountry] = useState<string>();
  const code = country ?? countries.data?.[0]?.code;
  const [category, setCategory] = useState("all");
  const [showHidden, setShowHidden] = useState(false);
  const providers = useProviders({ country: code, category: category === "all" ? undefined : category, includeHidden: admin && showHidden });
  const [editing, setEditing] = useState<Provider | "new" | null>(null);
  const qc = useQueryClient();
  const file = useRef<HTMLInputElement>(null);
  const current = countries.data?.find((c) => c.code === code);
  const settings = (current?.settings ?? {}) as Settings;
  const catName = (slug: string) => categories.data?.find((c) => c.slug === slug)?.name ?? slug;
  const usedCats = [...new Set((providers.data ?? []).map((p) => p.category))];

  const refresh = () => qc.invalidateQueries({ queryKey: ["catalog"] });
  const act = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      await refresh();
      toast.success(done);
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  const importFile = async (f: File) => {
    await act(async () => {
      const res = await fetch(apiUrl("/api/catalog/import"), { method: "POST", body: await f.text(), headers: { "Content-Type": "application/x-yaml" } });
      const out = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(out.detail ?? `Import failed (${res.status})`);
      toast.message(`Imported: ${out.added} added, ${out.updated} updated`);
    }, `${f.name} imported`);
    if (file.current) file.current.value = "";
  };

  return (
    <>
      <PageHeader
        title="Catalog"
        description="Known providers per country. Used to fill in new subscriptions and as the shortlist for deal searches."
        actions={<>
          {code && <Button variant="outline" asChild><a href={apiUrl(`/api/catalog/export/${code}`)}><DownloadIcon /> Export</a></Button>}
          {admin && <>
            <input ref={file} type="file" accept=".yaml,.yml,application/x-yaml,text/yaml" className="sr-only"
              onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
            <Button variant="outline" onClick={() => file.current?.click()}><UploadIcon /> Import</Button>
            <Button onClick={() => setEditing("new")}><PlusIcon /> Add provider</Button>
          </>}
        </>}
      />

      {current && <CountryCard code={current.code} name={current.name} currency={current.currency} settings={settings} admin={admin} onSaved={refresh} />}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {(countries.data?.length ?? 0) > 1 && (
          <Select value={code} onValueChange={setCountry}>
            <SelectTrigger aria-label="Country" className="w-40"><SelectValue /></SelectTrigger>
            <SelectContent>{countries.data!.map((c) => <SelectItem key={c.code} value={c.code}>{c.name}</SelectItem>)}</SelectContent>
          </Select>
        )}
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Category">
          {["all", ...(categories.data ?? []).map((c) => c.slug)].map((slug) => (
            <Button key={slug} size="sm" variant={category === slug ? "default" : "outline"} aria-pressed={category === slug}
              onClick={() => setCategory(slug)}>
              {slug === "all" ? "All" : catName(slug)}
            </Button>
          ))}
        </div>
        {admin && (
          <label className="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
            <Switch aria-label="Show hidden providers" checked={showHidden} onCheckedChange={setShowHidden} /> Show hidden
          </label>
        )}
      </div>

      {providers.isPending ? null : !providers.data?.length ? (
        <EmptyState icon={<BookOpenIcon className="size-6" />} title="No providers here yet">
          {admin ? "Add one, import a catalog file, or wait for AI suggestions." : "An admin can add providers."}
        </EmptyState>
      ) : (
        (category === "all" ? usedCats : [category]).map((cat) => (
          <section key={cat} className="mb-6">
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-muted-foreground uppercase">{catName(cat)}</h2>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {providers.data.filter((p) => p.category === cat).map((p) => (
                <ProviderCard key={p.id} p={p} admin={admin} onEdit={() => setEditing(p)}
                  onHide={() => act(async () => unwrap(await api.DELETE("/api/catalog/providers/{provider_id}", { params: { path: { provider_id: p.id! } } })),
                    p.source === "manual" || p.source === "ai-accepted" ? `${p.name} deleted` : `${p.name} hidden`)}
                  onRestore={() => act(async () => unwrap(await api.POST("/api/catalog/providers/{provider_id}/restore", { params: { path: { provider_id: p.id! } } })), `${p.name} restored`)} />
              ))}
            </div>
          </section>
        ))
      )}

      {editing && code && (
        <ProviderDialog key={editing === "new" ? "new" : editing.id} provider={editing === "new" ? null : editing} country={code}
          categories={(categories.data ?? []).map((c) => [c.slug, c.name] as [string, string])}
          defaultCategory={category === "all" ? undefined : category}
          onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await refresh(); }} />
      )}
    </>
  );
}

function ProviderCard({ p, admin, onEdit, onHide, onRestore }: { p: Provider; admin: boolean; onEdit: () => void; onHide: () => void; onRestore: () => void }) {
  const sw = (p.switching ?? {}) as Switching;
  const terms = sw.contract_lengths?.length ? sw.contract_lengths.map((m) => (m === 0 ? "no contract" : `${m} mo`)).join(" / ") : null;
  return (
    <Card className={p.hidden ? "opacity-60" : undefined}>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {p.name}
          {p.source === "edited" && <Badge variant="outline">Edited</Badge>}
          {p.source === "manual" && <Badge variant="outline">Added</Badge>}
          {p.source === "ai-accepted" && <Badge variant="outline">AI suggested</Badge>}
          {p.hidden && <Badge variant="secondary">Hidden</Badge>}
        </CardTitle>
        {p.coverage && <CardDescription>{p.coverage}</CardDescription>}
      </CardHeader>
      <CardContent className="grid gap-1 text-sm">
        {terms && <p><span className="text-muted-foreground">Terms:</span> {terms}</p>}
        <p><span className="text-muted-foreground">Notice:</span> {sw.notice_days ? `${sw.notice_days} days` : "none needed"}</p>
        {sw.cancel_method && <p className="text-muted-foreground">{sw.cancel_method}</p>}
      </CardContent>
      <CardFooter className="flex flex-wrap gap-1">
        {p.url && <Button variant="ghost" size="sm" asChild><a href={p.url} target="_blank" rel="noreferrer"><ExternalLinkIcon /> Website</a></Button>}
        {p.pricing_url && p.pricing_url !== p.url && <Button variant="ghost" size="sm" asChild><a href={p.pricing_url} target="_blank" rel="noreferrer"><ExternalLinkIcon /> Prices</a></Button>}
        {admin && (
          <span className="ml-auto flex gap-1">
            <Button variant="ghost" size="icon" aria-label={`Edit ${p.name}`} onClick={onEdit}><PencilIcon /></Button>
            {p.hidden
              ? <Button variant="ghost" size="icon" aria-label={`Restore ${p.name}`} onClick={onRestore}><RotateCcwIcon /></Button>
              : <Button variant="ghost" size="icon" aria-label={`Hide ${p.name}`} onClick={onHide}><EyeOffIcon /></Button>}
          </span>
        )}
      </CardFooter>
    </Card>
  );
}

function CountryCard({ code, name, currency, settings, admin, onSaved }: {
  code: string; name: string; currency: string; settings: Settings; admin: boolean; onSaved: () => void;
}) {
  const [cap, setCap] = useState(settings.dps_monthly_cap?.toString() ?? "");
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const next = { ...settings, dps_monthly_cap: cap === "" ? undefined : Number(cap) };
      unwrap(await api.PUT("/api/catalog/countries/{code}", { params: { path: { code } }, body: { settings: next } }));
      onSaved();
      toast.success("Saved");
    } catch (err) {
      toast.error(errorText(err));
    }
  };
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>{name}</CardTitle>
        <CardDescription className="flex flex-wrap gap-x-4 gap-y-1">
          <span>Compare: {(settings.switch_sites ?? []).map((s, i) => <span key={s.url}>{i > 0 && ", "}<a className="underline underline-offset-2" href={s.url} target="_blank" rel="noreferrer">{s.name}</a></span>)}</span>
          {settings.regulators && <span>Regulators: {Object.values(settings.regulators).map((r, i) => <span key={r.url}>{i > 0 && ", "}<a className="underline underline-offset-2" href={r.url} target="_blank" rel="noreferrer">{r.name}</a></span>)}</span>}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {admin ? (
          <form onSubmit={save} className="flex flex-wrap items-end gap-3">
            <Field label={`Drug Payment Scheme monthly cap (${currency})`} htmlFor="dps" hint="Used on the Medicines page.">
              <Input id="dps" type="number" min={0} step="0.01" className="w-40" value={cap} onChange={(e) => setCap(e.target.value)} />
            </Field>
            <Button type="submit" variant="outline">Save</Button>
          </form>
        ) : (
          <p className="text-sm">Drug Payment Scheme cap: {settings.dps_monthly_cap != null ? money(settings.dps_monthly_cap, currency) : "not set"}</p>
        )}
      </CardContent>
    </Card>
  );
}

function ProviderDialog({ provider, country, categories, defaultCategory, onClose, onSaved }: {
  provider: Provider | null; country: string; categories: [string, string][]; defaultCategory?: string;
  onClose: () => void; onSaved: () => void;
}) {
  const sw = (provider?.switching ?? {}) as Switching;
  const [f, setF] = useState({
    name: provider?.name ?? "", slug: provider?.slug ?? "", category: provider?.category ?? defaultCategory ?? categories[0]?.[0] ?? "",
    url: provider?.url ?? "", pricing_url: provider?.pricing_url ?? "", coverage: provider?.coverage ?? "",
    notice_days: sw.notice_days?.toString() ?? "", contract_lengths: (sw.contract_lengths ?? []).join(", "), cancel_method: sw.cancel_method ?? "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const slugify = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const save = async (e: FormEvent) => {
    e.preventDefault();
    const switching = {
      ...sw,
      notice_days: f.notice_days === "" ? null : Number(f.notice_days),
      contract_lengths: f.contract_lengths.split(/[,\s]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n) && n >= 0),
      cancel_method: f.cancel_method,
    };
    const body = { name: f.name, slug: f.slug || slugify(f.name), category: f.category, url: f.url, pricing_url: f.pricing_url,
      coverage: f.coverage, switching, plans: provider?.plans ?? [], plans_captured_at: provider?.plans_captured_at ?? null };
    try {
      unwrap(provider
        ? await api.PUT("/api/catalog/providers/{provider_id}", { params: { path: { provider_id: provider.id! } }, body })
        : await api.POST("/api/catalog/providers", { body: { ...body, country } }));
      toast.success(provider ? "Provider saved" : `${f.name} added`);
      onSaved();
    } catch (err) {
      toast.error(errorText(err));
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={save} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{provider ? `Edit ${provider.name}` : "Add provider"}</DialogTitle>
            <DialogDescription>
              {provider?.source === "bundled" ? "Your changes are kept when the built-in catalog updates." : `Catalog for ${country}.`}
            </DialogDescription>
          </DialogHeader>
          <Field label="Name" htmlFor="p-name"><Input id="p-name" required value={f.name} onChange={set("name")} /></Field>
          <Field label="Category">
            <Select value={f.category} onValueChange={(v) => setF({ ...f, category: v })}>
              <SelectTrigger aria-label="Category" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{categories.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Website" htmlFor="p-url" hint="Must start with https://"><Input id="p-url" type="url" pattern="https://.*" value={f.url} onChange={set("url")} /></Field>
          <Field label="Prices page" htmlFor="p-pricing"><Input id="p-pricing" type="url" pattern="https://.*" value={f.pricing_url} onChange={set("pricing_url")} /></Field>
          <Field label="Coverage" htmlFor="p-coverage"><Input id="p-coverage" value={f.coverage} onChange={set("coverage")} placeholder="e.g. Dublin and Kildare only" /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Notice (days)" htmlFor="p-notice"><Input id="p-notice" type="number" min={0} value={f.notice_days} onChange={set("notice_days")} /></Field>
            <Field label="Contract lengths (months)" htmlFor="p-terms" hint="0 = no contract"><Input id="p-terms" value={f.contract_lengths} onChange={set("contract_lengths")} placeholder="12, 24" /></Field>
          </div>
          <Field label="How to cancel / switch" htmlFor="p-cancel"><Textarea id="p-cancel" value={f.cancel_method} onChange={set("cancel_method")} /></Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit">Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
