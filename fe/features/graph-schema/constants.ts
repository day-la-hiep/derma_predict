import type { TopicKind } from "./types";

export const TOPIC_LABELS: Record<TopicKind, string> = { disease: "Bệnh", drug: "Thuốc" };

export const KG_LABELS = { primekg: "PrimeKG", dermo: "DermO", doc: "Bác sĩ định nghĩa" } as const;
