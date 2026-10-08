# AGENTS.md: Shared Memory Bank Protocol

This file is the canonical entry point for repository workflow rules.
Tool-specific files only point here. Before any task, read the installed
`MemBankRules.md` specification version 3.2 in full. It is normative, including
its lifecycle tables, templates' required fields, and safety procedures.
This entry point is a navigation index, not an abbreviated replacement.
Host/system/developer instructions and actual tool permissions take precedence.
Explicit overrides in a declared compatible extension take precedence over the base;
otherwise follow the base. If normative rules conflict ambiguously, stop and ask.

## 1. Memory Bank
Files in `memory-bank/`:
- `projectBrief.md`: WHAT and WHY (goals, scope, non-goals, constraints)
- `productContext.md`: WHO and HOW (personas, journeys, glossary)
- `systemPatterns.md`: architecture, boundaries, conventions
- `techContext.md`: stack and build/test/lint commands
- `activeContext.md`: session-local focus and pointers (never sole authority for approvals)
- `plans/PLAN-xxx-<title>.md`: tracked plan, status, approval, execution record, handoff
- `progress.md`: completed work, FIND-xxx backlog, test status
- `decisions.md` + `decisions/ADR-xxx-<title>.md`: architectural decisions

## 2. Operating Modes
Follow MemBankRules.md sections 1.4 and 1.6. Plan Mode is read-only. Documentation
Preparation needs host write permission and an authorized documentation scope.
Implementation starts at Ready or resumes owned In Progress work; approval and
dependency guards always apply. This protocol cannot switch or expand host modes.

## 3. Session Startup
Follow MemBankRules.md section 7.1: inspect Git before writes, load tiers and the
tracked work item, verify ownership/identity and freshness, then briefly acknowledge.

## 4. Source of Truth
Source code and tests establish observed behavior; approved requirements and approved
plans establish intended behavior. Descriptive memory follows verified observations.
An observed/intended discrepancy is a defect candidate or a proposed requirement
change, never permission to rewrite approved intent or alter code without approval.
Report evidence, distinguish fact from intent, and use the approval/change workflow.

## 5. Safety Rules
- Never run destructive commands without explicit developer permission. This includes:
  `git reset --hard`, `git clean`, `git push --force`, `git stash drop`, deleting branches,
  `rm -rf`, dropping or truncating database tables, and running migrations against shared environments.
- Never commit, stash, or discard the developer's own uncommitted work.
- Never write credentials, tokens, API keys, private keys, connection strings, personal data,
  or production data into any file, including Memory Bank files.
- Do not modify generated files, build output, lock files, or dependencies unless the work item requires it.
- In code you write: validate external input and avoid unsafe command execution.

## 6. Act Mode Procedure
Follow MemBankRules.md sections 6.1-6.4 in order: committed preparation, claim,
clean checkpoint (or reconciled resume), baseline, bounded implementation,
acceptance verification, metadata closeout, then an authorized completion commit.
Execution and verification statuses are separate (section 1.6). Never claim a
command ran or a human approved something without evidence.

## 7. Blocker Protocol
Follow MemBankRules.md section 6.5. Preserve evidence before rollback, inspect
ownership and index state, and never restore entire files whose ownership is uncertain.
Record Blocked and rollback disposition durably; request clarification in Plan Mode.

## 8. Staleness Detection
Follow MemBankRules.md section 2.3, including Fresh/Stale/Unknown, working-tree
changes, special Covers values, and mandatory task-critical reverification.

## 9. Memory Updates (Closeout)
Follow MemBankRules.md sections 7.2-7.3; closeout is part of completion, before the
completion commit. Never resolve a finding merely because one related item is Done.
Approvals and handoff remain in tracked artifacts even when activeContext is ignored.

## 10. Analysis Rules
- Inspect real implementation and tests; never infer behavior from file names alone.
- Cite file paths and line numbers for every finding.
- Separate verified facts from hypotheses.
- Never modify source files during read-only analysis.
- For architectural changes, present alternatives and trade-offs before implementing.

## 11. CDIP Extension
Before CDIP operations, read installed `MemBankRulesWithCDIP.md` specification
version 3.2 in full, in addition to base version 3.2. Missing or incompatible files
block CDIP writes until authorized preparation repairs the installation.
Its explicit overrides replace base tracked PLAN records with TASK files and add
task context, revision-bound approval chains, propagation, and derived-index rules.
Use its sections 1.5, 2.3, 4.4-4.6, 6, and 7 for those rules. Do not infer human
approval or rewrite intended requirements to match observed bugs.
All other base rules remain applicable, including host-mode limits, preparation,
ownership-safe rollback, verification states, and metadata-before-commit completion.
