export const chatPaths = {
  // cổng vào: tới đoạn chat đã nhớ của hồ sơ đang chọn, không có thì trang "mới" của hồ sơ đó
  entry: "/chats",
  // màn quản lý hồ sơ, không nằm dưới /chats
  profiles: "/profile",
  // hội thoại mới luôn kèm hồ sơ
  new: (profileId: string) => `/chats/new/${encodeURIComponent(profileId)}`,
  // hội thoại độc lập: hồ sơ lấy từ chính hội thoại
  conversation: (id: string) => `/chats/${encodeURIComponent(id)}`,
};

export type ChatRoute =
  | { kind: "entry" }
  | { kind: "profiles" }
  | { kind: "new"; profileId?: string }
  | { kind: "conversation"; id: string };

export function parseChatRoute(pathname: string): ChatRoute {
  const [area, first, second] = pathname.split("/").filter(Boolean);
  if (area === "profile") return { kind: "profiles" };
  if (!first) return { kind: "entry" };
  if (first === "new") return { kind: "new", profileId: second ? decodeURIComponent(second) : undefined };
  return { kind: "conversation", id: decodeURIComponent(first) };
}
