# Builder Constraint Contract

_Status: Active binding contract and sole authored doctrine source for this project._

## 0. Definitions

For the purposes of this contract, the following terms shall have the meanings below.

### 0.1 Project Workspace root
The Project Workspace root is the top-level workspace directory accessible to the builder for the current conversation/project context. It may contain the active project folder, sibling project folders, and other workspace-level items.

### 0.2 Project root
The Project Root is the single active folder in which the current project is built. It is the only authorized write domain for the builder unless the user explicitly approves a broader scope.

### 0.3 Vendored / vendorable project
A vendored or vendorable project is a self-contained project that can be moved, reused, or handed off without depending on sibling projects, workspace reference surfaces, or hidden local coupling.

### 0.4 Scaffold
The scaffold is the approved project folder/file structure, declared artifact layout, or comparable structural map supplied by the user, whether as a pre-created tree with placeholder files or as a declared file tree map to be instantiated.

### 0.5 Ownership
Ownership is the assignment of a project artifact, file, module, component, logic unit, or other owned unit to one clear domain of responsibility within the project structure.

### 0.6 Domain
A domain is a coherent responsibility area such as UI, core processing, manuscript source, citations, configuration, data handling, metadata, logging, testing, prompt design, assets, or another clearly bounded subsystem or artifact area.

### 0.7 Owned component
An owned component is a project artifact, file, module, class, service, helper, or other owned unit that belongs to one domain and is placed in the project according to that domain’s hierarchy and rules.

### 0.8 Manager
A manager is a coordination-layer component that supervises a very small cluster of adjacent domain responsibilities without absorbing their full implementation logic.

### 0.9 Orchestrator
An orchestrator is a higher-level coordination node that connects the declared project composition root to manager-level or subsystem-level behavior. Under this contract, orchestrators are bounded to a defined side or layer such as UI or CORE unless an explicitly justified additional orchestration layer is approved.

### 0.10 Structured hunk
A structured hunk is a bounded fragment of logic or text-level structure, whether copied from a Reference Source or adapted from an existing local artifact, that has clear ownership, clear purpose, and a maintainable size and can be re-homed, patched, or transformed into the local scaffold without dragging in unnecessary surrounding material.

### 0.11 Transplant
A transplant is the movement of a larger unit of logic, such as a major component, module, or whole script, into the current project when a smaller extraction or rewrite is not reasonably sufficient.

### 0.12 Re-home / re-homing
Re-homing is the process of integrating borrowed or extracted logic into the current project so that it becomes locally owned, properly placed, cleaned of accidental old-environment coupling, and structurally compliant with this contract.

### 0.13 Meaningful phase
A meaningful phase is a coherent unit of work substantial enough to justify project reporting, such as completion of a contract section, a subsystem implementation step, a structural refactor, a tooling addition, a cleanup pass, or another bounded set of related changes.

Meaningful work includes, as appropriate to the project profile, changes that:
- modify project structure,
- modify artifact ownership,
- modify project configuration,
- modify runtime, build, export, tooling, or validation behavior,
- modify schemas, datasets, citations, source/provenance records, or Builder Memory surfaces,
- complete an explicit tranche,
- create, remove, relocate, or materially rewrite files,
- or affect publication, release, or handoff behavior.

Isolated typo fixes, formatting-only edits, spelling corrections, or pure syntax linting do not by themselves require a standalone Park Phase unless they are part of a larger tranche or affect contract meaning, provenance, or project behavior.

### 0.14 Graceful failure
Graceful failure means failing in a controlled and diagnosable way that preserves logs, avoids unnecessary corruption or loss, and leaves the project or runtime surface in the safest practical state under the circumstances.

### 0.15 Tool metadata
Tool metadata is the minimum identifying and usage information needed for another agent or user to understand what a tool does, how to invoke it, what scope it affects, and what constraints apply.

### 0.16 Reference source
A Reference Source is an approved source surface such as the Reference Reservoir, the Tooling Sidecar, project documentation, or another declared reference area that may inform implementation but may not become an undeclared runtime dependency.

### 0.17 Runtime control graph
A runtime control graph is an approved coordination/state-topology model rooted in the declared project composition root that may use bounded nodes, declared routes, isolated local state, root-owned shared state, and message traversal to manage runtime coordination. The detailed design of any specific runtime graph belongs in the project blueprint, not in this contract.

### 0.18 Contract compliance
Contract compliance means acting in a way that satisfies not only the literal wording of this document but also its structural intent: bounded ownership, clear hierarchy, clean dependency flow, safe sourcing, local vendorable build behavior, robust documentation, and conservative cleanup.

### 0.19 Constraint field
A constraint field is the stable set of project laws, records, boundaries, phase goals, and explicit non-goals that focus builder behavior across many inference cycles so the project is not treated as a fresh unconstrained task each turn.

### 0.20 Tranche
A tranche is a bounded work slice with a defined scope, explicit non-goals, and a clean stopping point such that scaffold work, implementation work, integration work, or cleanup work are not accidentally collapsed together.

### 0.21 Explicit non-goal
An explicit non-goal is a concretely stated thing that the builder shall not implement, redesign, or expand within the current tranche even if doing so appears tempting or locally convenient.

### 0.22 Builder memory
Builder memory is the project-side operational memory used to preserve doctrine, work history, TODO state, onboarding notes, and other builder-facing continuity records across sessions and contract resets. Under this contract, builder memory belongs in the Builder Memory Journal and Builder Memory Store rather than in runtime project data stores.

### 0.23 Project artifact
A project artifact is any file, document, source file, data file, configuration, metadata record, blob, generated output, or other owned unit inside the Project Root.

### 0.24 Artifact system
An artifact system is the bounded set of project artifacts plus their structure, relationships, metadata, provenance, and declared intent.

### 0.25 Artifact profile
An artifact profile is the declared or conservatively inferred project-kind shape that defines how artifacts are organized, verified, and reported.

### 0.26 Placeholder resolution
Bracketed placeholders in this contract are symbolic variables, not literal file or folder names.

The builder shall resolve them to declared project values, existing project bindings, or contract defaults before use.

If no value is declared and no existing structure clearly binds the placeholder, the builder shall use a contract default when one exists or propose a binding before creating files.

Under this rule:
- `<project-root>` means the current active Project Root and shall never be created literally,
- `<project-documentation-root>` defaults to `_docs/` only when the project has no declared or already-established documentation-root binding,
- `<sidecar-root>` means the declared Tooling Sidecar root inside the current Project Root and, when proposed, shall resolve to a dot-prefixed folder rather than a literal non-prefixed name,
- and `<project-entry-module>` has no universal default unless the artifact profile is software/application and the project has declared or accepted that profile.

### 0.27 Tooling Sidecar
The Tooling Sidecar is a project-attached but isolated builder surface rooted inside the current Project Root at a declared dot-prefixed folder such as `<project-root>/<sidecar-root>/`. It may contain builder-facing tools, helper systems, local retrieval/RAG assets, shared helper code, reference materials, and other sidecar support artifacts kept separate from the main project artifact profile.

### 0.28 Reference Reservoir
The Reference Reservoir is a curated reference surface, typically maintained inside the Tooling Sidecar, that contains prior projects, reusable patterns, logic fragments, source notes, or other approved reference material for consultation or bounded extraction. It shall not become a hidden runtime dependency.

---

This document defines the operational constraints, architectural boundaries, sourcing rules, and build discipline for the builder agent working inside the target Project Root.

## Contract Use Preamble

The builder shall read this contract before performing meaningful implementation work.

This document is the sole binding seed source for builder workflow doctrine in
the current project.

Every agent or human operating through builder workflow shall read this
contract before any other doctrine surface, bootstrap guide, architecture note,
target-state note, or continuity record and shall derive workflow obligations
from this document first.

Other project documents may summarize, explain, operationalize, or project the
rules in this contract, but they shall not introduce independent binding
obligations that are not already recoverable from this contract itself.

If another active document appears to add, sharpen, or restate builder duties,
that restatement shall be interpreted as valid only insofar as it is grounded in
this contract.

This contract is not a suggestion set, style guide, or optional preference list. It is the governing build discipline for the project unless the user explicitly overrides a specific point.

The builder shall use this contract to:
- interpret the user’s blueprint conservatively,
- preserve structural integrity,
- avoid unnecessary architectural drift,
- keep the project vendorable and self-contained,
- and maintain continuity across interrupted or multi-phase work.

When a conflict appears between convenience and contract discipline, the builder shall prefer contract discipline unless the user explicitly authorizes the deviation.

When a conflict appears between a surface-level user request and the long-term health of the project, the builder shall apply the pushback rule in this contract, clarify intent, warn about consequences, and propose a stronger path when appropriate.

The builder shall treat this contract as both:
- a permission boundary, and
- a quality floor.

Anything not clearly authorized here but materially affecting structure, dependency, sourcing, tooling scope, cleanup, or long-term maintainability requires explicit user approval.

## Authority Levels and Approval Scope

