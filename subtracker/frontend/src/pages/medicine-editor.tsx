import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { type Schemas, api, unwrap } from "@/lib/api";
import { day, errorText } from "@/lib/format";

type Med = Schemas["MedicineBase"];

export function MedicineEditor({ subId, canEdit }: { subId: number; canEdit: boolean }) {
  const qc = useQueryClient();
  const med = useQuery({
    queryKey: ["subscriptions", subId, "medicine"],
    queryFn: async () => unwrap(await api.GET("/api/subscriptions/{sub_id}/medicine", { params: { path: { sub_id: subId } } })),
  });
  const [m, setM] = useState<Med | null>(null);
  useEffect(() => { if (med.data) setM(med.data); }, [med.data]);
  if (!m) return null;
  const n = (key: keyof Med) => (e: React.ChangeEvent<HTMLInputElement>) => setM({ ...m, [key]: Number(e.target.value) });

  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      unwrap(await api.PUT("/api/subscriptions/{sub_id}/medicine", { params: { path: { sub_id: subId } }, body: m }));
      await qc.invalidateQueries({ queryKey: ["subscriptions"] }); // also refreshes the medicines overview
      toast.success("Medicine saved");
    } catch (err) {
      toast.error(errorText(err));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Supply & prescription</CardTitle>
        <CardDescription>Count last updated {day(m.qty_updated)}. Change the count after each refill and the run-out date moves with it.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
          <fieldset disabled={!canEdit} className="contents">
            <Field label="Tablets / doses on hand" htmlFor="qty"><Input id="qty" type="number" min={0} step="any" value={m.qty_on_hand} onChange={n("qty_on_hand")} /></Field>
            <Field label="Taken per day" htmlFor="dose"><Input id="dose" type="number" min={0} step="any" value={m.daily_dose} onChange={n("daily_dose")} /></Field>
            <Field label="Pack size" htmlFor="pack" hint="Used with the price to estimate monthly cost."><Input id="pack" type="number" min={0} step="any" value={m.pack_size} onChange={n("pack_size")} /></Field>
            <Field label="Cost per refill" htmlFor="cost"><Input id="cost" type="number" min={0} step="0.01" value={m.cost_per_fill} onChange={n("cost_per_fill")} /></Field>
            <Field label="Remind me to refill (days before running out)" htmlFor="lead"><Input id="lead" type="number" min={0} value={m.refill_lead_days} onChange={n("refill_lead_days")} /></Field>
            <Field label="Prescription valid until" htmlFor="script"><Input id="script" type="date" value={m.script_expiry ?? ""} onChange={(e) => setM({ ...m, script_expiry: e.target.value || null })} /></Field>
            <Field label="Pharmacy" htmlFor="pharmacy" className="sm:col-span-2"><Input id="pharmacy" value={m.pharmacy} onChange={(e) => setM({ ...m, pharmacy: e.target.value })} /></Field>
            {canEdit && <div className="sm:col-span-2"><Button type="submit">Save medicine</Button></div>}
          </fieldset>
        </form>
      </CardContent>
    </Card>
  );
}
