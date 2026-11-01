"use client";

import { ChevronLeft, ChevronRight, ChevronUp, LogOut, Menu, Settings, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import {
  Sidebar,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenuButton,
  SidebarProvider,
} from "@/components/ui/sidebar";
import { logout } from "@/features/auth/logout";
import { SettingsDialog } from "@/features/settings/components/SettingsDialog";
import { getInitials } from "@/features/user";
import { cn } from "@/lib/utils";
import { AUTH_STATE_EVENT, getAuthenticatedUser } from "@/services/client";

const STORAGE_KEY = "derma.shell.sidebarCollapsed";
const ROLE_LABELS: Record<string, string> = { doctor: "Bác sĩ", admin: "Quản trị viên", patient: "Bệnh nhân" };

// cùng kiểu dòng chọn/không chọn với sidebar chat
const selectedRow = "bg-brand/10 text-brand font-medium border border-brand/25 shadow-xs";
const unselectedRow = "text-muted-foreground hover:bg-muted/70 hover:text-foreground border border-transparent";

export interface SidebarNavItem {
  href: string;
  label: string;
  hint: string;
  icon: LucideIcon;
  exact?: boolean;
}

// trang đưa nội dung lên topbar của khung (nút quay lại, tiêu đề, thao tác) qua <Topbar>
const TopbarContext = createContext<HTMLElement | null>(null);

export function Topbar({ children }: { children: React.ReactNode }) {
  const el = useContext(TopbarContext);
  return el ? createPortal(children, el) : null;
}

function isActive(pathname: string, href: string, exact?: boolean) {
  return exact ? pathname === href : pathname.startsWith(href);
}

function AccountFooter({ collapsed, onOpenSettings }: { collapsed: boolean; onOpenSettings: () => void }) {
  const [account, setAccount] = useState(() => getAuthenticatedUser());

  useEffect(() => {
    const sync = () => setAccount(getAuthenticatedUser());
    window.addEventListener(AUTH_STATE_EVENT, sync);
    return () => window.removeEventListener(AUTH_STATE_EVENT, sync);
  }, []);

  const displayName = account?.full_name || account?.username || "Tài khoản";

  return (
    <SidebarFooter className={cn("overflow-hidden border-t border-border bg-background/50 py-2.5 transition-all", collapsed ? "flex justify-center px-0" : "p-2.5")}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SidebarMenuButton
            size="lg"
            className={cn(
              "w-full cursor-pointer gap-2.5 overflow-hidden rounded-xl border border-transparent whitespace-nowrap transition-all hover:border-border/60 hover:bg-muted/80",
              collapsed ? "mx-auto size-9 justify-center p-0" : "px-2.5 py-2"
            )}
          >
            <Avatar className="size-7.5 shrink-0 rounded-full border border-border">
              <AvatarFallback className="rounded-full bg-brand/15 text-xs font-semibold text-brand">{getInitials(displayName)}</AvatarFallback>
            </Avatar>
            {!collapsed && (
              <div className="flex min-w-0 flex-1 items-center justify-between overflow-hidden">
                <div className="flex min-w-0 flex-col overflow-hidden text-left leading-tight whitespace-nowrap">
                  <span className="truncate text-xs font-semibold text-foreground">{displayName}</span>
                  <span className="truncate text-[10px] text-muted-foreground">
                    {account ? `@${account.username} · ${ROLE_LABELS[account.role] ?? account.role}` : "Đang tải tài khoản..."}
                  </span>
                </div>
                <ChevronUp className="ml-1 size-3.5 shrink-0 text-muted-foreground" />
              </div>
            )}
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" align={collapsed ? "start" : "center"} className="w-56 rounded-xl border border-border p-1 shadow-xl">
          <DropdownMenuItem onClick={onOpenSettings} className="cursor-pointer rounded-lg">
            <Settings className="size-4" />
            <span className="text-xs font-medium">Cài đặt hệ thống</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator className="bg-border" />
          <DropdownMenuItem variant="destructive" onClick={() => void logout()} className="cursor-pointer rounded-lg">
            <LogOut className="size-4" />
            <span className="text-xs font-medium">Đăng xuất</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarFooter>
  );
}

function SidebarInner({
  collapsed,
  drawer,
  brandLabel,
  brandIcon: BrandIcon,
  nav,
  onToggleCollapse,
  onNavigate,
  onOpenSettings,
}: {
  collapsed: boolean;
  drawer: boolean;
  brandLabel: string;
  brandIcon: LucideIcon;
  nav: SidebarNavItem[];
  onToggleCollapse: () => void;
  onNavigate: () => void;
  onOpenSettings: () => void;
}) {
  const pathname = usePathname();
  return (
    <Sidebar className="h-full w-full overflow-hidden border-r border-border bg-sidebar/70 backdrop-blur-md" collapsible="none">
      <SidebarHeader className="overflow-hidden border-b border-border bg-background/50 p-0 py-3.5">
        <div className={cn("flex h-9 w-full items-center overflow-hidden transition-all", collapsed ? "justify-center px-0" : "justify-between px-3.5")}>
          <div className="flex min-w-0 items-center gap-2.5 overflow-hidden">
            <button
              type="button"
              onClick={collapsed ? onToggleCollapse : undefined}
              aria-label={collapsed ? "Mở rộng thanh bên" : brandLabel}
              className={cn(
                "group/logo relative flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--brand)] to-[var(--brand-secondary,#4d7cff)] text-brand-foreground shadow-xs outline-hidden transition-all",
                collapsed ? "cursor-pointer hover:-translate-y-0.5 hover:shadow-accent" : "cursor-default"
              )}
            >
              <BrandIcon className={cn("size-4.5 transition-all duration-150", collapsed && "group-hover/logo:scale-0 group-hover/logo:opacity-0")} />
              {collapsed && (
                <ChevronRight className="absolute size-4.5 scale-0 opacity-0 transition-all duration-150 group-hover/logo:scale-100 group-hover/logo:opacity-100" />
              )}
            </button>
            {!collapsed && (
              <div className="flex min-w-0 flex-col leading-none">
                <span className="truncate text-sm font-semibold tracking-tight text-foreground">Derma AI</span>
                <span className="mt-0.5 truncate font-mono text-[10px] tracking-wider text-muted-foreground uppercase">{brandLabel}</span>
              </div>
            )}
          </div>
          {!collapsed &&
            (drawer ? (
              <Button variant="ghost" size="iconSm" onClick={onNavigate} aria-label="Đóng menu" className="rounded-lg text-muted-foreground hover:text-foreground">
                <X className="size-4" />
              </Button>
            ) : (
              <Button variant="ghost" size="iconSm" onClick={onToggleCollapse} aria-label="Thu gọn thanh bên" className="rounded-lg text-muted-foreground hover:text-foreground">
                <ChevronLeft className="size-4" />
              </Button>
            ))}
        </div>
      </SidebarHeader>

      <SidebarGroup className={cn("flex-1 overflow-y-auto py-3 transition-all", collapsed ? "flex items-center px-0" : "px-3")}>
        <nav className={cn("flex w-full flex-col gap-1", collapsed && "items-center")}>
          {nav.map(({ href, label, hint, icon: Icon, exact }) => (
            <SidebarMenuButton
              key={href}
              asChild
              size="lg"
              isActive={isActive(pathname, href, exact)}
              tooltip={label}
              className={cn(
                "cursor-pointer rounded-xl transition-colors",
                isActive(pathname, href, exact) ? selectedRow : unselectedRow,
                collapsed ? "size-9 justify-center p-0" : "w-full justify-start gap-2.5 px-3 py-2"
              )}
            >
              <Link href={href} onClick={onNavigate} title={hint} aria-current={isActive(pathname, href, exact) ? "page" : undefined}>
                <Icon className="size-4 shrink-0" />
                {!collapsed && <span className="truncate text-xs">{label}</span>}
              </Link>
            </SidebarMenuButton>
          ))}
        </nav>
      </SidebarGroup>

      <AccountFooter collapsed={collapsed} onOpenSettings={onOpenSettings} />
    </Sidebar>
  );
}

export function SidebarShell({
  brandLabel,
  brandIcon,
  nav,
  children,
}: {
  brandLabel: string;
  brandIcon: LucideIcon;
  nav: SidebarNavItem[];
  children: React.ReactNode;
}) {
  // nhớ theo trình duyệt; chỉ render sau AccessGate (client) nên đọc ngay khi khởi tạo không lệch hydration
  const [collapsed, setCollapsedState] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [topbarEl, setTopbarEl] = useState<HTMLElement | null>(null);

  const setCollapsed = (value: boolean) => {
    setCollapsedState(value);
    try {
      localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
    } catch {
      // trình duyệt chặn lưu trữ: vẫn thu gọn được trong phiên này
    }
  };

  const inner = (drawer: boolean) => (
    <SidebarInner
      collapsed={drawer ? false : collapsed}
      drawer={drawer}
      brandLabel={brandLabel}
      brandIcon={brandIcon}
      nav={nav}
      onToggleCollapse={() => setCollapsed(!collapsed)}
      onNavigate={() => setDrawerOpen(false)}
      onOpenSettings={() => setSettingsOpen(true)}
    />
  );

  return (
    <SidebarProvider open={!collapsed} onOpenChange={(open) => setCollapsed(!open)} className="min-h-dvh flex-row">
      <div className="flex min-h-dvh w-full bg-background print:block">
        <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
          <SheetContent side="left" showCloseButton={false} className="w-72 border-r border-border p-0 lg:hidden">
            <SheetTitle className="sr-only">Thanh bên điều hướng</SheetTitle>
            {inner(true)}
          </SheetContent>
        </Sheet>

        <aside
          className={cn(
            "group sticky top-0 hidden h-dvh shrink-0 flex-col overflow-hidden border-r border-border bg-sidebar transition-[width] duration-200 ease-linear lg:flex print:hidden",
            collapsed ? "w-16" : "w-72"
          )}
        >
          {inner(false)}
        </aside>

        <TopbarContext.Provider value={topbarEl}>
        <div className="flex min-w-0 flex-1 flex-col">
          {/* màn lớn chỉ hiện khi trang có đưa nội dung lên (ô rỗng thì ẩn); màn nhỏ luôn hiện để có nút mở menu */}
          <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-card px-4 after:absolute after:inset-x-0 after:top-full after:h-[calc(1rem+1px)] after:bg-background has-[[data-topbar-slot]:not(:empty)]:lg:flex lg:hidden print:hidden">
            <Button variant="ghost" size="iconSm" onClick={() => setDrawerOpen(true)} aria-label="Mở menu" className="rounded-lg lg:hidden">
              <Menu className="size-4" />
            </Button>
            <div ref={setTopbarEl} data-topbar-slot className="peer flex min-w-0 flex-1 items-center gap-3 empty:hidden" />
            <span className="text-sm font-semibold tracking-tight text-foreground peer-[:not(:empty)]:hidden lg:hidden">
              Derma AI <span className="font-normal text-muted-foreground">· {brandLabel}</span>
            </span>
          </header>
          {/* thu gọn sidebar thì bỏ giới hạn bề rộng để nội dung nở ra lấp phần vừa nhường */}
          <main className={cn("mx-auto w-full flex-1 px-4 py-6 sm:px-6 lg:px-8", collapsed ? "max-w-none" : "max-w-[96rem]")}>{children}</main>
          {/* dải nền đặc sát đáy che các dòng cuộn qua khe dưới thanh phân trang ghim (cao bằng bottom-6 của thanh đó) */}
          <div aria-hidden className="pointer-events-none sticky bottom-0 z-30 -mt-6 h-6 shrink-0 bg-background print:hidden" />
        </div>
        </TopbarContext.Provider>
      </div>
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </SidebarProvider>
  );
}
