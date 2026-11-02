import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import {
  CalendarClockIcon, CopyPlusIcon, DownloadIcon, ExternalLinkIcon, FileTextIcon, LockIcon, PencilIcon, Trash2Icon,
  UploadIcon, UsersIcon,
} from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { toast } from "sonner";
import { EmptyState, Field, PageHeader } from "@/components/page-header";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type Schemas, type Sub, api, apiUrl, unwrap, useMe, useSubscription } from "@/lib/api";
import { CYCLE_LABEL, EVENT_LABEL, KIND_LABEL, dateTime, day, errorText, inDays, money, urgency } from "@/lib/format";
import { MedicineEditor } from "@/pages/medicine-editor";

const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return d.toLocaleDateString("sv-SE"); // YYYY-MM-DD in local time
};

const path = (id: number) => ({ params: { path: { sub_id: id } } });

export function SubscriptionDetail() {
  const { id } = useParams({ strict: false }) as { id: string };
  const subId = Number(id);
  const sub = useSubscription(subId);
  const me = useMe();
  if (sub.isPending) return null;
  if (sub.isError) return <p className="text-sm text-destructive">{errorText(sub.error)}</p>;
  const s = sub.data;
  const canEdit = me.data?.role !== "viewer";
  return (
    <>
      <PageHeader
        title={<span className="flex flex-wrap items-center gap-2">{s.name}
          {s.owner_user_id && <Badge variant="outline" className="gap-1 font-normal"><LockIcon className="size-3" />Personal</Badge>}
          {s.status !== "active" && <Badge variant="secondary" className="capitalize">{s.status}</Badge>}
        </span>}
        description={[s.category, s.plan_name, KIND_LABEL[s.kind]].filter(Boolean).join(" · ")}
        actions={<>
          {s.account_url && (
            <Button variant="outline" asChild>
              <a href={s.account_url} target="_blank" rel="noreferrer"><ExternalLinkIcon /> Account</a>
            </Button>
          )}
          {canEdit && <Actions s={s} />}
        </>}
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        <Stat label="Per month" value={money(s.monthly_cost, s.currency)}
          hint={s.kind === "fixed" || s.kind === "contract" ? `${money(s.price, s.currency)} ${CYCLE_LABEL[s.cycle].toLowerCase()}` : undefined} />
        <Stat label="Next" value={s.next_event ? EVENT_LABEL[s.next_event.kind] : "Nothing due"}
          hint={s.next_event ? `${day(s.next_event.date)} · ${inDays(s.next_event.days)}` : undefined} />
        {s.kind !== "refill" && <Stat label="Notice deadline" value={s.notice_deadline ? day(s.notice_deadline) : "None"}
          hint={s.notice_deadline && s.notice_days
            ? `${s.notice_days} days' notice before ${day(addDays(s.notice_deadline, s.notice_days))}`
            : "Cancel any time"} />}
      </div>
      <Tabs defaultValue="timeline">
        <TabsList className="mb-2 flex-wrap">
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          {s.kind === "refill" && <TabsTrigger value="medicine">Medicine</TabsTrigger>}
          {s.kind === "usage" && <TabsTrigger value="bills">Bills</TabsTrigger>}
          {s.kind !== "refill" && <TabsTrigger value="prices">Price history</TabsTrigger>}
          <TabsTrigger value="documents">Documents</TabsTrigger>
        </TabsList>
        <TabsContent value="timeline"><Timeline s={s} /></TabsContent>
        {s.kind === "refill" && <TabsContent value="medicine"><MedicineEditor subId={s.id} canEdit={canEdit} /></TabsContent>}
        {s.kind === "usage" && <TabsContent value="bills"><Bills s={s} canEdit={canEdit} /></TabsContent>}
        <TabsContent value="prices"><Prices s={s} /></TabsContent>
        <TabsContent value="documents"><Documents subId={s.id} canEdit={canEdit} /></TabsContent>
      </Tabs>
    </>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card size="sm">
      <CardContent>
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
        <p className="mt-1 font-heading text-xl font-semibold tabular-nums">{value}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

function Actions({ s }: { s: Sub }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const me = useMe();
  const run = (fn: () => Promise<Sub | undefined>, done: string) => async () => {
    try {
      const out = await fn();
      await qc.invalidateQueries({ queryKey: ["subscriptions"] });
      toast.success(done);
      if (out && out.id !== s.id) navigate({ to: "/subscriptions/$id", params: { id: String(out.id) } });
    } catch (e) {
      toast.error(errorText(e));
    }
  };
  const remove = run(async () => {
    unwrap(await api.DELETE("/api/subscriptions/{sub_id}", path(s.id)));
    await navigate({ to: "/subscriptions" });
    qc.removeQueries({ queryKey: ["subscriptions", s.id] }); // gone: don't let the refresh below refetch it
    return undefined;
  }, `${s.name} deleted`);
  return (
    <>
      {!s.owner_user_id && (
        <Button variant="outline" onClick={run(async () => unwrap(await api.POST("/api/subscriptions/{sub_id}/copy-to-mine", path(s.id))), "Copied to your list")}>
          <CopyPlusIcon /> Add to my list
        </Button>
      )}
      {s.owner_user_id === me.data?.id && (
        <Button variant="outline" onClick={run(async () => unwrap(await api.POST("/api/subscriptions/{sub_id}/make-shared", path(s.id))), "Now shared with the household")}>
          <UsersIcon /> Share with household
        </Button>
      )}
      <Button variant="outline" asChild>
        <Link to="/subscriptions/$id/edit" params={{ id: String(s.id) }}><PencilIcon /> Edit</Link>
      </Button>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="destructive" aria-label="Delete"><Trash2Icon /></Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {s.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Its price history, bills, medicine details and uploaded documents are deleted too. This cannot be undone.
              To keep the history, set the status to Cancelled instead.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={remove}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function Timeline({ s }: { s: Sub }) {
  const events = useQuery({
    queryKey: ["subscriptions", s.id, "events"],
    queryFn: async () => unwrap(await api.GET("/api/subscriptions/{sub_id}/events", path(s.id))),
  });
  if (events.isPending) return null;
  if (!events.data?.length) {
    return (
      <EmptyState icon={<CalendarClockIcon className="size-6" />} title="No upcoming dates">
        Add a renewal date, contract end or medicine stock to get reminders.
      </EmptyState>
    );
  }
  return (
    <Card>
      <CardContent>
        <ol className="relative ml-2 border-l">
          {events.data.map((e) => (
            <li key={`${e.kind}-${e.date}`} className="mb-5 ml-5 last:mb-0">
              <span className="absolute -left-[5px] mt-1.5 size-2.5 rounded-full bg-primary ring-4 ring-card" aria-hidden />
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{e.title}</p>
                <Badge variant={urgency(e.days)}>{inDays(e.days)}</Badge>
              </div>
              <p className="text-sm text-muted-foreground">{day(e.date)}</p>
            </li>
          ))}
        </ol>
        {s.reminder_days && s.reminder_days.length > 0 && (
          <p className="mt-6 text-xs text-muted-foreground">
            Reminders {s.reminder_days.join(", ")} days before, and on the day.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Prices({ s }: { s: Sub }) {
  const prices = useQuery({
    queryKey: ["subscriptions", s.id, "prices"],
    queryFn: async () => unwrap(await api.GET("/api/subscriptions/{sub_id}/prices", path(s.id))),
  });
  const rows = [...(prices.data ?? [])].reverse();
  if (!rows.length) return <EmptyState icon={<CalendarClockIcon className="size-6" />} title="No price recorded yet" />;
  return (
    <Card>
      <Table>
        <TableHeader><TableRow><TableHead>From</TableHead><TableHead className="text-right">Price</TableHead><TableHead className="text-right">Change</TableHead></TableRow></TableHeader>
        <TableBody>
          {rows.map((p, i) => {
            const prev = rows[i + 1]?.price;
            const diff = prev === undefined ? null : p.price - prev;
            return (
              <TableRow key={p.id}>
                <TableCell>{day(p.effective_date)}</TableCell>
                <TableCell className="text-right tabular-nums">{money(p.price, s.currency)}</TableCell>
                <TableCell className={`text-right tabular-nums ${diff && diff > 0 ? "text-destructive" : "text-muted-foreground"}`}>
                  {diff === null ? "—" : `${diff > 0 ? "+" : ""}${money(diff, s.currency)}`}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}

const BLANK_BILL: Schemas["BillBase"] = { period_start: "", period_end: "", amount: 0, usage_value: null, usage_unit: "" };

function Bills({ s, canEdit }: { s: Sub; canEdit: boolean }) {
  const qc = useQueryClient();
  const key = ["subscriptions", s.id, "bills"];
  const bills = useQuery({ queryKey: key, queryFn: async () => unwrap(await api.GET("/api/subscriptions/{sub_id}/bills", path(s.id))) });
  const [b, setB] = useState(BLANK_BILL);
  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: key }), qc.invalidateQueries({ queryKey: ["subscriptions"] })]);
  const add = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/subscriptions/{sub_id}/bills", { ...path(s.id), body: b })),
    onSuccess: async () => { setB(BLANK_BILL); await refresh(); toast.success("Bill added"); },
    onError: (e) => toast.error(errorText(e)),
  });
  const del = useMutation({
    mutationFn: async (billId: number) =>
      unwrap(await api.DELETE("/api/subscriptions/{sub_id}/bills/{bill_id}", { params: { path: { sub_id: s.id, bill_id: billId } } })),
    onSuccess: refresh,
    onError: (e) => toast.error(errorText(e)),
  });
  const submit = (e: FormEvent) => { e.preventDefault(); add.mutate(); };
  const rows = [...(bills.data ?? [])].reverse();
  return (
    <div className="grid gap-4">
      {canEdit && (
        <Card>
          <CardHeader><CardTitle>Add a bill</CardTitle><CardDescription>The monthly cost averages your bills by the days they cover.</CardDescription></CardHeader>
          <CardContent>
            <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[repeat(4,1fr)_auto] sm:items-end">
              <Field label="From" htmlFor="bs"><Input id="bs" type="date" required value={b.period_start} onChange={(e) => setB({ ...b, period_start: e.target.value })} /></Field>
              <Field label="To" htmlFor="be"><Input id="be" type="date" required value={b.period_end} onChange={(e) => setB({ ...b, period_end: e.target.value })} /></Field>
              <Field label="Amount" htmlFor="ba"><Input id="ba" type="number" min={0} step="0.01" required value={b.amount || ""} onChange={(e) => setB({ ...b, amount: Number(e.target.value) })} /></Field>
              <Field label={`Usage${s.usage_unit ? ` (${s.usage_unit})` : ""}`} htmlFor="bu">
                <Input id="bu" type="number" min={0} value={b.usage_value ?? ""} onChange={(e) => setB({ ...b, usage_value: e.target.value === "" ? null : Number(e.target.value), usage_unit: s.usage_unit })} />
              </Field>
              <Button type="submit" disabled={add.isPending}>Add</Button>
            </form>
          </CardContent>
        </Card>
      )}
      {rows.length === 0 ? (
        <EmptyState icon={<FileTextIcon className="size-6" />} title="No bills yet" />
      ) : (
        <Card>
          <Table>
            <TableHeader><TableRow><TableHead>Period</TableHead><TableHead className="text-right">Usage</TableHead><TableHead className="text-right">Amount</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
            <TableBody>
              {rows.map((bill) => (
                <TableRow key={bill.id}>
                  <TableCell>{day(bill.period_start)} – {day(bill.period_end)}</TableCell>
                  <TableCell className="text-right tabular-nums">{bill.usage_value ?? "—"} {bill.usage_value != null ? bill.usage_unit : ""}</TableCell>
                  <TableCell className="text-right tabular-nums">{money(bill.amount, s.currency)}</TableCell>
                  <TableCell>
                    {canEdit && <Button variant="ghost" size="icon" aria-label="Delete bill" onClick={() => del.mutate(bill.id!)}><Trash2Icon /></Button>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

function Documents({ subId, canEdit }: { subId: number; canEdit: boolean }) {
  const qc = useQueryClient();
  const key = ["subscriptions", subId, "documents"];
  const docs = useQuery({ queryKey: key, queryFn: async () => unwrap(await api.GET("/api/subscriptions/{sub_id}/documents", path(subId))) });
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const upload = async (file: File) => {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(apiUrl(`/api/subscriptions/${subId}/documents?kind=${file.type === "application/pdf" ? "bill" : "other"}`), { method: "POST", body: form });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Upload failed (${res.status})`);
      await qc.invalidateQueries({ queryKey: key });
      toast.success(`${file.name} uploaded`);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };
  const del = useMutation({
    mutationFn: async (docId: number) =>
      unwrap(await api.DELETE("/api/subscriptions/{sub_id}/documents/{doc_id}", { params: { path: { sub_id: subId, doc_id: docId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <div className="grid gap-4">
      {canEdit && (
        <div>
          <input ref={input} type="file" accept="application/pdf,image/*" className="sr-only" id="doc-upload"
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <Button variant="outline" disabled={busy} onClick={() => input.current?.click()}>
            <UploadIcon /> {busy ? "Uploading…" : "Upload contract or bill"}
          </Button>
          <p className="mt-1 text-xs text-muted-foreground">PDF or image, up to 15 MB.</p>
        </div>
      )}
      {!docs.data?.length ? (
        <EmptyState icon={<FileTextIcon className="size-6" />} title="No documents" />
      ) : (
        <Card>
          <ul className="divide-y">
            {docs.data.map((d) => (
              <li key={d.id} className="flex items-center gap-3 px-4 py-3">
                <FileTextIcon className="size-4 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{d.filename}</p>
                  <p className="text-xs text-muted-foreground capitalize">{d.kind} · {dateTime(d.uploaded_at)}</p>
                </div>
                <Button variant="ghost" size="icon" asChild>
                  <a href={apiUrl(`/api/subscriptions/${subId}/documents/${d.id}`)} aria-label={`Download ${d.filename}`}><DownloadIcon /></a>
                </Button>
                {canEdit && <Button variant="ghost" size="icon" aria-label={`Delete ${d.filename}`} onClick={() => del.mutate(d.id!)}><Trash2Icon /></Button>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
