import { createHashHistory, createRootRoute, createRoute, createRouter } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import {
  BellIcon, BookOpenIcon, CircleUserIcon, LayoutDashboardIcon, PillIcon, ReceiptTextIcon, SettingsIcon,
  SparklesIcon, TagIcon, UsersIcon,
} from "lucide-react";
import { AppLayout } from "@/components/app-layout";
import { Placeholder } from "@/components/placeholder";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  adminOnly?: boolean;
  chunk: string; // build-plan chunk that delivers the page; shown until it lands
};

export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboardIcon, chunk: "C12" },
  { to: "/subscriptions", label: "Subscriptions", icon: ReceiptTextIcon, chunk: "C7" },
  { to: "/medicines", label: "Medicines", icon: PillIcon, chunk: "C7" },
  { to: "/deals", label: "Deals", icon: TagIcon, chunk: "C11" },
  { to: "/catalog", label: "Catalog", icon: BookOpenIcon, chunk: "C8" },
  { to: "/suggestions", label: "Suggestions", icon: SparklesIcon, adminOnly: true, chunk: "C10" },
  { to: "/inbox", label: "Inbox", icon: BellIcon, chunk: "C7" },
  { to: "/users", label: "Users", icon: UsersIcon, adminOnly: true, chunk: "C7" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, adminOnly: true, chunk: "C9" },
  { to: "/profile", label: "Profile", icon: CircleUserIcon, chunk: "C7" },
];

const rootRoute = createRootRoute({ component: AppLayout });

const pages = NAV.map((item) =>
  createRoute({ getParentRoute: () => rootRoute, path: item.to, component: () => <Placeholder item={item} /> }),
);

// Hash history: the Ingress URL prefix is per-session, so the document path must never change.
export const router = createRouter({ routeTree: rootRoute.addChildren(pages), history: createHashHistory() });
// shortcut: router not registered for type-safe paths (routes are generated from NAV); register once pages are real routes.
