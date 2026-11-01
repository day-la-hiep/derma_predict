"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";
import { AccessGate } from "./access-gate";
import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: React.ReactNode }) {
  // trang chat (hồ sơ bệnh nhân) cần TanStack Query; khu bác sĩ/quản trị vẫn có client riêng trong `app-shell`
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } })
  );
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <TooltipProvider>
          <AccessGate>{children}</AccessGate>
          <Toaster position="top-center" richColors />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
