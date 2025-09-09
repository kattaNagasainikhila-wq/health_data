import os
import json
import requests
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ---------- GITHUB RAW FILES ----------
DISEASES_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/diseases.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/symptoms.json"
PREVENTIONS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/preventions.json"
MAPPING_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/mapping.json"

# Cache for GitHub JSON
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
    """Get symptoms for a disease."""
    data = fetch_json(SYMPTOMS_URL)
    return data.get(disease_name, [])

def get_preventions(disease_name):
    """Get preventions for a disease."""
    data = fetch_json(PREVENTIONS_URL)
    return data.get(disease_name, [])

def get_diseases_from_symptom(symptom):
    """Find possible diseases from a symptom (reverse lookup)."""
    data = fetch_json(MAPPING_URL)
    return data.get(symptom.lower(), [])

def process_disease_query(user_input):
    """Handle disease name input."""
    diseases_data = fetch_json(DISEASES_URL)
    disease_key = find_disease_key(user_input, diseases_data)
    if disease_key:
        symptoms = get_symptoms(disease_key)
        preventions = get_preventions(disease_key)

        response = f"Here’s what I found about {disease_key}:"
        if symptoms:
            response += f"\n🤒 Symptoms: {', '.join(symptoms)}."
        else:
            response += f"\n(No symptoms data available.)"

        if preventions:
            response += f"\n🛡 Prevention: {', '.join(preventions)}"
        else:
            response += f"\n(No prevention info available.)"
        return response
    else:
        return None  # so we can fall back to symptom query

def process_symptom_query(user_input):
    """Handle symptom input."""
    diseases = get_diseases_from_symptom(user_input)
    if diseases:
        return f"🩺 The symptom '{user_input}' may be related to: {', '.join(diseases)}."
    return None

# ================== DIALOGFLOW WEBHOOK ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    """Dialogflow webhook."""
    try:
        req = request.get_json(force=True)
        intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "")
        params = req.get("queryResult", {}).get("parameters", {})

        user_input = params.get("diseases") or params.get("symptoms")
        response_text = "Sorry, I could not find any information."

        if user_input:
            # Try disease first
            response_text = process_disease_query(user_input)
            if not response_text:
                # If not a disease, try symptom lookup
                response_text = process_symptom_query(user_input)
            if not response_text:
                response_text = f"Sorry, no data available for '{user_input}'."

        return jsonify({"fulfillmentText": response_text})

    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({"fulfillmentText": "Sorry, something went wrong on the server."})

# ================== TWILIO WEBHOOK ==================
@app.route("/twilio-webhook", methods=["POST"])
def twilio_webhook():
    """Webhook for WhatsApp via Twilio."""
    try:
        incoming_msg = request.form.get("Body", "").strip()

        if not incoming_msg:
            reply = "Please enter a disease or symptom."
        else:
            # Try disease first
            reply = process_disease_query(incoming_msg)
            if not reply:
                # Then try symptom
                reply = process_symptom_query(incoming_msg)
            if not reply:
                reply = f"Sorry, no data available for '{incoming_msg}'."

        # TwiML response
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
