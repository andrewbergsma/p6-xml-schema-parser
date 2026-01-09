# p6schema

CLI utility for parsing and analyzing Oracle P6 EPPM/PPM schema files.

## Installation

```bash
pip install -e .
```

## Schema Registry

The tool automatically discovers schema files in the `schemas/` directory. Schemas can be referenced by registry key instead of file path:

```bash
p6schema list
```

```
Available Schemas (9):
  Key             Application Version    Path
  ----------------------------------------------------------------------
  eppm:20.12      EPPM       20.12      schemas/eppm_20_12_schema.xml
  eppm:23.04      EPPM       23.04      schemas/eppm_23_04_schema.xml
  eppm:23.10      EPPM       23.10      schemas/eppm_23_10_schema.xml
  eppm:23.12      EPPM       23.12      schemas/eppm_23_12_schema.xml
  eppm:24.12      EPPM       24.12      schemas/eppm_24_12_schema.xml
  eppm:25.04      EPPM       25.04      schemas/eppm_25_04_schema.xml
  ppm:21.12       PPM        21.12      schemas/ppm_21_12_schema.xml
  ppm:22.12       PPM        22.12      schemas/ppm_22_12_schema.xml
  ppm:23.04       PPM        23.04      schemas/ppm_23_04_schema.xml
```

When no schema is specified, the configured default is used (or latest EPPM if none configured).

## Configuration

Set a default schema to avoid specifying it with every command.

```bash
# Set a default schema
p6schema config set-default eppm:23.12

# Show current configuration
p6schema config show

# Clear the default (reverts to latest EPPM)
p6schema config clear
```

Configuration is stored in `.p6schemarc` in the tool's directory:

```json
{
  "default_schema": "eppm:23.12"
}
```

## Commands

### info

Show schema metadata.

```bash
p6schema info                  # uses latest EPPM
p6schema info eppm:23.04       # specific version
p6schema info ppm:23.04        # PPM schema
```

```
Schema Information:
  Version:       2412.0000.0000.0006
  DB Type:       PMDB
  Build Version: PM_24_12_00
  Min Pro Ver:   24.10.00
  Tables:        347
  Source:        schemas/eppm_24_12_schema.xml
```

### tables

List all tables in a schema.

```bash
p6schema tables
p6schema tables -f json        # JSON output
p6schema tables -f csv         # CSV output
```

```
Table Name                               Fields  Description
--------------------------------------------------------------------------------
ACCOUNT                                      12  Cost accounts
ACTVCODE                                     13  Activity code values
ACTVTYPE                                     13  Activity codes
...
```

### describe

Show detailed table structure including fields, indexes, and constraints.

```bash
p6schema describe PROJECT
p6schema describe TASK -s eppm:23.04    # specific schema
p6schema describe USERS -f json         # JSON output
```

```
Table: PROJECT
Title: Project
Description: Projects
Tablespace: PMDB_DAT1

Fields (104):
  Name                                Type         Length   Null     Description
  ------------------------------------------------------------------------------------------
  proj_id                             integer      22       NOT NULL FK to PROJECT table
  fy_start_month_num                  integer      22       NOT NULL Starting month number
  ...

Indexes (12):
  pk_project: proj_id (UNIQUE)
  ...

Constraints (8):
  PK: pk_project (proj_id)
  FK: fk_project_account (acct_id) -> ACCOUNT(acct_id)
  ...
```

### relationships

Show foreign key relationships for a table.

```bash
p6schema relationships PROJECT
p6schema rels TASK              # alias
p6schema rels USERS -f json     # JSON output
```

```
Relationships for: PROJECT
============================================================

References (7):
  This Table                Referenced Table          Fields
  ----------------------------------------------------------------------
  acct_id                   -> ACCOUNT                   (acct_id)
  base_type_id              -> BASETYPE                  (base_type_id)
  ...

Referenced By (71):
  Referencing Table         Fields                    This Table
  ----------------------------------------------------------------------
  ACTVTYPE                  proj_id                   -> proj_id
  CALENDAR                  proj_id                   -> proj_id
  TASK                      proj_id                   -> proj_id
  ...

Summary:
  References 7 table(s)
  Referenced by 71 table(s)
```

### search

Search for tables, fields, relationships, or all (default).

```bash
p6schema search PROJECT                 # search all (tables, fields, relationships)
p6schema search TASK -t table           # search table names only
p6schema search wbs_id -t field         # search field names only
p6schema search CALENDAR -t rel         # search relationships only
p6schema search proj_id -f json         # JSON output
```

