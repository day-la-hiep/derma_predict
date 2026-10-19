"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorMessage } from "@/features/document-pipeline/api";
import { ENTITY_LABELS, RELATION_LABELS } from "@/features/document-pipeline/constants";
import { graphSchemaApi } from "./api";
import type { EntityTypeCreate, EntityTypeUpdate, RelationCreate, RelationUpdate } from "./types";

export const qk = {
  entityTypes: ["graph-schema", "entity-types"] as const,
  relations: ["graph-schema", "relations"] as const,
};

export function useGraphEntityTypes() {
  return useQuery({ queryKey: qk.entityTypes, queryFn: graphSchemaApi.listEntityTypes });
}

export function useGraphRelations() {
  return useQuery({ queryKey: qk.relations, queryFn: graphSchemaApi.listRelations });
}

/** Nhãn tiếng Việt: bảng cố định cho loại có sẵn, danh mục của bác sĩ cho loại tự định nghĩa. */
export function useSchemaLabels() {
  const relations = useGraphRelations().data;
  const types = useGraphEntityTypes().data;
  return {
    relation: (type: string) => RELATION_LABELS[type] ?? relations?.find((r) => r.relation_type === type)?.title ?? type,
    /** loại do bác sĩ định nghĩa: nút mới của loại này tự được chấp nhận (không có từ điển chuẩn để đối chiếu) */
    custom: (type: string) => types?.some((t) => t.id === type && !t.builtin) ?? false,
    entity: (type: string) => ENTITY_LABELS[type] ?? types?.find((t) => t.id === type)?.title ?? type,
  };
}

/** Mọi thay đổi danh mục làm mới cả hai danh sách: xoá loại thực thể hay quan hệ đều đổi bảng kia. */
export function useGraphSchemaActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["graph-schema"] });
  const opts = { onSuccess: refresh, onError: (e: unknown) => toast.error(errorMessage(e)) };
  return {
    createEntityType: useMutation({ mutationFn: (b: EntityTypeCreate) => graphSchemaApi.createEntityType(b), ...opts }),
    updateEntityType: useMutation({ mutationFn: (v: { id: string; body: EntityTypeUpdate }) => graphSchemaApi.updateEntityType(v.id, v.body), ...opts }),
    deleteEntityType: useMutation({ mutationFn: (id: string) => graphSchemaApi.deleteEntityType(id), ...opts }),
    createRelation: useMutation({ mutationFn: (b: RelationCreate) => graphSchemaApi.createRelation(b), ...opts }),
    updateRelation: useMutation({ mutationFn: (v: { id: string; body: RelationUpdate }) => graphSchemaApi.updateRelation(v.id, v.body), ...opts }),
    deleteRelation: useMutation({ mutationFn: (id: string) => graphSchemaApi.deleteRelation(id), ...opts }),
  };
}
