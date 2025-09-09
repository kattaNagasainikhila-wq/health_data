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

def process_disease_query(user_input):
    """Process disease query and return response text."""
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
        return f"Sorry, I do not have information about '{user_input}'."

def get_diseases_by_symptom(symptom_name):
    """Fetch diseases list from mapping.json based on symptom."""
    data = fetch_json(MAPPING_URL)
    return data.get(symptom_name.lower(), [])

# ================== DIALOGFLOW WEBHOOK ==================
# ================== DIALOGFLOW WEBHOOK ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    """Dialogflow webhook for fulfillment."""
    try:
        req = request.get_json(force=True)
        intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "")
        params = req.get("queryResult", {}).get("parameters", {})

        response_text = "Sorry, I could not find information."

        # Case 1: Disease query
        disease_input = params.get("diseases")
        if disease_input:
            if isinstance(disease_input, list):
                disease_input = disease_input[0]
            response_text = process_disease_query(disease_input)

        # Case 2: Symptom query
        elif intent == "symptoms_info":
            symptom_input = params.get("symptoms")
            if symptom_input:
                # Ensure it's a string
                if isinstance(symptom_input, list):
                    symptom_input = symptom_input[0]
                diseases = get_diseases_by_symptom(symptom_input)
                if diseases:
                    response_text = f"🦠 The symptom '{symptom_input}' is commonly seen in: {', '.join(diseases)}."
                else:
                    response_text = f"Sorry, I don’t have diseases mapped for the symptom '{symptom_input}'."

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
            reply = "Please enter a disease name or a symptom to get info."
        else:
            # Try disease query first
            reply = process_disease_query(incoming_msg)

            # If disease not found, try symptom
            if "do not have information" in reply.lower():
                diseases = get_diseases_by_symptom(incoming_msg)
                if diseases:
                    reply = f"🦠 The symptom '{incoming_msg}' is commonly seen in: {', '.join(diseases)}."

        # TwiML response to Twilio
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
