# **Builder Constraint Contract**

*Status: Tranche 0 revision — adapted to the vended-sidecar model and the hybrid-in-SQLite spine.*
*Supersedes the precursor copy at `.parts/IMPORTANT-DOCUMENTS-TO-READ-FIRST/builder_constraint_contract.md`.*
*Provenance recorded in `/SOURCE_PROVENANCE.md`.*

---

## **0. Definitions**

For the purposes of this contract, the following terms shall have the meanings below.

### **0.1 Sandbox root**

The sandbox root is the top-level workspace directory accessible to the builder for the current conversation/project context. It may contain the active project folder, sibling project folders, `.parts/`, `.scaffold/`, and other sandbox-level items.

### **0.2 Project root**

The project root is the single active folder in which the current project is built. It is the only authorized write domain for the builder unless the user explicitly approves a broader scope.

### **0.3 Vendored / vendorable project**

A vendored or vendorable project is a self-contained project that can be moved, reused, or handed off without depending on sibling projects, sandbox reference folders, or hidden local coupling.

### **0.4 Scaffold**

The scaffold is the approved project folder/file structure supplied by the user, whether as a pre-created tree with placeholder files or as a declared file tree map to be instantiated.

### **0.5 Ownership**

Ownership is the assignment of a file, module, component, or logic unit to one clear domain of responsibility within the project structure.

### **0.6 Domain**

A domain is a coherent responsibility area such as UI, core processing, configuration, data handling, logging, testing, or another clearly bounded subsystem.

### **0.7 CAS (Content-Addressed Storage)**

A storage method where data is retrieved based on its content hash (SHA-256) rather than its location. In this project, CAS integrity is managed via a `blob_store` table inside the sidecar SQLite database.

### **0.8 Meaningful phase (tranche)**

A meaningful phase is a coherent unit of work substantial enough to justify project reporting, such as completion of a contract section, a subsystem implementation step, a structural refactor, a tooling addition, a cleanup pass, or another bounded set of related changes. Tranches are declared with explicit scope, non-goals, and completion points before implementation begins.

### **0.9 Builder memory**

Builder memory is the project-side operational memory used to preserve doctrine, work history, TODO state, and continuity records. Under this project, builder memory is authoritative and resides in the sidecar SQLite database (see §0.10 and §"Required Project Documentation").

### **0.10 Sidecar package and sidecar root** *(new in this revision)*

The **sidecar package** is the self-contained directory `.scaffold/` that may be vended (paste-and-unzip) into any target project. The **sidecar root** is the location of that directory at runtime. The sidecar package has a dual scope:

- **Development scope** — while the sidecar package is itself the active project being built, the sandbox root contains `.scaffold/` and the project root *is* `.scaffold/`. Reference materials live under `.scaffold/.parts/` and are read-only (see §1.1).
- **Deployment scope** — when the sidecar package has been vended into a host project, it appears as `<host_project>/.scaffold/`. The sidecar root is then `.scaffold/` inside the host. The host project's own application code never imports from the sidecar; the sidecar observes and acts on the host project through tools only.

In both scopes, the sidecar writes only inside its own subtree (`.scaffold/`) unless an action carries explicit `Apply` or `Export` authority granted by human approval (see §"Authority Levels").

---

## **Technical Pledges**

Anyone building on or modifying this package agrees to the following core technical disciplines:

1. **Isolation** — Keep the sidecar package portable and self-contained. No external runtime dependencies beyond the Python standard library and explicitly declared packages.
2. **Single Store** — UI, MCP, and CLI behavior must be unified through a single store layer (`src/components/sqlite_store.py` and `src/managers/journal_manager.py`). There is exactly one code path to the database.
3. **Schema Stability** — The SQLite schema is explicit and versioned. Prefer additive changes (new columns/tables) over destructive ones.
4. **CAS Integrity** — All large or content-addressed payloads flow through the `blob_store` via SHA-256 hashes. Where a payload has a readable form, that form remains readable; the `body_hash` is the additive integrity layer.
5. **Readable Exports** — Markdown and JSON exports from the sidecar must be human-readable and mechanically parseable.
6. **Spine Discipline** *(new in this revision)* — Every state mutation flows: Interface → Envelope → Router → ContractCheck → Orchestrator → Manager → Event → derived views. No sideways calls between managers. No back-channels. The envelope is the only currency through the spine.
7. **Envelope Lightness** *(new in this revision)* — Envelopes route and identify; they do not carry heavy payloads. Diffs, vectors, ASTs, screenshots, large text bodies, and logs are stored separately and referenced by id/hash inside the envelope.

