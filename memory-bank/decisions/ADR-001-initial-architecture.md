# ADR-001: Adopt Shared AI Memory Bank with CDIP

**Status:** Accepted
**Date:** 08-10-2026
**Deciders:** Team / Developer

## Status History
- 08-10-2026: Accepted; adopted standardized Shared AI Memory Bank protocol with CDIP.

## Context
AI coding assistants suffer from context drift across sessions and tool switches. A standardized repository-native memory bank and requirement hierarchy is needed.

## Decision
Adopt the Shared AI Memory Bank protocol (v3.2) with the CDIP extension. All agents enter through `AGENTS.md` and use thin adapters.

## Consequences
- **Positive:** Persistent context, multi-agent interoperability, end-to-end requirements traceability (`BR → SR → TASK`).
- **Negative:** Documentation must be maintained alongside code using the defined lifecycle.
