import uuid
from yaml import dump
import pandas as pd
import collections

from ts_api import answer_question, export_unsaved_answer_tml

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

def generate_model_tml(dataframes, db_name, demo_name, joins_override=None):
    model_tables = []
    column_definitions = []
    join_map = collections.defaultdict(list)
    defined_joins = set()

    # Build DATE_DIM early
    model_tables.append({"name": "AUTO_CREATE_DATE_DIM"})

    # Prepare display names and base model_tables
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

    # Add static column for date (always exposed)
    column_definitions.append({
        "name": "Calendar Date",
        "column_id": "AUTO_CREATE_DATE_DIM::CALENDAR_DATE",
        "properties": {
            "column_type": "ATTRIBUTE",
            "index_type": "DONT_INDEX"
        }
    })

    # Use join overrides if provided
    effective_joins = joins_override if joins_override else []
    print(effective_joins)
    # Load joins into map
    for join in effective_joins:
        for j in join["joins"]:
            if j not in join_map[join["name"]]:
                join_map[join["name"]].append(j)

    # Append DATE_DIM joins based on TODAY_OFFSET_KEY
    for table_name, df in dataframes.items():
        columns_upper = df.columns.str.upper()
        if "TODAY_OFFSET_KEY" in columns_upper:
            clean_name = clean_table_name(table_name, db_name).upper()
            date_join = {
                "with": "AUTO_CREATE_DATE_DIM",
                "on": f"[{clean_name}::TODAY_OFFSET_KEY] = [AUTO_CREATE_DATE_DIM::TODAY_OFFSET_KEY]",
                "type": "INNER",
                "cardinality": "MANY_TO_ONE"
            }
            if date_join not in join_map[clean_name]:
                join_map[clean_name].append(date_join)

    # Attach joins to model tables
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
        answer_token, session_id, gen_no, session = answer_question(question, model_id)
        answer_tml = export_unsaved_answer_tml(session,session_id, gen_no)
        visualizations.append(answer_tml)
        answer_tml['answer']['name'] = spec.get("chart_name", question)
        # visualizations.append({
        #     "id": f"Viz_{idx}",
        #     "answer": {
        #         "name": question.strip().capitalize(),
        #         "tables": [
        #             {
        #                 "id": f"{demo_name} Model",
        #                 "name": f"{demo_name} Model"
        #             }
        #         ],
        #         "search_query": answer_token,
        #     },
        #     "viz_guid": viz_guid
        # })

    dashboard_tml = {
        "guid": dashboard_guid,
        "liveboard": {
            "name": dashboard_name,
            "visualizations": visualizations
        }
    }
    return dump(dashboard_tml, sort_keys=False)
