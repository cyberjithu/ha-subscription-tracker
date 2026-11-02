import { createHashHistory, createRootRoute, createRoute, createRouter } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import {
  BellIcon, BookOpenIcon, CircleUserIcon, LayoutDashboardIcon, PillIcon, ReceiptTextIcon, SettingsIcon,
  SparklesIcon, TagIcon, UsersIcon,
} from "lucide-react";
import type { JSX } from "react";

type Page = () => JSX.Element | null;
import { AppLayout } from "@/components/app-layout";
import { AdminOnly, Placeholder } from "@/components/placeholder";
import { Catalog } from "@/pages/catalog";
import { DashboardPage } from "@/pages/dashboard";
import { Deals } from "@/pages/deals";
import { Inbox } from "@/pages/inbox";
import { Medicines } from "@/pages/medicines";
import { Profile } from "@/pages/profile";
import { Settings } from "@/pages/settings";
import { Suggestions } from "@/pages/suggestions";
import { SubscriptionDetail } from "@/pages/subscription-detail";
import { SubscriptionFormPage } from "@/pages/subscription-form";
import { SubscriptionsList } from "@/pages/subscriptions-list";
import { Users } from "@/pages/users";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  adminOnly?: boolean;
  chunk: string; // build-plan chunk that delivers the page; a placeholder shows until it lands
  page?: Page;
};

export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboardIcon, chunk: "C12", page: DashboardPage },
  { to: "/subscriptions", label: "Subscriptions", icon: ReceiptTextIcon, chunk: "C7", page: SubscriptionsList },
  { to: "/medicines", label: "Medicines", icon: PillIcon, chunk: "C7", page: Medicines },
  { to: "/deals", label: "Deals", icon: TagIcon, chunk: "C11", page: Deals },
  { to: "/catalog", label: "Catalog", icon: BookOpenIcon, chunk: "C8", page: Catalog },
  { to: "/suggestions", label: "Suggestions", icon: SparklesIcon, adminOnly: true, chunk: "C10", page: Suggestions },
  { to: "/inbox", label: "Inbox", icon: BellIcon, chunk: "C7", page: Inbox },
  { to: "/users", label: "Users", icon: UsersIcon, adminOnly: true, chunk: "C7", page: Users },
  { to: "/settings", label: "Settings", icon: SettingsIcon, adminOnly: true, chunk: "C9", page: Settings },
  { to: "/profile", label: "Profile", icon: CircleUserIcon, chunk: "C7", page: Profile },
];

const rootRoute = createRootRoute({ component: AppLayout });

const pages = NAV.map((item) => {
  const Page = item.page;
  const component = !Page ? () => <Placeholder item={item} />
    : item.adminOnly ? () => <AdminOnly what={item.label}><Page /></AdminOnly> : Page;
  return createRoute({ getParentRoute: () => rootRoute, path: item.to, component });
});
const sub = (path: string, component: Page) => createRoute({ getParentRoute: () => rootRoute, path, component });
const extra = [
  sub("/subscriptions/new", SubscriptionFormPage),
  sub("/subscriptions/$id", SubscriptionDetail),
  sub("/subscriptions/$id/edit", SubscriptionFormPage),
];

// Hash history: the Ingress URL prefix is per-session, so the document path must never change.
export const router = createRouter({ routeTree: rootRoute.addChildren([...pages, ...extra]), history: createHashHistory() });
// shortcut: router not registered for type-safe paths (routes are generated from NAV); register once pages are real routes.
