from sqlalchemy import text, create_engine
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import os

load_dotenv()  # Make sure .env file is in the same directory or specify the path

user = os.getenv("SNOWFLAKE_USER")
password = os.getenv("SNOWFLAKE_PASSWORD")
account = os.getenv("SNOWFLAKE_ACCOUNT")
warehouse = os.getenv("SNOWFLAKE_WAREHOUSE")
database = os.getenv("SNOWFLAKE_DATABASE")
schema = os.getenv("SNOWFLAKE_SCHEMA")

def get_engine():
    return create_engine(
        f'snowflake://{user}:{password}@{account}/{database}/{schema}?warehouse={warehouse}'
    )

def sanitize_dataframe_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        dtype = df[col].dtype
        if dtype == object or np.issubdtype(dtype, np.str_):
            df[col] = df[col].astype(str)
        elif np.issubdtype(dtype, np.datetime64):
            df[col] = pd.to_datetime(df[col], errors='coerce')
        elif np.issubdtype(dtype, np.integer):
            df[col] = df[col].astype(int)
        elif np.issubdtype(dtype, np.floating):
            df[col] = df[col].astype(float)
        elif np.issubdtype(dtype, np.bool_):
            df[col] = df[col].astype(bool)
    return df

def insert_dataframe_to_snowflake(df: pd.DataFrame, table_name: str, if_exists: str = "replace"):
    if not isinstance(df, pd.DataFrame):
        raise ValueError("df must be a pandas DataFrame")
    
    df = sanitize_dataframe_for_sql(df)
    print(df.dtypes)
    df.columns = df.columns.str.upper()

    engine = get_engine()

    try:
        with engine.begin() as conn:  # Begin = auto-commit transaction
            if if_exists == "replace":
                conn.execute(text(f'DROP TABLE IF EXISTS "{table_name.upper()}"'))
            df.to_sql(
                name=table_name,
                con=conn,
                index=False,
                if_exists=if_exists,
                method="multi"
            )
            print(f"✅ Inserted {len(df)} rows into '{table_name}'")
    except Exception as e:
        print(f"❌ Failed to insert into {table_name}: {e}")
        raise
