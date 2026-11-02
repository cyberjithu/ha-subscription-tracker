import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CalendarClockIcon, PlusIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, unwrap, useCategories, useMe } from "@/lib/api";
import { EVENT_LABEL, errorText, inDays, money, urgency } from "@/lib/format";

type Dashboard = {
  currency: string;
  monthly_total: number;
  yearly_total: number;
  active_count: number;
  possible_yearly_savings: number;
  by_category: { category: string; monthly: number }[];
  by_owner: { owner_id: string | null; name: string; monthly: number }[];
  trend: { month: string; total: number }[];
  upcoming: { subscription_id: number; name: string; kind: string; title: string; date: string; days: number }[];
};

const SERIES = "var(--chart-series-1)";
const monthLabel = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString(undefined, { month: "short" });

export function DashboardPage() {
  const me = useMe();
  const cats = useCategories();
  const q = useQuery({ queryKey: ["subscriptions", "dashboard"], queryFn: async () => unwrap(await api.GET("/api/dashboard")) as Dashboard });
  if (q.isPending) return null;
  if (q.isError) return <p className="text-sm text-destructive">{errorText(q.error)}</p>;
  const d = q.data;
  const cur = d.currency;
  const catName = (slug: string) => cats.data?.find((c) => c.slug === slug)?.name ?? slug.charAt(0).toUpperCase() + slug.slice(1);
  const categories = d.by_category.map((c) => ({ ...c, name: catName(c.category) }));

  if (d.active_count === 0) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <EmptyState icon={<CalendarClockIcon className="size-6" />} title="Nothing tracked yet">
          <p className="mb-3">Add your first subscription to see what the household spends each month and what is coming up.</p>
          {me.data?.role !== "viewer" && <Button asChild><Link to="/subscriptions/new"><PlusIcon /> Add subscription</Link></Button>}
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Dashboard" description="Monthly equivalents: a yearly bill counts as one twelfth each month." />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Per month" value={money(d.monthly_total, cur)} />
        <Stat label="Per year" value={money(d.yearly_total, cur)} />
        <Stat label="Active" value={String(d.active_count)} hint="subscriptions, contracts and medicines" />
        <Stat label="Possible savings" value={d.possible_yearly_savings > 0 ? `${money(d.possible_yearly_savings, cur)}/yr` : "—"}
          hint={d.possible_yearly_savings > 0 ? <Link to="/deals" className="underline underline-offset-2">from deal searches</Link> : "run a deal search to find out"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Monthly spend, last 12 months</CardTitle>
            <CardDescription>Usage bills by the days they cover; fixed prices from the price history.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-64" role="img" aria-label={`Monthly spend over the last 12 months, from ${money(d.trend[0].total, cur)} to ${money(d.trend.at(-1)!.total, cur)}`}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={d.trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="month" tickFormatter={monthLabel} tickLine={false} axisLine={false} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                  <YAxis tickFormatter={(v) => money(v, cur).replace(/[.,]00$/, "")} tickLine={false} axisLine={false} width={64}
                    tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                  <Tooltip cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }} content={<Tip cur={cur} fmt={(m) => new Date(`${m}-01T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" })} />} />
                  <Area isAnimationActive={false} type="monotone" dataKey="total" stroke={SERIES} strokeWidth={2} fill={SERIES} fillOpacity={0.12}
                    activeDot={{ r: 5, stroke: "var(--card)", strokeWidth: 2 }} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <DataTable caption="Monthly spend" rows={d.trend.map((t) => [monthLabel(t.month) + " " + t.month.slice(0, 4), money(t.total, cur)])} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Coming up in 30 days</CardTitle>
          </CardHeader>
          <CardContent>
            {d.upcoming.length === 0 ? <p className="text-sm text-muted-foreground">Nothing due.</p> : (
              <ul className="grid min-w-0 grid-cols-1 gap-2">
                {d.upcoming.slice(0, 8).map((e) => (
                  <li key={`${e.subscription_id}-${e.kind}-${e.date}`} className="min-w-0">
                    <Link to="/subscriptions/$id" params={{ id: String(e.subscription_id) }}
                      className="flex items-center gap-2 rounded-md p-1 text-sm hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:outline-none">
                      <span className="min-w-0 flex-1 truncate"><span className="font-medium">{e.name}</span> <span className="text-muted-foreground">· {EVENT_LABEL[e.kind]}</span></span>
                      <Badge variant={urgency(e.days)} className="shrink-0">{inDays(e.days)}</Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {d.upcoming.length > 8 && <p className="mt-2 text-xs text-muted-foreground">+{d.upcoming.length - 8} more on the Subscriptions page</p>}
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>By category, per month</CardTitle>
          </CardHeader>
          <CardContent>
            <div style={{ height: Math.max(categories.length * 36, 120) }} role="img"
              aria-label={`Monthly spend by category: ${categories.map((c) => `${c.name} ${money(c.monthly, cur)}`).join(", ")}`}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categories} layout="vertical" margin={{ top: 0, right: 72, bottom: 0, left: 0 }} barCategoryGap={8}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="name" width={120} tickLine={false} axisLine={false} tick={{ fill: "var(--foreground)", fontSize: 13 }} />
                  <Tooltip cursor={{ fill: "var(--accent)", opacity: 0.5 }} content={<Tip cur={cur} />} />
                  <Bar isAnimationActive={false} dataKey="monthly" fill={SERIES} radius={[0, 4, 4, 0]} maxBarSize={22}>
                    <LabelList dataKey="monthly" position="right" formatter={(v) => money(Number(v), cur)}
                      style={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <DataTable caption="By category" rows={categories.map((c) => [c.name, money(c.monthly, cur)])} />
          </CardContent>
        </Card>

        {d.by_owner.length > 1 && (
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Shared and personal</CardTitle>
              <CardDescription>Personal lists you can see, per month.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {d.by_owner.map((o) => (
                <div key={o.owner_id ?? "shared"}>
                  <div className="mb-1 flex justify-between text-sm"><span>{o.name}</span><span className="tabular-nums">{money(o.monthly, cur)}</span></div>
                  <div className="h-2 rounded-full bg-muted" aria-hidden>
                    <div className="h-2 rounded-full" style={{ width: `${(o.monthly / d.monthly_total) * 100}%`, background: SERIES }} />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: ReactNode }) {
  return (
    <Card size="sm">
      <CardContent>
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
        <p className="mt-1 font-heading text-2xl font-semibold tabular-nums">{value}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

// recharts injects active/payload; fmt turns a "YYYY-MM" key into a readable month
function Tip({ active, payload, cur, fmt }: {
  active?: boolean; payload?: { value: number; payload: { name?: string; month?: string } }[]; cur: string; fmt?: (m: string) => string;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  const title = p.payload.name ?? (p.payload.month && fmt ? fmt(p.payload.month) : p.payload.month);
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm text-popover-foreground shadow-md">
      <p className="text-muted-foreground">{title}</p>
      <p className="font-medium tabular-nums">{money(p.value, cur)}</p>
    </div>
  );
}

function DataTable({ caption, rows }: { caption: string; rows: string[][] }) {
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer text-xs text-muted-foreground">Show as table</summary>
      <table className="mt-2 w-full">
        <caption className="sr-only">{caption}</caption>
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-b last:border-0"><th scope="row" className="py-1 text-left font-normal">{k}</th><td className="py-1 text-right tabular-nums">{v}</td></tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
