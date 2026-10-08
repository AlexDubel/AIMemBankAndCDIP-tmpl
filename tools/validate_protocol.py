#!/usr/bin/env python3
"""Read-only checks for Shared Memory Bank 3.2 Markdown artifacts.

Only the documented record syntax is parsed; this is not a general Markdown parser,
an approval authenticator, a Git freshness checker, or a command execution engine.
"""

import argparse
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


VERSION = "3.2"
ID = r"(?:BR-\d+|SR-\d+|TASK-\d+[A-Z]*|PLAN-\d+)"
WORK_STATES = {"Backlog", "Ready", "In Progress", "Blocked", "Done", "Cancelled"}
REQ_STATES = {"Draft", "Approved", "Superseded", "Deprecated"}
VERIFICATIONS = {"Not Run", "Passed", "Failed", "Manual Accepted"}
BEGIN = "<!-- BEGIN DERIVED REQUIREMENTS -->"
END = "<!-- END DERIVED REQUIREMENTS -->"
ACCEPT_BEGIN = "<!-- BEGIN CURRENT ACCEPTANCE -->"
ACCEPT_END = "<!-- END CURRENT ACCEPTANCE -->"
FOLDERS = {"BR": "requirements/BR", "SR": "requirements/SR", "TASK": "requirements/tasks",
           "PLAN": "memory-bank/plans"}
EMPTY = {"", "none", "unresolved", "not run"}


def present(value):
    value = value.strip()
    return value.lower() not in EMPTY | {"tbd", "todo", "...", "unassigned"} and not re.fullmatch(r"<[^>]+>", value)


def iso_date(value):
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and bool(date.fromisoformat(value))
    except ValueError:
        return False


def prose(text):
    """Return non-fenced text with original line numbers, plus fence errors."""
    lines, errors, fence = [], [], None
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= fence[1] and not match[2].strip():
                fence = None
            continue
        if match:
            fence = (match[1][0], len(match[1]), number)
        else:
            lines.append((number, line))
    if fence:
        errors.append(f"line {fence[2]}: unclosed fenced block")
    return lines, errors


def anchors(text):
    result, counts = set(), {}
    for _, line in prose(text)[0]:
        match = re.match(r"^#{1,6}\s+(.+?)(?:\s+#+)?$", line)
        if match:
            slug = re.sub(r"[^\w\- ]", "", match[1].lower()).replace(" ", "-")
            count = counts.get(slug, 0)
            counts[slug] = count + 1
            result.add(f"{slug}-{count}" if count else slug)
    return result


def sections(text):
    """Parse level-two sections outside comments/fences; repeated names are invalid."""
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    result, current = {}, None
    for _, line in prose(text)[0]:
        if line.startswith("## "):
            current = line[3:].strip()
            if current in result:
                raise ValueError(f"duplicate section {current}")
            result[current] = []
        elif line.startswith("# "):
            current = None
        elif current is not None:
            result[current].append(line)
    return {key: "\n".join(value).strip() for key, value in result.items()}


