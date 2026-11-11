import { AppointmentDetailPage } from "@/features/appointments";

export default async function DoctorCaseRoute({ params }: { params: Promise<{ appointmentId: string }> }) {
  const { appointmentId } = await params;
  return <AppointmentDetailPage appointmentId={appointmentId} />;
}
