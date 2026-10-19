export type KgSource = "primekg" | "dermo" | "doc";
export type TopicKind = "disease" | "drug";

export interface GraphEntityType {
  id: string;
  /** true = có sẵn trong hệ thống, chỉ xem */
  builtin: boolean;
  kg: KgSource;
  label: string;
  title: string;
  hint: string;
  case_sensitive: boolean;
}

export interface GraphRelation {
  id: string | null;
  builtin: boolean;
  slot_id: string;
  relation_type: string;
  kg: KgSource;
  topic: TopicKind;
  object_type: string;
  /** true: chủ đề của mục sách -> đầu kia; false: đầu kia -> chủ đề */
  topic_is_head: boolean;
  title: string;
  display: string;
  hint: string;
  entity_hint: string;
  enabled: boolean;
}

export interface EntityTypeCreate {
  id: string;
  label: string;
  title: string;
  hint: string;
  case_sensitive: boolean;
}
export type EntityTypeUpdate = Partial<Pick<EntityTypeCreate, "title" | "hint" | "case_sensitive">>;

export interface RelationCreate {
  relation_type: string;
  topic: TopicKind;
  object_type: string;
  topic_is_head: boolean;
  title: string;
  display: string;
  hint: string;
  entity_hint: string;
  enabled: boolean;
}
export type RelationUpdate = Partial<Pick<RelationCreate, "title" | "display" | "hint" | "entity_hint" | "enabled">>;