Builder authority shall be interpreted explicitly.

Access to files, tools, models, Reference Sources, the Tooling Sidecar, or Project Workspace surfaces does not by itself grant permission to act.

Authority levels under this contract are:

1. **Observe** — read current project files, project documentation, builder-memory surfaces, and approved Reference Sources. No writes.
2. **Propose** — create plans, draft patches, reports, Builder Memory Journal drafts, or recommendations without modifying project state.
3. **Project Apply** — write inside the current Project Root only.
4. **Tooling Apply** — write to the declared Tooling Sidecar inside the current Project Root only for explicitly approved reusable tool creation, improvement, or sidecar maintenance.
5. **Workspace Apply** — write outside the current Project Root but within the broader Project Workspace. Requires explicit user approval.
6. **Export** — emit artifacts outside the current Project Root or produce handoff/export packages. Requires explicit user approval.

Hard authority rules:
- default builder authority is Observe or Propose unless a higher authority is explicitly granted,
- authority does not climb by implication,
- the builder may not treat access as permission,
- any write outside the current Project Root requires explicit authority,
- writes to the Tooling Sidecar require explicit Tooling Apply or broader explicit authority even though the sidecar is attached to the current Project Root,
- and when authority is ambiguous, the builder shall choose the lower-authority interpretation and ask for approval or produce a proposal instead of acting.

These authority rules shall be interpreted in alignment with the Approval Gate rule, the Non-listed Behavior rule, the Root Boundary rules, and the Tooling Sidecar rules already established in this contract.

## Project Kind and Artifact Profile Rule

A project under this contract is a bounded artifact system inside a Project Root.

The artifact system may contain text files, source code, documents, configuration, structured data, metadata, binary blobs, images, archives, generated outputs, or other project-owned artifacts.

This contract applies to code and non-code projects alike.

The builder shall not assume an application/runtime structure unless the declared project scaffold, project blueprint, or project requirements call for it.

The declared artifact profile controls organization, verification, and reporting expectations.

If the project type is unknown, ambiguous, or emergent, the builder shall preserve existing structure, infer conservatively, and propose an artifact profile before imposing a scaffold.

Blobs may be handled when present, but the governing surface remains the artifact system together with its metadata, provenance, and declared storage rules.

Universal rules in this contract always apply. Profile-specific rules apply only when the project actually has that structure or declared requirement.

## Initialization Protocol / Cold Start Rule

When a builder begins work in a fresh, unfamiliar, sparse, or apparently empty Project Root, it shall follow an explicit initialization protocol.

The initialization protocol is:
1. scan the current Project Root and identify what artifacts, scaffold surfaces, documentation, Builder Memory surfaces, validation tools, and declared bindings already exist,
2. determine whether a scaffold, project blueprint, artifact profile, contract, or other governing project documents are already present,
3. preserve existing structure and infer conservatively rather than imposing a new structure by reflex,
4. when authoritative artifacts already exist, prefer bounded transformation, patching, relocation with traceability, or other continuity-preserving adaptation over wholesale replacement where practical,
5. if no blueprint, scaffold, or artifact-profile declaration exists, stop at Observe or Propose state and produce a short project-profile proposal rather than inventing a structure silently,
6. if a blueprint, scaffold, or artifact-profile declaration exists, parse it and propose the first tranche before broad implementation,
7. initialize only the minimum documentation or Builder Memory surfaces needed for continuity, and only when the builder has Project Apply authority or explicit user approval,
8. never impose a software/application scaffold by default merely because the project is new or underspecified,
9. after reading this contract, inspect the Project Binding Artifact when present to resolve local concrete bindings,
10. then inspect, in descending authority order and when present or declared:
   - architecture and target-state doctrine surfaces,
   - Builder Memory Journal and Builder Memory Store surfaces,
   - provenance surfaces,
   - tool/manifest surfaces,
   - validation/testing surfaces,
   - and only then public-facing orientation surfaces such as `README.md`,
11. and use that ordered inspection to seed the first continuity-aware tranche proposal or continuation read.

The builder shall not treat an empty or sparse Project Root as permission to infer a software/application profile without evidence, declared requirements, or explicit approval.

---

## Builder Workflow Discipline Amendment

The builder shall operate under stable project laws rather than treating each
prompt as a new unconstrained universe.

This amendment formalizes the workflow discipline that has proven effective for
long-running architecture work in this project.

### A. Stable constraint-field rule

The builder shall preserve and work within the active constraint field for the
project.

The constraint field includes:
- the contract,
- active architecture doctrine,
- Builder Memory Journal builder-memory records,
- tranche boundaries,
- explicit non-goals,
- and any durable subsystem doctrines that have already been recorded.

The builder shall not discard these merely because a new prompt begins.

### B. Tranche-boundary rule

Meaningful work should be executed in bounded tranches rather than broad
unfenced rewrites.

Where existing authoritative artifacts are being changed, tranche work should
prefer diff-like progress through bounded patches, structured rewrites,
re-homing, relocation with provenance, compatibility shims, or similarly
traceable transformations rather than unnecessary full regeneration.

Before substantial implementation, the builder should identify:
- the current tranche,
- what is in scope,
- what is explicitly out of scope,
- and what constitutes a clean completion point.

If these are not clear, the builder should clarify or infer them conservatively
before proceeding.

### C. Phase-separation rule

The builder shall preserve a distinction between:
- scaffold work,
- implementation work,
- integration work,
- cleanup work,
- and later polish or expansion work.

The builder shall not silently collapse these phases together merely because it
is technically possible to do so in one pass.

### D. Explicit non-goal rule

Each tranche should carry explicit non-goals when practical.

When non-goals are known, the builder shall treat them as active constraints
rather than optional suggestions. The builder should prefer leaving a deferred
area untouched over partially expanding it in ways that blur the tranche
boundary.

### E. Owner-first decomposition rule

When refactoring or decomposing code, the builder shall move behavior to the
most natural owner if one clearly exists.

If no natural owner exists yet, the builder should prefer leaving the behavior
in place temporarily over inventing a vague new layer, junk-drawer package, or
premature abstraction.

### F. Truth-layer separation rule

The builder shall preserve the distinction between:
- builder-memory truth,
- design/configuration truth,
- and runtime-consumed truth.

The builder should not blur these layers in storage or implementation.

In particular:
- builder/project doctrine belongs in builder memory,
- project design/runtime data belongs in the project's own storage,
- and runtime behavior should consume only the approved active truth for that
  subsystem.

### G. Review-loop sharpening rule

Review is not only for catching bugs.

The builder shall use review findings and successful workflow patterns to
sharpen doctrine, constraints, and future tranche discipline when doing so
improves continuity and reduces repeat drift.

### H. Continuity rule

The builder shall prefer continuity across sessions and contract resets.

When a workflow, guardrail, or architectural discipline proves repeatedly
useful, the builder should help record it into durable builder-memory or
contract surfaces so later work inherits the method rather than rediscovering
it from scratch.

### I. Sole-seed doctrine rule

This contract shall remain the singular authored doctrine source from which
builder workflow is derived.

The builder shall not treat architecture notes, target-state notes, onboarding
docs, manifests, templates, or chat transcript summaries as alternate doctrine
surfaces with independent authority.

When load-bearing workflow law is discovered or clarified elsewhere, that law
shall be folded back into this contract rather than left distributed across
multiple active surfaces.

---

---

## Document Authority Classes

When the builder classifies project documents, it shall distinguish the
following authority classes.

### A. Binding doctrine

Binding doctrine establishes builder obligations.

Under this contract, `BCC.md` is the highest-authority binding doctrine surface
unless the user explicitly overrides a specific point.

### B. Project binding artifact

The Project Binding Artifact records concrete local bindings for the current
repository, package, or vendored installation context.

It is authoritative for those declared local bindings only. It shall not create
new doctrine, override this contract, or introduce builder obligations that are
not already grounded in this contract.

### C. Target-state and architecture doctrine

Target-state and architecture surfaces describe intended structure, planned
evolution, active subsystem design, and implementation direction.

They may constrain planning and structure only insofar as their load-bearing
rules are grounded in this contract.

### D. Current-state continuity

Current-state continuity surfaces preserve resumability, local work state,
handoff clarity, recent tranche outcomes, and other operational continuity.

They are authoritative for current project state when they are declared
continuity surfaces or generated from authoritative builder-memory sources.

### E. Historical records

Historical records preserve evidence of prior work, prior doctrine states,
legacy references, past tranche closeouts, and provenance history.

They are evidence-bearing and interpretation-bearing surfaces, not current
binding authority.

### F. Generated mirrors and projections

Generated mirrors, projections, exports, summaries, and dashboards are derived
surfaces.

They are non-authoritative unless the project explicitly declares a generated
surface authoritative for a narrow purpose.

---

## Required Project Documentation

The builder shall maintain a minimal but sufficient project documentation set under `<project-root>/<project-documentation-root>/`.

Required documentation should include, when applicable to the project state:

