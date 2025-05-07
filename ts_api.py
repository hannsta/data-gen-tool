import json
import requests
from dotenv import load_dotenv
import os

load_dotenv() 

THOUGHTSPOT_URL = os.getenv("THOUGHTSPOT_URL") 
THOUGHTSPOT_USER_NAME = os.getenv("THOUGHTSPOT_USER_NAME") 
THOUGHTSPOT_AUTH_TOKEN = os.getenv("THOUGHTSPOT_AUTH_TOKEN") 

THOUGHTSPOT_SERVER = THOUGHTSPOT_URL + "/api/rest/2.0/"


def get_auth_token(session):
    url = THOUGHTSPOT_SERVER + "auth/token/full"
    post_data = {
        'username': THOUGHTSPOT_USER_NAME,
        'secret_key': THOUGHTSPOT_AUTH_TOKEN,
        "validity_time_in_sec": 300,
        "auto_create": False,
    }  

    response = session.post(url=url, data=post_data)
    response.raise_for_status()
    token = response.json()['token']
    session.headers.update({
        'Authorization': f"Bearer {token}",
        'Accept-Language': 'application/json',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    })
    return session


def import_tmls_to_thoughtspot(tml_list):
    session = requests.Session()
    session = get_auth_token(session)
    url = THOUGHTSPOT_SERVER + "metadata/tml/import"
    response = session.post(url=url, data=json.dumps({
        "metadata_tmls": tml_list,
        "import_policy": "PARTIAL",
    }))
    print(response.text)
    response.raise_for_status()

    return response.json()

def answer_question(question: str, model_id: str):
    session = requests.Session()
    session.verify = False
    get_auth_token(session)
    print("making call")
    url = THOUGHTSPOT_SERVER + "ai/answer/create"
    response = session.post(url=url, data=json.dumps({"query":  question, "metadata_identifier": model_id}))
    print(response)
    print("Response")
    response.raise_for_status()

    return response.json()['tokens']