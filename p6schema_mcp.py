#!/usr/bin/env python3
"""
P6 Schema MCP Server - Expose P6 schema parsing as MCP tools.

Run with: fastmcp run p6schema_mcp.py
Or: python p6schema_mcp.py
"""

from dataclasses import asdict
from typing import Optional

from fastmcp import FastMCP

from p6schema import (
    Schema,
    get_registry,
    resolve_schema_path,
    load_config,
    save_config,
    get_default_schema,
    CONFIG_FILE,
)

mcp = FastMCP("P6 Schema Parser")


@mcp.tool
def list_schemas() -> list[dict]:
    """List all available P6 schemas in the registry.

    Returns a list of schemas with their keys, applications, versions, and paths.
    """
    registry = get_registry()
    entries = registry.list_all()

    return [
        {
            "key": e.key,
            "application": e.application.upper(),
            "version": e.version,
            "path": str(e.path),
        }
        for e in entries
    ]


@mcp.tool
def get_schema_info(schema: Optional[str] = None) -> dict:
    """Get metadata information about a schema.

    Args:
        schema: Schema specifier (e.g., 'eppm:24.12', 'ppm:23.04') or None for default.

    Returns:
        Schema metadata including version, DB type, build version, and table count.
    """
    s = Schema.from_xml(schema)
    return {
        "version": s.version,
        "dbtype": s.dbtype,
        "build_version": s.build_version,
        "min_pro_version": s.min_pro_version,
        "table_count": len(s.tables),
        "source_path": s.source_path,
    }


@mcp.tool
def list_tables(schema: Optional[str] = None) -> list[dict]:
    """List all tables in a schema.

    Args:
        schema: Schema specifier or None for default.

    Returns:
        List of tables with name, description, and field count.
    """
    s = Schema.from_xml(schema)
    tables = sorted(s.tables.values(), key=lambda t: t.name)

    return [
        {
            "name": t.name,
            "description": t.description,
            "field_count": len(t.fields),
        }
        for t in tables
    ]


@mcp.tool
def describe_table(table: str, schema: Optional[str] = None) -> dict:
    """Get detailed information about a specific table.

    Args:
        table: Table name (case-insensitive).
        schema: Schema specifier or None for default.

    Returns:
        Table details including fields, indexes, constraints, and triggers.
    """
    s = Schema.from_xml(schema)
    t = s.get_table(table)

    if not t:
        return {"error": f"Table '{table}' not found"}

    return {
        "name": t.name,
        "description": t.description,
        "title": t.title,
        "tablespace": t.tablespace,
        "fields": [asdict(f) for f in t.fields],
        "indexes": [asdict(i) for i in t.indexes],
        "constraints": [asdict(c) for c in t.constraints],
        "triggers": [asdict(tr) for tr in t.triggers],
    }


@mcp.tool
def get_relationships(table: str, schema: Optional[str] = None) -> dict:
    """Get foreign key relationships for a table.

    Args:
        table: Table name (case-insensitive).
        schema: Schema specifier or None for default.

    Returns:
        Outgoing references (tables this table references) and
        incoming references (tables that reference this table).
    """
    s = Schema.from_xml(schema)
    t = s.get_table(table)

    if not t:
        return {"error": f"Table '{table}' not found"}

    # Outgoing: tables this table references
    outgoing = []
    for c in t.constraints:
        if c.type == "FOREIGN":
            outgoing.append({
                "constraint": c.name,
                "fields": c.fields,
                "references_table": c.target_table,
                "references_fields": c.target_fields,
            })

    # Incoming: tables that reference this table
    incoming = []
    for other_table in s.tables.values():
        if other_table.name == t.name:
            continue
        for c in other_table.constraints:
            if c.type == "FOREIGN" and c.target_table.upper() == t.name.upper():
                incoming.append({
                    "table": other_table.name,
                    "constraint": c.name,
                    "fields": c.fields,
                    "references_fields": c.target_fields,
                })

    return {
        "table": t.name,
        "outgoing": outgoing,
        "incoming": incoming,
        "outgoing_count": len(outgoing),
        "incoming_count": len(incoming),
    }


@mcp.tool
def search(
    pattern: str,
    search_type: str = "all",
    schema: Optional[str] = None,
) -> dict:
    """Search for tables, fields, or relationships matching a pattern.

    Args:
        pattern: Search pattern (case-insensitive substring match).
        search_type: What to search - 'table', 'field', 'rel', or 'all' (default).
        schema: Schema specifier or None for default.

    Returns:
        Matching tables, fields, and/or relationships based on search_type.
    """
    s = Schema.from_xml(schema)
    result = {}

    if search_type in ("table", "all"):
        tables = s.search_tables(pattern)
        result["tables"] = [
            {"name": t.name, "description": t.description}
            for t in tables
        ]

    if search_type in ("field", "all"):
        fields = s.search_fields(pattern)
        result["fields"] = [
            {
                "table": table_name,
                "field": f.name,
                "datatype": f.datatype,
                "description": f.description,
            }
            for table_name, f in fields
        ]

    if search_type in ("rel", "relationship", "all"):
        rels = s.search_relationships(pattern)
        result["relationships"] = rels

    return result


