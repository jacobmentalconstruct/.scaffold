# INCORPORATION_INVENTORY.md

> **Status:** Tranche A output — review and triage of `.parts/.dev-tools-REF/`. No code copied; no scaffold edits applied. This document is the input to Tranche B (Incorporation & First Prototype Plan).

---

## Context

Tranche 0 (scaffold + plan files) is complete. The precursor at `.parts/.dev-tools-REF/` contains substantial reusable assets: a 50-tool builder library, 4 vendable packages, ~250 KB of doctrine docs, lib code (journal store, contract, snapshots, evidence, scan/scaffold helpers), an Ollama agent runtime, a teaching/training sandbox, a thin K8s wrapper, and an onboarding HTML microsite.

Tranche A walked every substantial piece and tagged each with one of:

- **ADOPT** — copy near-verbatim with path/name sanitization in Tranche 2+.
- **ADAPT** — rewrite using the precursor as a strong reference.
- **INSPIRE** — good idea, build a fresh shape that fits our spine.
- **SKIP** — precursor-specific or not aligned with our model.
- **DEFER** — keep in mind, not in the first prototype; possibly reserve schema fields now.

The First Working Prototype's proving loop (per ARCHITECTURE.md §9): install → scan → project map → events → graph edges → human dashboard → agent bootstrap → agent proposes a journal entry / patch plan → human inspects evidence. Nothing mutates the host project at this stage.

Decision Points already locked in plan-mode approval:
- **DP1: Agent runtime out of scope** for first prototype (agent-agnostic; any MCP client connects). The Ollama-backed `local_sidecar_agent` and `_ollama-prompt-lab` are deferred.
- **DP2: This file lives at** `_docs/INCORPORATION_INVENTORY.md`.
- **DP3: Roadmap will live at** top-level `IMPLEMENTATION_ROADMAP.md`.
- **DP4: Triage-focused depth** — read enough to decide; deepen only on `_constraint-registry` and `_manifold-mcp`.
- **DP5: Onboarding microsite — DEFER.**
- **DP6: Containerization (`_v2-pod/`) — DEFER.**

---

## Section 1 — Doctrine layer (Tranche A.1)

The precursor's `_docs/*.md` introduce **11 named concepts and 4 workflow patterns** not yet in our scaffold. The most architecturally significant are governance and continuity rituals; the rest are evidence/agent-runtime concepts to keep on the horizon.

### 1.1 Concepts and patterns — decision table

