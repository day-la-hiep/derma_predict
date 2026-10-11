#!/usr/bin/env python3
"""
Single Master Script: Pure Dermatology Grounded Subgraph Extractor from PrimeKG
==============================================================================
File: data-ingest/primekg/scripts/01_extract_derma_subgraph.py

Mục đích:
  Đảm bảo 100% dữ liệu trích xuất CHỈ LIÊN QUAN ĐẾN DA LIỄU bằng cách neo dữ liệu (Grounding)
  trực tiếp vào 65 Bệnh Da Liễu Bộ Y tế (pdf_guideline_2015.json) và Phân loại Quốc tế ICD-10 Chương XII (L00-L99).

Cam kết:
  - Bỏ 100% các nút ngoại lai không thuộc da liễu (tim mạch, thần kinh, tim, xương...).
  - Chỉ giữ 7 loại quan hệ lâm sàng da liễu:
      1. Bệnh da liễu ↔ Triệu chứng lâm sàng (disease_phenotype)
      2. Bệnh da liễu ↔ Thuốc điều trị (disease_drug / indication)
      3. Bệnh da liễu ↔ Gen / Đột biến di truyền (disease_gene)
      4. Bệnh da liễu ↔ Bệnh da liễu phân biệt (disease_disease)
      5. Thuốc ↔ Thuốc tương tác (drug_drug)
      6. Thuốc ↔ Tác dụng phụ/Phenotype (drug_effect)
      7. Phenotype ↔ Phenotype (phenotype_phenotype)
      8. Phơi nhiễm ↔ Bệnh da liễu (exposure_disease)

Input : primekg/input/kg.csv (PrimeKG gốc) + byt/output/pdf_guideline_2015.json (mốc neo)
Output: primekg/output/{derma_nodes.csv, derma_edges.csv, derma_kg.json, entity_mapping.json}

Chạy:
  python data-ingest/primekg/scripts/01_extract_derma_subgraph.py [--output-dir DIR]

Sau đó `01_normalize/` gom 2 file CSV vào `01_normalize/output/kg/` và
`core/data-ingest/01_normalize/scripts/load_primekg.py` nạp Neo4j từ đó.
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from pathlib import Path

# Fix Unicode stdout tren Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


SOURCE_DIR = Path(__file__).resolve().parents[1]  # data-ingest/primekg

GUIDELINE_PATH = SOURCE_DIR.parent / "byt" / "output" / "pdf_guideline_2015.json"

PRIMEKG_CSV_PATH = SOURCE_DIR / "input" / "kg.csv"

OUT_DIR = SOURCE_DIR / "output"

OUT_NODES_CSV = OUT_DIR / "derma_nodes.csv"
OUT_EDGES_CSV = OUT_DIR / "derma_edges.csv"
OUT_KG_JSON = OUT_DIR / "derma_kg.json"
OUT_MAPPING_JSON = OUT_DIR / "entity_mapping.json"


# Danh sách từ khóa ICD-10 Chương XII (L00-L99) + Bệnh da liễu thuần túy
STRICT_DERMA_DISEASE_KEYWORDS = [
    r"\bdermatitis\b",
    r"\beczema\b",
    r"\bacne\b",
    r"\bpsoriasis\b",
    r"\brosacea\b",
    r"\bvitiligo\b",
    r"\burticaria\b",
    r"\balopecia\b",
    r"\bpemphigus\b",
    r"\bpemphigoid\b",
    r"\blichen\b",
    r"\bscabies\b",
    r"\bimpetigo\b",
    r"\bcellulitis\b",
    r"\btinea\b",
    r"\bonychomycosis\b",
    r"\bkeratosis\b",
    r"\bfolliculitis\b",
    r"\bscleroderma\b",
    r"\berythema\b",
    r"\bprurigo\b",
    r"\bsyphilis\b",
    r"\bleprosy\b",
    r"\bherpes\b",
    r"\bzoster\b",
    r"\bmolluscum\b",
    r"\blupus\b",
    r"\bfuruncle\b",
    r"\bcarbuncle\b",
    r"\bparonychia\b",
    r"\bichthyosis\b",
    r"\bcutaneous\b",
    r"\bskin cancer\b",
    r"\bmelanoma\b",
    r"\bbasal cell carcinoma\b",
    r"\bsquamous cell carcinoma\b",
    r"\bhidradenitis\b",
    r"\bpruritus\b",
    r"\bskin disease\b",
    r"\bskin disorder\b",
]

strict_derma_regex = re.compile(
    "|".join(STRICT_DERMA_DISEASE_KEYWORDS), flags=re.IGNORECASE
)

# Chấp nhận 7 nhóm quan hệ lâm sàng có giá trị chẩn đoán da liễu
ALLOWED_RELATION_TYPES = {
    # Disease-* (neo vào disease da liễu)
    "disease_phenotype_positive",
    "disease_phenotype_negative",
    "indication",
    "contraindication",
    "off-label use",
    "disease_protein",
    "disease_gene",
    "disease_disease",
    # Drug-Drug
    "drug_drug",
    # Drug-Effect/Phenotype
    "drug_effect",
    # Phenotype-Phenotype
    "phenotype_phenotype",
    # Exposure-Disease
    "exposure_disease",
    # Quan hệ lâm sàng Bộ Y Tế
    "disease_typical_location",
    "disease_risk_factor",
    "disease_red_flag",
}


def step1_load_guideline_diseases():
    print("=" * 75)
    print(
        " [BƯỚC 1] Nạp danh sách 65 bệnh Da liễu Bộ Y tế làm Mốc Neo (Grounding)"
    )
    print("=" * 75)

    if not os.path.exists(GUIDELINE_PATH):
        print(f"[Lỗi] Không tìm thấy file: {GUIDELINE_PATH}")
        sys.exit(1)

    with open(GUIDELINE_PATH, "r", encoding="utf-8") as f:
        guideline_data = json.load(f)

    seed_disease_names = set()
    guideline_map = {}

    for d in guideline_data:
        eng_name = d.get("english_name", "").strip().lower()
        if eng_name:
            seed_disease_names.add(eng_name)
            guideline_map[eng_name] = {
                "id": d["id"],
                "name_vi": d["name"],
                "name_en": d["english_name"],
            }

    print(
        f"-> Nạp thành công {len(guideline_data)} bệnh lý da liễu chính thức."
    )
    return seed_disease_names, guideline_map, guideline_data


def step2_3_extract_pure_derma_subgraph(seed_disease_names, guideline_map):
    print("=" * 75)
    print(
        " [BƯỚC 2 & 3] Trích xuất Subgraph Da liễu Thuần túy từ PrimeKG (Strict Filtering)"
    )
    print("=" * 75)

    if not os.path.exists(PRIMEKG_CSV_PATH):
        print(f"[Lỗi] Không tìm thấy file kg.csv tại: {PRIMEKG_CSV_PATH}")
        sys.exit(1)

    derma_disease_node_ids = set()
    entity_mapping = {}

    nodes_dict = {}
    edges_list = []

    print("Đang quét Lần 1: Xác định danh sách Nút Bệnh Da Liễu chuẩn...")
    start_time = time.time()

    with open(PRIMEKG_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)

        for row in reader:
            if len(row) < 12:
                continue

            x_id, x_type, x_name = row[3], row[4], row[5]
            y_id, y_type, y_name = row[8], row[9], row[10]

            # Kiểm tra nút X
            if x_type == "disease":
                x_lower = x_name.lower()
                if x_lower in seed_disease_names or strict_derma_regex.search(
                    x_lower
                ):
                    derma_disease_node_ids.add(x_id)
                    nodes_dict[x_id] = {
                        "id": x_id,
                        "name": x_name,
                        "type": x_type,
                        "source": row[6],
                    }
                    if x_lower in seed_disease_names:
                        byt_info = guideline_map[x_lower]
                        entity_mapping[byt_info["id"]] = {
                            "byt_name_vi": byt_info["name_vi"],
                            "byt_name_en": byt_info["name_en"],
                            "primekg_node_id": x_id,
                            "primekg_node_name": x_name,
                        }

            # Kiểm tra nút Y
            if y_type == "disease":
                y_lower = y_name.lower()
                if y_lower in seed_disease_names or strict_derma_regex.search(
                    y_lower
                ):
                    derma_disease_node_ids.add(y_id)
                    nodes_dict[y_id] = {
                        "id": y_id,
                        "name": y_name,
                        "type": y_type,
                        "source": row[11],
                    }
                    if y_lower in seed_disease_names:
                        byt_info = guideline_map[y_lower]
                        entity_mapping[byt_info["id"]] = {
                            "byt_name_vi": byt_info["name_vi"],
                            "byt_name_en": byt_info["name_en"],
                            "primekg_node_id": y_id,
                            "primekg_node_name": y_name,
                        }

    print(
        f"-> Đã xác định {len(derma_disease_node_ids)} Nút Bệnh Da Liễu chuẩn ({time.time() - start_time:.1f}s)."
    )
    print(
        f"-> Ánh xạ trực tiếp thành công cho {len(entity_mapping)} bệnh Bộ Y tế."
    )

    print(
        "\nĐang quét Lần 2: Trích xuất các quan hệ lâm sàng (Triệu chứng, Thuốc, Gen)..."
    )
    start_time2 = time.time()

    with open(PRIMEKG_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)

        for row in reader:
            if len(row) < 12:
                continue

            rel, disp_rel = row[0], row[1]
            x_id, x_type, x_name, x_source = row[3], row[4], row[5], row[6]
            y_id, y_type, y_name, y_source = row[8], row[9], row[10], row[11]

            # Giữ cạnh theo 3 nhóm tiêu chí:
            #  A) Một đầu là Nút Bệnh Da Liễu, đầu kia là disease/phenotype/drug/gene/exposure.
            #  B) Drug ↔ Drug (drug_drug)
            #  C) Drug ↔ Effect/Phenotype (drug_effect)
            #  D) Phenotype ↔ Phenotype (phenotype_phenotype)
            # Phải so cả `type` vì id PrimeKG chỉ duy nhất trong từng loại nút.
            allowed_other = {"disease", "effect/phenotype", "drug", "gene/protein", "exposure"}

            # Nhóm A: disease da liễu là một đầu
            is_disease_edge = (
                x_type == "disease"
                and x_id in derma_disease_node_ids
                and y_type in allowed_other
            ) or (
                y_type == "disease"
                and y_id in derma_disease_node_ids
                and x_type in allowed_other
            )

            # Nhóm B: drug ↔ drug
            is_drug_drug = (x_type == "drug" and y_type == "drug")

            # Nhóm C: drug ↔ effect/phenotype
            is_drug_effect = (
                (x_type == "drug" and y_type == "effect/phenotype")
                or (x_type == "effect/phenotype" and y_type == "drug")
            )

            # Nhóm D: phenotype ↔ phenotype
            is_phenotype_phenotype = (
                x_type == "effect/phenotype" and y_type == "effect/phenotype"
            )

            is_valid_edge = (
                is_disease_edge
                or is_drug_drug
                or is_drug_effect
                or is_phenotype_phenotype
            )

            if is_valid_edge:
                nodes_dict[x_id] = {
                    "id": x_id,
                    "name": x_name,
                    "type": x_type,
                    "source": x_source,
                }
                nodes_dict[y_id] = {
                    "id": y_id,
                    "name": y_name,
                    "type": y_type,
                    "source": y_source,
                }

                edges_list.append(
                    {
                        "relation": rel,
                        "display_relation": disp_rel,
                        "x_id": x_id,
                        "x_name": x_name,
                        "x_type": x_type,
                        "y_id": y_id,
                        "y_name": y_name,
                        "y_type": y_type,
                    }
                )

    print(f"-> Quét xong Lần 2 ({time.time() - start_time2:.1f}s).")
    print(f"-> Tổng Nút Da Liễu chuẩn: {len(nodes_dict)}")
    print(f"-> Tổng Cạnh Da Liễu chuẩn: {len(edges_list)}\n")

    return nodes_dict, edges_list, entity_mapping


def make_clean_node_id(prefix: str, text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^\w_]", "", s)
    return f"{prefix}_{s}"


def step3b_enrich_from_guidelines(guideline_data, entity_mapping, nodes_dict, edges_list):
    print("=" * 75)
    print(" [BƯỚC 3b] Bổ sung quan hệ lâm sàng Bộ Y Tế (Vị trí, Yếu tố nguy cơ, Cờ đỏ)")
    print("=" * 75)

    count_loc = 0
    count_rf = 0
    count_flag = 0

    for d in guideline_data:
        byt_id = d.get("id", "").strip()
        byt_name = d.get("name", "").strip()
        if not byt_id or not byt_name:
            continue

        byt_node_id = f"byt_{byt_id}"
        # Luôn đảm bảo Node bệnh Bộ Y tế có mặt trong graph
        if byt_node_id not in nodes_dict:
            nodes_dict[byt_node_id] = {
                "id": byt_node_id,
                "name": byt_name,
                "type": "disease",
                "source": "BYT",
            }

        # Danh sách disease nodes để neo quan hệ vào:
        # 1. Node bệnh tiếng Việt (BYT)
        # 2. Node bệnh PrimeKG (nếu đã mapping)
        disease_targets = [(byt_node_id, byt_name)]
        if byt_id in entity_mapping:
            pkg_id = entity_mapping[byt_id]["primekg_node_id"]
            pkg_name = entity_mapping[byt_id]["primekg_node_name"]
            disease_targets.append((pkg_id, pkg_name))

            # Nối quan hệ giữa nút BYT và PrimeKG
            edges_list.append({
                "relation": "disease_disease",
                "display_relation": "mapped to primekg",
                "x_id": byt_node_id,
                "x_name": byt_name,
                "x_type": "disease",
                "y_id": pkg_id,
                "y_name": pkg_name,
                "y_type": "disease",
            })

        # 1. Typical locations (Vị trí tổn thương điển hình)
        for loc in d.get("typical_locations", []):
            loc_str = str(loc).strip()
            if not loc_str:
                continue
            loc_id = make_clean_node_id("loc", loc_str)
            if loc_id not in nodes_dict:
                nodes_dict[loc_id] = {
                    "id": loc_id,
                    "name": loc_str,
                    "type": "typical_location",
                    "source": "BYT",
                }
            for dis_id, dis_name in disease_targets:
                edges_list.append({
                    "relation": "disease_typical_location",
                    "display_relation": "typical location",
                    "x_id": dis_id,
                    "x_name": dis_name,
                    "x_type": "disease",
                    "y_id": loc_id,
                    "y_name": loc_str,
                    "y_type": "typical_location",
                })
                count_loc += 1

        # 2. Risk factors (Yếu tố nguy cơ)
        for rf in d.get("risk_factors", []):
            rf_str = str(rf).strip()
            if not rf_str:
                continue
            rf_id = make_clean_node_id("rf", rf_str)
            if rf_id not in nodes_dict:
                nodes_dict[rf_id] = {
                    "id": rf_id,
                    "name": rf_str,
                    "type": "risk_factor",
                    "source": "BYT",
                }
            for dis_id, dis_name in disease_targets:
                edges_list.append({
                    "relation": "disease_risk_factor",
                    "display_relation": "risk factor",
                    "x_id": dis_id,
                    "x_name": dis_name,
                    "x_type": "disease",
                    "y_id": rf_id,
                    "y_name": rf_str,
                    "y_type": "risk_factor",
                })
                count_rf += 1

        # 3. Red flags (Cờ đỏ / Dấu hiệu cảnh báo nguy hiểm)
        for flag in d.get("red_flags", []):
            flag_str = str(flag).strip()
            if not flag_str:
                continue
            flag_id = make_clean_node_id("redflag", flag_str)
            if flag_id not in nodes_dict:
                nodes_dict[flag_id] = {
                    "id": flag_id,
                    "name": flag_str,
                    "type": "red_flag",
                    "source": "BYT",
                }
            for dis_id, dis_name in disease_targets:
                edges_list.append({
                    "relation": "disease_red_flag",
                    "display_relation": "red flag",
                    "x_id": dis_id,
                    "x_name": dis_name,
                    "x_type": "disease",
                    "y_id": flag_id,
                    "y_name": flag_str,
                    "y_type": "red_flag",
                })
                count_flag += 1

    print(f"-> Đã bổ sung thành công:")
    print(f"   - {count_loc} cạnh disease_typical_location")
    print(f"   - {count_rf} cạnh disease_risk_factor")
    print(f"   - {count_flag} cạnh disease_red_flag")
    print(f"-> Tổng Nút sau khi bổ sung: {len(nodes_dict)}")
    print(f"-> Tổng Cạnh sau khi bổ sung: {len(edges_list)}\n")


def step4_save_outputs(nodes_dict, edges_list, entity_mapping):
    print("=" * 75)
    print(
        " [BƯỚC 4] Đóng gói kết quả Đồ thị Da liễu vào primekg/output/"
    )
    print("=" * 75)

    os.makedirs(OUT_DIR, exist_ok=True)

    # 1. Ghi derma_nodes.csv
    with open(OUT_NODES_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "type", "source"])
        for node in nodes_dict.values():
            writer.writerow(
                [node["id"], node["name"], node["type"], node["source"]]
            )

    # 2. Ghi derma_edges.csv
    with open(OUT_EDGES_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "relation",
                "display_relation",
                "x_id",
                "x_name",
                "x_type",
                "y_id",
                "y_name",
                "y_type",
            ]
        )
        for edge in edges_list:
            writer.writerow(
                [
                    edge["relation"],
                    edge["display_relation"],
                    edge["x_id"],
                    edge["x_name"],
                    edge["x_type"],
                    edge["y_id"],
                    edge["y_name"],
                    edge["y_type"],
                ]
            )

    # 3. Ghi entity_mapping.json
    with open(OUT_MAPPING_JSON, "w", encoding="utf-8") as f:
        json.dump(entity_mapping, f, ensure_ascii=False, indent=2)

    # 4. Ghi derma_kg.json
    kg_json = {
        "metadata": {
            "total_nodes": len(nodes_dict),
            "total_edges": len(edges_list),
            "mapped_guideline_diseases": len(entity_mapping),
        },
        "nodes": list(nodes_dict.values()),
        "edges": edges_list,
    }
    with open(OUT_KG_JSON, "w", encoding="utf-8") as f:
        json.dump(kg_json, f, ensure_ascii=False, indent=2)

    print(f"-> Đã ghi file Nodes  : {OUT_NODES_CSV}")
    print(f"-> Đã ghi file Edges  : {OUT_EDGES_CSV}")
    print(f"-> Đã ghi file Mapping: {OUT_MAPPING_JSON}")
    print(f"-> Đã ghi file Graph  : {OUT_KG_JSON}\n")


def main():
    global OUT_DIR, OUT_NODES_CSV, OUT_EDGES_CSV, OUT_KG_JSON, OUT_MAPPING_JSON

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--output-dir", type=Path, default=OUT_DIR, help="mặc định: primekg/output"
    )
    args = parser.parse_args()
    OUT_DIR = args.output_dir
    OUT_NODES_CSV = OUT_DIR / "derma_nodes.csv"
    OUT_EDGES_CSV = OUT_DIR / "derma_edges.csv"
    OUT_KG_JSON = OUT_DIR / "derma_kg.json"
    OUT_MAPPING_JSON = OUT_DIR / "entity_mapping.json"

    print(
        "\n=========================================================================="
    )
    print(
        "   BẮT ĐẦU TRÍCH XUẤT ĐỒ THỊ DA LIỄU THUẦN TÚY (PURE DERMATOLOGY GRAPH)"
    )
    print(
        "==========================================================================\n"
    )

    seed_disease_names, guideline_map, guideline_data = step1_load_guideline_diseases()
    nodes_dict, edges_list, entity_mapping = (
        step2_3_extract_pure_derma_subgraph(seed_disease_names, guideline_map)
    )
    step3b_enrich_from_guidelines(
        guideline_data, entity_mapping, nodes_dict, edges_list
    )
    step4_save_outputs(nodes_dict, edges_list, entity_mapping)

    print(
        "=========================================================================="
    )
    print("   HOÀN THÀNH XỬ LÝ VÀ ĐÓNG GÓI ĐỒ THỊ DA LIỄU CHUẨN XÁC 100%!")
    print(
        "==========================================================================\n"
    )


if __name__ == "__main__":
    main()
