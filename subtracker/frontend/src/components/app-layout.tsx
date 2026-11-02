import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { CalendarSyncIcon, MenuIcon, MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup,
  DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Toaster } from "@/components/ui/sonner";
import { api, unwrap, useInbox, useMe } from "@/lib/api";
import { watchTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { NAV } from "@/router";

const THEME_KEY = "subtracker.theme";

function useThemePref() {
  const me = useMe();
  const qc = useQueryClient();
  const [local, setLocal] = useState(() => {
    try {
      return localStorage.getItem(THEME_KEY) ?? "ha";
    } catch {
      return "ha";
    }
  });
  const pref = me.data?.theme ?? local; // profile wins; the local copy only avoids a flash on reload
  useEffect(() => {
    try {
      localStorage.setItem(THEME_KEY, pref);
    } catch {
      /* storage blocked: theme still applies for this session */
    }
    return watchTheme(pref);
  }, [pref]);
  const setPref = async (theme: string) => {
    setLocal(theme);
    if (!me.data) return;
    const { id: _id, role: _role, ...prefs } = me.data;
    try {
      qc.setQueryData(["me"], unwrap(await api.PUT("/api/me", { body: { ...prefs, theme } })));
    } catch (e) {
      toast.error(`Could not save theme: ${(e as Error).message}`);
    }
  };
  return [pref, setPref] as const;
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const me = useMe();
  const inbox = useInbox();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const items = NAV.filter((n) => !n.adminOnly || me.data?.role === "admin");
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {items.map(({ to, label, icon: Icon }) => {
        const active = to === "/" ? path === "/" : path.startsWith(to);
        const unread = to === "/inbox" ? inbox.data?.unread ?? 0 : 0;
        return (
          <Link
            key={to}
            to={to}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors",
              "hover:bg-accent hover:text-accent-foreground focus-visible:outline-2",
              active && "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary",
            )}
          >
            <Icon className="size-4 shrink-0" aria-hidden />
            <span className="flex-1">{label}</span>
            {unread > 0 && <Badge className="h-5 min-w-5 px-1.5 tabular-nums">{unread}</Badge>}
          </Link>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2 px-3 font-heading text-base font-semibold tracking-tight">
      <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
        <CalendarSyncIcon className="size-4" aria-hidden />
      </span>
      SubTracker
    </Link>
  );
}

function UserMenu({ pref, setPref }: { pref: string; setPref: (p: string) => void }) {
  const me = useMe();
  const name = me.data?.display_name || me.data?.id || "…";
  const ThemeIcon = pref === "dark" ? MoonIcon : pref === "light" ? SunIcon : MonitorIcon;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-auto w-full justify-start gap-3 px-3 py-2" aria-label="Account menu">
          <Avatar className="size-8">
            <AvatarFallback style={{ background: me.data?.avatar_color, color: "white" }}>
              {name.slice(0, 1).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <span className="flex min-w-0 flex-col items-start text-left">
            <span className="truncate text-sm font-medium">{name}</span>
            <span className="text-xs capitalize text-muted-foreground">{me.data?.role}</span>
          </span>
          <ThemeIcon className="ml-auto size-4 text-muted-foreground" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={pref} onValueChange={setPref}>
          <DropdownMenuRadioItem value="ha">Follow Home Assistant</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="light">Light</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">Dark</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/profile">Profile & notifications</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppLayout() {
  const [pref, setPref] = useThemePref();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    // the mobile sheet must not linger when the window widens to the desktop layout
    const wide = window.matchMedia("(min-width: 768px)");
    const close = () => wide.matches && setOpen(false);
    wide.addEventListener("change", close);
    return () => wide.removeEventListener("change", close);
  }, []);
  return (
    <div className="min-h-dvh bg-background">
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col gap-6 border-r bg-sidebar py-5 md:flex">
        <Brand />
        <div className="flex-1 overflow-y-auto px-3">
          <NavLinks />
        </div>
        <div className="px-3">
          <UserMenu pref={pref} setPref={setPref} />
        </div>
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur md:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open menu">
              <MenuIcon />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72 gap-6 p-0 py-5">
            <SheetHeader className="p-0">
              <SheetTitle asChild>
                <div><Brand /></div>
              </SheetTitle>
            </SheetHeader>
            <div className="flex-1 overflow-y-auto px-3">
              <NavLinks onNavigate={() => setOpen(false)} />
            </div>
            <div className="px-3">
              <UserMenu pref={pref} setPref={setPref} />
            </div>
          </SheetContent>
        </Sheet>
        <Brand />
      </header>

      <main className="px-4 py-6 md:ml-60 md:px-8 md:py-8">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
      <Toaster />
    </div>
  );
}
