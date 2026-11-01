export const doctorPaths = {
  // cổng vào: mở ca đã nhớ (không có thì ca đầu theo bộ lọc)
  entry: "/doctor",
  session: (id: string) => `/doctor/${encodeURIComponent(id)}`,
  records: "/doctor/records",
  report: (id: string) => `/doctor/records/${encodeURIComponent(id)}`,
};

export type DoctorRoute =
  | { kind: "entry" }
  | { kind: "session"; id: string }
  | { kind: "records"; reportId?: string };

export function parseDoctorRoute(pathname: string): DoctorRoute {
  const [, first, second] = pathname.split("/").filter(Boolean); // bỏ phần "doctor"
  if (!first) return { kind: "entry" };
  if (first === "records") return { kind: "records", reportId: second ? decodeURIComponent(second) : undefined };
  return { kind: "session", id: decodeURIComponent(first) };
}
