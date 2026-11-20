# OCED Importer

- Import event CSVs into Neo4j using the original OCEAN Cypher semantics.
- Never modify original OCEAN query logic.
- Object CSVs are optional for each selected object type.
- Generate missing object tables from distinct event references.
- Support comma-separated IDs, null handling, and ID consistency.
- Map timestamps to `eventDatetime`.
- Use the existing HTTP CSV import mechanism.
- Keep the guided import UI consistent with SOUP.
- Avoid unnecessary full-file parsing for previews.
- Preserve Memgraph isolation.