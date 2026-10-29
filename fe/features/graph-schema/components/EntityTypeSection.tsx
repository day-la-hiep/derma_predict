"use client";

import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { HintIcon } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/features/document-pipeline/components/ConfirmDialog";
import { EmptyState } from "@/features/document-pipeline/components/bits";
import { errorMessage } from "@/features/document-pipeline/api";
import { useGraphEntityTypes, useGraphSchemaActions } from "../hooks";
import type { GraphEntityType } from "../types";
import { Field, SourceBadge } from "./bits";

function EntityTypeDialog({ editing, onClose }: { editing: GraphEntityType | "new"; onClose: () => void }) {
  const { createEntityType, updateEntityType } = useGraphSchemaActions();
  const isNew = editing === "new";
  const [id, setId] = useState(isNew ? "" : editing.id);
  const [label, setLabel] = useState(isNew ? "" : editing.label);
  const [title, setTitle] = useState(isNew ? "" : editing.title);
  const [hint, setHint] = useState(isNew ? "" : editing.hint);
  const [caseSensitive, setCaseSensitive] = useState(isNew ? false : editing.case_sensitive);
  const pending = createEntityType.isPending || updateEntityType.isPending;

  const save = () => {
    const done = () => {
      toast.success(isNew ? "Đã thêm loại thực thể." : "Đã lưu.");
      onClose();
    };
    if (isNew) createEntityType.mutate({ id: id.trim(), label: label.trim(), title, hint, case_sensitive: caseSensitive }, { onSuccess: done });
    else updateEntityType.mutate({ id: editing.id, body: { title, hint, case_sensitive: caseSensitive } }, { onSuccess: done });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && !pending && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isNew ? "Thêm loại thực thể" : "Sửa loại thực thể"}</DialogTitle>
          <DialogDescription>Loại thực thể dùng làm đầu kia của quan hệ, ví dụ “Nhóm bệnh nhân”.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={<>Mã <HintIcon content="Chữ thường, số, gạch dưới (vd patient_group). Không đổi được sau khi tạo." /></>}>
              <Input value={id} onChange={(e) => setId(e.target.value)} disabled={!isNew} className="h-9 rounded-xl font-mono text-sm" />
            </Field>
            <Field label={<>Label Neo4j <HintIcon content="Viết kiểu PascalCase (vd PatientGroup), gắn vào nút trong đồ thị. Không đổi được sau khi tạo." /></>}>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} disabled={!isNew} className="h-9 rounded-xl font-mono text-sm" />
            </Field>
          </div>
          <Field label="Tên hiển thị">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} className="h-9 rounded-xl text-sm" />
          </Field>
          <Field label={<>Cách ghi tên <HintIcon content="Hướng dẫn gửi cho AI về cách viết tên thực thể loại này, nên có ví dụ. Vd: nhóm bệnh nhân tiếng Anh, vd 'children'." /></>}>
            <Textarea value={hint} onChange={(e) => setHint(e.target.value)} maxLength={300} className="min-h-16 rounded-xl text-sm" />
          </Field>
          <label className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1 text-xs font-medium text-foreground">
              Phân biệt hoa thường <HintIcon content="Bật cho ký hiệu viết tắt như tên gen (FLG khác Flg). Thường để tắt." />
            </span>
            <Switch checked={caseSensitive} onCheckedChange={setCaseSensitive} />
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={pending}>Hủy</Button>
          <Button onClick={save} disabled={pending || !title.trim() || !hint.trim() || (isNew && (!id.trim() || !label.trim()))}>
            {pending && <Loader2 className="animate-spin" />}
            Lưu
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EntityTypeSection() {
  const types = useGraphEntityTypes();
  const { deleteEntityType } = useGraphSchemaActions();
  const [editing, setEditing] = useState<GraphEntityType | "new" | null>(null);
  const [deleting, setDeleting] = useState<GraphEntityType | null>(null);

  if (types.isLoading) return <Skeleton className="h-48 rounded-2xl" />;
  if (types.isError) {
    return <EmptyState title="Không tải được loại thực thể" hint={errorMessage(types.error)} action={<Button variant="outline" onClick={() => types.refetch()}>Thử lại</Button>} />;
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setEditing("new")}>
          <Plus /> Thêm loại
        </Button>
      </div>
      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tên</TableHead>
              <TableHead>Mã</TableHead>
              <TableHead>Label Neo4j</TableHead>
              <TableHead>Nguồn</TableHead>
              <TableHead>Cách ghi tên</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(types.data ?? []).map((t) => (
              <TableRow key={t.id}>
                <TableCell className="font-medium text-foreground">{t.title}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{t.id}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{t.label}</TableCell>
                <TableCell><SourceBadge builtin={t.builtin} kg={t.kg} /></TableCell>
                <TableCell className="max-w-md text-xs whitespace-normal text-muted-foreground">{t.hint}</TableCell>
                <TableCell>
                  {!t.builtin && (
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="icon-xs" aria-label="Sửa" onClick={() => setEditing(t)}><Pencil /></Button>
                      <Button variant="ghost" size="icon-xs" aria-label="Xóa" className="text-muted-foreground hover:text-destructive" onClick={() => setDeleting(t)}><Trash2 /></Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {editing && <EntityTypeDialog key={editing === "new" ? "new" : editing.id} editing={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Xóa “${deleting?.title ?? ""}”?`}
        description="Chỉ xóa được khi không còn quan hệ nào dùng loại này. Các nút đã lưu vào đồ thị vẫn giữ nguyên."
        confirmLabel="Xóa loại"
        destructive
        pending={deleteEntityType.isPending}
        onConfirm={() => deleting && deleteEntityType.mutate(deleting.id, { onSuccess: () => { toast.success("Đã xóa."); setDeleting(null); } })}
      />
    </div>
  );
}