---

## **Spine Architecture (Reference)**

The sidecar is built on a hybrid-in-SQLite spine with three layered concerns inside one database:

1. **Authoritative event log** — append-only record of every accepted envelope.
2. **Graph index** — typed relations (closed set, see §"Relation Types") between objects, derived from events.
3. **Projection tables** — current-state views (read models) consumed by the UI and agents.

The MVP order of implementation is:

1. **SidecarState** (`src/core/state.py`)
2. **SidecarEnvelope** (`src/core/envelope.py`)
3. **EventStore** (`src/core/events.py`)
4. **Router** (`src/core/router.py`)
5. **ProjectionManager** (`src/core/projections.py`)

Once those exist, orchestrators and managers may be added without bending the spine.

### **Authority Levels**

Every envelope carries an authority claim. Authority climbs only by contract and approval.

| Level | Meaning |
|---|---|
| Observe | Read sidecar and project state. No writes. |
| Propose | Create draft envelopes (e.g., journal proposals, patch plans). No state changes outside the proposal record. |
| Sandbox Execute | Run tools in an isolated workspace under `.scaffold/workspaces/`. No project-tree writes. |
| Apply | Write to the host project tree. Requires explicit human approval per envelope. |
| Export | Emit artifacts outside `.scaffold/` (reports, packs, snapshots). Requires explicit human approval per envelope. |

The agent's default authority is **Observe** or **Propose**.

### **Event Streams (Mixed)**

Events are partitioned across mixed streams to avoid forcing every event into one category:

- `project` — project-level events (install, scan completed, project map updated)
- `task` — task/workflow events (task created, task superseded, task completed)
- `object` — events on specific objects (file observed, journal entry created, contract acknowledged)
- `tool` — tool execution events (tool invoked, tool result, tool failed)

### **Relation Types (Closed Set)**

Generic `related_to` is banned. Only these relation types may be created:

`belongs_to`, `observes`, `derives_from`, `supersedes`, `cites`, `modifies`, `validates`, `requires`, `emitted_by`, `approved_by`, `failed_due_to`, `produces`.

### **Day-One Projections**

The first set of projections built from events + graph:

- Current Sidecar State
- Agent Bootstrap Packet
- Human Dashboard View
- Evidence Bag View
- Contract Status View
- Project Map View
- Journal Timeline View

---

## **Builder Workflow Discipline Amendment**

The builder shall operate under stable project laws rather than treating each prompt as a new unconstrained universe.

### **A. Stable constraint-field rule**

The builder shall preserve and work within the active constraint field. This includes the contract, active architecture doctrine, builder-memory records in the sidecar DB, tranche boundaries, and explicit non-goals.

### **B. Tranche-boundary rule**

Meaningful work is executed in bounded tranches. Before implementation, the builder identifies the current tranche scope, explicit non-goals, and completion points.

### **C. Truth-layer separation rule**

The builder shall preserve the distinction between:

- **Builder-memory truth:** the sidecar DB at `data/sidecar.db`.
- **Design truth:** `/ARCHITECTURE.md` at the sidecar root.
- **Runtime-consumed truth:** the host project's own internal data stores (which the sidecar reads but does not own).

### **D. Park Phase Discipline** *(added 2026-05-11; codifies what was previously a conversational ritual — see journal entry `journal_18ae7fbc35603af0_ec2ea642`)*