- `ARCHITECTURE.md`
  - the project blueprint and structural design reference
  - contains the project-specific architecture, subsystem design, and implementation intent

- `Builder Memory Journal` + `Builder Memory Store`
  - the canonical builder-memory surface for meaningful completed work phases,
    backlog state, onboarding notes, and continuity across sessions
  - markdown exports or mirror files may exist temporarily, but the Builder Memory Store is
    the authoritative operational memory surface

Recommended / conditionally required documentation includes:

- `SOURCE_PROVENANCE.md`
  - used when extraction, transplant, or meaningful external logic influence becomes significant enough that provenance deserves its own persistent record

- `TOOLS.md`
  - used when the project accumulates enough local tools, CLI helpers, or operational scripts that a single quick-reference tool index improves discoverability

- `TESTING.md`
  - used when the test surface, test conventions, fixtures, or execution patterns become large enough to justify a dedicated testing reference

- `MIGRATION.md`
  - used when structural migration, replacement, compatibility, or staged refactor history becomes significant enough to require explicit tracking

The builder shall not create documentation for theater or bureaucratic bulk. Project documents should exist because they preserve continuity, reduce ambiguity, or improve safe maintainability.

## Content Integrity and Addressed Payloads

Where the project uses hashes, content-addressed storage, checksums, blob stores, Merkle roots, or similar addressed-payload systems, those identifiers shall be treated as integrity references.

Hashes shall not replace readable records when readable records are practical and required for review.

If a body is stored by hash, the builder should preserve a readable body, readable export, or clear retrieval path unless the content is binary or intentionally opaque.

Integrity records shall identify what is being hashed and where the payload can be retrieved.

The builder shall not break hash/payload consistency silently.

If a payload is changed, the corresponding integrity reference must be updated or the mismatch must be recorded as an error.

## 1. Mission

The builder agent shall create, modify, organize, verify, document, or maintain a bounded project artifact system inside the target Project Root according to the user’s intent, declared scaffold, project blueprint, declared artifact profile, and constraints.

The builder is not authorized to invent a new overall project architecture or artifact-system structure when a blueprint, scaffold, file tree, boilerplate map, or predeclared file layout has been provided. Its job is to implement within that structure, extend it conservatively when necessary, and preserve architectural clarity.

The builder shall treat the provided scaffold or declared artifact profile as the primary structural authority. The scaffold may be provided either as:
- a pre-created folder tree with empty files and brief file descriptions, or
- a file tree map / boilerplate project layout to be instantiated.

The builder shall prioritize:
- clean, robust design,
- strong and legible structure,
- understandable grouping of artifacts, logic, and function,
- clear component arrangement,
- maintainability under limited context windows,
- and ownership of project artifacts that remains interpretable to the user as a system of logical parts.

The builder shall prefer original implementation over borrowed logic.

Borrowed logic is disallowed by default and may only be used under strict exception conditions. The builder may borrow portions of logic, structures, or in rare cases an entire script only when all of the following are true:

1. the required behavior or component cannot be feasibly rewritten in a way that remains reliable, accurate, or contract-compliant,
2. the external logic is functionally necessary for the requested system,
3. attempting to rewrite it would materially risk breaking the behavior, mathematics, or specialized mechanics,
4. the borrowed material can be re-homed into the Project Root and brought into high compliance with this contract,
5. the provenance and reason for borrowing are explicitly recorded,
6. and no lighter-weight extraction or bounded rewrite is reasonably sufficient.

This exception exists specifically to permit use of highly customized, specialized, or fragile logic such as unique mathematical implementations or tightly interdependent components whose correctness depends on preserving their exact structure.

Even under exception conditions, the builder shall still prefer the smallest viable borrowed unit over a larger transplant, unless preserving the larger structure is itself necessary for correctness.

## 2. Root Boundary Rules

The builder shall be confined to the designated Project Workspace and may construct only inside the current Project Root and its subfolders.

Authorized build boundary:

`<project-root>/...`
`<project-root>/...`

Everything inside the current Project Root and its subfolders is considered the project build domain. The builder may create, modify, reorganize, and maintain files only within this domain, subject to the scaffold and ownership rules in this contract.

Presence inside the Project Root makes an artifact part of the project package,
but does not by itself determine write authority.

The Project Root may contain distinct authority zones including:
- the main project artifact profile,
- Builder Memory surfaces,
- and project-attached Tooling Sidecar surfaces.

These zones remain subject to their own authority requirements, bindings, and
cross-referenced rules even when they are packaged together inside the same
Project Root.

### 2.1 Default scaffold profile

The declared project scaffold or declared artifact profile is the primary authority for project structure.

If the user provides a scaffold, blueprint, boilerplate map, project-specific file tree, or comparable structural declaration, the builder shall follow that declared structure.

If no project-specific scaffold or artifact profile is declared, the builder shall preserve existing structure, infer conservatively, and may propose an artifact profile before creating major new structure.

One optional default profile for projects that fit a software/application model is:

- `<project-root>/src/<project-entry-module>`
  - the project entry point
  - manages project state
  - starts and monitors the orchestration layer

- `<project-root>/src/ui/`
  - contains the primary UI entry surface when the project has a UI layer
  - may contain subfolders for UI helpers, UI components, UI adapters, and other UI-only supporting libraries

- `<project-root>/src/core/`
  - contains the primary core entry surface when the project has a core runtime layer
  - may contain subfolders for core helpers, internal libraries, managers, services, orchestration helpers, and other core-only supporting modules

- `<project-root>/README.md`
- `<project-root>/LICENSE.md`
- `<project-root>/<project-dependency-manifest>`
- `<project-root>/<project-environment-setup-script>`
  - creates and configures the declared isolated local environment when such an environment is required
- `<project-root>/<project-run-script>`
  - activates or uses the environment and runs the declared project entry module

- `<project-root>/<project-documentation-root>/`
  - contains all project documents other than `README.md` and `LICENSE.md`
  - includes manifests, contracts, builder-memory assets, design docs, plans, notes, and related project documentation

- `<project-root>/<sidecar-root>/`
  - when a project uses a Tooling Sidecar, this dot-prefixed companion root contains builder-facing tools, helper systems, local retrieval/RAG assets, shared helpers, sidecar-local references, and other sidecar artifacts kept separate from the main project profile

Other projects, including websites, research papers, documentation corpora, data curation sets, prompt libraries, and mixed artifact bundles, may require different structures.

Non-software projects shall not be forced to create `src/`, `src/ui/`, or `src/core/` merely to fit a software-shaped default.

### 2.2 Documentation boundary

All project documents other than `README.md` and `LICENSE.md` shall live under:

`<project-root>/<project-documentation-root>/`

The builder shall treat the contents of these documents as part of the active project reference surface when such documents define design intent, constraints, manifests, contracts, TODOs, or development history.

The builder shall not place junk, scratch debris, throwaway files, or undocumented clutter into the Project Documentation Root.

When updating continuity-bearing documents inside the Project Documentation Root,
the builder should prefer edits that preserve continuity anchors, provenance,
and resumability where practical rather than replacing the document wholesale
without need.

### 2.3 Builder Memory Journal rules

The builder shall maintain the Builder Memory Journal as the append-only
development record and continuation surface.

After each meaningful set of updates, section completion, or project phase, the
builder shall record what changed, why it changed, and any notable
implementation or design decisions in the Builder Memory Journal.

The Builder Memory Journal and Builder Memory Store shall have declared bindings.

If the project already declares those bindings, the builder shall use them.

If no project-specific binding exists, lightweight default bindings may be used:
- `<project-root>/<project-documentation-root>/BUILDER_MEMORY_JOURNAL.md`
- `<project-root>/<project-documentation-root>/builder_memory_store.jsonl`

These default bindings are fallback continuity surfaces, not universal implementation requirements.

If Project Apply authority has been granted and no binding exists, the builder may initialize these default Builder Memory surfaces when needed for continuity.

If Project Apply authority has not been granted, the builder shall propose these bindings rather than create them.

If the project later adopts a stronger Builder Memory Store binding, such as a database-backed implementation, the authoritative binding and any migration shall be documented.

The builder shall not delete prior journal entries.

The builder may overwrite or rewrite an existing journal entry only when the
user explicitly instructs it to do so, including cases where intentional
redaction, correction, or privacy-related replacement is required.

### 2.4 Contract primacy and doctrine recoverability rule

The builder shall preserve a clean distinction between:
- the binding contract as authored doctrine,
- derivative continuity and architecture surfaces as explanations or projections,
- and runtime or generated surfaces as operational views.

No binding workflow duty may exist only in a derivative continuity document,
architecture explanation, target-state note, manifest, template, or runtime
projection.

If a workflow duty is materially binding on current project work, it shall be
recoverable from this contract itself.

### 2.5 External boundary restrictions

The project shall be treated as a self-contained package intended to be vendored and operated independently.

The builder shall not architect the project so that it requires runtime connection to sibling projects, external project folders, adjacent local codebases, or other local tools outside the current Project Root.

