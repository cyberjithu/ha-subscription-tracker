import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { LockIcon, PillIcon, PlusIcon } from "lucide-react";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { api, unwrap, useMe } from "@/lib/api";
import { day, errorText, money, urgency } from "@/lib/format";

export function Medicines() {
  const me = useMe();
  const data = useQuery({ queryKey: ["subscriptions", "medicines"], queryFn: async () => unwrap(await api.GET("/api/medicines")) });
  if (data.isPending) return null;
  if (data.isError) return <p className="text-sm text-destructive">{errorText(data.error)}</p>;
  const { items, monthly_total, monthly_cap, scheme_note, currency } = data.data;
  const overCap = monthly_cap != null && monthly_total > monthly_cap;
  return (
    <>
      <PageHeader
        title="Medicines"
        description="Supply countdown, refills and prescriptions. Medicines are never sent to AI."
        actions={me.data?.role !== "viewer" && (
          <Button asChild><Link to="/subscriptions/new" search={{ kind: "refill" }}><PlusIcon /> Add medicine</Link></Button>
        )}
      />
      {items.length > 0 && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle>{money(monthly_total, currency)} a month on prescriptions (estimate)</CardTitle>
            <CardDescription>
              {monthly_cap != null
                ? overCap
                  ? `Above the ${money(monthly_cap, currency)} monthly prescription cap. ${scheme_note}`
                  : `Below the ${money(monthly_cap, currency)} monthly prescription cap. ${scheme_note}`
                : scheme_note || "Set a monthly scheme cap for your country in the catalog to compare."}
            </CardDescription>
          </CardHeader>
          {monthly_cap != null && (
            <CardContent>
              <Progress value={Math.min(100, (monthly_total / monthly_cap) * 100)} aria-label="Spend against scheme cap" />
            </CardContent>
          )}
        </Card>
      )}
      {items.length === 0 ? (
        <EmptyState icon={<PillIcon className="size-6" />} title="No medicines yet">
          Add a subscription with the billing type "Refill (medicine)" to track stock and prescriptions.
        </EmptyState>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {items.map(({ subscription: s, medicine: m, remaining, days_left, run_out }) => {
            const pct = m.pack_size ? Math.min(100, (remaining / m.pack_size) * 100) : null;
            const scriptDays = m.script_expiry ? Math.round((new Date(m.script_expiry).getTime() - Date.now()) / 864e5) : undefined;
            return (
              <Link key={s.id} to="/subscriptions/$id" params={{ id: String(s.id) }} className="rounded-xl focus-visible:outline-2">
                <Card className="h-full transition-colors hover:bg-accent/40">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      {s.name}
                      {s.owner_user_id && <LockIcon className="size-3.5 text-muted-foreground" aria-label="Personal" />}
                    </CardTitle>
                    <CardDescription>{m.daily_dose} a day{m.pharmacy ? ` · ${m.pharmacy}` : ""}</CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-3">
                    <div>
                      <div className="mb-1 flex justify-between text-sm">
                        <span>{remaining} left</span>
                        <span className="text-muted-foreground">{days_left != null ? `${days_left} days` : "—"}</span>
                      </div>
                      {pct != null && <Progress value={pct} aria-label={`${s.name} supply`} />}
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <Badge variant={urgency(days_left ?? undefined)}>Runs out {day(run_out)}</Badge>
                      {m.script_expiry && <Badge variant={urgency(scriptDays)}>Script until {day(m.script_expiry)}</Badge>}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
