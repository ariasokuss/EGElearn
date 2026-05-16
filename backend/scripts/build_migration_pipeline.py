"""Build and display the Alembic migration pipeline.

Parses all migration files in alembic/versions/, builds the dependency DAG,
topologically sorts it, and outputs the ordered pipeline with diagnostics.

Usage:
    uv run python scripts/build_migration_pipeline.py
    uv run python scripts/build_migration_pipeline.py --format json
    uv run python scripts/build_migration_pipeline.py --format dot
    uv run python scripts/build_migration_pipeline.py --check
"""

import ast
import json
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

VERSIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"


@dataclass
class Migration:
    revision: str
    down_revision: Optional[str | tuple]
    branch_labels: Optional[str | tuple]
    depends_on: Optional[str | tuple]
    message: str
    create_date: str
    filename: str
    is_merge: bool = False

    @property
    def parents(self) -> list[str]:
        if self.down_revision is None:
            return []
        if isinstance(self.down_revision, tuple):
            return list(self.down_revision)
        return [self.down_revision]


def _extract_string_value(node: ast.expr) -> Optional[str | tuple]:
    """Extract a string, None, or tuple of strings from an AST node."""
    if isinstance(node, ast.Constant):
        return node.value  # str or None
    if isinstance(node, ast.Tuple):
        values = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.append(elt.value)
        return tuple(values) if values else None
    return None


def parse_migration(path: Path) -> Migration:
    source = path.read_text()
    tree = ast.parse(source)

    revision = down_revision = branch_labels = depends_on = None

    for node in ast.walk(tree):
        # Handle both plain assignments and annotated assignments (x: Type = value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    value = node.value
                    break
            else:
                continue
        else:
            continue

        if value is None:
            continue
        if name == "revision":
            revision = _extract_string_value(value)
        elif name == "down_revision":
            down_revision = _extract_string_value(value)
        elif name == "branch_labels":
            branch_labels = _extract_string_value(value)
        elif name == "depends_on":
            depends_on = _extract_string_value(value)

    # Extract message and create_date from the docstring
    message = ""
    create_date = ""
    docstring_match = re.search(r'"""(.*?)"""', source, re.DOTALL)
    if docstring_match:
        doc = docstring_match.group(1)
        lines = [l.strip() for l in doc.strip().splitlines()]
        if lines:
            message = lines[0]
        date_match = re.search(r"Create Date:\s*(.+)", doc)
        if date_match:
            create_date = date_match.group(1).strip()

    # A migration is a merge if both upgrade() and downgrade() are pass-only
    is_merge = isinstance(down_revision, tuple)

    return Migration(
        revision=revision or path.stem.split("_")[0],
        down_revision=down_revision,
        branch_labels=branch_labels,
        depends_on=depends_on,
        message=message,
        create_date=create_date,
        filename=path.name,
        is_merge=is_merge,
    )