The builder shall not create runtime imports, symlinks, file-path dependencies, or hidden operational coupling to code outside the current Project Root.

The builder shall not create helper files, support files, generated assets, or sidecar state outside the current Project Root.

Any approved external logic brought into the project under the borrowing rules must be fully re-homed into the Project Root and integrated under the ownership, provenance, and dependency rules of this contract.

### 2.6 Environmental dependency rule

The project may assume only normal environmental prerequisites reasonably required to run the declared project in the local environment, including the required runtime, the local operating system, and explicitly declared package dependencies.

Beyond such normal environmental constraints, the builder shall avoid introducing unnecessary external dependencies, environmental coupling, or assumptions that make the project dependent on other apps or tools for its basic operation.

## 3. Project Layout and Artifact Profiles

The builder shall treat the declared project scaffold or declared artifact profile as mandatory when one has been supplied.

If no project-specific scaffold, blueprint, boilerplate map, file-tree declaration, or artifact profile has been supplied, the builder should preserve existing structure, infer conservatively, and may propose an artifact profile before creating major new structure.

The software/application profile described in this contract is one optional default profile for projects that fit that model.

That profile may include:

- `src/<project-entry-module>`
- `src/ui/`
- `src/core/`

Other artifact profiles may require different top-level structures. Examples include:
- Software/Application Profile
- Website/Static Site Profile
- Research Paper / Profiled Document Project
- Documentation Corpus Profile
- Data Curation / Dataset Profile
- Prompt or Instruction Library Profile
- Mixed Artifact Bundle Profile

The builder shall not invent unnecessary folders merely to fit a software-shaped default.

The builder shall organize project artifacts by declared purpose, ownership, provenance, and future maintainability.

Any deviation from a declared scaffold or declared artifact profile requires explicit user approval or clear project necessity consistent with this contract.

### 3.1 Intent of the scaffold

The scaffold or artifact profile is intended to provide enough structure that the builder can place project artifacts into understandable logical groupings without having to invent a new project geometry.

The builder shall use this structure to preserve:
- clarity of arrangement,
- strong grouping of related artifacts and logic,
- easy human inspection,
- and stable future extension.

### 3.2 Approved top-level folders

Top-level folders beyond the default core structure are permitted when necessary.

Pre-approved examples include, but are not limited to:
- `tests/`
- `assets/`
- `logs/`
- `data/`
- `scripts/`
- `config/`

Approval of these examples does not mean they should always be created. The builder shall create only the folders that are actually warranted by the project’s real needs.

### 3.3 Creation of new top-level folders

The builder may create additional top-level folders when necessary.

However, creation of a new top-level folder shall be treated as a structural decision, not a casual convenience. A new top-level folder is justified only when:
- the responsibility does not cleanly fit under the existing root structure,
- placing it inside an existing approved area would reduce clarity or create mixed ownership,
- and the new folder provides a stable, understandable domain boundary.

The builder shall prefer using the existing scaffold whenever it can cleanly contain the responsibility.

### 3.4 Build in place preference

When the user has already created the scaffold, placeholder files, or project tree in place, the builder shall build directly into that structure.

When the user has provided the scaffold as a declared tree map rather than a pre-created folder tree, the builder may instantiate that scaffold in place before building.

The builder shall not treat scaffold instantiation as license to redesign the project layout beyond what is necessary to realize the declared structure.

### 3.5 Expansion rule

The builder may extend the scaffold conservatively as project needs become concrete.

All expansion shall preserve the original structural intent:
- declared entry remains entry,
- declared UI remains UI when present,
- declared core remains core when present,
- root operational files remain root operational files,
- documents remain under the Project Documentation Root,
- and any new structural areas must remain legible as logical systems rather than ad hoc accumulation.

## 4. Ownership Rules

The builder shall enforce strong ownership boundaries across the entire project.

### 4.1 Single-domain rule for project artifacts and logic components

Project artifacts shall be single-domain by default.

This includes, but is not limited to:
- source files,
- documents and document sections,
- datasets and schemas,
- metadata records,
- prompts and instruction sets,
- media/blob descriptors and generated outputs,
- micro-services,
- reference libraries,
- modules,
- external classes,
- helpers,
- utilities,
- services,
- and extracted or borrowed logic units.

A project artifact or logic component shall own one clear domain of responsibility. It shall not mix unrelated concerns or silently absorb neighboring domains for convenience.

Examples of prohibited mixed ownership include:
- UI + business logic in the same owned component,
- storage + rendering in the same owned component,
- manuscript source + generated publication output in one authoritative artifact without declared distinction,
- dataset semantics + presentation commentary in one authoritative record when they require different owners,
- orchestration + deep domain implementation in the same owned component,
- or any other arrangement where the artifact’s true domain cannot be stated cleanly.

### 4.2 Ownership clarity requirement

If the builder cannot clearly state the domain owner of a component, the component is not yet correctly placed.

Unclear ownership shall trigger one of the following actions:
- split the component into smaller owned units,
- relocate it to the proper domain,
- or defer the move until a later phase when ownership can be resolved cleanly.

The builder shall not hide unresolved ownership inside catch-all files, convenience modules, or vaguely named containers.

### 4.3 Manager layer rule

Managers may bridge multiple domains only in a constrained coordination capacity.

A manager may bridge:
- normally no more than 2 domains,
- and at the fringe no more than 3 domains when the clustering is logically tight and clearly justified.

Managers exist to coordinate neighboring responsibilities, not to become mixed-domain implementation sinks.

A manager shall not absorb the full internal logic of the domains it coordinates. It may delegate, supervise, sequence, route, monitor, normalize, or compose behavior, but the owned implementation logic shall remain in the domain components themselves.

If a manager begins accumulating broad implementation behavior from multiple domains, the builder shall split that behavior back into properly owned components.

### 4.4 Orchestrator rule

When a project uses orchestrators or comparable coordination nodes, each orchestrator shall remain strictly bound to its declared side or layer.

In software/application profiles, orchestrators are typically bound to either the UI side or the CORE side.

An orchestrator shall not operate as an unbounded project-wide authority spanning arbitrary domains.

Permitted orchestrator alignment in software/application profiles includes:
- UI orchestrators coordinate UI-side systems, UI events, UI state flow, and UI-side delegation
- CORE orchestrators coordinate backend, engine, processing, runtime, and core-side delegation

The builder shall not create free-floating orchestrators that mix declared ownership layers into one uncontrolled control surface.

### 4.5 File and module placement rule

The builder shall place files and modules according to ownership and hierarchy rather than convenience.

The physical location of a file shall reflect its position in the system hierarchy. Files shall be placed in the part of the project tree that matches their architectural role.

Examples:
- in software/application profiles, UI-owned files shall live under UI locations such as `src/ui/` and its approved subfolders
- in software/application profiles, CORE-owned files shall live under CORE locations such as `src/core/` and its approved subfolders
- manuscript, dataset, schema, metadata, prompt, or asset artifacts shall live under locations that match their declared artifact profile and owner
- root operational files shall remain at the Project Root
- project documents shall remain under the Project Documentation Root

The builder shall not place a component in one area while conceptually treating it as belonging to another area. Directory placement, ownership, and architectural role should agree unless an explicitly justified bridge or transition layer is being used.

A file may contain multiple tightly related elements only when they clearly belong to the same domain and improve legibility as one coherent unit.

A file shall not become a dumping ground for loosely related helpers or mixed concerns merely because they are small.

### 4.6 Adapters and bridges

Adapters, bridges, and compatibility layers do not become permanent ownership excuses.

If a temporary bridge is required, it shall remain narrow and explicitly transitional in purpose. The builder shall not use adapters to disguise unresolved ownership or to permanently warehouse mixed-domain logic.

### 4.7 General ownership principle

The ownership test is simple:
- a project artifact or logic component should be explainable as belonging to one domain,
- a manager may coordinate a very small cluster of adjacent domains,
- and when a project uses orchestrators, each orchestrator must remain bounded to its declared side or layer.

Anything broader than that shall be treated as a structural warning and refactored toward clearer ownership.

## 5. Dependency Rules

The dependency and coordination rules in this section apply when the project has runtime behavior, generated workflows, tool orchestration, graph/spine coordination, or interdependent artifact-processing pipelines.

Projects without runtime behavior still remain subject to artifact relationship, provenance, sourcing, and reporting rules.

When a project uses a bounded runtime control graph or comparable coordination structure, the builder shall structure dependency flow around the declared composition root for that profile. In a software/application profile, this is commonly rooted at `src/<project-entry-module>`.

This contract approves the architectural use of a bounded runtime control graph and constrains how it may support dependency flow, logging discipline, state handling, and clean coordination. The detailed graph design for a given project belongs in that project’s `ARCHITECTURE.md` or equivalent blueprint document.

### 5.1 Composition root rule

In software/application profiles, `src/<project-entry-module>` is the typical project composition root; in other profiles, the declared composition root or equivalent coordination authority fulfills this role.

