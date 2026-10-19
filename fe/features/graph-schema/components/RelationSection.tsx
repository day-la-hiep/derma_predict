"use client";

import { ArrowRight, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { HintIcon } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { RELATION_LABELS } from "@/features/document-pipeline/constants";
import { ConfirmDialog } from "@/features/document-pipeline/components/ConfirmDialog";
import { EmptyState } from "@/features/document-pipeline/components/bits";
import { errorMessage } from "@/features/document-pipeline/api";
import { TOPIC_LABELS } from "../constants";
import { useGraphEntityTypes, useGraphRelations, useGraphSchemaActions } from "../hooks";
import type { GraphEntityType, GraphRelation, TopicKind } from "../types";
import { Field, SourceBadge, selectBox } from "./bits";

function direction(r: GraphRelation, titles: Record<string, string>) {
  const topic = TOPIC_LABELS[r.topic];
  const other = titles[r.object_type] ?? r.object_type;
  return r.topic_is_head ? [topic, other] : [other, topic];
}

function RelationDialog({ editing, entityTypes, onClose }: { editing: GraphRelation | "new"; entityTypes: GraphEntityType[]; onClose: () => void }) {
  const { createRelation, updateRelation } = useGraphSchemaActions();
  const isNew = editing === "new";
  const [relationType, setRelationType] = useState(isNew ? "" : editing.relation_type);
  const [topic, setTopic] = useState<TopicKind>(isNew ? "disease" : editing.topic);
  const [objectType, setObjectType] = useState(isNew ? "effect/phenotype" : editing.object_type);
  const [topicIsHead, setTopicIsHead] = useState(isNew ? true : editing.topic_is_head);
  const [title, setTitle] = useState(isNew ? "" : editing.title);
  const [display, setDisplay] = useState(isNew ? "" : editing.display);
  const [hint, setHint] = useState(isNew ? "" : editing.hint);
  const [entityHint, setEntityHint] = useState(isNew ? "" : editing.entity_hint);
  const [enabled, setEnabled] = useState(isNew ? true : editing.enabled);
  const pending = createRelation.isPending || updateRelation.isPending;

  // thuốc không có nút DermO để nối
  const objects = entityTypes.filter((t) => !(topic === "drug" && t.id === "dermo"));
  const objectTitle = entityTypes.find((t) => t.id === objectType)?.title ?? objectType;
  const topicTitle = TOPIC_LABELS[topic];

  const save = () => {
    const done = () => {
      toast.success(isNew ? "Đã thêm quan hệ." : "Đã lưu.");
      onClose();
    };
    if (isNew) {
      createRelation.mutate(
        { relation_type: relationType.trim(), topic, object_type: objectType, topic_is_head: topicIsHead, title, display, hint, entity_hint: entityHint, enabled },
        { onSuccess: done }
      );
    } else if (editing.id) {
      updateRelation.mutate({ id: editing.id, body: { title, display, hint, entity_hint: entityHint, enabled } }, { onSuccess: done });
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && !pending && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{isNew ? "Thêm quan hệ" : "Sửa quan hệ"}</DialogTitle>
          <DialogDescription>Quan hệ nối chủ đề của một mục sách (bệnh hoặc thuốc) với một thực thể khác.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tên hiển thị">
              <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} placeholder="hay gặp ở" className="h-9 rounded-xl text-sm" />
            </Field>
            <Field label={<>Loại quan hệ <HintIcon content="Tên cạnh trong đồ thị, viết HOA và gạch dưới (vd DISEASE_AFFECTS_GROUP). Không đổi được sau khi tạo." /></>}>
              <Input
                value={relationType}
                onChange={(e) => setRelationType(e.target.value.toUpperCase())}
                disabled={!isNew}
                placeholder="DISEASE_AFFECTS_GROUP"
                className="h-9 rounded-xl font-mono text-sm"
              />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Chủ đề mục">
              <select
                value={topic}
                disabled={!isNew}
                onChange={(e) => {
                  const next = e.target.value as TopicKind;
                  setTopic(next);
                  if (next === "drug" && objectType === "dermo") setObjectType("effect/phenotype");
                }}
                className={selectBox}
              >
                {(Object.keys(TOPIC_LABELS) as TopicKind[]).map((k) => (
                  <option key={k} value={k}>{TOPIC_LABELS[k]}</option>
                ))}
              </select>
            </Field>
            <Field label="Đầu kia">
              <select value={objectType} disabled={!isNew} onChange={(e) => setObjectType(e.target.value)} className={selectBox}>
                {objects.map((t) => (
                  <option key={t.id} value={t.id}>{t.title}</option>
                ))}
              </select>
            </Field>
          </div>
          <Field label={<>Chiều <HintIcon content="Hướng của cạnh trong đồ thị. Ví dụ “Thuốc → Bệnh” cho quan hệ chỉ định." /></>}>
            <select value={topicIsHead ? "head" : "tail"} disabled={!isNew} onChange={(e) => setTopicIsHead(e.target.value === "head")} className={selectBox}>
              <option value="head">{topicTitle} → {objectTitle}</option>
              <option value="tail">{objectTitle} → {topicTitle}</option>
            </select>
          </Field>
          <Field label={<>Mô tả cho AI <HintIcon content="Giải thích cho AI khi nào ghi nhận quan hệ này. Càng cụ thể càng ít nhầm. Vd: nhóm bệnh nhân hay mắc bệnh này." /></>}>
            <Textarea value={hint} onChange={(e) => setHint(e.target.value)} maxLength={300} className="min-h-16 rounded-xl text-sm" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={<>Cách ghi thực thể <HintIcon content="Không bắt buộc. Để trống thì dùng hướng dẫn mặc định của loại thực thể đầu kia." /></>}>
              <Input value={entityHint} onChange={(e) => setEntityHint(e.target.value)} maxLength={300} className="h-9 rounded-xl text-sm" />
            </Field>
            <Field label={<>Nhãn trên cạnh <HintIcon content="Chữ lưu trên cạnh trong đồ thị. Để trống thì dùng tên hiển thị." /></>}>
              <Input value={display} onChange={(e) => setDisplay(e.target.value)} maxLength={100} className="h-9 rounded-xl text-sm" />
            </Field>
          </div>
          <label className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1 text-xs font-medium text-foreground">
              Bật <HintIcon content="Tắt thì lần trích sau không tìm quan hệ này nữa; những gì đã trích và duyệt vẫn được lưu." />
            </span>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={pending}>Hủy</Button>
          <Button onClick={save} disabled={pending || !title.trim() || !hint.trim() || (isNew && !relationType.trim())}>
            {pending && <Loader2 className="animate-spin" />}
            Lưu
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RelationSection() {
  const relations = useGraphRelations();
  const types = useGraphEntityTypes();
  const { updateRelation, deleteRelation } = useGraphSchemaActions();
  const [editing, setEditing] = useState<GraphRelation | "new" | null>(null);
  const [deleting, setDeleting] = useState<GraphRelation | null>(null);

  if (relations.isLoading || types.isLoading) return <Skeleton className="h-64 rounded-2xl" />;
  if (relations.isError || types.isError) {
    const err = relations.error ?? types.error;
    return <EmptyState title="Không tải được danh mục quan hệ" hint={errorMessage(err)} action={<Button variant="outline" onClick={() => { relations.refetch(); types.refetch(); }}>Thử lại</Button>} />;
  }
  const entityTypes = types.data ?? [];
  const titles = Object.fromEntries(entityTypes.map((t) => [t.id, t.title]));

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setEditing("new")}>
          <Plus /> Thêm quan hệ
        </Button>
      </div>
      <div className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card">
        {(relations.data ?? []).map((r) => {
          const [from, to] = direction(r, titles);
          return (
            <div key={`${r.slot_id}:${r.relation_type}`} className="flex items-start gap-4 px-4 py-3">
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-foreground">{r.builtin ? (RELATION_LABELS[r.relation_type] ?? r.title) : r.title}</span>
                  <SourceBadge builtin={r.builtin} kg={r.kg} />
                  <span className="font-mono text-[11px] text-muted-foreground">{r.relation_type}</span>
                </div>
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  {from} <ArrowRight className="size-3" /> {to}
                </p>
                <p className="text-xs text-muted-foreground">{r.hint}</p>
              </div>
              {r.builtin ? (
                <span className="shrink-0 text-[11px] text-muted-foreground">Luôn bật</span>
              ) : (
                <div className="flex shrink-0 items-center gap-2">
                  <Switch
                    size="sm"
                    checked={r.enabled}
                    aria-label={r.enabled ? "Tắt quan hệ" : "Bật quan hệ"}
                    onCheckedChange={(v) => r.id && updateRelation.mutate({ id: r.id, body: { enabled: v } })}
                  />
                  <Button variant="ghost" size="icon-xs" aria-label="Sửa" onClick={() => setEditing(r)}><Pencil /></Button>
                  <Button variant="ghost" size="icon-xs" aria-label="Xóa" className="text-muted-foreground hover:text-destructive" onClick={() => setDeleting(r)}><Trash2 /></Button>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {editing && <RelationDialog key={editing === "new" ? "new" : editing.id} editing={editing} entityTypes={entityTypes} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Xóa “${deleting?.title ?? ""}”?`}
        description="Xóa định nghĩa và mọi cạnh loại này đã lưu vào đồ thị từ các sách. Quan hệ đã trích trong từng sách sẽ bị bỏ qua khi lưu lại. Không thể hoàn tác."
        confirmLabel="Xóa quan hệ"
        destructive
        pending={deleteRelation.isPending}
        onConfirm={() => deleting?.id && deleteRelation.mutate(deleting.id, { onSuccess: () => { toast.success("Đã xóa."); setDeleting(null); } })}
      />
    </div>
  );
}
