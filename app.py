import os
import json
import requests
from flask import Flask, request, jsonify, Response, abort
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

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
    user_input_lower = user_input.lower()
    for disease, info in diseases_data.items():
        if disease.lower() == user_input_lower:
            return disease
        for syn in info.get("synonyms", []):
            if syn.lower() == user_input_lower:
                return disease
    return None

def get_symptoms(disease_name):
    return fetch_json(SYMPTOMS_URL).get(disease_name, [])

def get_preventions(disease_name):
    return fetch_json(PREVENTIONS_URL).get(disease_name, [])

def get_diseases_by_symptom(symptom):
    return fetch_json(MAPPING_URL).get(symptom.lower(), [])

def process_disease_query(user_input):
    diseases_data = fetch_json(DISEASES_URL)
    disease_key = find_disease_key(user_input, diseases_data)
    if disease_key:
        symptoms = get_symptoms(disease_key)
        preventions = get_preventions(disease_key)

        response = f"Here’s what I found about {disease_key}:"
        response += f"\n🤒 Symptoms: {', '.join(symptoms)}." if symptoms else "\n(No symptoms data available.)"
        response += f"\n🛡 Prevention: {', '.join(preventions)}" if preventions else "\n(No prevention info available.)"
        return response
    return f"Sorry, I do not have information about '{user_input}'."

def process_symptom_query(symptoms_list):
    mapping_data = fetch_json(MAPPING_URL)
    possible_diseases = set()
    not_found = []

    normalized = []
    for s in symptoms_list:
        if "," in s:
            normalized.extend([part.strip() for part in s.split(",") if part.strip()])
        else:
            normalized.append(s.strip())

    for symptom in normalized:
        found = False
        for key, diseases in mapping_data.items():
            if key.lower() == symptom.lower():
                possible_diseases.update(diseases)
                found = True
                break
        if not found:
            not_found.append(symptom)

    response_parts = []
    if possible_diseases:
        response_parts.append(f"🦠 Based on {', '.join(normalized)}, possible diseases: {', '.join(possible_diseases)}.")
    if not_found:
        response_parts.append(f"⚠️ Not found in mapping: {', '.join(not_found)}.")

    return "\n".join(response_parts) if response_parts else "Sorry, no disease info found."

# ================== DIALOGFLOW WEBHOOK ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        req = request.get_json(force=True)
        intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "")
        params = req.get("queryResult", {}).get("parameters", {})

        response_text = "Sorry, I could not find information."

        if params.get("diseases"):
            disease_input = params["diseases"]
            if isinstance(disease_input, list) and disease_input:
                disease_input = disease_input[0]
            response_text = process_disease_query(disease_input)

        elif intent == "symptoms_info":
            symptoms = params.get("symptoms", [])
            if isinstance(symptoms, str):
                symptoms = [symptoms]
            if symptoms:
                response_text = process_symptom_query(symptoms)

        return jsonify({"fulfillmentText": response_text})

    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({"fulfillmentText": "Sorry, something went wrong."})

# ================== TWILIO WEBHOOK ==================
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")

@app.route("/twilio", methods=["POST"])
def twilio_webhook():
    try:
        # Validate request (optional, but recommended)
        if TWILIO_AUTH_TOKEN:
            validator = RequestValidator(TWILIO_AUTH_TOKEN)
            twilio_sig = request.headers.get("X-Twilio-Signature", "")
            url = request.url
            params = request.form.to_dict()
            if not validator.validate(url, params, twilio_sig):
                abort(403)

        incoming_msg = request.form.get("Body", "").strip()
        reply = "Please enter a disease name or symptom."

        if incoming_msg:
            diseases_data = fetch_json(DISEASES_URL)
            if find_disease_key(incoming_msg, diseases_data):
                reply = process_disease_query(incoming_msg)
            else:
                reply = process_symptom_query([incoming_msg])

        resp = MessagingResponse()
        resp.message(reply)
        return Response(str(resp), mimetype="application/xml")

    except Exception as e:
        print("Twilio Webhook Error:", e)
        resp = MessagingResponse()
        resp.message("Sorry, something went wrong.")
        return Response(str(resp), mimetype="application/xml")

# ================== OPTIONAL: STATUS CALLBACK ==================
@app.route("/status", methods=["POST"])
def status_callback():
    sid = request.form.get("MessageSid")
    status = request.form.get("MessageStatus")
    to_number = request.form.get("To")
    print(f"Status update: Message {sid} to {to_number} is {status}")
    return ("", 200)

# ================== MAIN ==================
if __name__ == "__main__":
    app.run(port=5000, debug=True)