It is responsible for:
- maintaining the project-state authority,
- bootstrapping the runtime graph,
- registering orchestrators and other approved runtime nodes,
- starting and monitoring the orchestration layer,
- and coordinating root lifecycle behavior.

The builder shall not create competing top-level state authorities outside the project composition root without explicit user approval.

### 5.2 Runtime control graph model

The project may use a lean runtime graph as an active coordination and state-topology spine.

This runtime graph is approved as a valid architectural substrate when kept bounded and legible.

Its intended role is to provide:
- declared node identity,
- bounded routing,
- controlled message traversal,
- isolated local node state,
- root-owned global state,
- and append-only event logging.

This runtime graph shall be treated as a control graph / state-aware coordination graph, not as an excuse for uncontrolled shared mutation.

### 5.3 Approved prototype graph structure

When the project blueprint calls for a runtime graph, a lean prototype graph architecture is approved in principle with the following structure:

- `Message`
  - the strictly typed data payload vehicle for graph traversal
  - contains sender, target, action, timestamp, and a serializable payload

- `GraphNode`
  - abstract base for isolated project components
  - owns narrow local state
  - communicates outward only through the engine

- `GraphEngine`
  - central routing authority
  - holds root/global state
  - registers nodes
  - defines allowed routes / edges
  - dispatches messages
  - coordinates event logging

- `SQLiteLogger`
  - append-only local event ledger
  - records successfully dispatched messages to local SQLite storage

This prototype is accepted as a lean and structurally valid foundation for the runtime coordination layer.

### 5.4 Graph state rule

The graph may maintain:
- node identity,
- node type,
- edge topology,
- bounded local node state,
- root-owned shared state,
- routing permissions,
- subscriptions or dispatch metadata,
- and event history references.

However, the builder shall not treat the graph as an unbounded dumping ground for arbitrary mutable data.

The preferred state model is:
- canonical project/global state remains rooted under the declared project composition root authority,
- nodes hold only narrow local operational state,
- shared state is explicitly owned,
- and data objects move between nodes through declared routes.

### 5.5 Message traversal rule

Messages are the approved vehicle for moving intent and serializable data payloads across the runtime graph.

The builder shall prefer explicit message traversal over arbitrary node-to-node mutation or hidden side-channel coupling.

A message route must be declared or permitted by the graph authority before traversal.

The builder shall not allow broad uncontrolled cross-calls that bypass the declared routing structure.

### 5.6 Event ledger rule

A local SQLite-backed append-only event ledger is approved as a lightweight persistence and trace mechanism for successful runtime dispatches.

This event log is valid as:
- a dispatch history,
- a local trace ledger,
- a debugging and inspection aid,
- and a future foundation for stronger event-sourcing behavior.

However, the builder shall not falsely represent append-only event logging as full event sourcing unless replay, reconstruction, snapshotting, reducer semantics, schema evolution, and related state-rebuild mechanics are actually implemented.

### 5.7 Layered routing rule

Dependency and coordination flow should follow the logical hierarchy:
- the declared project composition root connects to orchestrators,
- orchestrators connect to managers,
- managers connect to owned lower-level parts,
- and lower-level parts do not arbitrarily reach upward or sideways outside approved routes.

The builder shall prefer routing through the declared hierarchy rather than allowing broad peer-to-peer dependency sprawl.

### 5.8 Boundaries and future extension

Additional orchestration layers beyond UI and CORE may be introduced only when a real project need or declared artifact-profile need justifies them and their placement remains clear in both hierarchy and file layout.

Any added orchestration layer must remain bounded, named, and structurally legible.

### 5.9 Practical prototype caveat

The approved runtime graph prototype is accepted as a lean but partial state architecture.

It is sufficient as a real foundation for a prototype or first implementation phase, but it does not by itself constitute a complete final state architecture.

If the builder evolves it further, the builder shall later define, as needed:
- mutation authority rules,
- state-slice ownership,
- replay semantics,
- snapshotting,
- sync vs async dispatch boundaries,
- error semantics,
- and schema/version discipline for persisted event payloads.

### 5.10 Spine / envelope / event discipline

Where a project declares a spine, event bus, router, message graph, envelope chain, workflow engine, or equivalent coordination layer, state mutations shall flow through the declared coordination path.

Components, managers, tools, and orchestrators shall not bypass the declared spine through hidden writes, sideways manager calls, undocumented shared mutation, or back-channel state changes.

The declared coordination path should make intent, authority, causation, correlation, and result state inspectable when the project architecture supports it.

If the project uses events, accepted state changes shall be recorded as events or journaled operations according to the declared storage model.

Derived views, projections, indexes, caches, or dashboards shall be treated as derived state unless explicitly declared authoritative.

The builder shall not blur authoritative state, derived state, and temporary working state.

### 5.11 Payload reference and envelope lightness rule

Routing messages, envelopes, graph messages, event records, or tool-call envelopes shall be used primarily to identify, authorize, correlate, and reference.

They shall not be used as dumping grounds for heavy payloads when the project has an owned storage surface available.

Large bodies, diffs, logs, screenshots, binary data, vectors, ASTs, model outputs, scan results, and long text blocks should be stored in an owned data surface and referenced by path, ID, hash, or record key.

Readability must be preserved where practical.

Payload references shall be stable enough for later inspection, provenance, and replay/review when the project supports those operations.

### 5.12 Graph relation typing rule

Where a project maintains graph-like relations, relation types shall be declared, bounded, and semantically meaningful.

Generic relation names such as `related_to` are prohibited unless the project explicitly defines their semantics, allowed use, and constraints.

Relation records should preserve enough source/provenance context to explain why the relation exists.

The builder shall not create vague graph edges merely to imply connection without a clear relation type.

### 5.13 Governed chat and projection surface rule

If the project exposes chat, UI panels, generated packets, bootstrap manifests,
or other human-facing or agent-facing operating surfaces, those surfaces shall
remain governed projections or action paths over the declared authority chain
rather than independent memory or authority layers.

Under this rule:
- the Builder Memory Journal and Builder Memory Store remain the durable
  builder-memory surfaces,
- the declared event spine remains the authority path for project actions,
- chat, UI, exports, manifests, and summaries may assist work but shall not
  become a second authoritative memory,
- and no operating surface may bypass the declared route from interface to
  envelope to contract check to orchestrator to manager to event to derived
  views.

## 6. Safe Sourcing / Extraction Rules

The builder shall distinguish clearly between the broader Project Workspace, the active project build domain, and the project-attached Tooling Sidecar when one exists.

### 6.1 Project Workspace and sidecar model

The active Project Root is a child of the agent-accessible Project Workspace root.

The Project Workspace root may contain:
- the current Project Root,
- other project folders,
- and other workspace-level files or folders.

The current Project Root may also contain a declared Tooling Sidecar rooted at a dot-prefixed sidecar folder.

The Tooling Sidecar is project-attached but isolated from the main project artifact profile. Normal project implementation authority does not by itself authorize edits inside the Tooling Sidecar.

The builder may inspect approved reference locations in the Project Workspace, but ordinary build targets for the current project remain confined to the current Project Root; sibling project folders, unrelated root files, and other non-target folders in the Project Workspace are off limits as build targets for the current project.

### 6.2 Approved reference sources

The builder may use the following approved reference sources for reference, analysis, and bounded extraction subject to this contract:

- `Reference Reservoir`
  - a curated reservoir of prior projects and logic fragments, typically maintained inside the Tooling Sidecar
  - intended as a Reference Source for reusable logic, patterns, structures, and specialized implementations

- `Tooling Sidecar`
  - the project-attached builder sidecar rooted at a declared dot-prefixed folder and containing local development tools, helper systems, and other approved builder-facing support artifacts

- approved documents inside the current project's Project Documentation Root
  - these are part of the active project reference surface and may define design
    manifests, contracts, builder-memory-backed history/backlog expectations, and
    other project-specific constraints

The builder shall treat these as Reference Sources, not as implicit runtime dependencies.

### 6.3 Project document location rule

All project documents other than `README.md` and `LICENSE.md` shall live inside:

`<project-root>/<project-documentation-root>/`

Examples include but are not limited to:
- `ARCHITECTURE.md`
- `CONTRACT.md`
- `Builder Memory Journal`
- `Builder Memory Store`
- manifests
- design notes
- implementation plans
- migration notes
- source provenance records

The builder shall not scatter project documents outside this location.

### 6.4 Reference-only rule for sidecar and external reference sources

The builder may read from the Reference Reservoir, the Tooling Sidecar, or other approved reference sources, but it shall not make the current project depend on them at runtime.

The builder shall not:
- import from them at runtime,
- link to them by path,
- symlink to them,
- treat them as live shared libraries,
- or create hidden coupling that requires them to remain present after the project is vendored.

Any approved logic drawn from these sources must be re-homed into the appropriate owned surface inside the current Project Root according to authority, ownership, and dependency rules.

### 6.5 Preferred sourcing order

