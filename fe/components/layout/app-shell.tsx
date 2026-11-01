"use client";

import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { ChevronDown, LogOut, Settings2, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Hint } from "@/components/ui/hint";
import { AccountSettingsDialog } from "@/features/auth/components/AccountSettingsDialog";
import { logout } from "@/features/auth/logout";
import { getInitials } from "@/features/user";
import { cn } from "@/lib/utils";
import { AUTH_STATE_EVENT, getAuthenticatedUser } from "@/services/client";
import { SidebarShell } from "./sidebar-shell";

export interface ShellNavItem {
  href: string;
  label: string;
  hint: string;
  icon: LucideIcon;
  exact?: boolean;
  // đường dẫn nào thì mục này sáng (mặc định theo href)
  match?: (pathname: string) => boolean;
}

interface AppShellProps {
  brandLabel: string;
  brandIcon: LucideIcon;
  navTitle: string;
  nav: ShellNavItem[];
  // trang 3 cột cần khung cao bằng màn hình; trang thường thì cuộn
  fullBleed?: boolean;
  // sidebar trái (cơ chế như sidebar chat) + nội dung bên phải thay cho thanh trên
  sidebar?: boolean;
  children: React.ReactNode;
}

function isActive(pathname: string, item: Pick<ShellNavItem, "href" | "exact" | "match">) {
  if (item.match) return item.match(pathname);
  return item.exact ? pathname === item.href : pathname.startsWith(item.href);
}

function Brand({ href, label, icon: Icon }: { href: string; label: string; icon: LucideIcon }) {
  return (
    <Link href={href} className="flex shrink-0 items-center gap-2.5">
      <span className="flex size-8 items-center justify-center rounded-xl bg-brand/10 text-brand">
        <Icon className="size-4" />
      </span>
      <span className="hidden text-sm font-semibold tracking-tight text-foreground sm:inline">
        Derma AI <span className="font-normal text-muted-foreground">· {label}</span>
      </span>
    </Link>
  );
}

function AccountMenu() {
  const [account, setAccount] = useState(() => getAuthenticatedUser());
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    const sync = () => setAccount(getAuthenticatedUser());
    window.addEventListener(AUTH_STATE_EVENT, sync);
    return () => window.removeEventListener(AUTH_STATE_EVENT, sync);
  }, []);

  if (!account) return null;
  const displayName = account.full_name || account.username;

  return (
    <div className="flex shrink-0 items-center">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" className="flex items-center gap-2 rounded-xl px-2 py-1.5 transition-colors hover:bg-muted">
            <Avatar className="size-7 shrink-0 rounded-full border border-border">
              <AvatarFallback className="rounded-full bg-brand/15 text-xs font-semibold text-brand">
                {getInitials(displayName)}
              </AvatarFallback>
            </Avatar>
            <span className="hidden max-w-40 truncate text-xs font-medium text-foreground sm:inline">{displayName}</span>
            <ChevronDown className="hidden size-3.5 shrink-0 text-muted-foreground sm:inline" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="bottom" align="end" className="w-52 rounded-xl border border-border p-1 shadow-xl">
          <DropdownMenuItem onClick={() => setSettingsOpen(true)} className="cursor-pointer rounded-lg">
            <Settings2 className="size-4" />
            <span className="text-xs font-medium">Cài đặt</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator className="bg-border" />
          <DropdownMenuItem variant="destructive" onClick={() => void logout()} className="cursor-pointer rounded-lg">
            <LogOut className="size-4" />
            <span className="text-xs font-medium">Đăng xuất</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <AccountSettingsDialog account={account} open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}

export function AppShell({ brandLabel, brandIcon, navTitle, nav, fullBleed = false, sidebar = false, children }: AppShellProps) {
  const pathname = usePathname();
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 5_000 } } })
  );
  const home = nav[0]?.href ?? "/";
  if (sidebar) {
    return (
      <QueryClientProvider client={client}>
        <SidebarShell brandLabel={brandLabel} brandIcon={brandIcon} nav={nav}>
          {children}
        </SidebarShell>
      </QueryClientProvider>
    );
  }

  return (
    <QueryClientProvider client={client}>
      <div className={cn("flex flex-col bg-background print:h-auto print:overflow-visible", fullBleed ? "h-dvh overflow-hidden" : "min-h-screen")}>
        <header className="sticky top-0 z-30 flex h-14 shrink-0 print:hidden items-center gap-4 border-b border-border bg-card/60 px-4 backdrop-blur-md sm:px-6">
          <Brand href={home} label={brandLabel} icon={brandIcon} />
          <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto" aria-label={navTitle}>
            {nav.map((item) => {
              const { href, label, hint, icon: Icon } = item;
              const active = isActive(pathname, item);
              return (
                <Hint key={href} side="bottom" content={hint}>
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                      active ? "bg-brand/10 text-brand" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                  >
                    <Icon className="size-3.5" />
                    {label}
                  </Link>
                </Hint>
              );
            })}
          </nav>
          <AccountMenu />
        </header>
        {fullBleed ? (
          <main className="min-h-0 flex-1 print:overflow-visible">{children}</main>
        ) : (
          <main className="mx-auto w-full max-w-[96rem] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
        )}
      </div>
    </QueryClientProvider>
  );
}
