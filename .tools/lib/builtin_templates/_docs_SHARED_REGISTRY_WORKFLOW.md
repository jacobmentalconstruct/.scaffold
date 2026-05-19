# Shared Registry Workflow

## Purpose

This document records the collaboration pattern used when a project benefits
from a shared visible state surface.

The goal is not hidden tool use. The goal is a shared working surface where the
human and the builder can stay synchronized to the same query state, evidence
shelf, selection, and recent action provenance.

## Current Proven Baseline

- A file-backed shared registry is a workable truth surface for collaboration.
- A separate sidecar viewer is often a good first landing point.
- Human-driven shared-state viewing is the first trustable baseline.
- Agent-driven visible panel actions should remain experimental until verified.

## Working Doctrine

Preferred collaboration loop:

1. sync to shared state
2. reason from shared state
3. act through the agreed tool or panel surface
4. resync after the action

Use this pattern when the work is exploratory, evidence-facing, or intended to
teach both sides how the system behaves.

## Typical registry contents

A small shared registry may track:

- current query
- active mode
- selected provider
- selected item
- last action source
- current payload or shelf summary

Only store what is needed for synchronization.

## Trust boundary

Promote to normal workflow only what has actually been proven. Examples:

- proven:
  - human-driven shared-state viewing
  - explicit action provenance
- not yet proven:
  - panel-command automation
  - full live UI telemetry
  - background action assumptions
