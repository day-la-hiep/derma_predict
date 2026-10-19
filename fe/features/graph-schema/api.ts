import { api } from "@/services/client";
import type { EntityTypeCreate, EntityTypeUpdate, GraphEntityType, GraphRelation, RelationCreate, RelationUpdate } from "./types";

/** Backend bọc mọi response trong `{ data }` (`ApiResponse`). */
async function unwrap<T>(p: Promise<{ data: { data: T } }>): Promise<T> {
  return (await p).data.data;
}

const root = "/admin/graph-schema";

export const graphSchemaApi = {
  listEntityTypes: () => unwrap<GraphEntityType[]>(api.get(`${root}/entity-types`)),
  createEntityType: (body: EntityTypeCreate) => unwrap<GraphEntityType>(api.post(`${root}/entity-types`, body)),
  updateEntityType: (id: string, body: EntityTypeUpdate) => unwrap<GraphEntityType>(api.patch(`${root}/entity-types/${encodeURIComponent(id)}`, body)),
  deleteEntityType: async (id: string) => {
    await api.delete(`${root}/entity-types/${encodeURIComponent(id)}`);
  },

  listRelations: () => unwrap<GraphRelation[]>(api.get(`${root}/relations`)),
  createRelation: (body: RelationCreate) => unwrap<GraphRelation>(api.post(`${root}/relations`, body)),
  updateRelation: (id: string, body: RelationUpdate) => unwrap<GraphRelation>(api.patch(`${root}/relations/${encodeURIComponent(id)}`, body)),
  deleteRelation: async (id: string) => {
    await api.delete(`${root}/relations/${encodeURIComponent(id)}`);
  },
};
