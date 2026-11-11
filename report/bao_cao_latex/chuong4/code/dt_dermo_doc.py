def parse(lines: list[str]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    header: dict[str, str] = {}
    terms: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    in_term = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("["):
            in_term = line == "[Term]"
            cur = new_term() if in_term else None
            if cur is not None:
                terms.append(cur)
            continue
        if ":" not in line:
            continue
        tag, _, value = line.partition(":")
        value = value.strip()
        if cur is None:
            if not in_term and not terms:
                header[tag] = value
            continue
        if tag == "id":
            cur["id"] = value
        elif tag == "name":
            cur["name"] = value
        elif tag == "def" and (m := DEF_RE.match(value)):
            cur["def"] = m.group(1)
        elif tag == "synonym" and (m := SYN_RE.match(value)):
            text = m.group(1).removeprefix(NEW_SYN_TAG).strip()
            if text:
                cur["synonyms"].append({"text": text, "scope": m.group(2)})
        elif tag == "xref":
            cur["xrefs"].append(value.split()[0])
        elif tag == "alt_id":
            cur["alt_ids"].append(value)
        elif tag == "is_a":
            cur["is_a"].append(value.split()[0])
        elif tag == "relationship":
            rel, target = value.split()[:2]
            cur["relationships"].append({"type": rel, "target": target})
        elif tag == "is_obsolete":
            cur["is_obsolete"] = value == "true"
    return header, terms
