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

def get_diseases_by_symptom(symptom):
    """Get diseases associated with a given symptom from mapping.json."""
    mapping_data = fetch_json(MAPPING_URL)
    return mapping_data.get(symptom.lower(), [])

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

def process_symptom_query(symptoms_list):
    """Process symptom query and return possible diseases (case-insensitive)."""
    mapping_data = fetch_json(MAPPING_URL)
    possible_diseases = set()

    normalized_symptoms = [s.lower() for s in symptoms_list]

    for symptom in normalized_symptoms:
        diseases = mapping_data.get(symptom, [])
        if diseases:
            possible_diseases.update(diseases)

    if possible_diseases:
        return f"🦠 Based on the symptom(s) {', '.join(symptoms_list)}, possible diseases are: {', '.join(possible_diseases)}."
    else:
        return f"Sorry, I don’t have diseases mapped for the given symptom(s): {', '.join(symptoms_list)}."

# ================== DIALOGFLOW WEBHOOK ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    """Dialogflow webhook for fulfillment."""
    try:
        req = request.get_json(force=True)
        print("Dialogflow Request:", json.dumps(req, indent=2))  # DEBUG LOG

        intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "")
        params = req.get("queryResult", {}).get("parameters", {})

        response_text = "Sorry, I could not find information."

        # Case 1: Disease info
        disease_input = params.get("diseases")
        if disease_input:
            if isinstance(disease_input, list) and disease_input:
                disease_input = disease_input[0]
            response_text = process_disease_query(disease_input)

        # Case 2: Symptom to disease mapping
        elif intent == "symptoms_info":
            symptoms = params.get("symptoms", [])
            if isinstance(symptoms, str):
                symptoms = [symptoms]
            if symptoms:
                # normalize symptoms here
                original_symptoms = symptoms
                symptoms = [s.lower() for s in symptoms]
                response_text = process_symptom_query(original_symptoms)

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
        from_number = request.form.get("From", "")

        if not incoming_msg:
            reply = "Please enter a disease name or symptom to get info."
        else:
            # First try as disease
            diseases_data = fetch_json(DISEASES_URL)
            disease_key = find_disease_key(incoming_msg, diseases_data)

            if disease_key:
                reply = process_disease_query(incoming_msg)
            else:
                # Otherwise, try as symptom(s)
                reply = process_symptom_query([incoming_msg])

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
