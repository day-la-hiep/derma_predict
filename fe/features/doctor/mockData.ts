/** Mock đồ thị hành trình để phát triển UI khi chưa có backend. */
import type { PatientJourneyGraph } from "./types";

/* ────────── Mock Patient Journey Graph ────────── */

export function getMockPatientJourneyGraph(patientId: string): PatientJourneyGraph {
  return {
    patientId,
    nodes: [
      {
        id: `patient-${patientId}`,
        label: "Patient",
        name: "Bệnh nhân",
        properties: {
          gender: "male",
          dob: "1990-05-12",
        },
      },
      {
        id: "session-cs-001",
        label: "ConsultationSession",
        name: "Phiên tư vấn 07/10/2026",
        properties: {
          sessionId: "cs-001",
          date: "2026-10-07T09:15:00Z",
          reason: "Nổi mẩn đỏ ngứa sau khi dùng Amoxicillin",
          summary: "Bệnh nhân nam xuất hiện mẩn đỏ ngứa lan rộng sau 3 ngày dùng kháng sinh.",
        },
      },
      {
        id: "session-cs-002",
        label: "ConsultationSession",
        name: "Phiên tái khám 12/10/2026",
        properties: {
          sessionId: "cs-002",
          date: "2026-10-12T14:30:00Z",
          reason: "Kiểm tra tình trạng da sau khi ngưng kháng sinh và uống Cetirizine",
          summary: "Mẩn đỏ đã lặn 80%, không còn ngứa về đêm.",
        },
      },
      {
        id: "symptom-man-do",
        label: "Symptom",
        name: "Mẩn đỏ dạng sẩn",
        properties: {
          detail: "Kích thước 2-5mm, rải rác cánh tay và bụng",
          origin: "patient_reported",
        },
      },
      {
        id: "symptom-ngua",
        label: "Symptom",
        name: "Ngứa tăng về đêm",
        properties: {
          detail: "Ngứa mức độ trung bình, cào gãi nhiều",
          origin: "patient_reported",
        },
      },
      {
        id: "symptom-thuyen-giam",
        label: "Symptom",
        name: "Mẩn đỏ giảm rõ rệt",
        properties: {
          detail: "Tổn thương lặn dần, để lại dát thâm nhẹ, không ngứa",
          origin: "doctor_observed",
        },
      },
      {
        id: "doc-001",
        label: "Doctor",
        name: "BS. Trần Văn Bình",
        properties: {
          doctorId: "doc-001",
          department: "Da liễu tổng quát",
        },
      },
      {
        id: "condition-di-ung-amox",
        label: "Condition",
        name: "Phát ban do dị ứng Amoxicillin",
        properties: {
          notes: "Maculopapular drug eruption mức độ nhẹ - trung bình",
        },
      },
      {
        id: "condition-on-dinh",
        label: "Condition",
        name: "Ban dị ứng thuốc thoái lui",
        properties: {
          notes: "Hồi phục tốt sau khi ngưng dị nguyên",
        },
      },
      {
        id: "advice-ngung-thuoc",
        label: "Advice",
        name: "Ngưng Amoxicillin & Uống Cetirizine 10mg",
        properties: {
          content: "Ngưng hoàn toàn Amoxicillin. Uống Cetirizine 10mg 1 viên/ngày trong 5 ngày.",
        },
      },
      {
        id: "advice-tranh-penicillin",
        label: "Advice",
        name: "Tránh kháng sinh nhóm Beta-lactam",
        properties: {
          content: "Ghi rõ tiền sử dị ứng Amoxicillin/Penicillin trong mọi lần khám bệnh sau này.",
        },
      },
    ],
    edges: [
      { source: `patient-${patientId}`, target: "session-cs-001", type: "HAD_SESSION", properties: {} },
      { source: `patient-${patientId}`, target: "session-cs-002", type: "HAD_SESSION", properties: {} },
      { source: "session-cs-001", target: "session-cs-002", type: "NEXT", properties: {} },
      { source: "session-cs-001", target: "symptom-man-do", type: "HAS_SYMPTOM", properties: {} },
      { source: "session-cs-001", target: "symptom-ngua", type: "HAS_SYMPTOM", properties: {} },
      { source: "session-cs-001", target: "doc-001", type: "CONDUCTED_BY", properties: {} },
      { source: "session-cs-001", target: "condition-di-ung-amox", type: "HAS_CONDITION", properties: {} },
      { source: "session-cs-001", target: "advice-ngung-thuoc", type: "RECEIVED_ADVICE", properties: {} },
      { source: "session-cs-002", target: "symptom-thuyen-giam", type: "HAS_SYMPTOM", properties: {} },
      { source: "session-cs-002", target: "doc-001", type: "CONDUCTED_BY", properties: {} },
      { source: "session-cs-002", target: "condition-on-dinh", type: "HAS_CONDITION", properties: {} },
      { source: "session-cs-002", target: "advice-tranh-penicillin", type: "RECEIVED_ADVICE", properties: {} },
    ],
  };
}