def table(text, columns):
    """Strict, unescaped-pipe Markdown table for normative relationship sections."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or any(not line.startswith("|") or not line.endswith("|") for line in lines):
        raise ValueError("expected a Markdown table")
    rows = [[cell.strip() for cell in line[1:-1].split("|")] for line in lines]
    if rows[0] != columns or any(len(row) != len(columns) for row in rows):
        raise ValueError("table columns do not match: " + ", ".join(columns))
    if any(not re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]):
        raise ValueError("invalid table separator")
    return [dict(zip(columns, row)) for row in rows[2:]]


def id_list(value):
    return [] if value in {"none", "unassigned", ""} else [item.strip() for item in value.split(",")]


def scope_paths(record):
    body = sections(record.text).get("Scope (files)", "")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    paths = []
    for line in lines:
        match = re.fullmatch(r"- `([^`]+)`", line)
        if not match:
            raise ValueError("Scope (files) must list exact paths as - `path`")
        name = match[1]
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or str(path) != name or name == "." or
                any(char in name for char in "*?[]\\") or "..." in name):
            raise ValueError(f"invalid scope path: {name}")
        paths.append(name)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("Scope (files) must be nonempty with unique paths")
    return sorted(paths)


def implementation_fingerprint(root, record):
    """sha256 of compact JSON [path, kind, executable, content-sha256] rows."""
    root = Path(root).resolve()
    rows = []
    for name in scope_paths(record):
        path = root / name
        if not path.resolve().is_relative_to(root) or path.resolve() == record.path.resolve():
            raise ValueError(f"scope escapes root or includes its own record: {name}")
        if any(part.is_symlink() for part in [path, *path.parents] if part != root.parent):
            raise ValueError(f"symlink scope is unsupported: {name}")
        if not path.exists():
            rows.append([name, "missing", False, ""])
        elif path.is_file():
            rows.append([name, "file", bool(path.stat().st_mode & 0o111), hashlib.sha256(path.read_bytes()).hexdigest()])
        else:
            raise ValueError(f"scope must contain files, not directories: {name}")
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def git_read(root, *args):
    """Only fixed read-only Git subcommands are passed by callers; no shell."""
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip() or "Git check failed")
    return result.stdout


def baseline_records(audit, reference, label="comparison"):
    records = {}
    sha = None
    try:
        sha = git_read(audit.root, "rev-parse", "--verify", "--end-of-options", reference + "^{commit}").decode().strip()
        git_read(audit.root, "merge-base", "--is-ancestor", sha, "HEAD")
        names = git_read(audit.root, "ls-tree", "-r", "--name-only", "-z", sha, "--", *FOLDERS.values())
        for name in names.decode("utf-8").split("\0"):
            path = Path(name)
            kind = next((key for key, folder in FOLDERS.items() if path.parent.as_posix() == folder), None)
            if kind and path.suffix == ".md":
                text = git_read(audit.root, "show", f"{sha}:{name}").decode("utf-8")
                record = parse_record(audit, audit.root / path, text, kind)
                if record:
                    if record.ident in records:
                        audit.error(record.path, "duplicate ID in comparison baseline")
                    records[record.ident] = record
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
        audit.error(audit.root, f"invalid {label} baseline: {exc}")
    return records, sha


class Audit:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.errors = []

    def error(self, path, message):
        self.errors.append(f"{path}: {message}")

    def read(self, path):
        path = Path(path)
        if not path.resolve().is_relative_to(self.root):
            self.error(path, "path escapes project root")
            return None
        try:
            return path.read_bytes().decode("utf-8")
        except (OSError, UnicodeError) as exc:
            self.error(path, f"cannot read: {exc}")
            return None

    def markdown(self, path, text):
        lines, errors = prose(text)
        for error in errors:
            self.error(path, error)
        for number, line in lines:
            # Inline code isn't a navigational Markdown link.
            line = re.sub(r"`+[^`]*`+", "", line)
            for raw in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", line):
                target = urlsplit(raw)
                if target.scheme or target.netloc:
                    continue
                destination = (path.parent / unquote(target.path)).resolve() if target.path else path
                if not destination.is_relative_to(self.root):
                    self.error(path, f"line {number}: link escapes project root: {raw}")
                elif not destination.is_file():
                    self.error(path, f"line {number}: missing link target: {raw}")
                elif target.fragment and destination.suffix == ".md":
                    other = text if destination == path else self.read(destination)
                    if other is not None and unquote(target.fragment) not in anchors(other):
                        self.error(path, f"line {number}: missing anchor: {raw}")


@dataclass
class Record:
    path: Path
    ident: str
    kind: str
    fields: dict
    text: str

    def get(self, key):
        return self.fields.get(key, "")


def parse_record(audit, path, text, kind):
    lines, _ = prose(re.sub(r"<!--[\s\S]*?-->", "", text))
    titles = [re.fullmatch(rf"# ({ID}): .+", line) for _, line in lines if line.startswith("# ")]
    if len(titles) != 1 or titles[0] is None:
        audit.error(path, "expected one '# ID: Title' record heading")
        return None
    ident = titles[0][1]
    if not ident.startswith(kind + "-") or not path.name.startswith(ident + "-"):
        audit.error(path, "record ID, filename, and directory type must agree")
    fields = {}
    for number, line in lines:
        match = re.fullmatch(r"(?:- )?\*\*([^*]+):\*\*\s*(.*)", line)
        if match:
            key, value = match.groups()
            if key in fields:
                audit.error(path, f"line {number}: duplicate field {key}")
            fields[key] = value.strip()
    return Record(path, ident, kind, fields, text)


def require(audit, record, keys):
    for key in keys:
        if key not in record.fields:
            audit.error(record.path, f"missing field: {key}")


def approve(audit, record, revision_key, bound_key):
    if record.get(bound_key) != record.get(revision_key) or not present(record.get(bound_key)):
        audit.error(record.path, f"{bound_key} must match {revision_key}")
    for key in ("Approved by", "Approval evidence"):
        if not present(record.get(key)):
            audit.error(record.path, f"approval requires {key}")
    if not iso_date(record.get("Approved on")):
        audit.error(record.path, "approval requires ISO Approved on date")


def references(audit, record, key, pattern):
    value = record.get(key)
    if value == "none":
        return []
    items = [item.strip() for item in value.split(",")]
    if not value or any(not re.fullmatch(pattern, item) for item in items):
        audit.error(record.path, f"{key} must contain comma-separated IDs or none")
        return []
    if len(set(items)) != len(items):
        audit.error(record.path, f"duplicate IDs in {key}")
    return items


def parent_of(audit, record, records):
    value = record.get("Parent")
    if record.kind == "SR" and value == "unresolved" and record.get("Status") == "Draft":
        if record.get("Parent version") != "none" or "## Open Questions" not in record.text:
            audit.error(record.path, "unresolved Draft SR needs Parent version none and Open Questions")
        return None
    kind = "BR" if record.kind == "SR" else "SR"
    match = re.fullmatch(rf"\[({kind}-\d+)\]\(([^)]+)\)", value)
    if not match or match[1] not in records:
        audit.error(record.path, f"Parent must link to an existing {kind} record")
        return None
    parent = records[match[1]]
    if parent.kind != kind:
        audit.error(record.path, f"Parent record must have type {kind}")
        return None
    if (record.path.parent / match[2]).resolve() != parent.path.resolve():
        audit.error(record.path, "Parent label and link target disagree")
    return parent


def matrix(records):
    lines = [BEGIN,
             "| BR | BR Version | BR Status | SR | SR Version | SR Status | Historical Done / Total | Cancelled |",
             "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"]
    for sr in sorted((r for r in records.values() if r.kind == "SR"), key=lambda r: r.ident):
        match = re.search(r"\[(BR-\d+)\]", sr.get("Parent"))
        br = records.get(match[1]) if match else None
        tasks = [r for r in records.values() if r.kind == "TASK" and r.get("Parent").startswith(f"[{sr.ident}](")]
        done = sum(t.get("Status") == "Done" for t in tasks)
        cancelled = sum(t.get("Status") == "Cancelled" for t in tasks)
        cells = [br.ident if br else "unresolved", br.get("Version") if br else "none",
                 br.get("Status") if br else "none", sr.ident, sr.get("Version"), sr.get("Status"),
                 f"{done} / {len(tasks) - cancelled}", str(cancelled)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines + [END])


COVERAGE_COLUMNS = ["SR criterion", "BR criterion", "Required TASKs", "Verification and integration evidence required"]
DEPENDENCY_COLUMNS = ["Dependency", "Published commit", "Available at", "Compatibility evidence"]
BLOCKER_COLUMNS = ["ID", "State", "Reason", "Resolution evidence"]


def criteria_definitions(record):
    body = sections(record.text).get("Acceptance Criteria", "")
    result = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(rf"- ({re.escape(record.ident)}-AC-\d+): (.+)", line.strip())
        if not match or not present(match[2]):
            raise ValueError("Acceptance Criteria requires '- ID-AC-number: measurable obligation' rows")
        if match[1] in result:
            raise ValueError(f"duplicate criterion {match[1]}")
        result[match[1]] = match[2]
    return result


def coverage_rows(record):
    body = sections(record.text).get("Acceptance Coverage", "")
    return table(body, COVERAGE_COLUMNS) if body else []


def approval_content(record):
    """Conservative contract projection; keep unknown sections and fenced examples.

    Operational metadata is excluded explicitly, never by removing all fields or
    all code blocks. Checkbox completion is administrative; checklist text is not.
    """
    administrative_fields = {
        "Status", "Version", "Revision", "Approved version", "Approved revision",
        "Approved by", "Approved on", "Approval evidence", "Review note",
        "Retirement reason", "Retirement decision", "Superseded by",
        "Cancellation reason", "Cancellation decision", "Verification result",
        "Verification evidence", "Manual acceptance", "Owner", "Branch", "Worktree",
        "Checkpoint", "Blocked reason", "Verified implementation",
        "Verification environment", "Approval reference", "Final checks",
        "Completed on", "Completion commit subject",
    }
    administrative_sections = {"Changelog", "Derived Tasks", "Derived System Requirements"}
    if record.kind in {"TASK", "PLAN"}:
        administrative_sections |= {"Blockers", "Dependency Evidence", "Execution Record", "Completion"}
    text = re.sub(r"<!--[\s\S]*?-->", "", record.text)
    outside_fences = {number for number, _ in prose(text)[0]}
    result, section, skip = [], None, False
    for number, line in enumerate(text.splitlines(), 1):
        if number in outside_fences:
            if line.startswith("## "):
                section = line[3:].strip()
                skip = section in administrative_sections
            if skip:
                continue
            field = re.fullmatch(r"(?:- )?\*\*([^*]+):\*\*\s*(.*)", line)
            if field and ((section is None and field[1] in administrative_fields) or
                          (section == "Verification" and field[1] == "Evidence")):
                continue
            if section == "Acceptance Coverage" and record.kind == "SR":
                # Allocation links are administrative, obligations are not.
                if line.startswith("## "):
                    obligations = [(row["SR criterion"], row["BR criterion"],
                                    row["Verification and integration evidence required"])
                                   for row in coverage_rows(record)]
                    result.append(json.dumps(sorted(obligations), ensure_ascii=False))
                continue
            line = re.sub(r"^(\s*- )\[[ xX]\]", r"\1[ ]", line)
        if not skip and line.strip():
            result.append(line.rstrip())
    return "\n".join(result)


def check_record_history(audit, records, previous):
    """Endpoint checks: approval binding and append-only blocker evidence."""
    for ident, old in previous.items():
        current = records.get(ident)
        work = old.kind in {"TASK", "PLAN"}
        try:
            if work:
                old_body = sections(old.text).get("Blockers", "")
                old_rows = table(old_body, BLOCKER_COLUMNS) if old_body else []
                new_body = sections(current.text).get("Blockers", "") if current else ""
                new_rows = table(new_body, BLOCKER_COLUMNS) if new_body else []
                new_by_id = {row["ID"]: row for row in new_rows}
                for row in old_rows:
                    new = new_by_id.get(row["ID"])
                    path = current.path if current else old.path
                    if new is None:
                        audit.error(path, f"recorded blocker {row['ID']} must not be deleted or renamed")
                    elif new["Reason"] != row["Reason"]:
                        audit.error(path, f"recorded blocker {row['ID']} must preserve its reason")
                    elif row["State"] == "Resolved" and new != row:
                        audit.error(path, f"resolved blocker {row['ID']} is immutable; create a new blocker")
                    elif row["State"] == "Open" and new["State"] == "Resolved" and not present(new["Resolution evidence"]):
                        audit.error(path, f"blocker {row['ID']} resolution requires evidence")
            if current is None:
                if not work and old.get("Status") == "Approved":
                    audit.error(old.path, "approved requirement must be retired, not deleted")
                continue
            revision_key = "Revision" if work else "Version"
            binding_key = "Approved revision" if work else "Approved version"
            pattern = r"[1-9]\d*" if work else r"\d+\.\d+"
            before, after = old.get(revision_key), current.get(revision_key)
            if not re.fullmatch(pattern, before) or not re.fullmatch(pattern, after):
                continue  # Current schema validation reports invalid revisions.
            old_number, new_number = tuple(map(int, before.split("."))), tuple(map(int, after.split(".")))
            if new_number < old_number:
                audit.error(current.path, f"{revision_key} must not decrease relative to comparison baseline")
            was_approved = old.get(binding_key) == before and present(old.get("Approval evidence"))
            if not was_approved:
                continue
            changed = approval_content(old) != approval_content(current)
            if changed and new_number <= old_number:
                audit.error(current.path, f"approval-sensitive content changed without a higher {revision_key}")
            currently_approved = current.get(binding_key) == after
            if (changed or new_number != old_number) and currently_approved and (
                    current.get("Approval evidence") == old.get("Approval evidence")):
                audit.error(current.path, "changed approved contract requires fresh approval evidence for the new revision")
        except ValueError as exc:
            audit.error(current.path if current else old.path, f"history check: {exc}")


def acceptance_matrix(records):
    """Proposed metadata view, deliberately not proof of published acceptance."""
    lines = [ACCEPT_BEGIN,
             "| SR | Version | Required TASKs | Evidence | Current-version result (proposed) |",
             "| :--- | :--- | :--- | :--- | :--- |"]
    for sr in sorted((r for r in records.values() if r.kind == "SR"), key=lambda r: r.ident):
        try:
            rows = coverage_rows(sr)
            definitions = criteria_definitions(sr)
        except ValueError:
            rows, definitions = [], {}
        required = sorted({ident for row in rows for ident in id_list(row["Required TASKs"])})
        complete = bool(definitions) and {row["SR criterion"] for row in rows} == set(definitions)
        complete = complete and all(id_list(row["Required TASKs"]) for row in rows)
        evidence = []
        for ident in required:
            task = records.get(ident)
            valid = (task is not None and task.kind == "TASK" and task.get("Status") == "Done" and
                     task.get("Parent").startswith(f"[{sr.ident}](") and task.get("Parent version") == sr.get("Version") and
                     task.get("Verification result") in {"Passed", "Manual Accepted"} and present(task.get("Verification evidence")))
            complete = complete and valid
            if valid:
                # IDs point to evidence records without copying arbitrary Markdown into a table.
                evidence.append(ident)
        parent_match = re.match(r"\[(BR-\d+)\]", sr.get("Parent"))
        parent = records.get(parent_match[1]) if parent_match else None
        approved = (sr.get("Status") == "Approved" and parent is not None and
                    parent.get("Status") == "Approved" and sr.get("Parent version") == parent.get("Version") and
                    sr.get("Approved version") == sr.get("Version") and
                    parent.get("Approved version") == parent.get("Version"))
        result = "Evidence complete" if complete and approved else "Pending"
        if sr.get("Status") != "Approved":
            result = "Not approved"
        lines.append(f"| {sr.ident} | {sr.get('Version')} | {', '.join(required) or 'none'} | {', '.join(evidence) or 'none'} | {result} |")
    return "\n".join(lines + [ACCEPT_END])


def check_relationships(audit, records, parents, historical):
    for sr in (r for r in records.values() if r.kind == "SR"):
        try:
            definitions = criteria_definitions(sr)
            rows = coverage_rows(sr)
            br = parents.get(sr.ident)
            br_definitions = criteria_definitions(br) if br else {}
            if sr.get("Status") == "Approved" and not definitions:
                audit.error(sr.path, "Approved SR requires Acceptance Criteria")
            # Retired requirements preserve old coverage; current parent links are checked separately.
            if sr.get("Status") in {"Superseded", "Deprecated"}:
                continue
            seen = set()
            for row in rows:
                criterion = row["SR criterion"]
                if criterion in seen or criterion not in definitions:
                    audit.error(sr.path, f"duplicate or undefined coverage criterion: {criterion}")
                seen.add(criterion)
                if row["BR criterion"] not in br_definitions:
                    audit.error(sr.path, f"undefined BR criterion: {row['BR criterion']}")
                if not present(row["Verification and integration evidence required"]):
                    audit.error(sr.path, "coverage requires verification/integration obligations")
                ids = id_list(row["Required TASKs"])
                if len(ids) != len(set(ids)):
                    audit.error(sr.path, "duplicate Required TASKs")
                for ident in ids:
                    task = records.get(ident)
                    if task is None or task.kind != "TASK":
                        audit.error(sr.path, f"missing coverage task {ident}")
                    elif parents.get(ident) != sr or criterion not in id_list(task.get("Acceptance criteria")):
                        audit.error(sr.path, f"nonreciprocal coverage mapping for {ident}")
                    elif task.get("Parent version") != sr.get("Version") or task.get("Status") == "Cancelled":
                        audit.error(sr.path, f"current coverage requires non-cancelled current-version task {ident}")
            if sr.get("Status") == "Approved" and seen != set(definitions):
                audit.error(sr.path, "Approved SR must cover every defined criterion")
            # An approved contract may await task decomposition, but executable tasks may not.
            for task in (r for r in records.values() if r.kind == "TASK" and parents.get(r.ident) == sr):
                if task.ident in historical or task.get("Status") not in {"Ready", "In Progress", "Done"}:
                    continue
                for criterion in id_list(task.get("Acceptance criteria")):
                    if not any(row["SR criterion"] == criterion and task.ident in id_list(row["Required TASKs"]) for row in rows):
                        audit.error(task.path, f"missing reciprocal acceptance mapping for {criterion}")
                if any(not id_list(row["Required TASKs"]) for row in rows):
                    audit.error(task.path, "task approval requires complete acceptance-task allocation")
        except ValueError as exc:
            audit.error(sr.path, str(exc))


def check_execution(audit, record, deps, historical, published_records, execution_baseline):
    """Check current blockers, scoped evidence, and dependency attestations."""
    try:
        parts = sections(record.text)
        blockers = table(parts.get("Blockers", ""), BLOCKER_COLUMNS)
        seen = set()
        unresolved = False
        for row in blockers:
            if not present(row["ID"]) or row["ID"] in seen:
                audit.error(record.path, "blocker IDs must be nonempty and unique")
            seen.add(row["ID"])
            if row["State"] not in {"Open", "Resolved"} or not present(row["Reason"]):
                audit.error(record.path, "invalid blocker state/reason")
            if row["State"] == "Open":
                unresolved = True
            elif not present(row["Resolution evidence"]):
                audit.error(record.path, "resolved blocker requires resolution evidence")
        state = record.get("Status")
        guarded = state in {"Ready", "In Progress", "Done"} and not historical
        if guarded and (unresolved or record.get("Blocked reason") != "none"):
            audit.error(record.path, "execution requires no unresolved blockers and Blocked reason none")
        if state == "Blocked" and not unresolved:
            audit.error(record.path, "Blocked requires an Open blocker row")
        if guarded:
            scope_paths(record)
            for name in ("Rollback Plan", "Execution Record", "Objective" if record.kind == "TASK" else "Behavior and Compatibility"):
                if not present(parts.get(name, "")):
                    audit.error(record.path, f"executable record requires populated {name}")
            verification = parts.get("Verification", "")
            for key in ("Command", "Success"):
                match = re.search(rf"^- \*\*{key}:\*\* (.+)$", verification, re.M)
                if not match or not present(match[1].strip("`")):
                    audit.error(record.path, f"Verification requires populated {key}")
            rows = table(parts.get("Dependency Evidence", ""), DEPENDENCY_COLUMNS)
            if sorted(row["Dependency"] for row in rows) != sorted(deps):
                audit.error(record.path, "Dependency Evidence must match Depends on exactly")
            for row in rows:
                if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", row["Published commit"]):
                    audit.error(record.path, "dependency requires full Published commit SHA")
                if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", row["Available at"]) or not present(row["Compatibility evidence"]):
                    audit.error(record.path, "dependency requires availability and compatibility evidence")
                if execution_baseline is not None:
                    dep = published_records.get(row["Dependency"])
                    if dep is None or dep.get("Status") != "Done":
                        audit.error(record.path, "dependency must be published Done in the execution baseline")
                    else:
                        try:
                            commit = row["Published commit"]
                            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
                                continue
                            git_read(audit.root, "merge-base", "--is-ancestor", commit, execution_baseline)
                            available = row["Available at"]
                            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", available):
                                continue
                            git_read(audit.root, "merge-base", "--is-ancestor", commit, available)
                            git_read(audit.root, "merge-base", "--is-ancestor", available, execution_baseline)
                            saved = git_read(audit.root, "show", f"{commit}:{dep.path.relative_to(audit.root).as_posix()}").decode("utf-8")
                            published = parse_record(audit, dep.path, saved, dep.kind)
                            if published is None or published.ident != dep.ident or published.get("Status") != "Done" or saved != dep.text:
                                audit.error(record.path, "dependency Published commit does not contain its Done record")
                        except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
                            audit.error(record.path, f"dependency publication check failed: {exc}")
        if state == "Done" and not historical:
            for key in ("Final checks", "Approval reference", "Verification environment"):
                if not present(record.get(key)):
                    audit.error(record.path, f"new Done requires {key}")
            if not re.search(r"\b(?:[0-9a-f]{40}|[0-9a-f]{64})\b", record.get("Approval reference")):
                audit.error(record.path, "Approval reference requires a full coordinator/integration SHA")
            if record.get("Verified implementation") != implementation_fingerprint(audit.root, record):
                audit.error(record.path, "Verified implementation does not match scoped files; reverify before completion")
    except (ValueError, OSError) as exc:
        audit.error(record.path, str(exc))


def check_cycles(audit, records, graph):
    # Iterative DFS avoids recursion limits on long task chains.
    colors = {}
    for start in graph:
        if colors.get(start):
            continue
        stack = [(start, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                colors[node] = 2
                continue
            if colors.get(node) == 1:
                audit.error(records[node].path, f"dependency cycle involving {node}")
                continue
            if colors.get(node) == 2:
                continue
            colors[node] = 1
            stack.append((node, True))
            stack.extend((dep, False) for dep in graph.get(node, []) if dep in graph)


def check_findings(audit, records, path, text):
    """Validate the documented findings table and bidirectional remediation IDs."""
    findings = {}
    header = None
    required = {"ID", "Severity", "Confidence", "Evidence", "Impact", "Remediation",
                "Regression risk", "Status", "Required items", "Resolution evidence"}
    for number, line in prose(text)[0]:
        if not line.startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0] == "ID" and "Status" in cells:
            header = cells
            if not required.issubset(header):
                audit.error(path, f"line {number}: findings table is missing required columns")
            continue
        if not cells or not re.fullmatch(r"FIND-\d+", cells[0]):
            continue
        if header is None or len(header) != len(cells):
            audit.error(path, f"line {number}: malformed findings row")
            continue
        row = dict(zip(header, cells))
        ident = row["ID"]
        if ident in findings:
            audit.error(path, f"duplicate finding ID: {ident}")
        items = row.get("Required items", "none")
        ids = [] if items == "none" else [item.strip() for item in items.split(",")]
        findings[ident] = ids
        if len(ids) != len(set(ids)):
            audit.error(path, f"{ident}: duplicate Required items")
        state = row.get("Status")
        if state not in {"Open", "Planned", "Resolved", "Won't Fix"}:
            audit.error(path, f"{ident}: invalid finding status")
        if state in {"Planned", "Resolved"} and not ids:
            audit.error(path, f"{ident}: {state} requires remediation items")
        for item in ids:
            record = records.get(item)
            if record is None or record.kind not in {"PLAN", "TASK"}:
                audit.error(path, f"{ident}: missing work item {item}")
                continue
            if ident not in [value.strip() for value in record.get("Resolves").split(",")]:
                audit.error(path, f"{ident}: {item} missing reciprocal Resolves link")
            if state == "Resolved" and record.get("Status") != "Done":
                audit.error(path, f"{ident}: cannot resolve before {item} is Done")
        if state in {"Resolved", "Won't Fix"} and not present(row.get("Resolution evidence", "")):
            audit.error(path, f"{ident}: {state} requires resolution/decision evidence")
    for record in records.values():
        if record.kind not in {"TASK", "PLAN"}:
            continue
        for ident in references(audit, record, "Resolves", r"FIND-\d+"):
            if ident not in findings or record.ident not in findings[ident]:
                audit.error(record.path, f"{ident}: missing reciprocal findings-log entry")


def validate_specs(root):
    audit = Audit(root)
    names = ("MemBankRules.md", "MemBankRulesWithCDIP.md")
    texts = {}
    for name in names:
        path = audit.root / name
        text = audit.read(path)
        if text is None:
            continue
        texts[name] = text
        audit.markdown(path, text)
        if not re.search(rf"\*\*Specification version:\*\* {re.escape(VERSION)} \(\d{{4}}-\d{{2}}-\d{{2}}\)", text):
            audit.error(path, f"expected specification version {VERSION} and ISO date")
    base = texts.get(names[0], "")
    extension = texts.get(names[1], "")
    if f"**Extends:** MemBankRules.md v{VERSION}." not in extension:
        audit.error(audit.root / names[1], "base version mismatch")
    if f"read the installed\n`MemBankRules.md` specification version {VERSION} in full" not in base:
        audit.error(audit.root / names[0], "missing full-spec base delegation")
    if f"read installed `MemBankRulesWithCDIP.md` specification\nversion {VERSION} in full" not in extension:
        audit.error(audit.root / names[1], "missing full-spec CDIP delegation")
    return audit.errors


def validate_artifacts(root, baseline=None, warnings=None, execution_baseline=None):
    audit = Audit(root)
    records = {}
    previous, resolved_baseline = baseline_records(audit, baseline) if baseline is not None else ({}, None)
    if baseline is not None and audit.errors:
        return audit.errors
    execution_reference = execution_baseline if execution_baseline is not None else ("HEAD" if baseline is not None else None)
    published_records, resolved_execution = baseline_records(audit, execution_reference, "execution") if execution_reference is not None else ({}, None)
    if audit.errors:
        return audit.errors
    if resolved_baseline is not None and resolved_execution is not None:
        try:
            git_read(audit.root, "merge-base", "--is-ancestor", resolved_baseline, resolved_execution)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            audit.error(audit.root, f"comparison baseline must be an ancestor of execution baseline: {exc}")
            return audit.errors
    if baseline is None and warnings is not None:
        warnings.append("No comparison baseline: terminal, approval-content and blocker history were not checked; all Done records are treated as new completion proposals.")
    if execution_reference is None and warnings is not None:
        warnings.append("No execution baseline: dependency publication and availability ancestry were not checked.")
    for kind, folder in FOLDERS.items():
        for path in sorted((audit.root / folder).glob("*.md")):
            text = audit.read(path)
            if text is None:
                continue
            audit.markdown(path, text)
            record = parse_record(audit, path, text, kind)
            if record:
                if record.ident in records:
                    audit.error(path, f"duplicate ID: {record.ident}")
                else:
                    records[record.ident] = record
    check_record_history(audit, records, previous)
    historical = set()
    for ident, old in previous.items():
        if old.kind not in {"TASK", "PLAN"} or old.get("Status") not in {"Done", "Cancelled"}:
            continue
        current = records.get(ident)
        if current is None or current.path != old.path or current.text != old.text:
            audit.error(old.path, "historical terminal record must remain unchanged; use a separate correction/follow-up record")
        else:
            historical.add(ident)
    if not records:
        audit.error(audit.root, "no protocol artifacts found")
        return audit.errors
    parents, graph = {}, {}
    for record in records.values():
        state = record.get("Status")
        work = record.kind in {"TASK", "PLAN"}
        require(audit, record, ["Status", "Approved by", "Approved on", "Approval evidence"])
        if state not in (WORK_STATES if work else REQ_STATES):
            audit.error(record.path, f"invalid Status: {state}")
        if not work:
            require(audit, record, ["Version", "Approved version"])
            if not re.fullmatch(r"\d+\.\d+", record.get("Version")):
                audit.error(record.path, "Version must be major.minor")
            if state == "Approved":
                approve(audit, record, "Version", "Approved version")
            elif any(record.get(key) != "none" for key in ("Approved version", "Approved by", "Approved on", "Approval evidence")):
                audit.error(record.path, "non-approved requirement must clear current approval fields to none")
        else:
            require(audit, record, ["Revision", "Approved revision", "Depends on", "Resolves",
                                   "Verification result", "Verification evidence", "Manual acceptance", "Owner", "Branch", "Worktree",
                                   "Checkpoint", "Blocked reason", "Review note", "Completed on", "Completion commit subject"])
            if record.ident not in historical:
                require(audit, record, ["Cancellation reason", "Cancellation decision", "Verified implementation",
                                       "Final checks", "Approval reference", "Verification environment"])
            if state == "Cancelled" and record.ident not in historical:
                for key in ("Cancellation reason", "Cancellation decision"):
                    if not present(record.get(key)):
                        audit.error(record.path, f"Cancelled requires {key}")
            if not re.fullmatch(r"[1-9]\d*", record.get("Revision")):
                audit.error(record.path, "Revision must be a positive integer")
            if state in {"Ready", "In Progress", "Done"}:
                approve(audit, record, "Revision", "Approved revision")
            elif present(record.get("Approved revision")):
                approve(audit, record, "Revision", "Approved revision")
            elif any(record.get(key) != "none" for key in ("Approved revision", "Approved by", "Approved on", "Approval evidence")):
                audit.error(record.path, "unapproved plan must clear all approval fields to none")
            verification = record.get("Verification result")
            if verification not in VERIFICATIONS:
                audit.error(record.path, f"invalid Verification result: {verification}")
            deps = references(audit, record, "Depends on", r"TASK-\d+[A-Z]*" if record.kind == "TASK" else r"PLAN-\d+")
            graph[record.ident] = deps
            if record.ident not in historical:
                check_execution(audit, record, deps, False, published_records, resolved_execution)
            for dep in deps:
                if dep == record.ident:
                    audit.error(record.path, "self-dependency")
                if dep not in records:
                    audit.error(record.path, f"missing dependency {dep}")
                elif state in {"Ready", "In Progress", "Done"} and records[dep].get("Status") != "Done":
                    audit.error(record.path, f"dependency {dep} is not Done")
            if state == "Blocked" and not present(record.get("Blocked reason")):
                audit.error(record.path, "Blocked requires a reason")
            if state in {"In Progress", "Done"}:
                for key in ("Owner", "Branch", "Worktree", "Checkpoint"):
                    if not present(record.get(key)):
                        audit.error(record.path, f"{state} requires {key}")
                if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", record.get("Checkpoint")):
                    audit.error(record.path, "Checkpoint must be a full Git SHA")
            for heading in ("## Scope (files)", "## Execution Record", "## Completion", "## Rollback Plan"):
                if heading not in record.text:
                    audit.error(record.path, f"missing section {heading}")
            if state == "Done":
                if not present(record.get("Verification evidence")):
                    audit.error(record.path, "Done requires Verification evidence")
                if verification not in {"Passed", "Manual Accepted"}:
                    audit.error(record.path, "Done requires Passed or Manual Accepted verification")
                if verification == "Manual Accepted" and not present(record.get("Manual acceptance")):
                    audit.error(record.path, "Manual Accepted requires explicit acceptance evidence")
                if not iso_date(record.get("Completed on")):
                    audit.error(record.path, "Done requires ISO Completed on date")
                subject = record.get("Completion commit subject")
                if record.ident not in subject or (record.kind == "TASK" and not subject.startswith(record.ident + ": ")):
                    audit.error(record.path, "completion subject must reference ID and use TASK prefix when applicable")
                if re.search(r"^\s*- \[ \]", "\n".join(line for _, line in prose(record.text)[0]), re.M):
                    audit.error(record.path, "Done has unchecked checklist items")
        if record.kind in {"SR", "TASK"}:
            require(audit, record, ["Parent", "Parent version"])
            parents[record.ident] = parent_of(audit, record, records)
        if record.kind == "TASK":
            require(audit, record, ["Acceptance criteria"])
            criteria = references(audit, record, "Acceptance criteria", r"SR-\d+-AC-\d+")
            if not criteria:
                audit.error(record.path, "TASK must map at least one acceptance criterion")
            parent = parents.get(record.ident)
            for criterion in criteria:
                if parent and record.ident not in historical and record.get("Status") in {"Ready", "In Progress", "Done"}:
                    try:
                        if criterion not in criteria_definitions(parent):
                            audit.error(record.path, f"criterion not defined by parent: {criterion}")
                    except ValueError as exc:
                        audit.error(parent.path, str(exc))
        if record.kind in {"BR", "SR"}:
            require(audit, record, ["Retirement reason", "Retirement decision", "Superseded by"])
            if state in {"Superseded", "Deprecated"}:
                for key in ("Retirement reason", "Retirement decision"):
                    if not present(record.get(key)):
                        audit.error(record.path, f"{state} requires {key}")
                if state == "Superseded":
                    successor = records.get(record.get("Superseded by"))
                    if successor is None or successor.kind != record.kind or successor.ident == record.ident:
                        audit.error(record.path, "Superseded by must identify a different existing requirement of the same kind")
            if record.kind == "BR" and state == "Approved":
                try:
                    if not criteria_definitions(record):
                        audit.error(record.path, "Approved BR requires Acceptance Criteria")
                except ValueError as exc:
                    audit.error(record.path, str(exc))
    # Only unchanged committed terminal records receive historical exemptions.
    for record in records.values():
        if not ((record.kind == "SR" and record.get("Status") == "Approved") or
                (record.kind == "TASK" and record.get("Status") in {"Ready", "In Progress", "Done"} and record.ident not in historical)):
            continue
        current = record
        while current.kind in {"SR", "TASK"}:
            parent = parents.get(current.ident)
            if parent is None:
                audit.error(record.path, "execution/approval requires a resolved parent chain")
                break
            if parent.get("Status") != "Approved" or current.get("Parent version") != parent.get("Version"):
                audit.error(record.path, f"invalid current approval chain at {parent.ident}")
            current = parent
    check_cycles(audit, records, graph)
    successor_graph = {r.ident: [r.get("Superseded by")] for r in records.values()
                       if r.kind in {"BR", "SR"} and r.get("Status") == "Superseded"
                       and r.get("Superseded by") in records}
    check_cycles(audit, records, successor_graph)
    check_relationships(audit, records, parents, historical)
    cdip = any(r.kind != "PLAN" for r in records.values())
    summary_paths = [audit.root / "memory-bank/progress.md"]
    if cdip:
        summary_paths.append(audit.root / "requirements/README.md")
    for path in summary_paths:
        text = audit.read(path)
        if text is None:
            continue
        audit.markdown(path, text)
        if path == audit.root / "memory-bank/progress.md":
            check_findings(audit, records, path, text)
        if cdip:
            for begin, end, expected, label in (
                (BEGIN, END, matrix(records), "derived requirements"),
                (ACCEPT_BEGIN, ACCEPT_END, acceptance_matrix(records), "current acceptance"),
            ):
                blocks = re.findall(re.escape(begin) + r"[\s\S]*?" + re.escape(end), text)
                if len(blocks) != 1 or blocks[0] != expected or text.count(begin) != 1 or text.count(end) != 1:
                    audit.error(path, f"missing, duplicate, or stale {label} block")
    return audit.errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--specs", type=Path, metavar="ROOT", help="check the two English specification files")
    mode.add_argument("--artifacts", type=Path, metavar="ROOT", help="check installed PLAN/BR/SR/TASK records and summaries")
    parser.add_argument("--baseline", help="ancestor Git commit for terminal, approval-content and blocker-history comparison")
    parser.add_argument("--execution-baseline", help="accepted published execution commit; defaults to HEAD when --baseline is supplied")
    parser.add_argument("--fingerprint", type=Path, metavar="RECORD", help="print scoped implementation fingerprint only (path relative to artifact root)")
    args = parser.parse_args(argv)
    if (args.baseline or args.execution_baseline or args.fingerprint) and args.artifacts is None:
        parser.error("--baseline, --execution-baseline and --fingerprint require --artifacts")
    if args.fingerprint and (args.baseline or args.execution_baseline):
        parser.error("--fingerprint cannot be combined with baseline options")
    if args.fingerprint:
        audit = Audit(args.artifacts)
        path = (audit.root / args.fingerprint).resolve()
        text = audit.read(path)
        kind = next((key for key in ("TASK", "PLAN") if path.name.startswith(key + "-")), None)
        record = parse_record(audit, path, text, kind) if text is not None and kind else None
        try:
            if record is None or audit.errors:
                raise ValueError("fingerprint requires a valid TASK or PLAN record within the root")
            print(implementation_fingerprint(audit.root, record))
            return 0
        except (ValueError, OSError) as exc:
            print(f"FAILED: {exc}", file=sys.stderr)
            return 1
    warnings = []
    errors = validate_specs(args.specs) if args.specs is not None else validate_artifacts(args.artifacts, args.baseline, warnings, args.execution_baseline)
    for warning in warnings:
        print("WARNING: " + warning, file=sys.stderr)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(f"FAILED: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("PASS: structural protocol checks (semantic review still required)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
