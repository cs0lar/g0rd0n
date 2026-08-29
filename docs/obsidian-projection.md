# Obsidian Projection

Phase 04 projects replayed `ResearchState` into deterministic Markdown notes.
Stable object IDs determine filenames, while research-object kinds determine
vault folders. Relationships appear as bidirectional Obsidian wikilinks, so a
claim links back through results and observations to experiments.

## Ownership and import policy

Generated notes declare `generated: true` and a generator version in frontmatter.
Only text between the manual ownership markers is preserved during regeneration.
Missing, duplicate, or reordered markers stop projection rather than risk losing
human work.

`collect_manual_edits()` returns non-empty manual regions as immutable
`HumanEdit` proposals. It does not mutate the ledger or knowledge store. A later
review workflow must interpret and approve those proposals as new provenance-
bearing scientific events; arbitrary Markdown is never treated as fact.

## Evidence

Referenced raw artifacts require a loader. The projector verifies each SHA-256
digest before copying bytes to `99-generated/artifacts/<digest>`. Notes link to
those vault-local files, keeping raw evidence distinct from rendered scientific
content and narrative interpretation.
