#!/usr/bin/env python3
"""
P6 Schema Parser - CLI utility for parsing Oracle P6 EPPM schema files.

Supports EPPM (pmSchema.xml) and PPM (ppmSchema.xml) formats.
"""

import argparse
import json
import csv
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# Default schema directory (relative to this script)
DEFAULT_SCHEMA_DIR = Path(__file__).parent / "schemas"

# Config file location (in the tool's root directory)
CONFIG_FILE = Path(__file__).parent / ".p6schemarc"


def load_config() -> dict:
    """Load configuration from .p6schemarc file."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict) -> None:
    """Save configuration to .p6schemarc file."""
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


def get_default_schema() -> Optional[str]:
    """Get the default schema from config, or None if not set."""
    config = load_config()
    return config.get("default_schema")


@dataclass
class SchemaEntry:
    """Registry entry for a schema file."""
    application: str  # eppm or ppm
    version: str      # e.g., "24.12"
    path: Path

    @property
    def key(self) -> str:
        """Return the registry key (app:version)."""
        return f"{self.application}:{self.version}"

    @property
    def display_name(self) -> str:
        """Return human-readable name."""
        app_name = "EPPM" if self.application == "eppm" else "PPM"
        return f"{app_name} {self.version}"


class SchemaRegistry:
    """Registry of available P6 schema files."""

    # Pattern to match schema filenames: eppm_24_12_schema.xml or ppm_23_04_schema.xml
    FILENAME_PATTERN = re.compile(r"^(eppm|ppm)_(\d{2})_(\d{2})_schema\.xml$", re.IGNORECASE)

    def __init__(self, schema_dir: Optional[Path] = None):
        self.schema_dir = schema_dir or DEFAULT_SCHEMA_DIR
        self._entries: dict[str, SchemaEntry] = {}
        self._scan()

    def _scan(self) -> None:
        """Scan schema directory and populate registry."""
        if not self.schema_dir.exists():
            return

        for path in self.schema_dir.iterdir():
            if not path.is_file():
                continue

            match = self.FILENAME_PATTERN.match(path.name)
            if match:
                app = match.group(1).lower()
                major = match.group(2)
                minor = match.group(3)
                version = f"{major}.{minor}"

                entry = SchemaEntry(application=app, version=version, path=path)
                self._entries[entry.key] = entry

    def get(self, specifier: str) -> Optional[SchemaEntry]:
        """Get schema entry by specifier (app:version)."""
        # Normalize the specifier
        specifier = specifier.lower().strip()

        # Handle version-only specifier (assumes eppm)
        if ":" not in specifier and re.match(r"^\d{2}\.\d{2}$", specifier):
            specifier = f"eppm:{specifier}"

        return self._entries.get(specifier)

    def list_all(self) -> list[SchemaEntry]:
        """List all registered schemas, sorted by app then version."""
        return sorted(
            self._entries.values(),
            key=lambda e: (e.application, e.version)
        )

    def list_by_app(self, application: str) -> list[SchemaEntry]:
        """List schemas for a specific application."""
        app = application.lower()
        return sorted(
            [e for e in self._entries.values() if e.application == app],
            key=lambda e: e.version
        )

    @property
    def available_keys(self) -> list[str]:
        """Return list of available schema keys."""
        return sorted(self._entries.keys())

    def get_latest(self, application: str = "eppm") -> Optional[SchemaEntry]:
        """Get the latest version for an application."""
        entries = self.list_by_app(application)
        return entries[-1] if entries else None


# Global registry instance
_registry: Optional[SchemaRegistry] = None


def get_registry() -> SchemaRegistry:
    """Get or create the global schema registry."""
    global _registry
    if _registry is None:
        _registry = SchemaRegistry()
    return _registry


def resolve_schema_path(specifier: Optional[str] = None) -> Path:
    """
    Resolve a schema specifier to a file path.

    Accepts:
    - None: Use config default, or latest EPPM version
    - File path: "./schemas/eppm_24_12_schema.xml"
    - Registry key: "eppm:24.12"
    - Version only: "24.12" (assumes EPPM)

    Returns Path to schema file.
    Raises ValueError if not found.
    """
    registry = get_registry()

    # If no specifier, check config for default schema
    if not specifier:
        specifier = get_default_schema()

    # Still no specifier - use latest EPPM
    if not specifier:
        latest = registry.get_latest("eppm")
        if latest:
            return latest.path
        raise ValueError(
            f"No EPPM schemas found in registry. "
            f"Provide a file path or add schemas to: {DEFAULT_SCHEMA_DIR}"
        )

    # Check if it looks like a file path
    path = Path(specifier)
    if path.suffix == ".xml" or "/" in specifier or "\\" in specifier:
        if path.exists():
            return path
        raise ValueError(f"Schema file not found: {specifier}")

    # Try registry lookup
    entry = registry.get(specifier)

    if entry:
        return entry.path

    # Not found - provide helpful error
    available = registry.available_keys
    if available:
        raise ValueError(
            f"Schema '{specifier}' not found. Available: {', '.join(available)}"
        )
    else:
        raise ValueError(
            f"Schema '{specifier}' not found and no schemas in registry. "
            f"Provide a file path or add schemas to: {DEFAULT_SCHEMA_DIR}"
        )


@dataclass
class Field:
    name: str
    datatype: str
    charlength: str = ""
    dataprecision: str = ""
    datascale: str = ""
    notnull: str = "N"
    default: str = ""
    description: str = ""
    idcolumn: str = "N"

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Field":
        return cls(
            name=elem.get("NAME", ""),
            datatype=elem.get("DATATYPE", ""),
            charlength=elem.get("CHARLENGTH", ""),
            dataprecision=elem.get("DATAPRECISION", ""),
            datascale=elem.get("DATASCALE", ""),
            notnull=elem.get("NOTNULL", "N"),
            default=elem.get("DEFAULT", ""),
            description=elem.get("DESC", ""),
            idcolumn=elem.get("IDCOLUMN", "N"),
        )


@dataclass
class Index:
    name: str
    fields: str
    uniqueness: str = "NONUNIQUE"
    tablespace: str = ""

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Index":
        return cls(
            name=elem.get("NAME", ""),
            fields=elem.get("FIELD", ""),
            uniqueness=elem.get("UNIQUENESS", "NONUNIQUE"),
            tablespace=elem.get("TABLESPACE", ""),
        )


@dataclass
class Constraint:
    name: str
    type: str
    fields: str
    target_table: str = ""
    target_fields: str = ""
    delete_rule: str = ""

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Constraint":
        return cls(
            name=elem.get("NAME", ""),
            type=elem.get("TYPE", ""),
            fields=elem.get("FIELDS", ""),
            target_table=elem.get("TARGETTABLE", ""),
            target_fields=elem.get("TARGETFIELDS", ""),
            delete_rule=elem.get("DELETERULE", ""),
        )


@dataclass
class Trigger:
    name: str
    set_type: str
    target: str = ""
    description: str = ""

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Trigger":
        return cls(
            name=elem.get("NAME", ""),
            set_type=elem.get("SET", ""),
            target=elem.get("TARGET", ""),
            description=elem.get("DESC", ""),
        )


@dataclass
class Table:
    name: str
    description: str = ""
    title: str = ""
    tabletype: str = "NORMAL"
    tablespace: str = ""
    ordinal: str = ""
    fields: list = field(default_factory=list)
    indexes: list = field(default_factory=list)
    constraints: list = field(default_factory=list)
    triggers: list = field(default_factory=list)

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "Table":
        table = cls(
            name=elem.get("NAME", ""),
            description=elem.get("DESC", ""),
            title=elem.get("TITLE", ""),
            tabletype=elem.get("TABLETYPE", "NORMAL"),
            tablespace=elem.get("TABLESPACE", ""),
            ordinal=elem.get("ORDINAL", ""),
        )
        for child in elem:
            if child.tag == "FIELD":
                table.fields.append(Field.from_xml(child))
            elif child.tag == "INDEX":
                table.indexes.append(Index.from_xml(child))
            elif child.tag == "CONSTRAINT":
                table.constraints.append(Constraint.from_xml(child))
            elif child.tag == "TRIGGER":
                table.triggers.append(Trigger.from_xml(child))
        return table


@dataclass
class Schema:
    version: str
    dbtype: str
    build_version: str
    min_pro_version: str = ""
    tables: dict = field(default_factory=dict)
    source_path: str = ""

    @classmethod
    def from_xml(cls, path_or_specifier: str) -> "Schema":
        """
        Load schema from file path or registry specifier.

        Args:
            path_or_specifier: File path or registry key (e.g., "eppm:24.12")
        """
        path = resolve_schema_path(path_or_specifier)
        tree = ET.parse(path)
        root = tree.getroot()

        schema = cls(
            version=root.get("VERSION", ""),
            dbtype=root.get("DBTYPE", ""),
            build_version=root.get("BUILD_VERSION_ID", ""),
            min_pro_version=root.get("MIN_PRO_VERSION", ""),
            source_path=str(path),
        )

        for table_elem in root.findall("TABLE"):
            table = Table.from_xml(table_elem)
            schema.tables[table.name] = table

        return schema

    def get_table(self, name: str) -> Optional[Table]:
        return self.tables.get(name.upper())

    def search_tables(self, pattern: str) -> list:
        pattern = pattern.upper()
        return [t for name, t in self.tables.items() if pattern in name]

    def search_fields(self, pattern: str) -> list:
        pattern = pattern.upper()
        results = []
        for table in self.tables.values():
            for f in table.fields:
                if pattern in f.name.upper():
                    results.append((table.name, f))
        return results

    def search_relationships(self, pattern: str) -> list:
        """Search foreign key relationships by table name, field, or constraint name."""
        pattern = pattern.upper()
        results = []
        for table in self.tables.values():
            for c in table.constraints:
                if c.type != "FOREIGN":
                    continue
                # Match against source table, target table, fields, or constraint name
                if (pattern in table.name.upper() or
                    pattern in c.target_table.upper() or
                    pattern in c.fields.upper() or
                    pattern in c.target_fields.upper() or
                    pattern in c.name.upper()):
                    results.append({
                        "source_table": table.name,
                        "constraint": c.name,
                        "fields": c.fields,
                        "target_table": c.target_table,
                        "target_fields": c.target_fields,
                    })
        return results


def cmd_list(args):
    """List available schemas in the registry."""
    registry = get_registry()
    entries = registry.list_all()

    if not entries:
        print(f"No schemas found in: {registry.schema_dir}")
        print("\nTo add schemas, place files matching pattern:")
        print("  eppm_YY_MM_schema.xml  (e.g., eppm_24_12_schema.xml)")
        print("  ppm_YY_MM_schema.xml   (e.g., ppm_23_04_schema.xml)")
        return

    if args.format == "json":
        data = [
            {
                "key": e.key,
                "application": e.application.upper(),
                "version": e.version,
                "path": str(e.path),
            }
            for e in entries
        ]
        print(json.dumps(data, indent=2))
    else:
        print(f"Available Schemas ({len(entries)}):")
        print(f"  {'Key':<15} {'Application':<10} {'Version':<10} Path")
        print("  " + "-" * 70)
        for e in entries:
            app_display = e.application.upper()
            print(f"  {e.key:<15} {app_display:<10} {e.version:<10} {e.path}")
        print()
        print("Usage: p6schema <command> <key>")
        print("  Example: p6schema info eppm:24.12")
        print("  Example: p6schema tables ppm:23.04")


def cmd_info(args):
    """Show schema information."""
    schema = Schema.from_xml(args.schema)
    print(f"Schema Information:")
    print(f"  Version:       {schema.version}")
    print(f"  DB Type:       {schema.dbtype}")
    print(f"  Build Version: {schema.build_version}")
    if schema.min_pro_version:
        print(f"  Min Pro Ver:   {schema.min_pro_version}")
    print(f"  Tables:        {len(schema.tables)}")
    print(f"  Source:        {schema.source_path}")


def cmd_tables(args):
    """List all tables."""
    schema = Schema.from_xml(args.schema)
    tables = sorted(schema.tables.values(), key=lambda t: t.name)

    if args.format == "json":
        data = [{"name": t.name, "description": t.description, "fields": len(t.fields)} for t in tables]
        print(json.dumps(data, indent=2))
    elif args.format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(["name", "description", "field_count"])
        for t in tables:
            writer.writerow([t.name, t.description, len(t.fields)])
    else:
        print(f"{'Table Name':<40} {'Fields':>6}  Description")
        print("-" * 80)
        for t in tables:
            desc = t.description[:30] + "..." if len(t.description) > 30 else t.description
            print(f"{t.name:<40} {len(t.fields):>6}  {desc}")


def cmd_describe(args):
    """Describe a table."""
    schema = Schema.from_xml(args.schema)
    table = schema.get_table(args.table)

    if not table:
        print(f"Table '{args.table}' not found.")
        sys.exit(1)

    if args.format == "json":
        data = {
            "name": table.name,
            "description": table.description,
            "title": table.title,
            "tablespace": table.tablespace,
            "fields": [asdict(f) for f in table.fields],
            "indexes": [asdict(i) for i in table.indexes],
            "constraints": [asdict(c) for c in table.constraints],
            "triggers": [asdict(t) for t in table.triggers],
        }
        print(json.dumps(data, indent=2))
        return

    print(f"\nTable: {table.name}")
    if table.title:
        print(f"Title: {table.title}")
    if table.description:
        print(f"Description: {table.description}")
    print(f"Tablespace: {table.tablespace}")

    print(f"\nFields ({len(table.fields)}):")
    print(f"  {'Name':<35} {'Type':<12} {'Length':<8} {'Null':<5} Description")
    print("  " + "-" * 90)
    for f in table.fields:
        length = f.charlength or f.dataprecision or ""
        nullable = "NULL" if f.notnull != "Y" else "NOT NULL"
        desc = f.description[:35] + "..." if len(f.description) > 35 else f.description
        print(f"  {f.name:<35} {f.datatype:<12} {length:<8} {nullable:<8} {desc}")

    if table.indexes:
        print(f"\nIndexes ({len(table.indexes)}):")
        for i in table.indexes:
            print(f"  {i.name}: {i.fields} ({i.uniqueness})")

    if table.constraints:
        print(f"\nConstraints ({len(table.constraints)}):")
        for c in table.constraints:
            if c.type == "PRIMARY":
                print(f"  PK: {c.name} ({c.fields})")
            elif c.type == "FOREIGN":
                print(f"  FK: {c.name} ({c.fields}) -> {c.target_table}({c.target_fields})")
            else:
                print(f"  {c.type}: {c.name} ({c.fields})")


def cmd_relationships(args):
    """Show table relationships (foreign keys)."""
    schema = Schema.from_xml(args.schema)
    table = schema.get_table(args.table)

    if not table:
        print(f"Table '{args.table}' not found.")
        sys.exit(1)

    # Outgoing: tables this table references
    outgoing = []
    for c in table.constraints:
        if c.type == "FOREIGN":
            outgoing.append({
                "constraint": c.name,
                "fields": c.fields,
                "references_table": c.target_table,
                "references_fields": c.target_fields,
            })

    # Incoming: tables that reference this table
    incoming = []
    for other_table in schema.tables.values():
        if other_table.name == table.name:
            continue
        for c in other_table.constraints:
            if c.type == "FOREIGN" and c.target_table.upper() == table.name.upper():
                incoming.append({
                    "table": other_table.name,
                    "constraint": c.name,
                    "fields": c.fields,
                    "references_fields": c.target_fields,
                })

    if args.format == "json":
        data = {
            "table": table.name,
            "outgoing": outgoing,
            "incoming": incoming,
        }
        print(json.dumps(data, indent=2))
        return

    print(f"\nRelationships for: {table.name}")
    print(f"{'=' * 60}")

    # Outgoing relationships
    print(f"\nReferences ({len(outgoing)}):")
    if outgoing:
        print(f"  {'This Table':<25} {'Referenced Table':<25} Fields")
        print("  " + "-" * 70)
        for rel in sorted(outgoing, key=lambda r: r["references_table"]):
            print(f"  {rel['fields']:<25} -> {rel['references_table']:<25} ({rel['references_fields']})")
    else:
        print("  (none)")

    # Incoming relationships
    print(f"\nReferenced By ({len(incoming)}):")
    if incoming:
        print(f"  {'Referencing Table':<25} {'Fields':<25} This Table")
        print("  " + "-" * 70)
        for rel in sorted(incoming, key=lambda r: r["table"]):
            print(f"  {rel['table']:<25} {rel['fields']:<25} -> {rel['references_fields']}")
    else:
        print("  (none)")

    # Summary
    print(f"\nSummary:")
    print(f"  References {len(outgoing)} table(s)")
    print(f"  Referenced by {len(incoming)} table(s)")


def cmd_search(args):
    """Search for tables, fields, relationships, or all."""
    schema = Schema.from_xml(args.schema)
    search_type = args.type

    # Collect results based on type
    table_results = []
    field_results = []
    rel_results = []

    if search_type in ("table", "all"):
        table_results = schema.search_tables(args.pattern)

    if search_type in ("field", "all"):
        field_results = schema.search_fields(args.pattern)

    if search_type in ("rel", "relationship", "all"):
        rel_results = schema.search_relationships(args.pattern)

    # JSON output
    if args.format == "json":
        if search_type == "all":
            data = {
                "tables": [{"name": t.name, "description": t.description} for t in table_results],
                "fields": [{"table": table, "field": f.name, "type": f.datatype, "description": f.description} for table, f in field_results],
                "relationships": rel_results,
            }
        elif search_type == "table":
            data = [{"name": t.name, "description": t.description} for t in table_results]
        elif search_type == "field":
            data = [{"table": table, "field": f.name, "type": f.datatype, "description": f.description} for table, f in field_results]
        else:  # rel/relationship
            data = rel_results
        print(json.dumps(data, indent=2))
        return

    # Text output
    if search_type == "all":
        total = len(table_results) + len(field_results) + len(rel_results)
        print(f"Search results for '{args.pattern}' ({total} matches):")
        print()

    if table_results:
        print(f"Tables ({len(table_results)}):")
        for t in table_results:
            desc = t.description[:50] + "..." if len(t.description) > 50 else t.description
            print(f"  {t.name}: {desc}")
        if search_type == "all":
            print()

    if field_results:
        print(f"Fields ({len(field_results)}):")
        for table, f in field_results:
            print(f"  {table}.{f.name} ({f.datatype})")
        if search_type == "all":
            print()

    if rel_results:
        print(f"Relationships ({len(rel_results)}):")
        for rel in rel_results:
            print(f"  {rel['source_table']}.{rel['fields']} -> {rel['target_table']}.{rel['target_fields']}")

    # No results message
    if search_type == "table" and not table_results:
        print(f"No tables matching '{args.pattern}'")
    elif search_type == "field" and not field_results:
        print(f"No fields matching '{args.pattern}'")
    elif search_type in ("rel", "relationship") and not rel_results:
        print(f"No relationships matching '{args.pattern}'")
    elif search_type == "all" and not (table_results or field_results or rel_results):
        print(f"No results matching '{args.pattern}'")


def cmd_compare(args):
    """Compare two schemas."""
    schema1 = Schema.from_xml(args.schema1)
    schema2 = Schema.from_xml(args.schema2)

    tables1 = set(schema1.tables.keys())
    tables2 = set(schema2.tables.keys())

    added = tables2 - tables1
    removed = tables1 - tables2
    common = tables1 & tables2

    if args.format == "json":
        data = {
            "schema1": {"version": schema1.version, "tables": len(tables1)},
            "schema2": {"version": schema2.version, "tables": len(tables2)},
            "added_tables": sorted(added),
            "removed_tables": sorted(removed),
            "modified_tables": [],
        }
        for name in common:
            t1 = schema1.tables[name]
            t2 = schema2.tables[name]
            f1 = {f.name for f in t1.fields}
            f2 = {f.name for f in t2.fields}
            if f1 != f2:
                data["modified_tables"].append({
                    "table": name,
                    "added_fields": sorted(f2 - f1),
                    "removed_fields": sorted(f1 - f2),
                })
        print(json.dumps(data, indent=2))
        return

    print(f"Schema Comparison")
    print(f"  Schema 1: {schema1.version} ({len(tables1)} tables)")
    print(f"  Schema 2: {schema2.version} ({len(tables2)} tables)")
    print()

    if added:
        print(f"Tables added in {schema2.version} ({len(added)}):")
        for name in sorted(added):
            print(f"  + {name}")
        print()

    if removed:
        print(f"Tables removed in {schema2.version} ({len(removed)}):")
        for name in sorted(removed):
            print(f"  - {name}")
        print()

    modified = []
    for name in common:
        t1 = schema1.tables[name]
        t2 = schema2.tables[name]
        f1 = {f.name for f in t1.fields}
        f2 = {f.name for f in t2.fields}
        if f1 != f2:
            modified.append((name, f2 - f1, f1 - f2))

    if modified:
        print(f"Tables with field changes ({len(modified)}):")
        for name, added_fields, removed_fields in modified:
            print(f"  {name}:")
            for f in sorted(added_fields):
                print(f"    + {f}")
            for f in sorted(removed_fields):
                print(f"    - {f}")


def cmd_export(args):
    """Export schema to JSON."""
    schema = Schema.from_xml(args.schema)

    data = {
        "version": schema.version,
        "dbtype": schema.dbtype,
        "build_version": schema.build_version,
        "min_pro_version": schema.min_pro_version,
        "table_count": len(schema.tables),
        "tables": {},
    }

    for name, table in schema.tables.items():
        data["tables"][name] = {
            "name": table.name,
            "description": table.description,
            "title": table.title,
            "tablespace": table.tablespace,
            "fields": [asdict(f) for f in table.fields],
            "indexes": [asdict(i) for i in table.indexes],
            "constraints": [asdict(c) for c in table.constraints],
        }

    output = json.dumps(data, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Exported to {args.output}")
    else:
        print(output)


def cmd_fields(args):
    """List fields for a table or all tables."""
    schema = Schema.from_xml(args.schema)

    if args.table:
        table = schema.get_table(args.table)
        if not table:
            print(f"Table '{args.table}' not found.")
            sys.exit(1)
        tables = [table]
    else:
        tables = sorted(schema.tables.values(), key=lambda t: t.name)

    if args.format == "json":
        data = []
        for t in tables:
            for f in t.fields:
                data.append({
                    "table": t.name,
                    "field": f.name,
                    "datatype": f.datatype,
                    "length": f.charlength,
                    "notnull": f.notnull == "Y",
                    "description": f.description,
                })
        print(json.dumps(data, indent=2))
    elif args.format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(["table", "field", "datatype", "length", "notnull", "description"])
        for t in tables:
            for f in t.fields:
                writer.writerow([t.name, f.name, f.datatype, f.charlength, f.notnull, f.description])
    else:
        print(f"{'Table':<30} {'Field':<35} {'Type':<12} {'Length':<8}")
        print("-" * 90)
        for t in tables:
            for f in t.fields:
                length = f.charlength or f.dataprecision or ""
                print(f"{t.name:<30} {f.name:<35} {f.datatype:<12} {length:<8}")


def cmd_constraints(args):
    """List constraints (foreign keys, primary keys)."""
    schema = Schema.from_xml(args.schema)

    if args.type == "fk":
        constraint_type = "FOREIGN"
    elif args.type == "pk":
        constraint_type = "PRIMARY"
    else:
        constraint_type = None

    results = []
    for table in schema.tables.values():
        for c in table.constraints:
            if constraint_type is None or c.type == constraint_type:
                results.append((table.name, c))

    if args.format == "json":
        data = [{"table": t, "name": c.name, "type": c.type, "fields": c.fields, "target_table": c.target_table, "target_fields": c.target_fields} for t, c in results]
        print(json.dumps(data, indent=2))
    else:
        print(f"{'Table':<30} {'Type':<8} {'Fields':<30} {'References':<40}")
        print("-" * 110)
        for table, c in results:
            ref = f"{c.target_table}({c.target_fields})" if c.target_table else ""
            print(f"{table:<30} {c.type:<8} {c.fields:<30} {ref:<40}")


def cmd_stats(args):
    """Show schema statistics."""
    schema = Schema.from_xml(args.schema)

    total_fields = sum(len(t.fields) for t in schema.tables.values())
    total_indexes = sum(len(t.indexes) for t in schema.tables.values())
    total_constraints = sum(len(t.constraints) for t in schema.tables.values())
    total_fks = sum(1 for t in schema.tables.values() for c in t.constraints if c.type == "FOREIGN")

    datatypes = {}
    for t in schema.tables.values():
        for f in t.fields:
            datatypes[f.datatype] = datatypes.get(f.datatype, 0) + 1

    if args.format == "json":
        data = {
            "version": schema.version,
            "tables": len(schema.tables),
            "fields": total_fields,
            "indexes": total_indexes,
            "constraints": total_constraints,
            "foreign_keys": total_fks,
            "datatypes": datatypes,
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"Schema Statistics: {schema.version}")
        print(f"  Tables:       {len(schema.tables)}")
        print(f"  Fields:       {total_fields}")
        print(f"  Indexes:      {total_indexes}")
        print(f"  Constraints:  {total_constraints}")
        print(f"  Foreign Keys: {total_fks}")
        print(f"\nField Data Types:")
        for dtype, count in sorted(datatypes.items(), key=lambda x: -x[1]):
            print(f"  {dtype:<15} {count:>6}")


def cmd_config(args):
    """Manage configuration settings."""
    registry = get_registry()
    config = load_config()

    if args.action == "show":
        if not config:
            print("No configuration set.")
            print(f"Config file: {CONFIG_FILE}")
            return
        print("Current configuration:")
        print(f"  Config file: {CONFIG_FILE}")
        if "default_schema" in config:
            print(f"  Default schema: {config['default_schema']}")
        if args.format == "json":
            print(json.dumps(config, indent=2))

    elif args.action == "set-default":
        schema_spec = args.schema
        # Validate the schema exists
        entry = registry.get(schema_spec)
        if not entry:
            # Check if it's a valid file path
            path = Path(schema_spec)
            if path.suffix == ".xml" and path.exists():
                config["default_schema"] = schema_spec
                save_config(config)
                print(f"Default schema set to: {schema_spec}")
                return
            available = registry.available_keys
            print(f"Error: Schema '{schema_spec}' not found.", file=sys.stderr)
            if available:
                print(f"Available: {', '.join(available)}", file=sys.stderr)
            sys.exit(1)
        config["default_schema"] = schema_spec
        save_config(config)
        print(f"Default schema set to: {entry.display_name} ({entry.key})")

    elif args.action == "clear":
        if "default_schema" in config:
            del config["default_schema"]
            if config:
                save_config(config)
            else:
                # Remove empty config file
                CONFIG_FILE.unlink(missing_ok=True)
            print("Default schema cleared. Will use latest EPPM.")
        else:
            print("No default schema was set.")


SCHEMA_HELP = "Schema: file path or registry key (default: latest EPPM)"


def main():
    parser = argparse.ArgumentParser(
        prog="p6schema",
        description="Parse and analyze Oracle P6 EPPM schema files. "
        "Use 'p6schema list' to see available schemas. "
        "If no schema is specified, the latest EPPM version is used.",
        epilog="Schema can be specified as a file path or registry key (e.g., eppm:24.12)",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command - show available schemas
    p = subparsers.add_parser("list", help="List available schemas in registry")
    p.add_argument("-f", "--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_list)

    # info command
    p = subparsers.add_parser("info", help="Show schema information")
    p.add_argument("schema", nargs="?", default=None, help=SCHEMA_HELP)
    p.set_defaults(func=cmd_info)

    # tables command
    p = subparsers.add_parser("tables", help="List all tables")
    p.add_argument("schema", nargs="?", default=None, help=SCHEMA_HELP)
    p.add_argument("-f", "--format", choices=["text", "json", "csv"], default="text")
    p.set_defaults(func=cmd_tables)

    # describe command
    p = subparsers.add_parser("describe", help="Describe a table")
    p.add_argument("table", help="Table name")
    p.add_argument("-s", "--schema", default=None, help=SCHEMA_HELP)
    p.add_argument("-f", "--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_describe)

    # relationships command
    p = subparsers.add_parser("relationships", aliases=["rels"], help="Show table relationships")
    p.add_argument("table", help="Table name")
    p.add_argument("-s", "--schema", default=None, help=SCHEMA_HELP)
    p.add_argument("-f", "--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_relationships)

    # search command
    p = subparsers.add_parser("search", help="Search tables, fields, relationships, or all")
    p.add_argument("pattern", help="Search pattern")
    p.add_argument("-s", "--schema", default=None, help=SCHEMA_HELP)
    p.add_argument(
        "-t", "--type",
        choices=["table", "field", "rel", "relationship", "all"],
        default="all",
        help="What to search: table, field, rel[ationship], or all (default: all)"
    )
    p.add_argument("-f", "--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_search)

    # compare command
    p = subparsers.add_parser("compare", help="Compare two schemas")
    p.add_argument("schema1", help=SCHEMA_HELP)
    p.add_argument("schema2", help=SCHEMA_HELP)
    p.add_argument("-f", "--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_compare)

    # export command
    p = subparsers.add_parser("export", help="Export schema to JSON")
    p.add_argument("schema", nargs="?", default=None, help=SCHEMA_HELP)
    p.add_argument("-o", "--output", help="Output file (stdout if not specified)")
    p.set_defaults(func=cmd_export)

    # fields command
    p = subparsers.add_parser("fields", help="List fields")
    p.add_argument("schema", nargs="?", default=None, help=SCHEMA_HELP)
    p.add_argument("-t", "--table", help="Filter by table name")
    p.add_argument("-f", "--format", choices=["text", "json", "csv"], default="text")
    p.set_defaults(func=cmd_fields)

    # constraints command
    p = subparsers.add_parser("constraints", help="List constraints")
    p.add_argument("schema", nargs="?", default=None, help=SCHEMA_HELP)
    p.add_argument("-t", "--type", choices=["all", "pk", "fk"], default="all")
    p.add_argument("-f", "--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_constraints)

    # stats command
    p = subparsers.add_parser("stats", help="Show schema statistics")
    p.add_argument("schema", nargs="?", default=None, help=SCHEMA_HELP)
    p.add_argument("-f", "--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_stats)

    # config command
    p = subparsers.add_parser("config", help="Manage configuration (set default schema)")
    p.add_argument(
        "action",
        choices=["show", "set-default", "clear"],
        help="show: display config, set-default: set default schema, clear: remove default"
    )
    p.add_argument("schema", nargs="?", help="Schema specifier for set-default (e.g., eppm:24.12)")
    p.add_argument("-f", "--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_config)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
