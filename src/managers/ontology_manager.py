"""
FILE: src/managers/ontology_manager.py
ROLE: Owner of the ontology domain — types, schemas, and naming registries.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

DOMAIN
------
"Ontology" = the registry of object types, kinds, tags, and predicates
that the sidecar recognizes. It does NOT mean "the graph itself"
(that's `src/core/graph.py`). It is the dictionary that describes the
graph's vocabulary.

The ontology is what lets the sidecar say:
- "this object_type 'patch_proposal' has these expected fields"
- "this tag 'security' implies importance >= 7"
- "this predicate 'modifies' is allowed between (patch, file) but not
  between (file, file)"

OPERATION INTENTS HANDLED
-------------------------
- `register_object_type` (e.g., a new tool registers a custom object type)
- `update_object_type`
- `register_tag` / `update_tag`
- `query_ontology` (read-side)

STATE
-----
- Owns `ontology_object_types`, `ontology_tags`, `ontology_predicate_rules`.
- Reads from `src/schemas/` for built-in types (these are seeded on first
  boot, then lived in the DB so external tools can extend them).
- Updates `SidecarState.ontology_state` for the agent bootstrap packet.

SPINE FIT
---------
- Receives envelopes from Router.
- Read API consulted by:
    * ContractAuthority (for predicate rules at envelope validation)
    * ProjectionManager (for tag-driven queries)
    * Tools that need to introspect known object types.

DEPENDENCIES
------------
- `src/components/sqlite_store.py`
- `src/schemas/contract_schema.py` and friends for seed data.

NON-GOALS
---------
- Does not own relations themselves — Graph does.
- Does not enforce rules — it stores them; ContractAuthority consults
  them when validating envelopes.

OPEN QUESTIONS
--------------
- Tag inheritance / hierarchies: defer until needed.
- Object type versioning: probably yes; mirror envelope versioning.
"""
