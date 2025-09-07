import os
import json
import re
import requests
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ---------- GITHUB RAW FILES ----------
DISEASES_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/diseases.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/symptoms.json"
PREVENTIONS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/preventions.json"

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

def clean_input(text):
    """Normalize and clean user input (remove punctuation, lowercase)."""
    return re.sub(r"[^\w\s]", "", text.lower())

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

# ================== MAIN PROCESSORS ==================
def process_disease_query(user_input):
    """Process disease query and return info."""
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
    return None

def process_symptom_query(user_input):
    """Process symptom(s) query and return possible diseases."""
    symptoms_data = fetch_json(SYMPTOMS_URL)

    # Clean input: remove punctuation, lowercase
    clean_text = clean_input(user_input)

    # Split by "and" or "," into individual symptoms
    symptoms_given = [s.strip() for s in re.split(r"and|,", clean_text) if s.strip()]
    print("Parsed symptoms:", symptoms_given)

    matched_diseases = {}
    for disease, symptoms in symptoms_data.items():
        normalized_symptoms = [s.lower() for s in symptoms]
        for symptom in symptoms_given:
            if symptom in normalized_symptoms:
                matched_diseases[disease] = matched_diseases.get(disease, 0) + 1

    if matched_diseases:
        sorted_diseases = sorted(matched_diseases.items(), key=lambda x: x[1], reverse=True)
        response = "🩺 Based on your symptoms, possible diseases are:\n"
        for disease, count in sorted_diseases:
            total = len(symptoms_data.get(disease, []))
            percent = round((count / total) * 100, 1) if total else 0
            response += f"- {disease} ({count} symptom match, {percent}% match)\n"
        return response.strip()
    return None

# ================== DIALOGFLOW WEBHOOK ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    """Dialogflow webhook for fulfillment."""
    try:
        req = request.get_json(force=True)
        user_input = req.get("queryResult", {}).get("queryText", "").strip()
        print("Dialogflow input:", user_input)

        response_text = process_disease_query(user_input)
        if not response_text:
            response_text = process_symptom_query(user_input)

        if not response_text:
            response_text = f"Sorry, I do not have information about '{user_input}'."

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
        print("Twilio input:", incoming_msg)

        if not incoming_msg:
            reply = "Please enter a disease name or symptoms."
        else:
            reply = process_disease_query(incoming_msg)
            if not reply:
                reply = process_symptom_query(incoming_msg)
            if not reply:
                reply = f"Sorry, I do not have information about '{incoming_msg}'."

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
