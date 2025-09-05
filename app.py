import os
import json
import requests
from flask import Flask, request, Response, jsonify
from google.cloud import dialogflow_v2 as dialogflow

app = Flask(__name__)

# ---------- ENV VARS ----------
PROJECT_ID = os.environ.get("DIALOGFLOW_PROJECT_ID")

# --- Save service account JSON to temp file ---
sa_json = os.environ.get("DIALOGFLOW_SA_JSON")
if sa_json:
    sa_path = "/tmp/dialogflow_sa.json"
    with open(sa_path, "w") as f:
        f.write(sa_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path

# ---------- GITHUB RAW FILES ----------
DISEASES_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/diseases.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/symptoms.json"
PREVENTIONS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/preventions.json"

# Cache for GitHub JSON to avoid fetching every time
data_cache = {}

# ================== HELPERS ==================
def fetch_json(url):
    """Fetch and cache JSON from GitHub."""
    if url in data_cache:
        return data_cache[url]
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        data_cache[url] = data
        return data
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return {}

def find_disease_key(user_input, diseases_data):
    """Return the disease key matching user input or synonym."""
    user_input_lower = user_input.lower()
    for disease, info in diseases_data.items():
        if disease.lower() == user_input_lower:
            return disease
        for syn in info.get("synonyms", []):
            if syn.lower() == user_input_lower:
                return disease
    return None

def get_symptoms(disease_name):
    """Get symptoms list from symptoms JSON."""
    data = fetch_json(SYMPTOMS_URL)
    return data.get(disease_name, [])

def get_preventions(disease_name):
    """Get prevention list from prevention JSON."""
    data = fetch_json(PREVENTIONS_URL)
    return data.get(disease_name, [])

# ================== DIALOGFLOW HELPER ==================
def detect_intent_text(project_id, session_id, text, language_code="en"):
    """Send text to Dialogflow and return fulfillment text."""
    session_client = dialogflow.SessionsClient()
    session = session_client.session_path(project_id, session_id)

    text_input = dialogflow.TextInput(text=text, language_code=language_code)
    query_input = dialogflow.QueryInput(text=text_input)

    response = session_client.detect_intent(
        request={"session": session, "query_input": query_input}
    )
    return response.query_result.fulfillment_text

# ================== DIALOGFLOW FULFILLMENT ==================
@app.route("/dialogflow-webhook", methods=["POST"])
def dialogflow_webhook():
    """Webhook called by Dialogflow to fetch symptoms/preventions."""
    try:
        req = request.get_json(force=True)
        intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "")
        params = req.get("queryResult", {}).get("parameters", {})

        disease_input = params.get("diseases")
        response_text = "Sorry, I could not find information for that disease."

        if disease_input:
            diseases_data = fetch_json(DISEASES_URL)
            disease_key = find_disease_key(disease_input, diseases_data)

            if disease_key:
                parts = []
                if intent in ["ask_symptoms", "disease_info"]:
                    symptoms = get_symptoms(disease_key)
                    if symptoms:
                        parts.append(f"🤒 Symptoms of {disease_key}: {', '.join(symptoms)}.")
                if intent in ["ask_preventions", "disease_info"]:
                    preventions = get_preventions(disease_key)
                    if preventions:
                        parts.append(f"🛡 Prevention: {', '.join(preventions)}")

                if parts:
                    response_text = "\n".join(parts)

        return jsonify({"fulfillmentText": response_text})

    except Exception as e:
        print("Dialogflow Webhook Error:", e)
        return jsonify({"fulfillmentText": "Sorry, something went wrong."})

# ================== TWILIO WEBHOOK ==================
@app.route("/twilio-webhook", methods=["POST"])
def twilio_webhook():
    """Entry point for WhatsApp via Twilio."""
    try:
        incoming_msg = request.form.get("Body", "").strip()
        from_number = request.form.get("From", "user")

        if not incoming_msg:
            reply = "Please type something so I can help you."
        else:
            reply = detect_intent_text(PROJECT_ID, from_number, incoming_msg)

        # TwiML reply
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{reply}</Message>
</Response>"""

        return Response(twiml, mimetype="text/xml")

    except Exception as e:
        print("Twilio Webhook Error:", e)
        return Response(
            """<?xml version="1.0" encoding="UTF-8"?><Response><Message>Sorry, something went wrong.</Message></Response>""",
            mimetype="text/xml"
        )

# ================== MAIN ==================
if __name__ == "__main__":
    app.run(port=5000, debug=True)
