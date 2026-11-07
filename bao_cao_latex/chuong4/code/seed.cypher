EXACT_SEED_QUERY = """
MATCH (n:Entity)
WHERE n.type IN $types AND toLower(n.name) IN $names
RETURN elementId(n) AS id, n.name AS name, n.type AS type
"""

LOOSE_SEED_QUERY = """
MATCH (n:Entity)
WHERE n.type IN $types AND toLower(n.name) CONTAINS $name
RETURN elementId(n) AS id, n.name AS name, n.type AS type
ORDER BY size(n.name)
LIMIT 3
"""
