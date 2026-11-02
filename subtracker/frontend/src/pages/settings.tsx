import { CheckCircle2Icon, PlugZapIcon, XCircleIcon } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, unwrap, useSettings } from "@/lib/api";
import { errorText } from "@/lib/format";

const PROVIDER_LABEL: Record<string, string> = {
  none: "Off",
  anthropic: "Claude (Anthropic)",
  openai: "OpenAI",
  ollama: "Ollama (local)",
  ha_ai_task: "Home Assistant AI Task",
};

type TestResult = { ok: boolean; detail: string; provider?: string; ms?: number };

export function Settings() {
  const settings = useSettings();
  const [result, setResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const opts = (settings.data?.options ?? {}) as Record<string, unknown>;
  const model = { anthropic: opts.anthropic_model, openai: opts.openai_model, ollama: opts.ollama_model, ha_ai_task: opts.ha_ai_task_entity }[
    settings.data?.ai_provider ?? ""] as string | undefined;

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      setResult(unwrap(await api.POST("/api/settings/test-ai")) as TestResult);
    } catch (e) {
      setResult({ ok: false, detail: errorText(e) });
    } finally {
      setTesting(false);
    }
  };

  if (!settings.data) return null;
  const s = settings.data;
  return (
    <>
      <PageHeader title="Settings" description="Change these in Home Assistant: Settings → Add-ons → SubTracker → Configuration." />
      <div className="grid max-w-3xl gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              AI assistant
              <Badge variant={s.ai_ready ? "default" : "secondary"}>{s.ai_ready ? "Configured" : "Not set up"}</Badge>
            </CardTitle>
            <CardDescription>
              Used to suggest new providers for the catalog and to look for better deals before a renewal.
              Medicines are never sent, and personal details only when you allow it per subscription.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Provider</dt><dd>{PROVIDER_LABEL[s.ai_provider] ?? s.ai_provider}</dd>
              {model && <><dt className="text-muted-foreground">Model</dt><dd className="font-mono text-xs leading-5">{model}</dd></>}
              <dt className="text-muted-foreground">Countries</dt><dd>{s.countries.join(", ")}</dd>
              <dt className="text-muted-foreground">Provider suggestions</dt>
              <dd>{opts.discovery_interval_days ? `every ${opts.discovery_interval_days} days` : "off"}</dd>
              <dt className="text-muted-foreground">Deal search</dt><dd>{String(opts.deal_search_lead_days ?? "—")} days before the notice deadline</dd>
            </dl>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={test} disabled={testing || s.ai_provider === "none"}>
                <PlugZapIcon /> {testing ? "Testing…" : "Test AI connection"}
              </Button>
              {result && (
                <p role="status" className={`flex items-center gap-1.5 text-sm ${result.ok ? "text-primary" : "text-destructive"}`}>
                  {result.ok ? <CheckCircle2Icon className="size-4" /> : <XCircleIcon className="size-4" />}
                  {result.detail}{result.ms != null && ` (${(result.ms / 1000).toFixed(1)} s)`}
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Connections</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Home Assistant</dt>
              <dd>{s.ha_connected ? "Connected" : "Not connected (development mode: notifications are only logged)"}</dd>
              <dt className="text-muted-foreground">Email</dt>
              <dd>{opts.resend_api_key_set ? `Resend, from ${String(opts.resend_from || "—")}` : opts.email_notify_service ? String(opts.email_notify_service) : "Not set up"}</dd>
              <dt className="text-muted-foreground">Dashboard card</dt>
              <dd>{opts.install_lovelace_card ? "Installed to /local/subtracker-card.js" : "Off"}</dd>
            </dl>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
