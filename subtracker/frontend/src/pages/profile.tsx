import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useState } from "react";
import { toast } from "sonner";
import { Field, PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { type Me, type Schemas, api, unwrap, useMe, useSubscriptions } from "@/lib/api";
import { DATE_STYLES, errorText } from "@/lib/format";
import { NAV } from "@/router";

type Prefs = Schemas["UserPrefs"];
const CHANNELS: [string, string, string][] = [
  ["push", "Phone push", "Home Assistant companion app"],
  ["persistent", "Home Assistant bell", "Shared items only: everyone in Home Assistant can see these"],
  ["inbox", "Inbox here", "Kept in SubTracker's inbox"],
  ["email", "Email", "Needs an email address below"],
];

export function Profile() {
  const me = useMe();
  if (!me.data) return null;
  return <ProfileForm me={me.data} />;
}

function ProfileForm({ me }: { me: Me }) {
  const { id: _id, role: _role, ...initial } = me;
  // older profiles stored a pattern like "dd/MM/yyyy"; map anything unknown onto the default locale
  const [p, setP] = useState<Prefs>({ ...initial, date_format: initial.date_format in DATE_STYLES ? initial.date_format : "en-IE" });
  const [days, setDays] = useState((initial.reminder_days ?? []).join(", "));
  const qc = useQueryClient();
  const subs = useSubscriptions();
  const services = useQuery({ queryKey: ["notify-services"], queryFn: async () => unwrap(await api.GET("/api/notify-services")) });
  const set = <K extends keyof Prefs>(k: K, v: Prefs[K]) => setP((prev) => ({ ...prev, [k]: v }));
  const channels = (p.channels ?? {}) as Record<string, boolean>;
  const categories = [...new Set((subs.data ?? []).map((s) => s.category))].sort();
  const muted = p.muted_categories ?? [];

  const save = async (e: FormEvent) => {
    e.preventDefault();
    const reminder_days = days.trim() ? days.split(/[,\s]+/).filter(Boolean).map(Number) : null;
    if (reminder_days?.some((d) => !Number.isInteger(d) || d < 0 || d > 365)) {
      toast.error("Reminder days must be whole numbers between 0 and 365");
      return;
    }
    if (!!p.quiet_start !== !!p.quiet_end) {
      toast.error("Set both a start and an end for quiet hours, or neither");
      return;
    }
    try {
      qc.setQueryData(["me"], unwrap(await api.PUT("/api/me", { body: { ...p, reminder_days } })));
      toast.success("Profile saved");
    } catch (err) {
      toast.error(errorText(err));
    }
  };

  return (
    <form onSubmit={save} className="max-w-3xl">
      <PageHeader title="Profile" description={`Signed in through Home Assistant as ${me.id} (${me.role}).`}
        actions={<Button type="submit">Save</Button>} />
      <div className="grid gap-4">
        <Section title="Display">
          <Field label="Name" htmlFor="display_name">
            <Input id="display_name" maxLength={80} value={p.display_name} onChange={(e) => set("display_name", e.target.value)} />
          </Field>
          <Field label="Colour" htmlFor="avatar_color">
            <Input id="avatar_color" type="color" className="h-9 w-20 p-1" value={p.avatar_color} onChange={(e) => set("avatar_color", e.target.value)} />
          </Field>
          <Field label="Theme">
            <Choice value={p.theme} onChange={(v) => set("theme", v)} label="Theme"
              options={[["ha", "Follow Home Assistant"], ["light", "Light"], ["dark", "Dark"]]} />
          </Field>
          <Field label="Open on">
            <Choice value={p.default_view} onChange={(v) => set("default_view", v)} label="Start page"
              options={NAV.filter((n) => !n.adminOnly || me.role === "admin").map((n) => [n.to === "/" ? "dashboard" : n.to.slice(1), n.label])} />
          </Field>
          <Field label="Date style">
            <Choice value={p.date_format} onChange={(v) => set("date_format", v)} label="Date style" options={Object.entries(DATE_STYLES)} />
          </Field>
        </Section>

        <Section title="Where reminders go">
          <Field label="Phone (Home Assistant notify service)" htmlFor="push_service"
            hint={services.data?.length ? undefined : "No notify services found (or not running inside Home Assistant). Type one, e.g. notify.mobile_app_pixel_8."}>
            {services.data?.length ? (
              <Choice value={p.push_service || "none"} onChange={(v) => set("push_service", v === "none" ? "" : v)} label="Notify service"
                options={[["none", "None"], ...services.data.map((s) => [s, s] as [string, string])]} />
            ) : (
              <Input id="push_service" value={p.push_service} onChange={(e) => set("push_service", e.target.value)} placeholder="notify.mobile_app_…" />
            )}
          </Field>
          <Field label="Email" htmlFor="email">
            <Input id="email" type="email" value={p.email} onChange={(e) => set("email", e.target.value)} />
          </Field>
          <div className="grid gap-3 sm:col-span-2">
            {CHANNELS.map(([key, label, hint]) => (
              <label key={key} className="flex items-start gap-3 text-sm">
                <Switch className="mt-0.5" aria-label={label} checked={!!channels[key]} onCheckedChange={(v) => set("channels", { ...channels, [key]: v })} />
                <span><span className="font-medium">{label}</span><span className="block text-muted-foreground">{hint}</span></span>
              </label>
            ))}
          </div>
        </Section>

        <Section title="When" description="Reminders during quiet hours are held and delivered when they end.">
          <Field label="Quiet from" htmlFor="qs"><Input id="qs" type="time" value={p.quiet_start ?? ""} onChange={(e) => set("quiet_start", e.target.value || null)} /></Field>
          <Field label="Quiet until" htmlFor="qe"><Input id="qe" type="time" value={p.quiet_end ?? ""} onChange={(e) => set("quiet_end", e.target.value || null)} /></Field>
          <Field label="My reminder days" htmlFor="rd" className="sm:col-span-2"
            hint="Leave empty to use each subscription's own days. Comma separated, e.g. 30, 7, 1.">
            <Input id="rd" value={days} onChange={(e) => setDays(e.target.value)} />
          </Field>
        </Section>

        {categories.length > 0 && (
          <Section title="Mute categories" description="No reminders for these categories reach you.">
            <div className="flex flex-wrap gap-x-6 gap-y-2 sm:col-span-2">
              {categories.map((c) => (
                <label key={c} className="flex items-center gap-2 text-sm capitalize">
                  <Checkbox aria-label={`Mute ${c}`} checked={muted.includes(c)}
                    onCheckedChange={(v) => set("muted_categories", v === true ? [...muted, c] : muted.filter((m) => m !== c))} />
                  {c}
                </label>
              ))}
            </div>
          </Section>
        )}
      </div>
    </form>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">{children}</CardContent>
    </Card>
  );
}

function Choice({ value, onChange, options, label }: { value: string; onChange: (v: string) => void; options: [string, string][]; label: string }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={label} className="w-full"><SelectValue /></SelectTrigger>
      <SelectContent>{options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
    </Select>
  );
}