When implementing required behavior, the builder shall prefer the following order:

1. original implementation inside the current project
2. bounded rewrite informed by reference material
3. narrow structured extraction of the smallest viable hunk
4. larger transplant only under explicit contract-compliant exception conditions

The builder shall not skip directly to broad copying when a cleaner local implementation or smaller bounded extraction is reasonably feasible.

When an authoritative local artifact already exists, the builder should prefer
bounded transformation of that artifact, including patch-like edits, structured
rewrite, re-homing, relocation with traceability, or compatibility-preserving
adaptation, before resorting to unnecessary full replacement or de novo
regeneration.

### 6.6 Bounded extraction rule

When reference logic is needed, the builder shall prefer copying only structured hunks when necessary and only according to the ownership and extraction rules of this contract.

When local logic or documentation already exists, the builder should prefer
working at the hunk level where practical so that the resulting change remains
bounded, explainable, and continuity-preserving.

A structured hunk must:
- have clear ownership,
- serve a necessary purpose,
- be bounded enough to understand and maintain,
- and be capable of being re-homed into the current scaffold.

The builder shall avoid pulling in excess surrounding code, unrelated helpers, or broad dependency chains merely because one useful fragment exists nearby.

### 6.7 Full-component or full-script exception

The builder may copy parts of or whole scripts only under strict exception conditions already established in this contract.

This exception exists for cases such as:
- highly customized mathematics,
- specialized logic whose correctness depends on preserving exact structure,
- tightly interdependent components that cannot be safely rewritten without material risk,
- or other rare cases where bounded extraction would damage correctness.

Even under exception conditions, the builder shall still prefer the smallest viable borrowed unit unless preserving the larger structure is itself necessary for correctness.

### 6.8 Re-homing and cleanup rule

Any borrowed or extracted logic incorporated into the current project shall be:
- re-homed into the local project tree,
- placed according to ownership and hierarchy,
- renamed or reorganized when needed to fit the local scaffold,
- cleaned of unrelated debris,
- stripped of accidental dependency on its old environment,
- and brought into high compliance with this contract.

The builder shall not copy external code verbatim into the project and leave it structurally foreign, dangling, or dependent on its original surroundings unless exact preservation is itself the justified condition for correctness.

### 6.9 Provenance recording rule

When logic is extracted, transplanted, or materially informed by the Reference Reservoir, the Tooling Sidecar, or other approved reference sources, the builder shall record provenance in project
documentation under `<project-root>/<project-documentation-root>/` and shall append an
implementation note to the Builder Memory Journal when the change is meaningful.

The provenance record shall identify, as appropriate:
- source location,
- borrowed unit or component,
- destination owner,
- reason borrowing was necessary,
- whether the logic was rewritten, extracted, or transplanted,
- and any cleanup or compliance adjustments performed.

### 6.10 Off-limits write rule

The builder shall not modify sibling project folders or any other non-target Project Workspace contents as part of building the current project.

The builder shall not modify the Tooling Sidecar or sidecar-contained Reference Reservoir as part of ordinary project implementation unless the current work carries explicit Tooling Apply authority or another explicit authorization consistent with this contract.

The builder’s write authority for the defined project is confined to its own Project Root only.

## 7. Tooling Sidecar Rules

The builder may use the Tooling Sidecar as both a project-attached reference reservoir and a practical development-assistance reservoir, subject to the constraints of this contract.

For clarity, the Tooling Sidecar exists inside the current Project Root at a declared dot-prefixed folder such as `<project-root>/<sidecar-root>/`, but it remains isolated from the main project artifact profile. It is not part of the main runtime tree unless the project explicitly declares such a relationship.

### 7.1 Approved use of the Tooling Sidecar

The builder may:
- inspect local tools for reference,
- use local tools during development when they save time or tokens,
- copy tool logic in part or in whole when the copied structure complies with the established ownership, dependency, sourcing, and boundary rules,
- and derive new local tools inspired by patterns found there.

The builder shall not treat the Tooling Sidecar as a permanent runtime dependency for the finished vendorable project.

### 7.2 Copy / transplant rule for Tooling Sidecar tools

Logic from the Tooling Sidecar may be copied in part or in whole only when the copied structure complies with the established project rules.

Any such copied or transplanted logic must:
- be re-homed into the current project,
- fit the local scaffold,
- obey ownership and hierarchy rules,
- avoid hidden dependency on the original tool environment,
- and remain bounded to the current project’s allowed operational domain.

### 7.3 Tool-building encouragement rule

The builder is explicitly encouraged to create new local tools when doing so improves token efficiency, reduces repeated manual work, makes recurring project operations more reliable, or increases the fidelity of continuity-preserving transformations.

Awareness of token efficiency should be a primary driver in deciding whether to create a new helper tool.

The builder should prefer creating a local reusable tool over repeatedly spending large amounts of context or tokens on the same mechanical task.

This includes tools that support diff-like editing, token-aware patching,
bounded rewrites, structure-preserving migration, or safer artifact
transformation when such tools would reduce accidental continuity loss.

### 7.4 CLI accessibility rule

Any newly created tool intended to handle repeated tasks shall provide command-line access so that any agent working within the project can invoke it consistently.

CLI accessibility is required for reusable project tools unless the user explicitly approves another interface pattern.

### 7.5 Project-local effect rule

Any tool used or created for the project shall have effects confined to the current Project Root unless the user explicitly authorizes a wider scope.

The builder shall not create tools that modify, scan, patch, or otherwise affect files outside the current Project Root as part of the normal project workflow.

### 7.6 Local helper model rule

The builder may create or use local agentic helper tooling, including tooling that invokes local Ollama models or similar local inference helpers, when doing so supports repeated task execution, token efficiency, or bounded automation.

Such helper usage is encouraged when it remains fully compliant with this contract.

### 7.7 Hardware and inference budget rule

The builder shall respect the user’s system limits when using or creating local helper-model workflows.

Preferred limits:
- no local helper models above approximately the 4B parameter threshold,
- no more than approximately 4k tokens per inference cycle for agentic helpers,
- and no workflows that materially exceed the user’s practical system capabilities.

The builder shall not design helper workflows that assume unrealistic compute, context, memory, or model size relative to the user’s system.

### 7.8 Documentation rule for project tools

When the builder creates or materially incorporates a development tool for the
project, it shall document the tool under the project documentation area and
append a meaningful entry to the Builder Memory Journal.

This documentation shall identify:
- the tool’s purpose,
- its scope of effect,
- its CLI entry pattern,
- any model or runtime assumptions,
- and any important operational constraints.

### 7.9 Reusable tool interface contract

Reusable tools shall declare:
- tool name,
- purpose,
- category or responsibility domain,
- scope of effect,
- input shape or schema,
- output/result shape,
- CLI invocation pattern when applicable,
- failure behavior,
- logging behavior,
- and assumptions or external dependencies.

Reusable tools should produce machine-readable output where practical.

Tools that modify files shall report changed targets.

Tools that validate without writing shall expose a dry-run or validation mode where practical.

Tool failures shall be diagnosable and should not silently mutate project state.

Tool documentation shall be sufficient for another builder agent to discover and invoke the tool safely.

### 7.10 Tool legacy / shared utility rule

This rule is an explicit narrow exception to the normal separation between the main project artifact profile and the project-attached Tooling Sidecar.

If the builder creates or improves a development tool that is useful beyond the immediate local project step, it may place or update that tool in the Tooling Sidecar only when explicit Tooling Apply authority has been granted and the work remains bounded, intentional, and clearly documented.

The builder shall not use this rule as an excuse for unrelated edits, broad workspace changes, or uncontrolled write activity outside the intended sidecar scope.

If such authority has not been granted, the builder shall preserve the tool as a proposal or project-local draft rather than writing to the Tooling Sidecar.

Such tools must be clearly marked up with enough instructions and tool metadata that another agent can discover what the tool is, how to invoke it, what scope it operates on, and what constraints apply.

If the tool is multifile, the builder shall place it in an appropriate isolating subfolder under the Tooling Sidecar so the tool remains self-contained and legible. More robust instruction `.md` files may be created there when warranted.

The sidecar root itself shall remain dot-prefixed and visually distinct from the main project profile.

Entry points and usage of tools must always be clear.

If existing tools in the Tooling Sidecar are not clearly marked, the builder should,
when appropriate, improve tool metadata, usage discoverability, or
instructions. If immediate rectification is not appropriate, the builder should
record the issue in the project backlog inside the Builder Memory Journal or, if that
tooling area maintains its own local backlog document, in that tool-local
continuation surface.

### 7.11 Same-core-rules principle

The Tooling Sidecar is a privileged and useful source, but it is not exempt from the project's core architectural rules.

All logic derived from the Tooling Sidecar remains subject to:
- root boundary rules,
- ownership rules,
- dependency rules,
- safe sourcing rules,
- code quality rules,
- and prohibited behavior rules.

## 8. Support File Proposal Rules

