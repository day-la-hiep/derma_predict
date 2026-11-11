import { api } from "@/services/client";
import { errorMessage } from "@/features/doctor";

export { errorMessage };

/* eslint-disable @typescript-eslint/no-explicit-any */

export interface CitationPassage {
  chunkId: string;
  section: string;
  pages: string;
  text: string;
  isCited: boolean;
}

export interface CitationPassages {
  title: string;
  passages: CitationPassage[];
}

export interface CitationSource {
  url: string;
  title: string;
  page: number | null;
}

async function unwrap<T>(p: Promise<{ data: any }>): Promise<T> {
  const res = (await p).data;
  return (res && typeof res === "object" && "data" in res ? res.data : res) as T;
}

export const citationApi = {
  async passages(documentId: string, pageStart: number | null, pageEnd: number | null, chunkId: string | null): Promise<CitationPassages> {
    const r = await unwrap<any>(
      api.get(`/citations/documents/${encodeURIComponent(documentId)}/passages`, {
        params: { page_start: pageStart ?? undefined, page_end: pageEnd ?? pageStart ?? undefined, chunk_id: chunkId ?? undefined },
      })
    );
    return {
      title: r.title ?? "",
      passages: (r.passages ?? []).map((x: any) => ({
        chunkId: x.chunk_id ?? "",
        section: x.section ?? "",
        pages: x.pages ?? "",
        text: x.text ?? "",
        isCited: Boolean(x.is_cited),
      })),
    };
  },

  async sourceUrl(documentId: string, page: number | null): Promise<CitationSource> {
    const r = await unwrap<any>(api.get(`/citations/documents/${encodeURIComponent(documentId)}/source-url`, { params: { page: page ?? undefined } }));
    return { url: r.url, title: r.title ?? "", page: r.page ?? page };
  },
};
