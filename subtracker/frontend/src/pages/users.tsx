import { useQueryClient } from "@tanstack/react-query";
import { Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, unwrap, useMe, useUsers } from "@/lib/api";
import { errorText } from "@/lib/format";

const ROLES: [string, string][] = [
  ["admin", "Admin: settings, catalog, users"],
  ["member", "Member: add and edit"],
  ["viewer", "Viewer: read only"],
];

export function Users() {
  const users = useUsers();
  const me = useMe();
  const qc = useQueryClient();
  const act = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["users"] });
      toast.success(done);
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  return (
    <>
      <PageHeader title="Users" description="Everyone who has opened SubTracker from Home Assistant. New people join as members." />
      <Card className="py-0">
        <ul className="divide-y">
          {(users.data ?? []).map((u) => (
            <li key={u.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <Avatar className="size-8">
                <AvatarFallback style={{ background: u.avatar_color, color: "white" }}>{(u.display_name || u.id).slice(0, 1).toUpperCase()}</AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{u.display_name || u.id}{u.id === me.data?.id && " (you)"}</p>
                <p className="truncate text-xs text-muted-foreground">{u.id}</p>
              </div>
              <Select value={u.role}
                onValueChange={(role) => act(async () => unwrap(await api.PUT("/api/users/{user_id}/role", {
                  params: { path: { user_id: u.id } }, body: { role: role as typeof u.role } })), `${u.display_name || u.id} is now ${role}`)}>
                <SelectTrigger aria-label={`Role for ${u.display_name || u.id}`} className="w-60"><SelectValue /></SelectTrigger>
                <SelectContent>{ROLES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
              </Select>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="icon" disabled={u.id === me.data?.id} aria-label={`Remove ${u.display_name || u.id}`}><Trash2Icon /></Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Remove {u.display_name || u.id}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Their preferences are forgotten. Their personal subscriptions stay theirs, and they come back as a member next time they open SubTracker.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction variant="destructive"
                      onClick={() => act(async () => unwrap(await api.DELETE("/api/users/{user_id}", { params: { path: { user_id: u.id } } })), "Removed")}>
                      Remove
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