def load_all_migrations(versions_dir: Path = VERSIONS_DIR) -> dict[str, Migration]:
    migrations: dict[str, Migration] = {}
    for path in sorted(versions_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        m = parse_migration(path)
        if m.revision:
            migrations[m.revision] = m
    return migrations


def build_dag(migrations: dict[str, Migration]) -> dict[str, list[str]]:
    """Return adjacency list: revision -> [children revisions]."""
    children: dict[str, list[str]] = defaultdict(list)
    for rev, m in migrations.items():
        for parent in m.parents:
            children[parent].append(rev)
    return children


def topological_sort(migrations: dict[str, Migration]) -> list[Migration]:
    """Kahn's algorithm for topological sort of the migration DAG."""
    in_degree: dict[str, int] = defaultdict(int)
    children = build_dag(migrations)

    for rev in migrations:
        in_degree.setdefault(rev, 0)
        for child in children.get(rev, []):
            in_degree[child] += 1

    # Roots = migrations with no parents that exist in our set
    queue = deque(
        sorted(
            [rev for rev, deg in in_degree.items() if deg == 0],
            key=lambda r: migrations[r].create_date,
        )
    )
    ordered: list[Migration] = []

    while queue:
        rev = queue.popleft()
        if rev not in migrations:
            continue
        ordered.append(migrations[rev])
        for child in sorted(children.get(rev, []), key=lambda r: migrations.get(r, Migration("", None, None, None, "", "", "")).create_date):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    return ordered


def find_heads(migrations: dict[str, Migration], children: dict[str, list[str]]) -> list[str]:
    """Revisions that have no children = current heads."""
    return [rev for rev in migrations if not children.get(rev)]


def find_roots(migrations: dict[str, Migration]) -> list[str]:
    """Revisions with no parents = initial migrations."""
    return [rev for rev, m in migrations.items() if not m.parents]


def diagnose(migrations: dict[str, Migration]) -> list[str]:
    """Return a list of diagnostic warnings."""
    issues: list[str] = []
    known = set(migrations.keys())

    for rev, m in migrations.items():
        for parent in m.parents:
            if parent not in known:
                issues.append(f"  [missing parent] {rev[:8]} references unknown revision {parent[:8]}")

    children = build_dag(migrations)
    heads = find_heads(migrations, children)
    if len(heads) > 1:
        issues.append(f"  [multiple heads] {len(heads)} branch heads detected — a merge migration may be needed")
        for h in heads:
            issues.append(f"    -> {h[:8]}  {migrations[h].message}")

    roots = find_roots(migrations)
    if len(roots) > 1:
        issues.append(f"  [multiple roots] {len(roots)} root migrations (expected 1)")

    return issues


# ── Output formats ────────────────────────────────────────────────────────────

def format_text(ordered: list[Migration], migrations: dict[str, Migration]) -> str:
    children = build_dag(migrations)
    heads = set(find_heads(migrations, children))
    roots = set(find_roots(migrations))

    lines = ["Migration Pipeline", "=" * 80]
    for i, m in enumerate(ordered, 1):
        tags = []
        if m.revision in roots:
            tags.append("ROOT")
        if m.revision in heads:
            tags.append("HEAD")
        if m.is_merge:
            tags.append("MERGE")

        tag_str = f"  [{', '.join(tags)}]" if tags else ""
        connector = "┌" if m.revision in roots else ("└" if m.revision in heads else "├")
        parents_str = ""
        if m.parents:
            parents_str = f"  ← {', '.join(p[:8] for p in m.parents)}"

        lines.append(
            f"{i:>3}. {connector} {m.revision[:8]}  {m.message[:55]:<55}{tag_str}{parents_str}"
        )
        if m.create_date:
            lines.append(f"       │  {m.create_date[:19]}  {m.filename}")
        else:
            lines.append(f"       │  {m.filename}")

    lines.append("=" * 80)
    lines.append(f"Total: {len(ordered)} migrations")
    return "\n".join(lines)


def format_json(ordered: list[Migration]) -> str:
    data = [
        {
            "index": i,
            "revision": m.revision,
            "down_revision": m.down_revision,
            "message": m.message,
            "create_date": m.create_date,
            "filename": m.filename,
            "is_merge": m.is_merge,
            "parents": m.parents,
        }
        for i, m in enumerate(ordered, 1)
    ]
    return json.dumps(data, indent=2)


def format_dot(ordered: list[Migration], migrations: dict[str, Migration]) -> str:
    children = build_dag(migrations)
    heads = set(find_heads(migrations, children))
    roots = set(find_roots(migrations))

    lines = ["digraph migrations {", '    rankdir=TB;', '    node [shape=box fontname="monospace" fontsize=10];']
    for m in ordered:
        label = f"{m.revision[:8]}\\n{m.message[:40]}"
        attrs = [f'label="{label}"']
        if m.revision in heads:
            attrs.append("color=green style=filled fillcolor=lightgreen")
        elif m.revision in roots:
            attrs.append("color=blue style=filled fillcolor=lightblue")
        elif m.is_merge:
            attrs.append("color=orange style=filled fillcolor=lightyellow")
        lines.append(f'    "{m.revision[:8]}" [{" ".join(attrs)}];')

    for m in ordered:
        for parent in m.parents:
            p = parent[:8]
            lines.append(f'    "{p}" -> "{m.revision[:8]}";')

    lines.append("}")
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--format", choices=["text", "json", "dot"], default="text", help="Output format (default: text)")
    parser.add_argument("--check", action="store_true", help="Exit with non-zero status if issues are found")
    parser.add_argument("--versions-dir", type=Path, default=VERSIONS_DIR, help="Path to alembic/versions/")
    args = parser.parse_args()

    versions_dir = args.versions_dir

    if not versions_dir.is_dir():
        print(f"Error: versions directory not found: {versions_dir}", file=sys.stderr)
        sys.exit(1)

    migrations = load_all_migrations(versions_dir)
    if not migrations:
        print("No migration files found.", file=sys.stderr)
        sys.exit(1)

    ordered = topological_sort(migrations)
    issues = diagnose(migrations)

    if args.format == "json":
        print(format_json(ordered))
    elif args.format == "dot":
        print(format_dot(ordered, migrations))
    else:
        print(format_text(ordered, migrations))

    if issues:
        print("\nDiagnostics:", file=sys.stderr)
        for issue in issues:
            print(issue, file=sys.stderr)
        if args.check:
            sys.exit(1)


if __name__ == "__main__":
    main()
