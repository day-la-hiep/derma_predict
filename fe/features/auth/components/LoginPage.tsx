"use client";

import { useRouter } from "next/navigation";
import { AuthScreen } from "./AuthScreen";
import { homePathOf, type AuthArea } from "@/services/client";

// Trang đăng nhập riêng của một khu. Đăng nhập đúng khu thì AccessGate tự chuyển (về `next` hoặc trang chủ);
// đăng nhập bằng tài khoản thuộc khu khác thì phiên đã lưu ở khu đó nên chuyển thẳng sang khu đó.
export function LoginPage({ area }: { area: AuthArea }) {
  const router = useRouter();
  return <AuthScreen area={area} allowRegister={area === "patient"} onAuthenticated={(loggedArea) => loggedArea !== area && router.replace(homePathOf(loggedArea))} />;
}