The builder may create new files and folders as needed when doing so is in accordance with the established rules of this contract.

New file creation is expected to occur when it is the cleanest way to preserve ownership, reduce fragility, and maintain legible structure.

### 8.1 General creation rule

The builder may add support files or support folders whenever they serve a real structural need and align with the ownership, hierarchy, dependency, and boundary rules already established.

The builder shall not avoid creating a needed file merely to appear minimal if doing so would create mixed ownership, hidden complexity, or fragile code.

### 8.2 Balance rule

All files should aim for a balance of:
- minimality,
- non-fragility,
- cleanliness,
- efficiency,
- and clarity to other agents.

The builder shall not pursue extreme minimalism when it causes brittleness, nor excessive decomposition when it creates needless sprawl.

### 8.3 Purpose and placement rule

When the builder creates a new file or folder, its purpose and placement must be clear.

A new file or folder should exist because:
- it owns a real responsibility,
- it preserves domain clarity,
- it keeps the hierarchy legible,
- or it cleanly isolates a tool, subsystem, data area, asset area, or support concern.

### 8.4 Markup and metadata rule

Files should communicate clearly to other agents what they are and how they fit into the project.

The builder should use light but meaningful markup, headers, metadata, docstrings, or other in-file cues where appropriate so that purpose, ownership, and usage are understandable.

However, the builder shall not over-bloat scripts with excessive metadata, repetitive headers, or documentation volume that materially complicates the code.

The goal is enough clarity to orient future agents without turning code into documentation-heavy clutter.

### 8.5 Temporary and dead-file cleanup rule

The builder has an active duty to clean up temporary files, unused dead files, obsolete scratch artifacts, and similar debris when such cleanup can be performed safely.

Cleanup must be performed conservatively.

The builder shall not prune files casually or aggressively when there is material uncertainty about whether they are still needed.

The builder should prefer safe identification of removable items through:
- clear naming,
- known temporary status,
- explicit replacement history,
- lack of active references,
- or documented obsolescence.

When uncertainty remains, the builder should preserve the file, relocate it to a clearly marked holding area if appropriate, or record the cleanup candidate in project documentation rather than risk erroneous deletion.

### 8.6 No-error-prune rule

Nothing should be pruned by accident.

Before deleting or pruning a file or folder, the builder should have a reasonable basis to conclude that:
- the item is temporary, obsolete, unused, replaced, or intentionally disposable,
- removing it will not break the project,
- and the deletion aligns with the user’s intent and project history.

If that basis does not exist, the builder shall not delete the item.

### 8.7 Cleanup documentation rule

Meaningful cleanup actions, especially pruning of unused files or structural
reorganization, should be recorded in the Builder Memory Journal and, when warranted, in
supporting project documentation under the Project Documentation Root.

This is especially important when files were superseded, intentionally removed, or replaced by new structure.

## 9. Artifact Quality and Code Quality Rules

The builder shall produce project artifacts that are clean, inspectable, robust under interruption, and appropriate to the declared artifact profile.

When the project contains code, code-specific quality rules in this section apply directly. When the project is document, research, data, website, prompt-library, or mixed-artifact work, equivalent quality discipline still applies: clarity, traceability, consistency, provenance, validation, recoverability, and maintainability.

### 9.1 Logging instead of print rule

There is no general excuse for `print()`-based debugging or operational output in application, runtime, build, or tooling code when the project profile calls for proper logging or trace capture.

The builder shall use proper logging infrastructure rather than ad hoc print statements in those code contexts.

This requirement is strengthened by the presence of runtime graphs, coordination layers, central authority paths, and structured event/state mechanisms when the project uses them.

`print()` may be used only in narrowly justified one-off tooling or explicitly throwaway contexts when the user has not required logging discipline there. It shall not be used as a substitute for real application, runtime, build, or tooling logging.

### 9.2 Full logging rule

The builder shall implement full logging appropriate to the project scope.

Logging should support:
- startup and shutdown visibility,
- major lifecycle transitions,
- orchestration actions,
- manager-level coordination events,
- errors and warnings,
- meaningful state changes where appropriate,
- tool execution when relevant,
- and cleanup / migration / structural actions when significant.

Logging should be structured and useful rather than noisy spam.

### 9.3 Graceful failure rule

Failures shall happen gracefully.

The builder shall prefer controlled failure handling, clear error reporting, and safe degradation over abrupt unexplained crashes.

Graceful failure includes, where appropriate:
- clear exception handling at suitable boundaries,
- meaningful logs,
- preservation of useful diagnostics,
- safe shutdown paths,
- and avoiding corruption of state, files, or active workflows.

### 9.4 Testing and task-checklist rule

The builder shall use robust testing and temporary task checklists to support reliable execution.

Tests should be used to verify meaningful logic, especially new or changed behavior.

Task checklists should be used to track work that may be interrupted so that progress can be resumed cleanly by reading the recorded checklist state.

This is especially important in agentic or token-limited workflows where interruptions, context loss, or partial completion are realistic risks.

### 9.5 Central configuration rule

Configuration should be centralized.

The builder shall prefer a clear central configuration model over scattered ad hoc settings.

The runtime graph and state registry should be used to make configuration handling clearer rather than more diffuse.

Configuration values should be discoverable, intentionally owned, and easy to inspect or update.

### 9.6 Hidden globals and magic constants rule

The builder shall avoid hidden globals and unexplained magic constants.

Shared state, mutable operational settings, and important cross-cutting values should not be smuggled into the codebase through accidental module globals or hard-coded values with unclear meaning.

Constants should be named, owned, and placed where their role is legible.

If a constant materially affects behavior, routing, thresholds, limits, timing, paths, or protocol expectations, the builder should make it explicit and understandable.

### 9.7 Type and schema discipline rule

The builder shall prefer typed structures where they materially improve clarity, safety, and maintainability.

Typed configuration objects, typed message payload envelopes, typed state slices, dataclasses, or similarly clear structured models are encouraged when they help define stable contracts between parts of the system.

The builder should not introduce heavy type ceremony for its own sake, but it should use typing deliberately where structure matters.

### 9.8 Documentation and metadata balance rule

The builder should include enough docstrings, inline guidance, headers, or metadata to clarify the purpose and usage of meaningful public-facing or structurally important code.

However, the builder shall avoid over-documenting trivial internal details in ways that bloat and clutter the code.

The objective is operational clarity, not documentation theater.

### 9.9 Structural quality principle

Artifact quality is not only syntax quality.

The builder shall treat the following as part of artifact quality and, where applicable, code quality:
- ownership clarity,
- stable file placement,
- clean routing or artifact relationship handling,
- explicit state handling where runtime or workflow state exists,
- provenance clarity,
- safe cleanup,
- testability or verifiability appropriate to the declared artifact profile,
- recoverability after interruption,
- and legibility to future agents and the user.

For non-code profiles, this includes citation/provenance clarity for research and document projects, schema/field consistency and transformation records for data curation projects, structure/content/assets/build relationships for website projects, and versioning, intent, and usage notes or test cases where applicable for prompt or instruction libraries.

## 10. Reporting / Phase Output Rules

The builder shall maintain clear phase-level reporting through project
documentation, primarily using the Builder Memory Journal under the Project Documentation Root.

### 10.1 Journal entry format rule

The Builder Memory Journal shall function as the append-only execution ledger for
meaningful work phases.

Each new entry should be:
- date stamped,
- time stamped,
- and include a meaningful entry identifier.

Each entry shall record:
- the files changed,
- a short but complete summary of what changed,
- and any materially relevant implementation note.

Summaries must remain concise, but they shall not use cut-off shorthand such as `...` in place of omitted meaning.

### 10.2 File-change recording rule

The builder shall record all files changed for a meaningful work phase.

This should include created, modified, relocated, or deleted text artifacts, documents, datasets, schemas, prompts, assets, generated outputs, or code files when such changes are part of the phase.

The goal is for another agent or the user to reconstruct what was touched without ambiguity.

### 10.3 Testing report rule

The builder shall record meaningful testing, checking, or validation activity at the phase level, but it does not need to list every individual test name or every passing result in the dev log.

Normal successful verification activity may be summarized compactly.

This may include build checks, linting, citation checks, schema validation, data validation, link checks, spell/style checks, smoke tests, review passes, or manual verification appropriate to the declared artifact profile.

If failures are persistent, significant, blocking, or diagnostically important, the builder should record more detail.

### 10.4 Tool-usage metrics rule

The builder should track tool usage metrics when meaningful.

This includes, as appropriate:
- tools used,
- tools created,
- repeated-task automation employed,
- or other significant efficiency-relevant tooling activity.

Tool usage should be recorded compactly but clearly enough to understand how work was performed.

### 10.5 Backlog ownership rule

Unresolved issues, deferred work, next steps, and deferred cleanup items belong
in the Builder Memory Journal backlog surface.

The Builder Memory Journal is the operational backlog / continuation surface.

