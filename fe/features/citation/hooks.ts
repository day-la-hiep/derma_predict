"use client";

import { useQuery } from "@tanstack/react-query";
import { citationApi } from "./api";

export function useCitationPassages(documentId: string, pageStart: number | null, pageEnd: number | null, chunkId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["citation", "passages", documentId, pageStart, pageEnd, chunkId],
    queryFn: () => citationApi.passages(documentId, pageStart, pageEnd, chunkId),
    enabled,
  });
}

export function useCitationSource(documentId: string, page: number | null, enabled: boolean) {
  // URL ký sẵn có hạn: không giữ cache lâu để lần mở sau lấy URL mới
  return useQuery({
    queryKey: ["citation", "source", documentId, page],
    queryFn: () => citationApi.sourceUrl(documentId, page),
    enabled,
    staleTime: 0,
    gcTime: 0,
  });
}
