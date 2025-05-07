import uuid
from yaml import dump
import pandas as pd
import collections

from ts_api import answer_question

# ------------------------------------------------------------------------
# Column Type Mapping
# ------------------------------------------------------------------------

def pandas_dtype_to_tml(pandas_dtype):
    if pd.api.types.is_integer_dtype(pandas_dtype):
        return "INT64", "MEASURE", "SUM"
    elif pd.api.types.is_float_dtype(pandas_dtype):
        return "DOUBLE", "MEASURE", "SUM"
    elif pd.api.types.is_datetime64_any_dtype(pandas_dtype):
        return "DATE", "ATTRIBUTE", None
    else:
        return "VARCHAR", "ATTRIBUTE", None

# ------------------------------------------------------------------------
# Table TML Generation
# ------------------------------------------------------------------------

def generate_table_tml(table_name, df):
    tml = {
        "guid": str(uuid.uuid4()),
        "table": {
            "name": table_name.upper(),
            "db": "AUTO_CREATE_TEST",
            "schema": "PUBLIC",
            "db_table": table_name.upper(),
            "connection": {"name": "AutoCreateConnection"},
            "columns": [],
            "properties": {"sage_config": {"is_sage_enabled": False}}
        }
    }
    for col in df.columns:
        dtype, col_type, agg = pandas_dtype_to_tml(df[col].dtype)
        col_entry = {
            "name": col.upper(),
            "db_column_name": col.upper(),
            "properties": {
                "column_type": col_type,
                "index_type": "DONT_INDEX"
            },
            "db_column_properties": {
                "data_type": dtype
            }
        }
        if agg:
            col_entry["properties"]["aggregation"] = agg
        tml["table"]["columns"].append(col_entry)
    return dump(tml, sort_keys=False)

# ------------------------------------------------------------------------
# Model TML Generation
# ------------------------------------------------------------------------

def normalize_column_name(name):
    return name.strip().lower().replace("_", "")

def clean_table_name(table_name: str, db_name: str):
    return f"{db_name}_{table_name.replace('_df', '').upper()}"

def generate_model_tml(dataframes, db_name, demo_name, joins_override = None):
    model_tables = []
    column_definitions = []
    joins = []
    defined_joins = set()

    # Detect all _ID columns per table
    id_column_sources = {}
    for table, df in dataframes.items():
        for col in df.columns:
            if col.upper().endswith("_ID"):
                id_column_sources.setdefault(col.upper(), []).append(table)

    print(id_column_sources)
    # Detect joins based on ID usage volume
    for id_col, related_tables in id_column_sources.items():
        if len(related_tables) < 2:
            continue  # Only consider shared IDs

        # Count rows with non-null ID values per table
        id_counts = {}
        for table in related_tables:
            df = dataframes[table]
            id_counts[table] = df.shape[0]
        if len(id_counts) < 2:
            continue

        # Sort tables by increasing count of ID usage
        sorted_tables = sorted(id_counts.items(), key=lambda x: x[1])
        dim_table = sorted_tables[0][0]
        dim_clean = clean_table_name(dim_table, db_name).upper()
        for fact_table, _ in sorted_tables[1:]:
            fact_clean = clean_table_name(fact_table, db_name).upper()
            join_key = (dim_clean, fact_clean, id_col)
            if join_key in defined_joins:
                continue

            joins.append({
                "name": dim_clean,
                "joins": [{
                    "with": fact_clean,
                    "on": f"[{dim_clean}::{id_col}] = [{fact_clean}::{id_col}]",
                    "type": "INNER",
                    "cardinality": "ONE_TO_MANY"
                }]
            })
            defined_joins.add(join_key)

    # Map column names to avoid collisions in display names
    column_name_map = {}

    for table_name, df in dataframes.items():
        df.columns = df.columns.str.upper()
        clean_name = clean_table_name(table_name, db_name).upper()
        model_tables.append({"name": clean_name})

        for col in df.columns:
            norm_name = normalize_column_name(col)
            if norm_name in column_name_map:
                display_name = f"{clean_name.replace('_', ' ')} {col.replace('_', ' ').title()}"
            else:
                display_name = col.replace('_', ' ').title()
                column_name_map[norm_name] = (col, clean_name)

            col_type = "ATTRIBUTE"
            agg = None
            if pd.api.types.is_numeric_dtype(df[col]):
                col_type = "MEASURE"
                agg = "SUM"

            col_def = {
                "name": display_name,
                "column_id": f"{clean_name}::{col.upper()}",
                "properties": {
                    "column_type": col_type,
                    "index_type": "DONT_INDEX"
                }
            }
            if agg:
                col_def["properties"]["aggregation"] = agg

            column_definitions.append(col_def)

    # Attach joins to owning tables
    join_map = collections.defaultdict(list)
    effective_joins = joins_override if joins_override else joins
    for join in effective_joins:
        join_map[join["name"]].extend(join["joins"])
    for table in model_tables:
        if table["name"] in join_map:
            table["joins"] = join_map[table["name"]]

    model_tml = {
        "guid": str(uuid.uuid4()),
        "model": {
            "name": f"{demo_name} Model",
            "model_tables": model_tables,
            "columns": column_definitions,
            "properties": {
                "is_bypass_rls": False,
                "join_progressive": True,
                "sage_config": {
                    "is_sage_enabled": True
                }
            }
        }
    }

    return dump(model_tml, sort_keys=False)


import uuid

def generate_dashboard_tml(questions, model_id, demo_name, dashboard_name="Generated Dashboard"):
    dashboard_guid = str(uuid.uuid4())
    visualizations = []

    for idx, spec in enumerate(questions, start=1):
        question = spec["question"]
        chart_type = spec.get("chart_type", "COLUMN")  # Default to COLUMN if not provided

        viz_guid = str(uuid.uuid4())
        answer_token = answer_question(question, model_id)

        visualizations.append({
            "id": f"Viz_{idx}",
            "answer": {
                "name": question.strip().capitalize(),
                "tables": [
                    {
                        "id": f"{demo_name} Model",
                        "name": f"{demo_name} Model"
                    }
                ],
                "search_query": answer_token,
                "chart": {
                    "type": chart_type
                }
            },
            "viz_guid": viz_guid
        })

    dashboard_tml = {
        "guid": dashboard_guid,
        "liveboard": {
            "name": dashboard_name,
            "visualizations": visualizations
        }
    }

    return dump(dashboard_tml, sort_keys=False)