Every tranche closes with a Park Phase per `ARCHITECTURE.md §12.2`. The phase is **not optional** and is **not memorized in chat** — it is encoded in the codebase and enforced by `smoke_test.py`.

A complete parking record is the union of these five artifacts. If any one is missing, the tranche is not parked and the next tranche must not begin:

1. A `kind='tranche'` journal entry written via the standard envelope chain (`create_journal_entry`), with `evidence_refs` citing a CAS-stored park-notes blob, importance ≥ 8, related_path pointing at `_docs/T_n_PARK_NOTES.md`.
2. The park-notes file itself (`_docs/T_n_PARK_NOTES.md`) and its blob in `blob_store`.
3. **All continuity docs updated** (this is the most-drifted step — make it mechanical):
    - `IMPLEMENTATION_ROADMAP.md` — tranche marked `COMPLETE` with metrics and entry uid.
    - `SOURCE_PROVENANCE.md` — dated entry distinguishing original code vs structural borrows.
    - `TOOLS.md` — row count must equal `tool_registry` count.
    - `ARCHITECTURE.md §15` — `Resolved at T_n` subsection added.
    - `README.md` — top-level status header reflects current state.
4. An `accept_task` envelope and a correlated `complete_task` envelope (the tranche lifecycle events).
5. A `close_journal_entry` envelope moving the tranche entry's status from `'open'` → `'closed'`. The entry's content is immutable per `ARCHITECTURE.md §13.1` (Journal Doctrine); the status change is a non-destructive lifecycle update.

**Verification:** `python smoke_test.py` includes **drift-detection sections** that fail when any of the above is missing. If smoke test fails, the tranche is not parked. **A failed Park Phase is a HARD_BLOCK gate violation** for any non-bootstrap intent submitted after the tranche's last `complete_task` event — i.e., the next tranche cannot proceed.

---

## **Required Project Documentation & Persistence**

The builder shall maintain a minimal but sufficient project documentation set inside `.scaffold/`.

### **1. The Sidecar Database (Authoritative builder memory)**

- **Location:** `data/sidecar.db`
- **Role:** The canonical ledger of all work, decisions, system history, events, graph relations, and projections. This is the single SQLite spine.
- **Backlog:** Unresolved issues and deferred tasks live as journal entries inside the DB with `status='open'` or `kind='todo'`.

### **2. Top-level Documents (at `.scaffold/`)**

- `README.md` — what the sidecar is, how it is dropped into a project, and the invariant that the host project does not import it.
- `ARCHITECTURE.md` — design truth: spine rule, MVP-5 order, layer model, envelope and event shapes.
- `SOURCE_PROVENANCE.md` — provenance of any logic re-homed from `.parts/` or other external sources, including this contract revision.
- `TOOLS.md` — quick-reference index of tools registered under `src/tools/`.

### **3. Operational Folders (at `.scaffold/`)**

| Folder | Purpose |
|---|---|
| `config/` | Sidecar-local configuration (JSON, TOML). No secrets. |
| `contracts/` | Binding contracts including this file. |
| `data/` | The SQLite spine and any directly-managed runtime data. |
| `logs/` | Runtime logs (rotated). The `print()` prohibition (§2.1) routes here. |
| `cache/` | Derived/regenerable caches. Safe to delete. |
| `exports/` | Markdown / JSON exports produced under `Export` authority. |
| `workspaces/` | Sandbox workspaces for `Sandbox Execute` operations. Isolated; never the host project tree. |
| `snapshots/` | Point-in-time snapshots (Merkle-rooted) of the spine. |

---

## **Standard Tool Contract**

Every tool residing in `src/tools/` must follow the metadata and entrypoint pattern:

### **Required Exports**

Each Python tool must export a `FILE_METADATA` dictionary and a `run(arguments)` function:

- `tool_name`: Unique identifier.
- `category`: e.g., bootstrap, write, query, export, scaffold, scan, contract, projection, snapshot.
- `input_schema`: JSON Schema for arguments.
- `mcp_name`: MCP tool registration name.

### **Required CLI Support**

Tools must support metadata inspection and JSON input:

