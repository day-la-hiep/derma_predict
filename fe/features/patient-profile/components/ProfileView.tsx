"use client";

import { useState } from "react";
import { ArrowLeft, BadgeCheck, Loader2, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Hint, HintIcon } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { EMPTY_PROFILE, FACT_TYPE_LABELS, GENDER_LABELS, HINTS, RELATIONSHIP_LABELS } from "../constants";
import { useFinalizeReports, useProfileActions, useProfiles } from "../hooks";
import type {
  Gender,
  LongTermFactType,
  PatientProfile,
  PatientProfileInput,
  ProfileFactInput,
  ProfileRelationship,
} from "../types";

type Tab = "info" | "reports";

function age(dob: string): number | null {
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  return now.getFullYear() - d.getFullYear() - (now < new Date(now.getFullYear(), d.getMonth(), d.getDate()) ? 1 : 0);
}

function toInput(p: PatientProfile): PatientProfileInput {
  return {
    full_name: p.full_name,
    dob: p.dob,
    gender: p.gender,
    relationship: p.relationship,
    phone: p.phone,
    long_term_facts: p.long_term_facts.map(({ fact_type, label, detail }) => ({ fact_type, label, detail })),
  };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
        {label}
        {hint && <HintIcon content={hint} />}
      </span>
      {children}
    </label>
  );
}

