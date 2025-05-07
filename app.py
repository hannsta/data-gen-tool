from flask import Flask, request, jsonify, abort
import pandas as pd
import numpy as np
from faker import Faker
import traceback
from functools import wraps
from tml_util import generate_table_tml, generate_model_tml, generate_dashboard_tml
from snowflake_util import insert_dataframe_to_snowflake
from ts_api import import_tmls_to_thoughtspot


from dotenv import load_dotenv
import os

load_dotenv() 

app = Flask(__name__)
API_KEY = os.getenv("APP_API_KEY") 



def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        client_key = request.headers.get('X-API-Key')
        if client_key != API_KEY:
            abort(401, description="Unauthorized: Invalid API Key")
        return f(*args, **kwargs)
    return decorated

def run_code(code_str):
    exec_env = {"pd": pd, "np": np, "fake": Faker()}
    try:
        exec(code_str, exec_env)
    except Exception as e:
        return None, str(e)
    dataframes = {
        var: df for var, df in exec_env.items()
        if var.endswith("_df") and isinstance(df, pd.DataFrame)
    }
    return dataframes, None

@app.route('/generate-data', methods=['POST'])
@require_api_key
def generate_data():
    code = request.json.get("code")
    if not code:
        return jsonify({"error": "Missing code"}), 400

    dataframes, error = run_code(code)
    if error:
        return jsonify({"error": error}), 400

    preview = {
        name: df.head(25).to_dict(orient="records")
        for name, df in dataframes.items()
    }
    return jsonify({"dataframes": preview}), 200



@app.route('/insert-data', methods=['POST'])
@require_api_key
def insert_data():
    code = request.json.get("code")
    demo_unique_prefix = request.json.get("demo_unique_prefix")
    demo_name = request.json.get("demo_name")
    joins = request.json.get("joins")
    if not code or not demo_unique_prefix or not demo_name:
        return jsonify({"error": "Missing code, db_name, or model_name"}), 400

    dataframes, error = run_code(code)
    if error:
        return jsonify({"error": error}), 400

    try:
        # Insert into Snowflake
        for name, df in dataframes.items():
            table_name = f"{demo_unique_prefix}_{name.replace('_df', '')}".upper()
            insert_dataframe_to_snowflake(df, table_name)

        # Generate and insert TML
        table_tmls = [generate_table_tml(f"{demo_unique_prefix}_{name.replace('_df', '')}".upper(), df) for name, df in dataframes.items()]
        for tml in table_tmls:
            import_tmls_to_thoughtspot([tml])

        model_tml = generate_model_tml(dataframes, demo_unique_prefix, demo_name, joins_override=joins)
        print(model_tml)
        with open("output.txt", "w") as f:
            f.write(model_tml)
        resp = import_tmls_to_thoughtspot([model_tml])
        model_id = resp[0]['response']['header']['id_guid']

        return jsonify({
            "status": "success",
            "tables": [name for name in dataframes],
            "model_id": model_id
        }), 200
    except Exception as e:
        return jsonify({"error": traceback.format_exc()}), 500

@app.route('/create-dashboard', methods=['POST'])
@require_api_key
def create_dashboard():
    payload = request.json
    questions = payload.get("questions")
    model_id = payload.get("model_id")
    demo_name = payload.get("demo_name")
    dashboard_name = payload.get("dashboard_name", "Generated Dashboard")

    if not questions or not model_id or not demo_name:
        return jsonify({"error": "Missing questions, model_id, or demo_name"}), 400

    try:
        dashboard_tml = generate_dashboard_tml(questions, model_id, demo_name, dashboard_name)
        response = import_tmls_to_thoughtspot([dashboard_tml])
        dashboard_id = response[0]['response']['header']['id_guid']

        return jsonify({
            "status": "success",
            "dashboard_id": dashboard_id,
            "dashboard_name": dashboard_name,
        }), 200
    except Exception as e:
        return jsonify({"error": traceback.format_exc()}), 500



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0',port=3030 )