- `python <tool>.py metadata`
- `python <tool>.py run --input-json '{"key": "value"}'`
- `python <tool>.py run --input-file path/to/input.json`

### **Result Envelope**

All tools return a stable JSON shape:

```json
{ "status": "ok|error", "tool": "<tool_name>", "input": { ... }, "result": { ... } }
```

---

## **Envelope Schema (Frozen Minimum)**

Every envelope flowing through the spine carries at minimum these eighteen fields:

`envelope_version`, `object_id`, `object_type`, `project_id`, `sidecar_id`, `actor_id`, `created_at`, `operation_intent`, `status`, `source_refs`, `relation_refs`, `contract_refs`, `evidence_refs`, `event_id`, `correlation_id`, `causation_id`, `surface_manifest`, `payload_ref`.

Heavy content is stored separately (`blob_store` or filesystem) and referenced via `payload_ref` and `evidence_refs`. Envelopes do not embed large bodies.

---

## **Journal Data Model (Standard Schema)**

The sidecar journal preserves these concepts in the `journal_entries` table. Any modification to the journal must respect this schema:

| Field | Purpose |
| :---- | :---- |
| `entry_uid` | Unique identifier (e.g., `journal_<hash>`) |
| `kind` | note, decision, todo, issue, log, contract, specification, work_log, devlog, design_record |
| `source` | user, agent, system, builder |
| `body` | Full body text (always readable) |
| `body_hash` | SHA-256 hash pointing to `blob_store` |
| `tags_json` | JSON array of tags |
| `metadata_json` | JSON object for tool-specific or context data |

---

## **1. Mission Boundary Rules**

The builder shall keep the sidecar self-contained inside `.scaffold/`.

### **1.1 Sandbox Root and read-only references**

The builder may read from `.parts/` (precursor reference materials) for orientation but shall not write into `.parts/`. Outputs go into the sidecar root (`.scaffold/`) under the appropriate top-level folder.

### **1.2 External boundary restrictions**

No runtime imports from outside `.scaffold/`. The sidecar package ships intact — there is no "re-homing into the host project" step at deployment because `.scaffold/` *is* the deliverable that gets dropped in. The host project's application code must never import from `.scaffold/`.

### **1.3 Hardware and inference budget**

- Preferred local helper model threshold: **8B – 14B parameters**.
- No workflows exceeding the user's practical compute capabilities.

### **1.4 Sidecar storage discipline** *(new in this revision)*

All sidecar runtime data lives under `.scaffold/<folder>/` per §"Operational Folders." The sidecar never writes to the host project tree unless the action carries `Apply` authority granted by an explicit human approval recorded in the event log.

---

## **2. Code Quality & Reporting**

### **2.1 Logging instead of print rule**

Use proper logging infrastructure (`src/lib/logging_setup.py`). `print()` is prohibited in the application core. Logs are written under `logs/`.

### **2.2 Graceful failure rule**

Failures shall be handled via controlled boundaries, meaningful logs, and safe shutdown paths.

### **2.3 Journal reporting**

The sidecar journal is the append-only ledger. Entries must be timestamped and include a summary of changed files and implementation notes.

---

## **3. Decision Priority and Pushback Rule**

The builder's priority is correctness and maintainability. If a request is structurally unsound or violates the technical pledges (e.g., bypassing CAS integrity, the Single Store rule, or Spine Discipline), the builder shall push back, warn of consequences, and propose alternatives.

---

## **4. Prohibited Behaviors**

- Writing outside `.scaffold/` without `Apply` or `Export` authority.
- Runtime imports from `.parts/` or any path outside `.scaffold/`.
- Bypassing the `journal_manager` / `sqlite_store` for database access.
- Modifying the SQLite schema in a destructive way without a migration plan.
- Reckless or undocumented pruning of project files.
- Sideways manager-to-manager calls that bypass the router.
- Embedding large payloads in envelopes instead of referencing them.
- Creating relations of type `related_to` or any type not in the closed set in §"Relation Types".