function FactsEditor({
  facts,
  verified,
  onChange,
}: {
  facts: ProfileFactInput[];
  verified: Set<string>;
  onChange: (facts: ProfileFactInput[]) => void;
}) {
  const patch = (i: number, value: Partial<ProfileFactInput>) =>
    onChange(facts.map((f, j) => (j === i ? { ...f, ...value } : f)));
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
        Dị ứng · tiền sử · thuốc đang dùng
        <HintIcon content={HINTS.facts} />
      </span>
      {facts.length === 0 && <p className="text-xs text-muted-foreground/80">Chưa có thông tin.</p>}
      {facts.map((f, i) => (
        <div key={i} className="flex items-center gap-2">
          <Select value={f.fact_type} onValueChange={(v) => patch(i, { fact_type: v as LongTermFactType })}>
            <SelectTrigger className="w-36 shrink-0"><SelectValue /></SelectTrigger>
            <SelectContent position="popper" side="bottom" align="start">
              {Object.entries(FACT_TYPE_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
          <Input value={f.label} onChange={(e) => patch(i, { label: e.target.value })} placeholder="Ví dụ: penicillin" />
          <Input value={f.detail} onChange={(e) => patch(i, { detail: e.target.value })} placeholder="Chi tiết (không bắt buộc)" />
          {verified.has(`${f.fact_type}:${f.label.trim().toLowerCase()}`) && (
            <Hint content="Bác sĩ đã xác nhận khi khám">
              <BadgeCheck className="size-4 shrink-0 text-brand" />
            </Hint>
          )}
          <Button type="button" variant="ghost" size="iconSm" aria-label="Xoá dòng" onClick={() => onChange(facts.filter((_, j) => j !== i))}>
            <X className="size-4 text-muted-foreground" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="self-start"
        onClick={() => onChange([...facts, { fact_type: "allergy", label: "", detail: "" }])}
      >
        <Plus className="size-4" /> Thêm dòng
      </Button>
    </div>
  );
}

function ProfileForm({ profile, onDone }: { profile: PatientProfile | null; onDone: (saved: PatientProfile) => void }) {
  const { create, update } = useProfileActions();
  // nơi gọi đặt `key` theo id hồ sơ nên đổi hồ sơ là dựng lại form, không cần đồng bộ state bằng effect
  const [form, setForm] = useState<PatientProfileInput>(profile ? toInput(profile) : EMPTY_PROFILE);

  const set = <K extends keyof PatientProfileInput>(key: K, value: PatientProfileInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));
  const saving = create.isPending || update.isPending;
  const valid = form.full_name.trim() && form.dob;

  const verified = new Set(
    (profile?.long_term_facts ?? []).filter((f) => f.verified_at).map((f) => `${f.fact_type}:${f.label.toLowerCase()}`)
  );

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const body = {
      ...form,
      full_name: form.full_name.trim(),
      phone: form.phone?.trim() || null,
      long_term_facts: form.long_term_facts
        .map((f) => ({ ...f, label: f.label.trim(), detail: f.detail.trim() }))
        .filter((f) => f.label),
    };
    const onSuccess = (saved: PatientProfile) => {
      toast.success(profile ? "Đã lưu" : "Đã thêm hồ sơ");
      onDone(saved);
    };
    if (profile) update.mutate({ id: profile.id, body }, { onSuccess });
    else create.mutate(body, { onSuccess });
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Họ tên">
          <Input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} placeholder="Họ và tên" />
        </Field>
        <Field label="Ngày sinh">
          <Input type="date" value={form.dob} onChange={(e) => set("dob", e.target.value)} />
        </Field>
        <Field label="Giới tính">
          <Select value={form.gender} onValueChange={(v) => set("gender", v as Gender)}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent position="popper" side="bottom" align="start">
              {Object.entries(GENDER_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Quan hệ">
          <Select value={form.relationship} onValueChange={(v) => set("relationship", v as ProfileRelationship)}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent position="popper" side="bottom" align="start">
              {Object.entries(RELATIONSHIP_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Số điện thoại">
          <Input value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} placeholder="Không bắt buộc" />
        </Field>
      </div>
      <FactsEditor facts={form.long_term_facts} verified={verified} onChange={(v) => set("long_term_facts", v)} />
      <div className="flex justify-end">
        <Button type="submit" variant="brand" disabled={!valid || saving}>
          {saving && <Loader2 className="size-4 animate-spin" />}
          {profile ? "Lưu" : "Thêm"}
        </Button>
      </div>
    </form>
  );
}

function FinalizeReports({ profileId }: { profileId: string }) {
  const { data, isLoading, error } = useFinalizeReports(profileId);
  if (isLoading) return <p className="text-xs text-muted-foreground">Đang tải…</p>;
  if (error) return <p className="text-xs text-destructive">Không tải được báo cáo kết luận.</p>;
  if (!data?.length) return <p className="text-xs text-muted-foreground">Chưa có báo cáo kết luận.</p>;
  return (
    <ul className="flex flex-col gap-3">
      {data.map((r) => (
        <li key={r.id} className="rounded-xl border border-border p-3.5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm font-medium text-foreground">{r.diagnosis}</span>
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
              {new Date(r.created_at).toLocaleDateString("vi-VN")}
            </span>
          </div>
          {r.notes && <p className="mt-1.5 whitespace-pre-line text-xs leading-relaxed text-muted-foreground">{r.notes}</p>}
          <p className="mt-2 text-[10px] text-muted-foreground/80">{r.doctor_name ?? "Bác sĩ"}</p>
        </li>
      ))}
    </ul>
  );
}

// Màn riêng trong khu vực nội dung chính (không phải Dialog) — thay cho `MessageList`/`ChatInput` khi đang xem Hồ sơ.
export function ProfileView({ onBack }: { onBack: () => void }) {
  const { data: profiles = [], isLoading } = useProfiles();
  const { remove } = useProfileActions();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [tab, setTab] = useState<Tab>("info");

  // chưa chọn (hoặc hồ sơ vừa bị xoá) thì hiện hồ sơ đầu tiên
  const selected = creating ? null : (profiles.find((p) => p.id === selectedId) ?? profiles[0] ?? null);

  const pick = (id: string) => {
    setCreating(false);
    setSelectedId(id);
  };

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col bg-background">
      <header className="flex shrink-0 items-center gap-3 border-b border-border/80 bg-background/80 px-4 py-3 backdrop-blur-md">
        <Button variant="ghost" size="iconSm" onClick={onBack} aria-label="Quay lại chat" className="rounded-lg text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" />
        </Button>
        <h1 className="font-serif text-sm font-semibold tracking-tight text-foreground">Hồ sơ</h1>
      </header>
      <div className="mx-auto flex w-full min-h-0 max-w-4xl flex-1 flex-col sm:flex-row">
        <aside className="flex shrink-0 flex-col gap-1 border-b border-border/80 p-3 sm:w-56 sm:border-b-0 sm:border-r">
          {isLoading && <p className="px-2 text-xs text-muted-foreground">Đang tải…</p>}
          {profiles.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => pick(p.id)}
              className={cn(
                "flex flex-col items-start rounded-xl px-3 py-2 text-left transition-colors",
                p.id === selected?.id ? "bg-brand/10 text-brand" : "hover:bg-muted/70"
              )}
            >
              <span className="w-full truncate text-xs font-medium">{p.full_name}</span>
              <span className="text-[10px] text-muted-foreground">
                {RELATIONSHIP_LABELS[p.relationship]}
                {age(p.dob) !== null && ` · ${age(p.dob)} tuổi`}
              </span>
            </button>
          ))}
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 justify-start"
            onClick={() => {
              setCreating(true);
              setTab("info");
            }}
          >
            <Plus className="size-4" /> Thêm
          </Button>
        </aside>

        <section className="min-h-0 flex-1 overflow-y-auto p-6">
          {creating ? (
            <ProfileForm
              key="new"
              profile={null}
              onDone={(p) => {
                setCreating(false);
                setSelectedId(p.id);
              }}
            />
          ) : selected ? (
            <div className="flex flex-col gap-5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex gap-1 rounded-lg bg-muted p-1">
                  {(["info", "reports"] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setTab(t)}
                      className={cn(
                        "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                        tab === t ? "bg-background text-foreground shadow-xs" : "text-muted-foreground"
                      )}
                    >
                      {t === "info" ? "Thông tin" : "Kết luận"}
                    </button>
                  ))}
                </div>
                {tab === "info" ? (
                  <Hint content={HINTS.delete}>
                    <Button
                      variant="ghost"
                      size="iconSm"
                      aria-label="Xoá hồ sơ"
                      disabled={remove.isPending}
                      onClick={() => {
                        if (window.confirm(`Xoá hồ sơ "${selected.full_name}"?`))
                          remove.mutate(selected.id, { onSuccess: () => setSelectedId(null) });
                      }}
                    >
                      <Trash2 className="size-4 text-muted-foreground" />
                    </Button>
                  </Hint>
                ) : (
                  <HintIcon content={HINTS.reports} />
                )}
              </div>
              {tab === "info" ? (
                <ProfileForm key={selected.id} profile={selected} onDone={() => undefined} />
              ) : (
                <FinalizeReports profileId={selected.id} />
              )}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
