import { LockIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useMe } from "@/lib/api";
import type { NavItem } from "@/router";

/** Renders children for admins; everyone else gets a polite dead end (the API enforces it anyway). */
export function AdminOnly({ what, children }: { what: string; children: ReactNode }) {
  const me = useMe();
  if (!me.data) return null;
  if (me.data.role === "admin") return children;
  return (
    <Card className="mx-auto mt-10 max-w-md text-center">
      <CardHeader>
        <LockIcon className="mx-auto size-6 text-muted-foreground" aria-hidden />
        <CardTitle>Admins only</CardTitle>
        <CardDescription>Ask a household admin if you need access to {what}.</CardDescription>
      </CardHeader>
    </Card>
  );
}

export function Placeholder({ item }: { item: NavItem }) {
  const Icon = item.icon;
  const page = (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-semibold tracking-tight">{item.label}</h1>
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <span className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary">
            <Icon className="size-6" aria-hidden />
          </span>
          <p className="font-medium">{item.label} is on its way</p>
          <p className="max-w-sm text-sm text-muted-foreground">This screen lands in build chunk {item.chunk}.</p>
        </CardContent>
      </Card>
    </div>
  );
  return item.adminOnly ? <AdminOnly what={item.label}>{page}</AdminOnly> : page;
}
