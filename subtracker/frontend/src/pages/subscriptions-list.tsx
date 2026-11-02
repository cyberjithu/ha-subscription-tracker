import { Link } from "@tanstack/react-router";
import { LockIcon, PlusIcon, ReceiptTextIcon, SearchIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { type Sub, useMe, useSubscriptions, useUsers } from "@/lib/api";
import { EVENT_LABEL, KIND_LABEL, errorText, inDays, money, urgency } from "@/lib/format";

const ALL = "all";

export function SubscriptionsList() {
  const subs = useSubscriptions();
  const me = useMe();
  const users = useUsers();
  const [q, setQ] = useState("");
  const [scope, setScope] = useState(ALL);
  const [kind, setKind] = useState(ALL);
  const [category, setCategory] = useState(ALL);
  const [status, setStatus] = useState("active");

  const categories = useMemo(() => [...new Set((subs.data ?? []).map((s) => s.category))].sort(), [subs.data]);
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (subs.data ?? [])
      .filter((s) => scope === ALL || (scope === "shared" ? !s.owner_user_id : s.owner_user_id === me.data?.id))
      .filter((s) => kind === ALL || s.kind === kind)
      .filter((s) => category === ALL || s.category === category)
      .filter((s) => status === ALL || s.status === status)
      .filter((s) => !needle || `${s.name} ${s.plan_name} ${s.category}`.toLowerCase().includes(needle))
      .sort((a, b) => (a.next_event?.days ?? 1e9) - (b.next_event?.days ?? 1e9) || a.name.localeCompare(b.name));
  }, [subs.data, q, scope, kind, category, status, me.data?.id]);

  const total = rows.filter((s) => s.status !== "cancelled").reduce((sum, s) => sum + s.monthly_cost, 0);
  const ownerName = (s: Sub) =>
    s.owner_user_id === me.data?.id ? "Only you" : users.data?.find((u) => u.id === s.owner_user_id)?.display_name;

  return (
    <>
      <PageHeader
        title="Subscriptions"
        description={subs.data ? `${rows.length} shown · ${money(total)} a month` : "Everything the household pays for"}
        actions={me.data?.role !== "viewer" && (
          <Button asChild>
            <Link to="/subscriptions/new"><PlusIcon /> Add subscription</Link>
          </Button>
        )}
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative min-w-48 flex-1 basis-full sm:basis-48">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" className="pl-8" aria-label="Search subscriptions" />
        </div>
        <Filter label="List" value={scope} onChange={setScope}
          options={[[ALL, "Everything"], ["shared", "Household"], ["mine", "My list"]]} />
        <Filter label="Type" value={kind} onChange={setKind}
          options={[[ALL, "All types"], ...Object.entries(KIND_LABEL)]} />
        <Filter label="Category" value={category} onChange={setCategory}
          options={[[ALL, "All categories"], ...categories.map((c) => [c, c] as [string, string])]} />
        <Filter label="Status" value={status} onChange={setStatus}
          options={[["active", "Active"], ["switching", "Switching"], ["cancelled", "Cancelled"], [ALL, "Any status"]]} />
      </div>

      {subs.isPending ? (
        <div className="grid gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : subs.isError ? (
        <p className="text-sm text-destructive">Could not load subscriptions: {errorText(subs.error)}</p>
      ) : rows.length === 0 ? (
        <EmptyState icon={<ReceiptTextIcon className="size-6" />} title={subs.data.length ? "Nothing matches these filters" : "No subscriptions yet"}>
          {subs.data.length ? "Try clearing a filter." : "Add your broadband, energy, bins, streaming and medicines to get reminders before they renew."}
        </EmptyState>
      ) : (
        <ul className="divide-y overflow-hidden rounded-xl border bg-card">
          {rows.map((s) => (
            <li key={s.id}>
              <Link
                to="/subscriptions/$id"
                params={{ id: String(s.id) }}
                className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:outline-none"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`truncate font-medium ${s.status === "cancelled" ? "text-muted-foreground line-through" : ""}`}>{s.name}</span>
                    {s.owner_user_id && (
                      <Badge variant="outline" className="gap-1 font-normal"><LockIcon className="size-3" aria-hidden />{ownerName(s) ?? "Personal"}</Badge>
                    )}
                    {s.status === "switching" && <Badge variant="secondary">Switching</Badge>}
                  </div>
                  <p className="truncate text-sm text-muted-foreground">
                    {[s.category, s.plan_name, KIND_LABEL[s.kind]].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <div className="hidden text-right sm:block">
                  <p className="font-medium tabular-nums">{money(s.monthly_cost, s.currency)}</p>
                  <p className="text-xs text-muted-foreground">per month</p>
                </div>
                <div className="w-32 shrink-0 text-right sm:w-44">
                  {s.next_event ? (
                    <Badge variant={urgency(s.next_event.days)} className="h-auto py-0.5 whitespace-normal">
                      {EVENT_LABEL[s.next_event.kind]} {inDays(s.next_event.days)}
                    </Badge>
                  ) : (
                    <span className="text-xs text-muted-foreground">No upcoming dates</span>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Filter({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: [string, string][];
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={label} className="min-w-0 grow basis-[calc(50%-0.25rem)] sm:w-40 sm:grow-0 sm:basis-auto"><SelectValue /></SelectTrigger>
      <SelectContent>
        {options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}
