import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeftIcon, ExternalLinkIcon, ShieldCheckIcon, SparklesIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { type Sub, api, unwrap } from "@/lib/api";
import { dateTime, errorText, money } from "@/lib/format";

// mirrors services/ai/schemas.py DealOffer (stored as JSON, so not in the OpenAPI types)
type Offer = {
  provider: string; plan: string; price: number; currency: string; cycle: string; contract_months: number | null;
  estimated_annual_cost: number | null; estimated_annual_saving: number | null; source_url: string | null; caveats: string;
};
const PROVIDER_NAME: Record<string, string> = { anthropic: "Claude", openai: "OpenAI", ollama: "Ollama", ha_ai_task: "Home Assistant AI" };
const path = (id: number) => ({ params: { path: { sub_id: id } } });

export function DealTab({ s, canEdit }: { s: Sub; canEdit: boolean }) {
  const qc = useQueryClient();
  const preview = useQuery({
    queryKey: ["subscriptions", s.id, "deal-preview"],
    queryFn: async () => unwrap(await api.GET("/api/subscriptions/{sub_id}/deal-preview", path(s.id))),
  });
  const history = useQuery({
    queryKey: ["subscriptions", s.id, "deals"],
    queryFn: async () => unwrap(await api.GET("/api/subscriptions/{sub_id}/deals", path(s.id))),
  });
  const [running, setRunning] = useState(false);
  const [shown, setShown] = useState<number | null>(null);

  const run = async () => {
    setRunning(true);
    try {
      const out = unwrap(await api.POST("/api/subscriptions/{sub_id}/deals", path(s.id)));
      await qc.invalidateQueries({ queryKey: ["subscriptions", s.id, "deals"] });
      await qc.invalidateQueries({ queryKey: ["deals"] });
      setShown(null);
      if (out.status === "error") toast.error(out.error);
      else toast.success(out.offers?.length ? `${out.offers.length} offers found` : "No offers found");
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setRunning(false);
    }
  };
  const markSwitching = async () => {
    try {
      const { id: _id, owner_user_id: _o, monthly_cost: _m, notice_deadline: _n, next_event: _e, ...body } = s;
      unwrap(await api.PUT("/api/subscriptions/{sub_id}", { ...path(s.id), body: { ...body, status: "switching" } }));
      await qc.invalidateQueries({ queryKey: ["subscriptions"] });
      toast.success(`${s.name} marked as switching`);
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  if (!preview.data) return null;
  const p = preview.data;
  if (!p.eligible) return <EmptyState icon={<ShieldCheckIcon className="size-6" />} title="No deal search">{p.reason}</EmptyState>;
  const searches = history.data ?? [];
  // default to the newest search that worked; a failed retry shouldn't hide earlier offers
  const current = searches.find((x) => x.id === shown) ?? searches.find((x) => x.status === "done") ?? searches[0];
  const latestFailed = searches[0]?.status === "error" && searches[0].id !== current?.id ? searches[0] : null;
  const list = (current?.offers ?? []) as Offer[];

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Look for a better deal</CardTitle>
          <CardDescription>
            {p.provider
              ? `Uses ${PROVIDER_NAME[p.provider] ?? p.provider}${p.web_search ? " with web search" : " with the providers' price pages"}. Runs on its own when the notice deadline gets close.`
              : "Set up an AI provider in the add-on configuration first."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <details className="rounded-md border bg-muted/40 p-3 text-sm">
            <summary className="cursor-pointer font-medium">Exactly what is sent</summary>
            <pre className="mt-2 font-mono text-xs leading-5 whitespace-pre-wrap">{p.prompt}</pre>
            <p className="mt-2 text-xs text-muted-foreground">Usage and Eircode are only included when switched on in Edit → Better-deal search. Notes, account links and names are never sent.</p>
          </details>
          {canEdit && (
            <div>
              <Button onClick={run} disabled={running || !p.provider}>
                <SparklesIcon /> {running ? "Searching… (can take a minute)" : "Search now"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {latestFailed && (
        <p role="status" className="text-sm text-destructive">Latest search ({dateTime(latestFailed.ran_at)}) failed: {latestFailed.error}</p>
      )}
      {current && (
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              {current.status === "error" ? "Search failed" : `${list.length} offers`}
              <Badge variant="outline">{current.trigger === "auto" ? "Automatic" : "Manual"}</Badge>
              <span className="text-sm font-normal text-muted-foreground">{dateTime(current.ran_at)}</span>
            </CardTitle>
            <CardDescription>
              {current.status === "error" ? current.error : current.summary}
              {current.current_annual_cost != null && current.status !== "error" && ` You pay about ${money(current.current_annual_cost, s.currency)} a year now.`}
            </CardDescription>
          </CardHeader>
          {current.status !== "error" && list.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Offer</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Per year</TableHead>
                  <TableHead className="text-right">Saving</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((o, i) => (
                  <TableRow key={`${o.provider}-${i}`}>
                    <TableCell className="whitespace-normal">
                      <div className="font-medium">
                        {o.source_url
                          ? <a href={o.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">{o.provider}<ExternalLinkIcon className="size-3" /></a>
                          : o.provider}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {[o.plan, o.contract_months ? `${o.contract_months}-month contract` : null, o.caveats].filter(Boolean).join(" · ")}
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{money(o.price, o.currency ?? s.currency)}<span className="text-xs text-muted-foreground"> /{o.cycle}</span></TableCell>
                    <TableCell className="text-right tabular-nums">{o.estimated_annual_cost != null ? money(o.estimated_annual_cost, o.currency ?? s.currency) : "—"}</TableCell>
                    <TableCell className={`text-right tabular-nums ${(o.estimated_annual_saving ?? 0) > 0 ? "font-medium text-primary" : "text-muted-foreground"}`}>
                      {o.estimated_annual_saving != null ? money(o.estimated_annual_saving, s.currency) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {canEdit && s.status === "active" && current.status !== "error" && list.length > 0 && (
            <CardContent className="pt-4">
              <Button variant="outline" onClick={markSwitching}><ArrowRightLeftIcon /> I'm switching provider</Button>
              <p className="mt-1 text-xs text-muted-foreground">AI prices can be wrong or out of date: confirm on the provider's site before you sign up.</p>
            </CardContent>
          )}
        </Card>
      )}

      {searches.length > 1 && (
        <div className="text-sm">
          <p className="mb-1 font-medium">Earlier searches</p>
          <ul className="flex flex-wrap gap-1.5">
            {searches.map((x) => (
              <li key={x.id}>
                <Button size="sm" variant={x.id === current?.id ? "default" : "outline"} onClick={() => setShown(x.id!)}>
                  {dateTime(x.ran_at)}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
