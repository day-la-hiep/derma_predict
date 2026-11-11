export const doctorPaths = {
  home: "/doctor",
  caseDetail: (appointmentId: string) => `/doctor/cases/${encodeURIComponent(appointmentId)}`,
};
