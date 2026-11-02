import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckIcon, ExternalLinkIcon, PencilIcon, SparklesIcon, XIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";
import { EmptyState, Field, PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { type Schemas, api, unwrap, useCategories, useCountries, useSettings } from "@/lib/api";
import { dateTime, errorText } from "@/lib/format";

type Suggestion = Schemas["Suggestion"];
type Payload = Schemas["ProviderSuggestion"];
const ALL = "all";

export const useSuggestions = (status: "pending" | "accepted" | "rejected" = "pending", enabled = true) =>
  useQuery({
    queryKey: ["suggestions", status],
    queryFn: async () => unwrap(await api.GET("/api/suggestions", { params: { query: { status } } })),
    enabled,
  });

export function Suggestions() {
  const [status, setStatus] = useState<"pending" | "accepted" | "rejected">("pending");
  const list = useSuggestions(status);
  const categories = useCategories();
  const countries = useCountries();
  const settings = useSettings();
  const qc = useQueryClient();
  const [country, setCountry] = useState<string>();
  const [category, setCategory] = useState(ALL);
  const [running, setRunning] = useState(false);
  const [editing, setEditing] = useState<Suggestion | null>(null);
  const code = country ?? countries.data?.[0]?.code;
  const catName = (slug: string) => categories.data?.find((c) => c.slug === slug)?.name ?? slug;

  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ["suggestions"] }), qc.invalidateQueries({ queryKey: ["catalog"] })]);
  const act = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      await refresh();
      toast.success(done);
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  const run = async () => {
    if (!code) return;
    setRunning(true);
    try {
      const out = unwrap(await api.POST("/api/suggestions/discover", {
        body: { country: code, category: category === ALL ? null : category },
      })) as { found?: number; started?: boolean };
      if (out.started) toast.message("Searching every category in the background. You'll get a notification when new providers are found.");
      else toast.success(out.found ? `${out.found} new provider${out.found === 1 ? "" : "s"} to review` : "Nothing new found");
      await refresh();
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <PageHeader title="Suggestions"
        description="Providers the AI found that are not in your catalog yet. Nothing is added until you accept it." />

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Find new providers</CardTitle>
          <CardDescription>
            {settings.data?.ai_ready
              ? "Searches the web for providers missing from the catalog. Runs on its own on the schedule in Settings."
              : "Set up an AI provider in the add-on configuration first."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          {(countries.data?.length ?? 0) > 1 && (
            <Select value={code} onValueChange={setCountry}>
              <SelectTrigger aria-label="Country" className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>{countries.data!.map((c) => <SelectItem key={c.code} value={c.code}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          )}
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger aria-label="Category" className="w-52"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All categories</SelectItem>
              {(categories.data ?? []).filter((c) => c.ai_deals).map((c) => <SelectItem key={c.slug} value={c.slug}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button onClick={run} disabled={running || !settings.data?.ai_ready || !code}>
            <SparklesIcon /> {running ? "Searching… (can take a minute)" : "Search now"}
          </Button>
        </CardContent>
      </Card>

      <div className="mb-4 flex gap-1.5" role="group" aria-label="Status">
        {(["pending", "accepted", "rejected"] as const).map((s) => (
          <Button key={s} size="sm" variant={status === s ? "default" : "outline"} aria-pressed={status === s} onClick={() => setStatus(s)} className="capitalize">
            {s}
          </Button>
        ))}
      </div>

      {list.isPending ? null : !list.data?.length ? (
        <EmptyState icon={<SparklesIcon className="size-6" />} title={status === "pending" ? "Nothing to review" : `No ${status} suggestions`} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {list.data.map((s) => {
            const p = s.payload as Payload;
            return (
              <Card key={s.id}>
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2">
                    {p.name}<Badge variant="outline">{catName(s.category)}</Badge><Badge variant="secondary">{s.country}</Badge>
                  </CardTitle>
                  <CardDescription>{p.reason || "No reason given."}</CardDescription>
                </CardHeader>
                <CardContent className="grid gap-1 text-sm">
                  {p.coverage && <p><span className="text-muted-foreground">Coverage:</span> {p.coverage}</p>}
                  {!!p.contract_lengths?.length && <p><span className="text-muted-foreground">Terms:</span> {p.contract_lengths.map((m) => (m ? `${m} mo` : "no contract")).join(" / ")}</p>}
                  {p.notice_days != null && <p><span className="text-muted-foreground">Notice:</span> {p.notice_days ? `${p.notice_days} days` : "none"}</p>}
                  {p.cancel_method && <p className="text-muted-foreground">{p.cancel_method}</p>}
                  {!!s.source_urls?.length && (
                    <p className="text-xs text-muted-foreground">
                      Sources: {(s.source_urls as string[]).map((u, i) => (
                        <span key={u}>{i > 0 && ", "}<a href={u} target="_blank" rel="noreferrer" className="underline underline-offset-2">{new URL(u).hostname}</a></span>
                      ))}
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">Found by {s.ai_provider || "AI"} · {dateTime(s.created_at)}</p>
                </CardContent>
                <CardFooter className="flex flex-wrap gap-1">
                  {p.url && <Button variant="ghost" size="sm" asChild><a href={p.url} target="_blank" rel="noreferrer"><ExternalLinkIcon /> Website</a></Button>}
                  {status === "pending" && (
                    <span className="ml-auto flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setEditing(s)}><PencilIcon /> Edit</Button>
                      <Button variant="outline" size="sm" onClick={() => act(async () => unwrap(await api.POST("/api/suggestions/{sid}/reject", { params: { path: { sid: s.id! } } })), `${p.name} rejected`)}>
                        <XIcon /> Reject
                      </Button>
                      <Button size="sm" onClick={() => act(async () => unwrap(await api.POST("/api/suggestions/{sid}/accept", { params: { path: { sid: s.id! } } })), `${p.name} added to the catalog`)}>
                        <CheckIcon /> Accept
                      </Button>
                    </span>
                  )}
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}

      {editing && <EditDialog s={editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await refresh(); }} />}
    </>
  );
}

function EditDialog({ s, onClose, onSaved }: { s: Suggestion; onClose: () => void; onSaved: () => void }) {
  const p = s.payload as Payload;
  const [f, setF] = useState({ ...p, notice: p.notice_days?.toString() ?? "", terms: (p.contract_lengths ?? []).join(", ") });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const save = async (e: FormEvent) => {
    e.preventDefault();
    const { notice, terms, ...rest } = f;
    const body: Payload = {
      ...rest, url: f.url || null, pricing_url: f.pricing_url || null,
      notice_days: notice === "" ? null : Number(notice),
      contract_lengths: terms.split(/[,\s]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n) && n >= 0),
    };
    try {
      unwrap(await api.PUT("/api/suggestions/{sid}", { params: { path: { sid: s.id! } }, body }));
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
            <DialogTitle>Edit before accepting</DialogTitle>
            <DialogDescription>Fix anything the AI got wrong. Links that are not https are removed.</DialogDescription>
          </DialogHeader>
          <Field label="Name" htmlFor="s-name"><Input id="s-name" required value={f.name} onChange={set("name")} /></Field>
          <Field label="Website" htmlFor="s-url"><Input id="s-url" type="url" pattern="https://.*" value={f.url ?? ""} onChange={set("url")} /></Field>
          <Field label="Prices page" htmlFor="s-pricing"><Input id="s-pricing" type="url" pattern="https://.*" value={f.pricing_url ?? ""} onChange={set("pricing_url")} /></Field>
          <Field label="Coverage" htmlFor="s-coverage"><Input id="s-coverage" value={f.coverage ?? ""} onChange={set("coverage")} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Notice (days)" htmlFor="s-notice"><Input id="s-notice" type="number" min={0} value={f.notice} onChange={set("notice")} /></Field>
            <Field label="Contract lengths (months)" htmlFor="s-terms"><Input id="s-terms" value={f.terms} onChange={set("terms")} /></Field>
          </div>
          <Field label="How to cancel / switch" htmlFor="s-cancel"><Textarea id="s-cancel" value={f.cancel_method ?? ""} onChange={set("cancel_method")} /></Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit">Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
