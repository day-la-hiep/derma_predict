async def resolve_seeds(self, entities: list[str]) -> tuple[list[dict[str, Any]], list[str], set[str]]:
    """Trả (các nút PrimeKG khớp, input không khớp nút nào, DermO id của các input)."""
    seeds: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    dermo_ids: set[str] = set()
    for entity in entities:
        names = {entity.lower()}
        record = await self.exact_dermo(entity)
        if record:
            dermo_ids.add(record["id"])
            names |= {str(record["name"]).lower(), *(s.lower() for s in record.get("synonyms") or [])}
        rows = await self.run(EXACT_SEED_QUERY, types=SEED_TYPES, names=sorted(names))
        if not rows:
            rows = await self.run(LOOSE_SEED_QUERY, types=SEED_TYPES, name=entity.lower())
        if not rows:
            unmatched.append(entity)
        for row in rows:
            seeds[row["id"]] = row
    return list(seeds.values()), unmatched, dermo_ids