| Concept | Precursor source | Decision | Target landing |
|---|---|---|---|
| **Setup Doctrine** | `SETUP_DOCTRINE.md` — 13-step "setup before features" sequence | **FOLD-IN** | New section in our `ARCHITECTURE.md`: "Setup Phase" with the discipline (not the precursor's exact 13 steps — adapt to our spine). |
| **Parking Workflow** | `PARKING_WORKFLOW.md` — tranche closeout: inspect→verify→capture→journal→update-docs→rerun→report | **FOLD-IN** | New section in `ARCHITECTURE.md`: "Park Phase". Reuse our existing tranche discipline; formalize the closeout as a structured "parking record." |
| **Experiential Workflow** | `EXPERIENTIAL_WORKFLOW.md` — lived collaboration rhythm: orient from manifests, choose the right surface, work inside boundaries, verify before shipping, leave a clean return path | **FOLD-IN as principle** | Short "Collaboration Rhythm" section in `ARCHITECTURE.md`. |
| **Journal Doctrine** | `SETUP_DOCTRINE.md` §journal — append-only; no generated mirrors as truth; deferred work belongs in journal/TODO | **FOLD-IN** | Already partially encoded in our contract Pledge 2 + journal_manager plan; tighten the wording to call out append-only + no-generated-mirror-truth. |
| **North Stars Cadence** | `NORTHSTARS.md` — living "satisfied" vs "later expansion" table | **FOLD-IN as lightweight pattern** | Add `NORTHSTARS.md` at scaffold root (or fold into `IMPLEMENTATION_ROADMAP.md`) with explicit non-goals to prevent scope creep. |
| **Evidence Shelf + Bag of Evidence** | `ARCHITECTURE.md` lines 348–382 — session STM archive (Bag) + rolling summary (Shelf) | **DEFER, reserve schema** | Keep our planned `evidence_manager` simple for prototype; reserve fields on events/evidence for `session_id`, `evidence_kind`, `summary`, `body_hash`. |
| **Recovery Classification** | `ARCHITECTURE.md` lines 164–213 — named failure classes for live-model runs | **DEFER, reserve schema** | Add optional `recovery_class` field to event schema now (enum reserved, unused at MVP). Avoids backport. |
| **Sliding-Window Overflow** | `AGENT_GUIDE.md` lines 374–406 — Window→Archive→Shelf→Retrieve→Promote loop | **DEFER** | Pure agent-session optimization; not our concern until we run multi-turn local agent loops. |
| **Workspace Boundary Auditing** | `workspace_boundary_audit` tool + `text_workspace.py` lib | **INSPIRE** | Encode boundary-safety as a precondition check inside `install_orchestrator` and any `Apply`-authority envelope. Don't build a separate audit tool yet. |
| **Constraint Registry & Profiles** | `_constraint-registry/` package — 65+ atomic constraints, 8 task profiles | **ADOPT shape (see Section 3)** | Strong fit for our `core/contracts.py` ContractAuthority. See §3 for details. |
| **Teaching Sandbox / Training Runway** | `teaching_sandbox_harness` (170 KB!) + `TRAINING_RUNWAY.md` | **DEFER (Tranche 13+), reserve schema** | Add optional event-schema fields: `run_id`, `scenario_id`, `run_mode`, `score_result`, `pass_fail_state`, `touched_paths`. |

### 1.2 Schema reservations to take NOW

Adding these as optional/nullable fields on our event schema (with no behavior at MVP) keeps the door open for the deferred concepts without forcing a future migration:

**Recovery (deferred to post-prototype):**
`recovery_class` (nullable string), `recovery_decision` (nullable string), `evidence_id` (nullable FK).

**Session & training (deferred to Tranche 13+):**
`session_id`, `run_id`, `scenario_id`, `run_mode` (mocked|live|null), `timeout_seconds`, `max_tool_rounds`, `score_result`, `pass_fail_state`, `touched_paths` (JSON array).

**Journal durability (FOLD-IN now):**
`journal_entry_id` FK on related events; `is_durable` boolean (true for journal entries; false for transient evidence).

These additions belong in `src/schemas/event_schema.py` plan revision in Tranche B.

### 1.3 Tensions / contradictions

None. The precursor's concepts operate at a different layer (agent playbook, governance rituals, runtime evidence) than our scaffold's spine. They compose cleanly.

---

## Section 2 — 50 Tools (Tranche A.2)

### 2.1 First-prototype tool slate (the must-haves)

These tools are required for the proving loop. **All ADOPT or ADAPT.**

| tool_name | precursor category | decision | one-line purpose |
|---|---|---|---|
| `sidecar_install` | install | ADOPT | Bring the sidecar online inside the host project (one-time + idempotent). |
| `journal_init` | bootstrap | ADOPT | Create journal DB, seed contract, scaffold `_docs/`. |
| `journal_write` | write | ADOPT | Create/update/append journal entries. |
| `journal_query` | query | ADOPT | Search/filter or fetch by uid. |
| `journal_acknowledge` | contract | ADOPT | Record agent/human acceptance of contract — the gate. |
| `file_tree_snapshot` | introspection | ADOPT | Snapshot project file tree with metadata; feeds project_map. |
| `workspace_boundary_audit` | introspection | ADOPT | Audit project root, git root, ignored paths — boundary safety check. |
| `host_capability_probe` | introspection | ADOPT | Read-only probe of host capabilities. |
| `dependency_env_check` | introspection | ADOPT | Check Python/Node dependency readiness. |
| `project_command_profile` | introspection | ADOPT | Detect declared setup/test/run/build commands. |
| `text_file_reader` | introspection | ADOPT | Bounded text reads with protections. |
| `text_file_writer` | write | ADOPT | Confirmed create/overwrite/append text writes (used by Apply-authority envelopes). |
| `directory_scaffold` | scaffold | ADOPT | Declarative directory/file scaffolding (workspace-only initially). |
| `session_evidence_store` | memory | ADAPT | Strip the sliding-window/Shelf logic; keep simple "attach evidence" surface. |
| `text_file_validator` | testing | ADOPT | Validate Python, JSON, TOML before commit. |
| `secret_surface_audit` | security | ADOPT | Scan for committed secrets; safety check before any write to host. |
| `repo_search` | introspection | ADAPT | Useful but route through our envelope; integrate with evidence attach flow. |
| `project_setup` | bootstrap | ADAPT | Reshape for our contract model; reuse the handshake-read-order concept. |

**Total first-prototype tool count: ~18** (some can be folded together; final count in Tranche B). This exceeds the 4–8 figure in the original plan because the proving loop is more demanding than initially estimated. **Decision Point for B: confirm 18 is the target, or further trim.**

### 2.2 Highly-recommended Tranche 6+ (DEFER)

| tool_name | category | why valuable post-prototype |
|---|---|---|
| `git_private_workspace` | version-control | Checkpoint agent reasoning in ignored .git history. |
| `agent_run_trace` | memory | Eval/tuning data; couples to recovery_class field. |
| `dev_server_manager` | operations | Run host project's declared dev/test commands safely. |
| `smoke_test_runner` | testing | Tool-suite health in CI. |
| `journal_export` | export | External review/audit artifacts. |
| `journal_snapshot` | snapshot | Merkle snapshots — depends on snapshots.py adoption. |
| `file_delete_guarded`, `file_move_guarded` | editing | Safe project mutations. |
| `tokenizing_patcher` | editing | Whitespace-immune patch application. |
| `journal_actions` | ledger | Cross-actor action audit trail. |

### 2.3 Inspire-only

| tool_name | what to take |
|---|---|
| `dead_code_finder` | Build a fresh, scoped read-only scanner; the concept is good. |
| `python_complexity_scorer` | Lightweight complexity probe for the project_index. |
| `module_decomp_planner` | Strong reference for decomp-recommendation tool — much later. |
| `test_scaffold_generator` | Build less AST-heavy variant. |

### 2.4 Skip outright

| tool_name | reason |
|---|---|
| `domain_boundary_audit` | Precursor-specific architecture rules. |
| `scan_blocking_calls`, `tkinter_widget_tree` | UI-stack-specific; our UI patterns differ. |
| `onboarding_site_check` | DP5 deferred onboarding microsite. |
| `local_sidecar_agent` | DP1 — we are agent-agnostic in prototype. |

### 2.5 Notable design surprises

1. **The precursor is heavily journal-centric** — separate tables for journal entries, run traces, action ledger, contract acks, snapshots. We've folded most of this into the unified events + graph + projections spine. Confirm in Tranche B that we don't need separate `action_log` table.
2. **Code-quality tools exist but are deferred** — dead-code, complexity, decomposition planner. Nice-to-have signals for the project_index projection later.
3. **No UI-specific tools needed for our prototype** — the precursor's Tkinter introspection tools won't carry over.
4. **"Guarded mutation" pattern is universal** — almost every mutating tool has dry-run, confirm, and reason metadata. **Adopt this pattern in our `Apply`-authority envelope contract.**
5. **Teaching/eval is baked in** — `teaching_sandbox_harness` (170 KB!) + `agent_run_trace`. Confirms the precursor was designed for tuning runs. Defer the harness; reserve the trace fields.

---

## Section 3 — 4 Packages (Tranche A.3)

### 3.1 `_constraint-registry/` — **ADOPT FILES (strong fit for ContractAuthority)**

**Purpose:** Machine-readable projection of the Builder Constraint Contract. Decomposes a long-form contract into atomic constraint units, queryable by task profile.

**Data model (worth adopting):**
- `constraint_units` table: uid, section, title, domain_tags (JSON), severity (HARD_BLOCK | PUSHBACK | ADVISORY), tier (spirit | letter | gate), instruction, full_text.
- `task_profiles` table: profile_id, description, constraint_uids (JSON array).

**65+ atomic constraints, 8 pre-built profiles:** `ui_implementation`, `core_implementation`, `refactoring`, `sourcing_extraction`, `documentation`, `cleanup`, `tool_creation`, `scaffolding`.

**Why this fits:**
- The tier system (spirit/letter/gate) maps cleanly to our authority levels (Observe → Propose → Sandbox Execute → Apply → Export).
- The domain tagging system aligns with our closed predicate set.
- The `run(arguments) → {status, tool, input, result}` envelope and `common.py` pattern *is* our Standard Tool Contract.

**What to actually adopt:**
1. The two-table schema (`constraint_units` + `task_profiles`) — extend our `data/sidecar.db` plan in Tranche B.
2. The `constraint_query(profile)` API — adopt as a method on `ContractAuthority`.
3. The `common.py` envelope helpers — fold into our `src/lib/common.py` plan.
4. **NEW SCAFFOLD FILES NEEDED:** likely add `src/managers/constraint_manager.py` to own the registry tables (or fold into `core/contracts.py`). Decide in Tranche B.

**What NOT to adopt:** the precursor's specific 65 constraint texts — we have our own contract.

### 3.2 `_manifold-mcp/` — **INSPIRE (architectural tension; partial fit only)**

**Purpose:** Reversible text-evidence-hypergraph. Ingest text → evidence spans → hypergraph → query → reconstruct verbatim source.

**Data model:**
- Single JSON corpus bundle with five record types: `documents`, `evidence_spans` (deterministic SHA1[:12] IDs, char offsets preserved), `nodes` (kinds: document/claim/entity), `hyperedges` (n-ary), all grounded to evidence_spans for full reversibility.

**Tension:** Our graph is designed around **authority decisions** (typed predicates, closed set, drives projections for UI/agent). Manifold's graph is designed around **text reversibility** (every claim → evidence span → verbatim source). These compose conceptually but Manifold's data model is heavier than we need.

**What to actually inspire (NOT adopt):**
1. **Deterministic IDs** — adopt SHA-based IDs for our event_id, object_id, evidence_id. Predictable, sortable, dedupable.
2. **Evidence-span indexing** — when we attach evidence to an envelope, store char-offset metadata if applicable. Useful for "show me the line that supports this claim" UI.
3. **Reconstruction discipline** — every projection should be reconstructible from events alone. (Already in our ARCHITECTURE.md; this confirms the principle.)

**What NOT to do:** adopt the corpus-bundle schema or hypergraph kinds. Our closed-predicate graph is the right shape for our scope.

**DEFER full evaluation** to a future Tranche when we want multi-document evidence chaining (likely Tranche 8+).

### 3.3 `_app-journal/` — **SKIP for prototype, code-time reference only**

**Purpose:** Standalone journal package (separate from the precursor's main src/lib/journal_store.py). Has its own UI + MCP + tools.

**Decision:** SKIP as a unit for prototype. Already fully absorbed conceptually into our `journal_manager.py` + `sqlite_store.py` + `journal_orchestrator.py` + `journal_panel.py` + the journal-category tools.

**Code-time reference:** when writing our journal manager, read this package's `lib/journal_store.py` and `tools/journal_*.py` for implementation patterns. That's a Tranche 4-time concern, not a Tranche B concern.

### 3.4 `_ollama-prompt-lab/` — **DEFER ENTIRELY (DP1)**

**Purpose:** Local prompt evaluation harness for Ollama models.

**Decision:** Deferred per Decision Point #1 (no agent runtime in first prototype). The only carry-forward principle: *"prefer deterministic checks before model-judge checks"* — fold into our ContractAuthority design as a general principle (validations and explicit gates beat model-as-judge).

### 3.5 New question: do we add a `packages/` folder to `.scaffold/`?

The precursor's `packages/` pattern (vendable sub-projects each with own MCP server + tools + contract) is interesting but adds complexity. Our current scaffold has no `packages/` folder — everything is in `src/`. **Tranche B Decision:** keep flat (everything in `src/`), or add `packages/` for future modularity?

Recommendation: keep flat for prototype. Promote to `packages/` later only if/when a sub-project grows large enough to warrant separate vending.

---

## Section 4 — `src/lib/` triage (Tranche A.4)

| File | Size | Decision | Target in our scaffold |
|---|---|---|---|
| `journal_store.py` | 24 KB | **ADAPT** | Reference for `src/components/sqlite_store.py` and `src/managers/journal_manager.py`. |
| `contract.py` | 4 KB | **ADOPT** | `seed_contract()` + `get_builtin_contract_text()` patterns into `src/core/contracts.py`. |
| `snapshots.py` | 7 KB | **DEFER, reserve concept** | Snapshot orchestrator already deferred in our scaffold. Reference at code-time. |
| `text_workspace.py` | ~8 KB | **INSPIRE** | Boundary-safety patterns. Fold into install_orchestrator preconditions; do NOT create a new manager. |
| `agent_run_trace.py` | 5 KB | **ADAPT, DEFER use** | Schema skeleton; integrates with the deferred `recovery_class` field. |
| `session_evidence_store.py` | 10 KB | **DEFER, reserve schema** | The Bag/Shelf concepts. Reserve fields per §1.2. |
| `intake.py` | 4 KB | **ADAPT** | `register_project()` patterns into our `project_index_manager.py` (or a new `project_registry`-shaped table — see §3.5). |
| `sidecar_release.py` | 5 KB | **ADAPT** | `load_release_payload_manifest()` pattern into install_orchestrator. |
| `operator_ui_support.py` | ~8 KB | **INSPIRE** | Mutating-tool flagging + sanitization regex. Reference for `src/ui/main_window.py` action submission. |
| `project_setup.py` | 177 lines | **ADAPT** | `REQUIRED_ROOT_PATHS`, `REQUIRED_DOC_PATHS`, `HANDSHAKE_READ_ORDER` constants → install_orchestrator. |
| `scaffolds.py` | 139 lines | **ADAPT** | Template registry + unpacking loop → scaffold_orchestrator. |
| `teaching_sandbox_harness.py` | **4192 lines!** | **SKIP for prototype, DEFER full** | Sandbox pedagogy; archive for Training Runway tranche. |
| `builtin_contract.md` | 61 KB | **ADAPT sections** | Use defined sections (definitions, domains, phases, non-goals) as reference for our `contracts/BCC.md` evolution; we already updated the contract in Tranche 0. |
| `builtin_templates/` | 24 files, ~40 KB | **ADAPT cherry-pick** | Pull Python skeleton templates (`src_app.py`, `src_core_engine.py`, etc.) for first-prototype scaffolding. Map to our naming. Defer doc templates. |

---

## Section 5 — Misc inspection (Tranche A.5)

### 5.1 `agent_ui.py` (41 KB top-level)

Tkinter desktop UI for local-agent control. Wires theme, tool form builder, log pane, recovery UI; depends on local_sidecar_agent runtime.

**Decision: ADAPT patterns, not files.** The dark theme, tool-form builder, mutating-tool guard, and async tool-execution pattern are good. Strip the Ollama runtime dependency. Adapt into our `src/ui/main_window.py` + panels in Tranche 3. Stay with Tkinter (matches our scaffold plan).

### 5.2 `install.py` (14 KB)

Tkinter folder picker → preview → `shutil.copytree` → smoke test → file inventory.

**Decision: SKIP installer ceremony, ADAPT post-install steps.** Per our paste-and-unzip vending model, no installer UI is needed. Adopt: target structure verification, smoke test trigger, journal seeding. Fold into `install_orchestrator.py` as the first-boot routine.

### 5.3 Manifests — `tool_manifest.json` and `toolbox_manifest.json`

- `tool_manifest.json` (9.9 KB) — per-tool metadata (name, description, category, input_schema, mcp_transport, result_envelope_keys).
- `toolbox_manifest.json` (3.8 KB) — high-level descriptor: `builder_tools`, `vendable_packages`, `vendable_documents`, plus a "zero-context entry protocol."

**Decision: ADOPT both.** Use tool_manifest shape for our auto-generated `config/tool_manifest.json`. Use toolbox_manifest shape (tiers + zero-context protocol) for a new `config/toolbox_manifest.json` that describes the whole `.scaffold/` to a fresh agent. **NEW FILE PROPOSED for Tranche B**: `config/toolbox_manifest.json.PLAN.md`.

### 5.4 `onboarding/` directory — discrepancy resolved

**State:** **NOT empty.** Agent 1 was right; Agent 2 missed it. Contains 8 HTML files (~30 KB total) + 1 CSS:
- `START_HERE.html` (17 KB entry point)
- 7 page HTMLs (2–3 KB each): how-a-new-session-starts, how-humans-and-agents-share-the-loop, how-the-workflow-feels-in-practice, how-to-vend-this-toolbox, how-tools-packages-and-templates-fit-together, toolbox-atlas, why-the-toolbox-matters

**Decision: DEFER (per DP5).** Archive HTML assets as a Phase 2 reference. The narrative tone is good and could inspire our own onboarding doc later.

### 5.5 `_v2-pod/` — confirmed thin K8s wrapper

`Dockerfile` (1.4 KB) + `entrypoint.sh` (1.5 KB) + `k8s/deployment.yaml` + `.dockerignore` + `README.md` (5.3 KB).

Pattern: ephemeral pod, install into `/workspace`, smoke test, exec MCP server.

**Decision: DEFER (per DP6).** Clean reference for Phase 2 containerization. Archive.

---

## Section 6 — Net adoption summary

### 6.1 Files we will copy (with sanitization) — Tranche 2+

**Tools (~18 for first prototype):** see §2.1.
**Lib references and patterns:** `journal_store.py`, `contract.py`, `agent_run_trace.py`, `intake.py`, `scaffolds.py`, `project_setup.py`, `sidecar_release.py` (all ADAPT into our existing planned files; not copied verbatim).
**Schema patterns:** `_constraint-registry`'s two-table model.
**Manifests:** the toolbox-manifest + tool-manifest JSON shapes.
**Templates:** cherry-picked Python skeletons from `src/lib/builtin_templates/`.

### 6.2 Concepts to fold into ARCHITECTURE.md (Tranche B.2 update)

- Setup Phase (from Setup Doctrine)
- Park Phase + Parking Record (from Parking Workflow)
- Collaboration Rhythm (from Experiential Workflow)
- Journal Doctrine tightening (append-only + no-mirror-truth)
- Guarded-mutation pattern for `Apply`-authority envelopes
- Deterministic IDs (SHA-based) — from `_manifold-mcp` inspiration
- Boundary-safety preconditions inside install_orchestrator and Apply envelopes

### 6.3 Schema additions to take NOW (Tranche B.2)

Per §1.2 — recovery, session/training, journal-durability fields on event/projection schemas. All optional/nullable; no behavior change at MVP; avoids future migration.

### 6.4 New scaffold files proposed for Tranche B

| Proposed file | Why |
|---|---|
| `IMPLEMENTATION_ROADMAP.md` (top level) | DP3 — the Tranche B output. |
| `NORTHSTARS.md` (top level) OR §in IMPLEMENTATION_ROADMAP | §1.1 — "satisfied vs later expansion" pattern. |
| `_docs/` folder | Already created with this file. |
| `config/toolbox_manifest.json.PLAN.md` | §5.3 — high-level descriptor of `.scaffold/`. |
| `config/tool_manifest.json.PLAN.md` | §5.3 — already proposed earlier; confirm in B. |
| Possibly `src/managers/constraint_manager.py.PLAN.md` | §3.1 — if we promote ContractAuthority to need a manager layer for the constraint registry tables. |
| Possibly `src/orchestrators/snapshot_orchestrator.py.PLAN.md` | Currently snapshot is implicit in install/scan; if formalized, needs its own file. |

### 6.5 Things we are explicitly NOT taking

- The precursor's flat `src/tools/`, `src/lib/`, `src/mcp_server.py` shape (we have a deeper layer model).
- `_app-journal` as a package unit (already absorbed into our spine).
- `_ollama-prompt-lab` and `local_sidecar_agent` (DP1 deferred).
- `teaching_sandbox_harness.py` as code (DEFER; reserve schema fields only).
- `domain_boundary_audit`, `scan_blocking_calls`, `tkinter_widget_tree`, `onboarding_site_check` tools.
- Onboarding HTML microsite (DP5).
- `_v2-pod/` containerization (DP6).
- The precursor's full 65-constraint catalog (we author our own using their schema shape).
- The Bag/Shelf full implementation (DEFER; schema reserved only).

---

## Section 7 — Open questions for Tranche B (decisions needed)

These emerged from Tranche A and need resolution before the Implementation Roadmap can be locked:

1. **`packages/` folder in `.scaffold/`?** The precursor uses one for vendable sub-projects. Recommendation: skip for prototype (keep flat); promote later if a sub-project grows large.

2. **Promote ContractAuthority to a manager?** §3.1 — if we adopt the two-table constraint registry shape, we may need `src/managers/constraint_manager.py` to own the tables, with `core/contracts.py` becoming a slim gate that consults it. Or fold both responsibilities into `core/contracts.py`.

3. **First-prototype tool count:** §2.1 lists 18 tools. The original plan estimated 4–8. Confirm 18 is acceptable or further trim.

4. **Schema reservations:** §1.2 — confirm all proposed nullable fields go on the event schema now.

5. **Project registry table:** §4 (intake.py adoption) — add a `project_registry` table now, or wait?

6. **Toolbox manifest:** §5.3 — confirm we want a top-level `config/toolbox_manifest.json` describing the whole `.scaffold/` for zero-context agent entry.

7. **Constraint registry adoption depth:** §3.1 — adopt schema-only, OR adopt schema + the 8 task profiles concept (and define our own constraint texts), OR adopt all the way down to the constraint-query API.

8. **Tools path strategy:** Tranche 2 will need to start populating `src/tools/`. Do we land all 18 first-prototype tools in one tranche, or split into "scan tools" (Tranche 2) + "journal tools" (Tranche 4) per the Roadmap?

---

## Verification

This document is complete when:
- Every reviewed precursor item has a decision tag — **YES.**
- All discrepancies from the original Explore reports are resolved (`onboarding/` populated, `src/lib/` has additional files like `project_setup.py`, `scaffolds.py`, `teaching_sandbox_harness.py` that weren't in initial inventory) — **YES.**
- Open questions are explicit and ready for Tranche B — **YES, listed in §7.**
- No code has been written or copied — **YES.**

**Next step:** user reviews this inventory; confirms or corrects decisions; then Tranche B (Incorporation & First Prototype Plan) writes the `IMPLEMENTATION_ROADMAP.md`.