**Search types:**
- `all` (default) - Search tables, fields, and relationships
- `table` - Search table names only
- `field` - Search field names only
- `rel` or `relationship` - Search foreign key relationships

```
$ p6schema search CALENDAR -t rel

Relationships (3):
  CALENDAR.proj_id -> PROJECT.proj_id
  RSRC.clndr_id -> CALENDAR.clndr_id
  TASK.clndr_id -> CALENDAR.clndr_id
```

```
$ p6schema search PROJECT

Search results for 'PROJECT' (135 matches):

Tables (7):
  PROJECT: Projects
  PROJECTCOSTCBSSPREAD: Summary data for Project Cost CBS Spreads
  ...

Fields (48):
  ACTIVITYSPREAD.projectobjectid (integer)
  PROJECT.project_flag (string)
  ...

Relationships (80):
  ACTVTYPE.proj_id -> PROJECT.proj_id
  PROJECT.acct_id -> ACCOUNT.acct_id
  ...
```

### compare

Compare two schema versions to find differences.

```bash
p6schema compare eppm:23.04 eppm:24.12
p6schema compare eppm:20.12 eppm:24.12 -f json
```

```
Schema Comparison
  Schema 1: 2304.0000.0000.0009 (346 tables)
  Schema 2: 2412.0000.0000.0006 (347 tables)

Tables added in 2412.0000.0000.0006 (1):
  + BODEFLABELS

Tables with field changes (6):
  USESSION:
    + remote_client_ip
  PAUDITX:
    + activity_id
    + activity_name
    ...
```

### fields

List fields, optionally filtered by table.

```bash
p6schema fields                         # all fields
p6schema fields -t PROJECT              # fields in PROJECT table
p6schema fields -f csv > fields.csv     # export to CSV
```

### constraints

List constraints (primary keys, foreign keys).

```bash
p6schema constraints                    # all constraints
p6schema constraints -t pk              # primary keys only
p6schema constraints -t fk              # foreign keys only
p6schema constraints -f json
```

### stats

Show schema statistics.

```bash
p6schema stats
p6schema stats ppm:23.04
```

```
Schema Statistics: 2412.0000.0000.0006
  Tables:       347
  Fields:       5138
  Indexes:      791
  Constraints:  722
  Foreign Keys: 363

Field Data Types:
  string            1498
  integer           1296
  date              1124
  double             625
  ...
```

### export

Export entire schema to JSON.

```bash
p6schema export -o schema.json
p6schema export eppm:23.04 -o eppm_23.json
```

## Output Formats

Most commands support multiple output formats:

- `text` (default) - Human-readable tabular output
- `json` - JSON for programmatic use
- `csv` - CSV for spreadsheet import (where applicable)

```bash
p6schema tables -f json
p6schema fields -f csv
p6schema describe PROJECT -f json
```

## Adding Schemas

Place schema files in the `schemas/` directory following the naming convention:

```
eppm_YY_MM_schema.xml   (e.g., eppm_24_12_schema.xml)
ppm_YY_MM_schema.xml    (e.g., ppm_23_04_schema.xml)
```

The registry will automatically discover them on next run.

## MCP Server

The P6 Schema Parser can also run as an MCP (Model Context Protocol) server, allowing LLMs to query schema information directly.

### Installation

Install with MCP support:

```bash
pip install -e ".[mcp]"
```

### Running the Server

```bash
# Using FastMCP CLI
fastmcp run p6schema_mcp.py

# Or directly
python p6schema_mcp.py
```

### Claude Desktop Configuration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "p6schema": {
      "command": "python",
      "args": ["/path/to/p6schema_mcp.py"]
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `list_schemas` | List all available schemas in the registry |
| `get_schema_info` | Get metadata about a schema |
| `list_tables` | List all tables in a schema |
| `describe_table` | Get detailed table structure |
| `get_relationships` | Show foreign key relationships for a table |
| `search` | Search tables, fields, or relationships |
| `compare_schemas` | Compare two schema versions |
| `get_fields` | List fields (optionally filtered by table) |
| `get_constraints` | List primary/foreign key constraints |
| `get_stats` | Show schema statistics |
| `config_show` | Show current configuration |
| `config_set_default` | Set the default schema |
| `config_clear_default` | Clear the default schema setting |
