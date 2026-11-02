import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { TagIcon } from "lucide-react";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { api, unwrap } from "@/lib/api";
import { dateTime, day, errorText, money, urgency } from "@/lib/format";

export function Deals() {
  const rows = useQuery({ queryKey: ["deals"], queryFn: async () => unwrap(await api.GET("/api/deals")) });
  if (rows.isPending) return null;
  if (rows.isError) return <p className="text-sm text-destructive">{errorText(rows.error)}</p>;
  const today = new Date().setHours(0, 0, 0, 0);
  return (
    <>
      <PageHeader title="Deals"
        description="Subscriptions that can be checked for a better deal, soonest decision first. Searches also run on their own as a decision date gets close." />
      {rows.data.length === 0 ? (
        <EmptyState icon={<TagIcon className="size-6" />} title="Nothing to check yet">
          Add a broadband, energy or streaming subscription with a renewal or contract end date.
        </EmptyState>
      ) : (
        <Card className="py-0">
          <ul className="divide-y">
            {rows.data.map((r) => {
              const offers = (r.search?.offers ?? []) as { estimated_annual_saving?: number | null; provider: string }[];
              const best = offers.reduce<typeof offers[number] | null>((b, o) => ((o.estimated_annual_saving ?? 0) > (b?.estimated_annual_saving ?? 0) ? o : b), null);
              const days = r.decide_by ? Math.round((new Date(`${r.decide_by}T00:00:00`).getTime() - today) / 864e5) : undefined;
              return (
                <li key={r.subscription_id}>
                  <Link to="/subscriptions/$id" params={{ id: String(r.subscription_id) }} search={{ tab: "deals" }}
                    className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 transition-colors hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:outline-none">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{r.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {r.category}{r.search ? ` · checked ${dateTime(r.search.ran_at)}` : " · not checked yet"}
                      </p>
                    </div>
                    <div className="text-right text-sm">
                      {r.search?.status === "error" ? <span className="text-destructive">Last search failed</span>
                        : best ? <span className="font-medium text-primary">Save {money(best.estimated_annual_saving)}/yr with {best.provider}</span>
                        : r.search ? <span className="text-muted-foreground">No cheaper offer</span> : null}
                    </div>
                    {r.decide_by && <Badge variant={urgency(days)}>Decide by {day(r.decide_by)}</Badge>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </>
  );
}
