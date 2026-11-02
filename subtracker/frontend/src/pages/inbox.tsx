import { useQueryClient } from "@tanstack/react-query";
import { BellIcon, CheckCheckIcon } from "lucide-react";
import { toast } from "sonner";
import { EmptyState, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, unwrap, useInbox } from "@/lib/api";
import { dateTime, errorText } from "@/lib/format";

export function Inbox() {
  const inbox = useInbox();
  const qc = useQueryClient();
  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["inbox"] });
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  const items = inbox.data?.items ?? [];
  return (
    <>
      <PageHeader
        title="Inbox"
        description="Every reminder sent to you, including ones held back by quiet hours."
        actions={!!inbox.data?.unread && (
          <Button variant="outline" onClick={() => act(async () => unwrap(await api.POST("/api/inbox/read-all")))}>
            <CheckCheckIcon /> Mark all read
          </Button>
        )}
      />
      {inbox.isPending ? null : items.length === 0 ? (
        <EmptyState icon={<BellIcon className="size-6" />} title="No reminders yet">
          Reminders appear here on the days you chose before each renewal, notice deadline or refill.
        </EmptyState>
      ) : (
        <Card className="py-0">
          <ul className="divide-y">
            {items.map((i) => (
              <li key={i.id} className="flex items-start gap-3 px-4 py-3">
                <span className={`mt-1.5 size-2 shrink-0 rounded-full ${i.read ? "bg-transparent" : "bg-primary"}`} aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className={`text-sm ${i.read ? "text-muted-foreground" : "font-medium"}`}>{i.title}</p>
                  {i.body && <p className="text-sm text-muted-foreground">{i.body}</p>}
                  <p className="mt-0.5 text-xs text-muted-foreground">{dateTime(i.created_at)}</p>
                </div>
                {!i.read && (
                  <Button variant="ghost" size="sm"
                    onClick={() => act(async () => unwrap(await api.POST("/api/inbox/{item_id}/read", { params: { path: { item_id: i.id! } } })))}>
                    Mark read
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
