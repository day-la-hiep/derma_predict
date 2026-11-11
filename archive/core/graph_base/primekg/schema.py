# PrimeKG gốc có 10 loại nút, 30 loại quan hệ; chỉ giữ phần quan hệ bệnh / triệu chứng / thuốc / gen / tác nhân tiếp xúc
NODE_LABELS: dict[str, str] = {
    "disease": "Disease",
    "effect/phenotype": "EffectPhenotype",
    "drug": "Drug",
    "gene/protein": "GeneProtein",
    "exposure": "Exposure",
}

# relation trong kg.csv -> relationship type trong Neo4j
RELATIONS: dict[str, str] = {
    "disease_phenotype_positive": "DISEASE_PHENOTYPE_POSITIVE",
    "disease_phenotype_negative": "DISEASE_PHENOTYPE_NEGATIVE",
    "disease_disease": "DISEASE_DISEASE",
    "disease_protein": "DISEASE_PROTEIN",
    "indication": "INDICATION",
    "contraindication": "CONTRAINDICATION",
    "off-label use": "OFF_LABEL_USE",
    "drug_effect": "DRUG_EFFECT",
    "drug_drug": "DRUG_DRUG",
    "phenotype_phenotype": "PHENOTYPE_PHENOTYPE",
    "exposure_disease": "EXPOSURE_DISEASE",
}
