"""DTO cho đồ thị hành trình bệnh nhân (Patient Journey Knowledge Graph - PJKG)."""
from typing import Any
from pydantic import BaseModel, Field


class GraphNodeOutput(BaseModel):
    id: str = Field(..., description="ID định danh duy nhất của Node")
    label: str = Field(..., description="Nhãn chính của Node (Patient, ConsultationSession, Symptom, v.v.)")
    name: str = Field(..., description="Tên hiển thị trực quan trên đồ thị")
    properties: dict[str, Any] = Field(default_factory=dict, description="Các thuộc tính chi tiết của Node")


class GraphEdgeOutput(BaseModel):
    id: str = Field(..., description="ID định danh duy nhất của quan hệ")
    source: str = Field(..., description="ID của Node nguồn")
    target: str = Field(..., description="ID của Node đích")
    type: str = Field(..., description="Loại quan hệ (HAD_SESSION, NEXT, REPORTED_SYMPTOM, v.v.)")
    properties: dict[str, Any] = Field(default_factory=dict, description="Thuộc tính của cạnh (nếu có)")


class PatientJourneyGraphOutput(BaseModel):
    patient_id: str = Field(..., description="ID của hồ sơ bệnh nhân")
    nodes: list[GraphNodeOutput] = Field(default_factory=list, description="Danh sách các Node trong đồ thị")
    edges: list[GraphEdgeOutput] = Field(default_factory=list, description="Danh sách các Cạnh liên kết")
