from typing import Literal

from pydantic import BaseModel


class Hypothesis(BaseModel):
    disease_id: str
    name: str
    score: float
    # Điểm từng nguồn trước khi gộp: kg, cnn, rag, history
    signals: dict[str, float] = {}


class GuidelineNote(BaseModel):
    fact: str
    stance: Literal["support", "refute", "irrelevant"]
    chunk_id: str


class EvidenceRow(BaseModel):
    disease_id: str
    matched: list[str] = []
    missing: list[str] = []
    contradicted: list[str] = []
    unexplained: list[str] = []
    guideline: list[GuidelineNote] = []


class Claim(BaseModel):
    text: str
    cites: list[str] = []
    status: Literal["verified", "unverified"] = "unverified"
