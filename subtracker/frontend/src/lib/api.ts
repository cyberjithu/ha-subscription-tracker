import { useQuery } from "@tanstack/react-query";
import createClient from "openapi-fetch";
import type { components, paths } from "./api-types";

export type Schemas = components["schemas"];
export type Me = Schemas["Me"];

// Resolve against the page so calls work under the Ingress path prefix (hash routing keeps the path fixed).
const baseUrl = new URL(".", window.location.href).href.replace(/\/$/, "");

export const api = createClient<paths>({ baseUrl });

/** Turn an openapi-fetch result into data or a thrown Error carrying the API's detail message. */
export function unwrap<T>(res: { data?: T; error?: unknown; response: Response }): T {
  if (res.error !== undefined || !res.response.ok) {
    const detail = (res.error as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      // FastAPI validation errors: "price: Input should be greater than or equal to 0"
      throw new Error(detail.map((d: { loc?: unknown[]; msg?: string }) => `${d.loc?.at(-1) ?? ""}: ${d.msg}`).join("; "));
    }
    throw new Error(typeof detail === "string" ? detail : `Request failed (${res.response.status})`);
  }
  return res.data as T;
}

export const useMe = () =>
  useQuery({ queryKey: ["me"], queryFn: async () => unwrap(await api.GET("/api/me")) });

export type Settings = {
  ai_provider: string;
  ai_ready: boolean;
  countries: string[];
  ha_connected: boolean;
  options?: Record<string, unknown>;
};

export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: async () => unwrap(await api.GET("/api/settings")) as Settings });

export const useInbox = () =>
  useQuery({ queryKey: ["inbox"], queryFn: async () => unwrap(await api.GET("/api/inbox")), refetchInterval: 60_000 });

export type Sub = Schemas["SubscriptionOut"];
export type SubIn = Schemas["SubscriptionIn"];

export const useSubscriptions = () =>
  useQuery({ queryKey: ["subscriptions"], queryFn: async () => unwrap(await api.GET("/api/subscriptions")) });

export const useSubscription = (id: number) =>
  useQuery({
    queryKey: ["subscriptions", id],
    queryFn: async () => unwrap(await api.GET("/api/subscriptions/{sub_id}", { params: { path: { sub_id: id } } })),
    enabled: id > 0,
  });

export const useUsers = () =>
  useQuery({ queryKey: ["users"], queryFn: async () => unwrap(await api.GET("/api/users")) });

/** Absolute URL for links the browser follows itself (downloads), under the Ingress prefix. */
export const apiUrl = (path: string) => `${baseUrl}${path}`;
