"""Service quản lý Đồ thị hành trình người bệnh (Patient Journey Knowledge Graph - PJKG) trên Neo4j."""
from datetime import UTC, datetime
import logging
from typing import Any

from app.dto.response.patient_graph import (
    GraphEdgeOutput,
    GraphNodeOutput,
    PatientJourneyGraphOutput,
)
from app.infra.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class PatientGraphService:
    def __init__(self, neo4j: Neo4jClient) -> None:
        self._neo4j = neo4j

    async def sync_pre_consultation(
        self,
        patient_id: str,
        session_id: str,
        session_date: datetime,
        summary: str,
        reason: str,
        facts: list[dict[str, Any]],
        gender: str = "unknown",
        dob: str = "",
        images: list[dict[str, Any]] | None = None,
    ) -> None:
        """Đồng bộ một phiên tư vấn (Pre-consultation), các dữ kiện lâm sàng và ảnh da lên đồ thị."""
        if not patient_id or not session_id:
            return

        date_iso = session_date.isoformat()

        # 1. Tạo Node Patient, Session và nối chuỗi thời gian NEXT với phiên tư vấn liền trước
        upsert_session_query = """
        MERGE (p:Patient {id: $patient_id})
        ON CREATE SET p.gender = $gender, p.dob = $dob

        MERGE (s:ConsultationSession {id: $session_id})
        ON CREATE SET 
            s.date = $session_date,
            s.status = 'pre_consultation',
            s.reason = $reason,
            s.summary = $summary
        ON MATCH SET
            s.summary = $summary

        MERGE (p)-[:HAD_SESSION]->(s)

        WITH p, s
        OPTIONAL MATCH (p)-[:HAD_SESSION]->(prev:ConsultationSession)
        WHERE prev.id <> s.id AND prev.date < s.date
        WITH s, prev ORDER BY prev.date DESC LIMIT 1
        FOREACH (_ IN CASE WHEN prev IS NOT NULL THEN [1] ELSE [] END |
            MERGE (prev)-[:NEXT]->(s)
        )
        """
        await self._neo4j.run(
            upsert_session_query,
            patient_id=patient_id,
            gender=gender,
            dob=dob,
            session_id=session_id,
            session_date=date_iso,
            reason=reason or "Bệnh nhân yêu cầu bác sĩ tư vấn",
            summary=summary or "",
        )

        # 2. Nạp các Facts lâm sàng và liên kết với phiên tư vấn
        if facts:
            upsert_facts_query = """
            MATCH (s:ConsultationSession {id: $session_id})
            UNWIND $facts AS f
            MERGE (fact:ClinicalFact {id: f.id})
            SET fact.name = f.label,
                fact.type = f.fact_type,
                fact.detail = f.detail,
                fact.status = coalesce(f.status, 'active')
            MERGE (s)-[r:REPORTED_FACT]->(fact)
            SET r.fact_type = f.fact_type
            """
            clean_facts = [
                {
                    "id": f.get("id", ""),
                    "label": f.get("template_label") or f.get("label") or "Dữ kiện lâm sàng",
                    "fact_type": f.get("fact_type", "symptom"),
                    "detail": f.get("detail", ""),
                    "status": f.get("status", "active"),
                }
                for f in facts
                if f.get("id")
            ]
            if clean_facts:
                await self._neo4j.run(
                    upsert_facts_query,
                    session_id=session_id,
                    facts=clean_facts,
                )

                # 3. Liên kết thực thể lâm sàng với Ontology DermO (nếu có term khớp)
                map_dermo_query = """
                UNWIND $facts AS f
                MATCH (fact:ClinicalFact {id: f.id})
                OPTIONAL MATCH (d:DermoTerm)
                WHERE NOT d.is_obsolete AND toLower(d.name) = toLower(fact.name)
                FOREACH (_ IN CASE WHEN d IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (fact)-[:MAPS_TO]->(d)
                )
                """
                await self._neo4j.run(map_dermo_query, facts=clean_facts)

        # 4. Nạp các Ảnh bệnh nhân gửi trong phiên và liên kết với phiên / fact
        if images:
            upsert_images_query = """
            MATCH (s:ConsultationSession {id: $session_id})
            UNWIND $images AS img
            MERGE (pi:PatientImage {id: img.file_id})
            SET pi.file_id = img.file_id,
                pi.url = img.url,
                pi.content_type = img.content_type,
                pi.body_site = coalesce(img.body_site, pi.body_site, '')
            MERGE (s)-[:HAS_IMAGE]->(pi)
            WITH pi, img
            UNWIND coalesce(img.fact_ids, []) AS f_id
            MATCH (f:ClinicalFact {id: f_id})
            MERGE (pi)-[:EVIDENCES]->(f)
            """
            clean_images = [
                {
                    "file_id": img.get("file_id", ""),
                    "url": img.get("url") or f"/api/v1/files/{img.get('file_id')}/view",
                    "content_type": img.get("content_type", "image/jpeg"),
                    "body_site": img.get("body_site", ""),
                    "fact_ids": [fid for fid in img.get("fact_ids", []) if fid],
                }
                for img in images
                if img.get("file_id")
            ]
            if clean_images:
                await self._neo4j.run(upsert_images_query, session_id=session_id, images=clean_images)

    async def sync_finalized_session(
        self,
        session_id: str,
        doctor_id: str,
        suspected_condition: str,
        notes: str,
        instructions: list[str],
        images: list[dict[str, Any]] | None = None,
    ) -> None:
        """Đồng bộ khi Bác sĩ hoàn tất phiên tư vấn: nhận định sơ bộ, lời khuyên và nhãn ảnh xác nhận."""
        if not session_id:
            return

        now_iso = datetime.now(UTC).isoformat()

        # Query 1: Cập nhật trạng thái Session + SuspectedCondition
        finalize_query = """
        MATCH (s:ConsultationSession {id: $session_id})
        SET s.status = 'resolved',
            s.notes = $notes,
            s.resolved_at = $resolved_at
        WITH s
        FOREACH (_ IN CASE WHEN $condition <> '' THEN [1] ELSE [] END |
            MERGE (c:SuspectedCondition {name: $condition})
            MERGE (s)-[:SUSPECTED_CONDITION {by_doctor_id: $doctor_id}]->(c)
        )
        """
        await self._neo4j.run(
            finalize_query,
            session_id=session_id,
            doctor_id=doctor_id or "",
            condition=suspected_condition.strip(),
            notes=notes.strip(),
            resolved_at=now_iso,
        )

        # Query 2: Thêm các lời khuyên (tách riêng vì UNWIND [] sẽ xoá kết quả trước đó)
        clean_instructions = [i.strip() for i in instructions if i and i.strip()]
        if clean_instructions:
            advice_query = """
            MATCH (s:ConsultationSession {id: $session_id})
            UNWIND $instructions AS inst
            MERGE (a:Advice {content: inst})
            MERGE (s)-[:RECOMMENDED_ADVICE]->(a)
            """
            await self._neo4j.run(
                advice_query,
                session_id=session_id,
                instructions=clean_instructions,
            )

        # Query 3: Cập nhật thông tin ảnh được bác sĩ chọn kèm nhãn xác nhận
        if images:
            upsert_final_images_query = """
            MATCH (s:ConsultationSession {id: $session_id})
            UNWIND $images AS img
            MERGE (pi:PatientImage {id: img.file_id})
            SET pi.body_site = coalesce(img.body_site, pi.body_site, ''),
                pi.description = coalesce(img.description, pi.description, ''),
                pi.confirmed_label = img.confirmed_label
            MERGE (s)-[:HAS_IMAGE]->(pi)
            WITH pi, img
            FOREACH (_ IN CASE WHEN img.confirmed_label IS NOT NULL AND img.confirmed_label <> '' THEN [1] ELSE [] END |
                MERGE (c:SuspectedCondition {name: img.confirmed_label})
                MERGE (pi)-[:CONFIRMED_AS]->(c)
            )
            """
            clean_final_images = [
                {
                    "file_id": img.get("file_id", ""),
                    "body_site": img.get("body_site", ""),
                    "description": img.get("description", ""),
                    "confirmed_label": img.get("confirmed_label", ""),
                }
                for img in images
                if img.get("file_id")
            ]
            if clean_final_images:
                await self._neo4j.run(upsert_final_images_query, session_id=session_id, images=clean_final_images)

    async def get_history_hints(self, patient_id: str) -> tuple[list[str], list[str]]:
        """(nhận định, lời khuyên) bác sĩ đã chốt ở các phiên trước của bệnh nhân, mới nhất trước."""
        query = """
        MATCH (:Patient {id: $patient_id})-[:HAD_SESSION]->(s:ConsultationSession)
        OPTIONAL MATCH (s)-[:SUSPECTED_CONDITION]->(c:SuspectedCondition)
        OPTIONAL MATCH (s)-[:RECOMMENDED_ADVICE]->(a:Advice)
        WITH s, collect(DISTINCT c.name) AS conditions, collect(DISTINCT a.content) AS advice
        ORDER BY s.resolved_at DESC
        RETURN conditions, advice
        """
        rows = await self._neo4j.run(query, patient_id=patient_id)
        conditions = list(dict.fromkeys(c for r in rows for c in r["conditions"]))
        advice = list(dict.fromkeys(a for r in rows for a in r["advice"]))
        return conditions, advice

    async def get_patient_journey_graph(self, patient_id: str) -> PatientJourneyGraphOutput:
        """Truy vấn đồ thị hành trình bệnh nhân (nodes và edges) để phục vụ trực quan hoá trên giao diện."""
        query = """
        MATCH (p:Patient {id: $patient_id})
        OPTIONAL MATCH (p)-[r_sess:HAD_SESSION]->(s:ConsultationSession)
        OPTIONAL MATCH (s)-[r_next:NEXT]->(s_next:ConsultationSession)
        OPTIONAL MATCH (s)-[r_fact:REPORTED_FACT]->(f:ClinicalFact)
        OPTIONAL MATCH (f)-[r_dermo:MAPS_TO]->(d:DermoTerm)
        OPTIONAL MATCH (s)-[r_cond:SUSPECTED_CONDITION]->(c:SuspectedCondition)
        OPTIONAL MATCH (s)-[r_adv:RECOMMENDED_ADVICE]->(a:Advice)
        OPTIONAL MATCH (s)-[r_img:HAS_IMAGE]->(img:PatientImage)
        OPTIONAL MATCH (img)-[r_evi:EVIDENCES]->(img_fact:ClinicalFact)
        OPTIONAL MATCH (img)-[r_conf:CONFIRMED_AS]->(img_cond:SuspectedCondition)
        RETURN p, s, s_next, f, d, c, a, img, img_fact, img_cond,
               r_sess, r_next, r_fact, r_dermo, r_cond, r_adv, r_img, r_evi, r_conf
        """
        try:
            records = await self._neo4j.run(query, patient_id=patient_id)
        except Exception as e:
            logger.warning("Lỗi truy vấn đồ thị bệnh nhân %s từ Neo4j: %s", patient_id, e)
            records = []

        node_map: dict[str, GraphNodeOutput] = {}
        edge_map: dict[str, GraphEdgeOutput] = {}
        session_images_map: dict[str, list[dict[str, Any]]] = {}

        def _add_node(raw_node: dict[str, Any] | None, default_label: str) -> None:
            if not raw_node:
                return
            node_id = str(raw_node.get("id") or raw_node.get("content") or raw_node.get("name") or "")
            if not node_id or node_id in node_map:
                return
            if default_label == "ConsultationSession":
                date_val = str(raw_node.get("date") or "")
                date_part = date_val.split("T")[0] if date_val else ""
                name = str(raw_node.get("name") or (f"Phiên {date_part}" if date_part else "Phiên tư vấn"))
            elif default_label == "Patient":
                raw_name = str(raw_node.get("name") or raw_node.get("full_name") or "")
                name = raw_name if raw_name and not raw_name.startswith("pp-") else "Bệnh nhân"
            elif default_label == "PatientImage":
                body_site = raw_node.get("body_site")
                lbl = raw_node.get("confirmed_label")
                parts = [p for p in [body_site, lbl] if p]
                name = f"Ảnh da{f' ({', '.join(parts)})' if parts else ''}"
            else:
                name = str(raw_node.get("name") or raw_node.get("content") or raw_node.get("summary") or node_id)

            node_map[node_id] = GraphNodeOutput(
                id=node_id,
                label=default_label,
                name=name,
                properties=raw_node,
            )

        def _add_edge(source: str, target: str, rel_type: str, props: dict[str, Any] | None = None) -> None:
            if not source or not target:
                return
            edge_id = f"{source}-{rel_type}-{target}"
            if edge_id not in edge_map:
                edge_map[edge_id] = GraphEdgeOutput(
                    id=edge_id,
                    source=source,
                    target=target,
                    type=rel_type,
                    properties=props or {},
                )

        def _stable_id(prefix: str, content: str) -> str:
            """ID ổn định từ nội dung: cùng nội dung → cùng ID, tránh collision khi text dài."""
            import hashlib

            return f"{prefix}-{hashlib.sha256(content.encode()).hexdigest()[:12]}"

        next_sessions: list[tuple[str, str]] = []

        for row in records:
            p = row.get("p")
            s = row.get("s")
            s_next = row.get("s_next")
            f = row.get("f")
            d = row.get("d")
            c = row.get("c")
            a = row.get("a")
            img = row.get("img")
            img_fact = row.get("img_fact")
            img_cond = row.get("img_cond")

            if p:
                _add_node(p, "Patient")
            if s:
                _add_node(s, "ConsultationSession")
                if p:
                    _add_edge(str(p.get("id")), str(s.get("id")), "HAD_SESSION")
            if s and s_next:
                _add_node(s_next, "ConsultationSession")
                _add_edge(str(s.get("id")), str(s_next.get("id")), "NEXT")
                next_sessions.append((str(s.get("id")), str(s_next.get("id"))))
            if s and f:
                fact_type = f.get("type", "symptom")
                label = "Symptom" if fact_type == "symptom" else ("Lesion" if fact_type == "lesion" else "ClinicalFact")
                _add_node(f, label)
                _add_edge(str(s.get("id")), str(f.get("id")), "REPORTED_FACT", {"fact_type": fact_type})
            if f and d:
                _add_node(d, "DermoTerm")
                _add_edge(str(f.get("id")), str(d.get("id") or d.get("name")), "MAPS_TO")
            if s and c:
                cond_name = str(c.get("name") or "")
                cond_id = _stable_id("cond", cond_name)
                _add_node({"id": cond_id, "name": cond_name}, "SuspectedCondition")
                _add_edge(str(s.get("id")), cond_id, "SUSPECTED_CONDITION")
            if s and a:
                adv_content = str(a.get("content") or "")
                adv_id = _stable_id("adv", adv_content)
                _add_node({"id": adv_id, "name": adv_content}, "Advice")
                _add_edge(str(s.get("id")), adv_id, "RECOMMENDED_ADVICE")
            if s and img:
                img_dict = dict(img)
                _add_node(img_dict, "PatientImage")
                _add_edge(str(s.get("id")), str(img.get("id")), "HAS_IMAGE")
                s_id = str(s.get("id"))
                if s_id not in session_images_map:
                    session_images_map[s_id] = []
                if not any(i.get("id") == img.get("id") for i in session_images_map[s_id]):
                    session_images_map[s_id].append(img_dict)
            if img and img_fact:
                _add_edge(str(img.get("id")), str(img_fact.get("id")), "EVIDENCES")
            if img and img_cond:
                cond_name = str(img_cond.get("name") or "")
                cond_id = _stable_id("cond", cond_name)
                _add_node({"id": cond_id, "name": cond_name}, "SuspectedCondition")
                _add_edge(str(img.get("id")), cond_id, "CONFIRMED_AS")

        # Nối quan hệ tiến triển theo thời gian FOLLOWS giữa các ảnh cùng vị trí body_site ở 2 phiên kế tiếp
        for prev_sid, next_sid in set(next_sessions):
            prev_imgs = session_images_map.get(prev_sid, [])
            next_imgs = session_images_map.get(next_sid, [])
            for p_img in prev_imgs:
                p_site = (p_img.get("body_site") or "").strip().lower()
                if not p_site:
                    continue
                for n_img in next_imgs:
                    n_site = (n_img.get("body_site") or "").strip().lower()
                    if p_site == n_site:
                        _add_edge(str(p_img.get("id")), str(n_img.get("id")), "FOLLOWS", {"body_site": p_site})

        return PatientJourneyGraphOutput(
            patient_id=patient_id,
            nodes=list(node_map.values()),
            edges=list(edge_map.values()),
        )