The builder should place into the Builder Memory Journal backlog, as appropriate:
- unresolved issues,
- blocked items,
- deferred cleanup,
- follow-up steps,
- risks to revisit,
- and pending structural corrections.

### 10.6 Cleanup reporting rule

If cleanup was performed and is materially relevant, the builder should note it
in the Builder Memory Journal.

If cleanup remains needed and was not performed, that deferred cleanup should
be recorded in the Builder Memory Journal backlog.

### 10.7 Reporting principle

The reporting system should preserve:
- continuity across interrupted work,
- clear traceability of changes,
- concise but non-truncated summaries,
- and a clean separation between completed history and pending work through
  journal entry kinds, titles, tags, and status.

### 10.8 Park Phase closure rule

A meaningful tranche is not complete until a Park Phase record exists in the Builder Memory Journal or Builder Memory Store.

A Park Phase record shall include:
1. tranche identifier or meaningful phase name,
2. scope completed,
3. explicit non-goals preserved,
4. files created, modified, moved, or deleted, including text artifacts, documents, datasets, schemas, prompts, assets, generated outputs, and code when applicable,
5. source/provenance references for borrowed or materially informed logic,
6. tests, checks, validations, smoke tests, build checks, citation checks, schema validation, data validation, link checks, spell/style checks, review passes, or manual verification run, as appropriate to the declared artifact profile,
7. known failures, skipped checks, or unverified assumptions,
8. unresolved issues,
9. deferred cleanup,
10. next recommended tranche or continuation note,
11. closure status.

For projects that use the sidecar spine and its tranche-close discipline, a
complete Park Phase closure shall also be recoverable across five required
artifact surfaces:
1. the tranche journal entry,
2. the sealed park-notes artifact or equivalent closeout record,
3. the continuity surfaces updated to reflect the new current state,
4. the tranche-closing event trail in the spine,
5. and the final closure record that marks the tranche sealed.

If a project implements these five surfaces through different concrete files,
blobs, or event objects, the builder shall still ensure that the full closure
set exists and is mutually consistent before treating the tranche as parked.

If required verification fails, the tranche is not parked.

If no verification was run, the Park Phase shall explicitly say so and explain why.

If no automated verification exists for the project profile, the builder shall record the manual, editorial, structural, or provenance review performed, or state what remains unverified.

If a project has a validation tool, smoke test, journal validator, contract checker, or equivalent gate, the builder shall run it when practical before declaring the tranche complete.

The builder shall not rely on chat memory as the only tranche closure record.

The Park Phase belongs in durable builder memory.

## 11. Decision Priority and Pushback Rule

The builder’s job is not mere compliance theater and not blind obedience to every user impulse.

The builder’s job is to produce the strongest, cleanest, most maintainable project reasonably achievable within the project goals, blueprint, and contract.

Accordingly, decision priority shall be:

1. preserve correctness, structural integrity, and long-term maintainability,
2. preserve contract compliance and bounded architecture,
3. preserve the real intent of the user’s goal,
4. prefer the cleanest effective implementation,
5. prefer token-efficient and repeatable workflows,
6. satisfy surface-level preferences only when they do not materially damage the system.

If the user requests something that appears structurally unsound, unnecessary, contradictory, maladaptive, overly fragile, or likely to damage the quality of the project, the builder should not simply comply.

Instead, the builder should:
- push back clearly,
- verify the underlying intent,
- warn about likely consequences,
- explain the tradeoff or structural cost,
- and when appropriate propose a stronger alternative.

The builder should treat magnitude seriously. The worse the likely consequence of a proposed user decision, the more explicitly the builder should surface the risk.

However, pushback should remain grounded, technical, and aimed at making the best project possible rather than resisting for its own sake.

## 12. Prohibited Behaviors

This section summarizes prohibition logic, but prohibitions are distributed throughout the entire contract. The builder shall not interpret this section as limiting prohibitions only to the examples listed here.

Prohibited behaviors are established throughout this contract by the rules already stated.

Any action explicitly disallowed by the sections of this document is prohibited.

### 12.1 Contract-first prohibition rule

The builder shall treat the constraints in this document as the primary authority for what is forbidden.

If a behavior violates the mission, root boundary rules, ownership rules, dependency rules, sourcing rules, tooling rules, support-file rules, code-quality rules, or reporting rules, that behavior is prohibited.

### 12.2 Non-listed behavior rule

If a behavior is not explicitly authorized by this contract, it shall be treated as a possibility requiring user approval before the builder proceeds.

Silence in the contract is not blanket permission for structural deviation, risky behavior, boundary crossing, or architecture changes.

### 12.3 Approval gate rule

When the builder encounters an action that is not clearly covered by the contract and that could materially affect structure, boundaries, dependency, sourcing, tooling scope, cleanup, or long-term maintainability, it shall pause that action, surface it clearly, and seek user approval.

### 12.4 General prohibited examples

Without limiting the broader rules already established, prohibited behavior includes examples such as:
- writing outside the current Project Root when not explicitly authorized,
- creating runtime dependency on the Reference Reservoir, the Tooling Sidecar, or sibling projects,
- hiding mixed ownership inside convenience files,
- using print statements in place of proper project, runtime, or tooling logging where logging discipline is required,
- corrupting or overwriting source documents without provenance,
- silently changing dataset semantics,
- breaking citation or source traceability,
- mixing generated outputs with authoritative source artifacts without declaring the distinction,
- imposing an application scaffold on a non-application project without need or approval,
- deleting files recklessly or without sufficient basis,
- leaving copied logic structurally foreign and unowned,
- introducing hidden globals or unexplained magic constants,
- creating unclear tool entry points,
- or silently bypassing the declared hierarchy and routing model.

These examples do not replace the contract; they illustrate it.

## Appendix A. Historical Equivalence Map (non-normative)

This appendix exists only to help interpret historical records created before
the single-source cutover.

It does not create additional duties beyond the operative sections above.

| Historical reference | Current BCC anchor |
|---|---|
| `contracts/builder_constraint_contract.md` | `contracts/BCC.md` |
| `§D` / `contract §D` | `§10.8 Park Phase closure rule` |
| `§3.1` / `chat-over-spine rule` | `§5.10 Spine / envelope / event discipline` and `§5.13 Governed chat and projection surface rule` |
| `§0.10` dual-scope note | `Contract Use Preamble`, `§2.4 Contract primacy and doctrine recoverability rule`, and `§5.13 Governed chat and projection surface rule` |
| `Park Phase Discipline` | `§10.8 Park Phase closure rule` |
| `five artifacts` | `§10.8 Park Phase closure rule` |

## Appendix B. Project Binding Artifact

This appendix defines the required interpretation, discovery order, and minimum
shape for the external binding artifact that supplies concrete local bindings
for a specific repository or vendored package.

The Project Binding Artifact is a local-instantiation surface. It may bind
paths, named projections, verification entrypoints, documentation roots,
continuity surfaces, package facts, and runtime/store locations. It shall not
create new doctrine, and if it conflicts with this contract, this contract
wins.

### Discovery order

When a builder needs local concrete bindings, it shall resolve them in this
order:
1. inspect the project's declared Project Binding Artifact when one is already
   present,
2. otherwise inspect the conventional Markdown binding artifact path
   `_docs/reference/PROJECT_BINDINGS.md`,
3. otherwise inspect a clearly declared equivalent local binding surface when
   the project has intentionally chosen a different artifact,
4. otherwise stop at Observe or Propose state and create or propose a compliant
   Project Binding Artifact before relying on undeclared local bindings.

### Required interpretation rules

- The Project Binding Artifact is authoritative for declared local bindings
  only.
- Exactly one active Project Binding Artifact shall govern a given package or
  installation context at a time.
- If a project replaces the conventional artifact path with another local
  binding surface, the replacement shall be explicitly declared as the active
  binding artifact and the old surface shall become either a redirect note, a
  historical artifact, or be removed.
- It shall be read after `BCC.md` and before convenience orientation surfaces.
- It may restate local concrete paths and package facts, but shall not restate
  or extend doctrine except to cite this contract.
- Missing, ambiguous, or stale bindings shall be treated as a continuity issue
  requiring repair rather than guessed silently.

### Required minimum shape

When the artifact is written in Markdown, it should include clearly labeled
sections for:
- packaging and root bindings,
- doctrine and continuity bindings,
- Builder Memory bindings,
- tooling and verification bindings,
- and any repo-local notes needed to explain package or installation context.

At minimum it shall declare:
- the binding contract path,
- the project documentation root when one exists,
- the architecture surface when one exists,
- the target-state surface when one exists,
- the current-state continuity entry when one exists,
- the Builder Memory Store and Builder Memory Journal surfaces when they exist,
- the tool manifest or equivalent tool index surface when one exists,
- and the primary verification entrypoint for the local package.

Every declared binding shall either resolve in the current package context or
carry an explicit status marker such as `generated`, `optional`,
`installed-context`, `development-context`, `not-yet-created`, or another
equally clear local status that explains why the binding is not expected to
resolve here and now.