@mcp.tool
def compare_schemas(schema1: str, schema2: str) -> dict:
    """Compare two schema versions to find differences.

    Args:
        schema1: First schema specifier (e.g., 'eppm:23.04').
        schema2: Second schema specifier (e.g., 'eppm:24.12').

    Returns:
        Added tables, removed tables, and tables with field changes.
    """
    s1 = Schema.from_xml(schema1)
    s2 = Schema.from_xml(schema2)

    tables1 = set(s1.tables.keys())
    tables2 = set(s2.tables.keys())

    added = tables2 - tables1
    removed = tables1 - tables2
    common = tables1 & tables2

    modified = []
    for name in common:
        t1 = s1.tables[name]
        t2 = s2.tables[name]
        f1 = {f.name for f in t1.fields}
        f2 = {f.name for f in t2.fields}
        if f1 != f2:
            modified.append({
                "table": name,
                "added_fields": sorted(f2 - f1),
                "removed_fields": sorted(f1 - f2),
            })

    return {
        "schema1": {"version": s1.version, "table_count": len(tables1)},
        "schema2": {"version": s2.version, "table_count": len(tables2)},
        "added_tables": sorted(added),
        "removed_tables": sorted(removed),
        "modified_tables": modified,
    }


@mcp.tool
def get_fields(table: Optional[str] = None, schema: Optional[str] = None) -> list[dict]:
    """List fields, optionally filtered by table.

    Args:
        table: Filter by table name (optional).
        schema: Schema specifier or None for default.

    Returns:
        List of fields with table, name, datatype, length, and description.
    """
    s = Schema.from_xml(schema)

    if table:
        t = s.get_table(table)
        if not t:
            return [{"error": f"Table '{table}' not found"}]
        tables = [t]
    else:
        tables = sorted(s.tables.values(), key=lambda t: t.name)

    result = []
    for t in tables:
        for f in t.fields:
            result.append({
                "table": t.name,
                "field": f.name,
                "datatype": f.datatype,
                "length": f.charlength or f.dataprecision or "",
                "notnull": f.notnull == "Y",
                "description": f.description,
            })

    return result


@mcp.tool
def get_constraints(
    constraint_type: str = "all",
    schema: Optional[str] = None,
) -> list[dict]:
    """List constraints (primary keys, foreign keys).

    Args:
        constraint_type: Filter by type - 'pk', 'fk', or 'all' (default).
        schema: Schema specifier or None for default.

    Returns:
        List of constraints with table, name, type, fields, and target info.
    """
    s = Schema.from_xml(schema)

    if constraint_type == "fk":
        filter_type = "FOREIGN"
    elif constraint_type == "pk":
        filter_type = "PRIMARY"
    else:
        filter_type = None

    result = []
    for table in s.tables.values():
        for c in table.constraints:
            if filter_type is None or c.type == filter_type:
                result.append({
                    "table": table.name,
                    "name": c.name,
                    "type": c.type,
                    "fields": c.fields,
                    "target_table": c.target_table,
                    "target_fields": c.target_fields,
                })

    return result


@mcp.tool
def get_stats(schema: Optional[str] = None) -> dict:
    """Get schema statistics.

    Args:
        schema: Schema specifier or None for default.

    Returns:
        Statistics including table count, field count, indexes, constraints,
        foreign keys, and datatype distribution.
    """
    s = Schema.from_xml(schema)

    total_fields = sum(len(t.fields) for t in s.tables.values())
    total_indexes = sum(len(t.indexes) for t in s.tables.values())
    total_constraints = sum(len(t.constraints) for t in s.tables.values())
    total_fks = sum(
        1 for t in s.tables.values()
        for c in t.constraints if c.type == "FOREIGN"
    )

    datatypes = {}
    for t in s.tables.values():
        for f in t.fields:
            datatypes[f.datatype] = datatypes.get(f.datatype, 0) + 1

    return {
        "version": s.version,
        "tables": len(s.tables),
        "fields": total_fields,
        "indexes": total_indexes,
        "constraints": total_constraints,
        "foreign_keys": total_fks,
        "datatypes": datatypes,
    }


@mcp.tool
def config_show() -> dict:
    """Show current configuration.

    Returns:
        Current configuration including default schema and config file path.
    """
    config = load_config()
    return {
        "config_file": str(CONFIG_FILE),
        "default_schema": config.get("default_schema"),
        "config": config,
    }


@mcp.tool
def config_set_default(schema: str) -> dict:
    """Set the default schema.

    Args:
        schema: Schema specifier to set as default (e.g., 'eppm:24.12').

    Returns:
        Confirmation message with the new default schema.
    """
    registry = get_registry()
    entry = registry.get(schema)

    if not entry:
        available = registry.available_keys
        return {
            "error": f"Schema '{schema}' not found",
            "available": available,
        }

    config = load_config()
    config["default_schema"] = schema
    save_config(config)

    return {
        "success": True,
        "message": f"Default schema set to: {entry.display_name} ({entry.key})",
        "default_schema": schema,
    }


@mcp.tool
def config_clear_default() -> dict:
    """Clear the default schema setting.

    Returns:
        Confirmation message.
    """
    config = load_config()

    if "default_schema" in config:
        del config["default_schema"]
        if config:
            save_config(config)
        else:
            CONFIG_FILE.unlink(missing_ok=True)
        return {
            "success": True,
            "message": "Default schema cleared. Will use latest EPPM.",
        }

    return {
        "success": True,
        "message": "No default schema was set.",
    }


if __name__ == "__main__":
    mcp.run()
