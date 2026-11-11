export const doctorPaths = {
  appointments: "/doctor/appointments",
  followups: "/doctor/followups",
  records: "/doctor/records",
  report: (id: string) => `/doctor/records/${encodeURIComponent(id)}`,
};

export function parseRecordsReportId(pathname: string): string | null {
  const [, area, id] = pathname.split("/").filter(Boolean); // bỏ phần "doctor"
  return area === "records" && id ? decodeURIComponent(id) : null;
}
