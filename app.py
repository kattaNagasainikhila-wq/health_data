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

data_cache = {}

# ============== HELPERS =================
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

def clean_input(text):
    return re.sub(r"[^\w\s]", "", text.lower())

# ================== PROCESSORS ==================
def process_symptom_query(symptoms_list):
    """Return possible diseases based on symptoms, always returns text."""
    symptoms_data = fetch_json(SYMPTOMS_URL)
    preventions_data = fetch_json(PREVENTIONS_URL)

    if not symptoms_list:
        return "Sorry, I couldn't detect any symptoms. Please provide your symptoms clearly."

    symptoms_given = [s.lower().strip() for s in symptoms_list]
    matched_diseases = {}

    for disease, disease_symptoms in symptoms_data.items():
        normalized_symptoms = [s.lower().strip() for s in disease_symptoms]
        match_count = sum(1 for s in symptoms_given if s in normalized_symptoms)
        if match_count > 0:
            matched_diseases[disease] = match_count

    if matched_diseases:
        sorted_diseases = sorted(matched_diseases.items(), key=lambda x: x[1], reverse=True)
        response = "🩺 Based on your symptoms, possible diseases are:\n"
        for disease, count in sorted_diseases:
            total_symptoms = len(symptoms_data.get(disease, []))
            percent = round((count / total_symptoms) * 100, 1) if total_symptoms else 0
            prevention_list = preventions_data.get(disease, [])
            prevention_text = f"\n🛡 Prevention: {', '.join(prevention_list)}" if prevention_list else ""
            response += f"- {disease} ({count} symptom match, {percent}% match){prevention_text}\n"
        return response.strip()
    else:
        return "I couldn't find any disease matching your symptoms exactly. Please consult a doctor if you feel unwell."

def process_disease_query(disease_name):
    """Return info about a disease, including symptoms and prevention."""
    diseases_data = fetch_json(DISEASES_URL)
    symptoms_data = fetch_json(SYMPTOMS_URL)
    preventions_data = fetch_json(PREVENTIONS_URL)

    if not disease_name:
        return "Please provide a disease name to get information."

    disease_key = None
    for key in diseases_data.keys():
        if key.lower() == disease_name.lower():
            disease_key = key
            break

    if not disease_key:
        return f"Sorry, I do not have information about '{disease_name}'."

    symptoms = symptoms_data.get(disease_key, [])
    preventions = preventions_data.get(disease_key, [])

    response = f"Here’s what I found about {disease_key}:"
    if symptoms:
        response += f"\n🤒 Symptoms: {', '.join(symptoms)}."
    if preventions:
        response += f"\n🛡 Prevention: {', '.join(preventions)}"
    return response

# ================== DIALOGFLOW WEBHOOK ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        req = request.get_json(force=True)
        intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "")
        parameters = req.get("queryResult", {}).get("parameters", {})
        query_text = req.get("queryResult", {}).get("queryText", "").strip()

        response_text = None

        if intent == "symptoms_info":
            symptoms_list = parameters.get("symptoms", [])
            response_text = process_symptom_query(symptoms_list) or process_symptom_query([query_text])
        elif intent == "disease_info":
            disease_name = parameters.get("diseases") or query_text
            response_text = process_disease_query(disease_name)
        else:
            # fallback: try symptoms first, then disease info
            response_text = process_symptom_query([query_text]) or process_disease_query(query_text)

        # Always return fulfillmentMessages to avoid empty response
        return jsonify({
            "fulfillmentMessages": [
                {"text": {"text": [response_text]}}
            ]
        })

    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({
            "fulfillmentMessages": [
                {"text": {"text": ["Sorry, something went wrong on the server."]}}
            ]
        })

# ================== TWILIO WEBHOOK ==================
@app.route("/twilio-webhook", methods=["POST"])
def twilio_webhook():
    try:
        incoming_msg = request.form.get("Body", "").strip()
        reply = process_disease_query(incoming_msg) or process_symptom_query([incoming_msg])
        if not reply:
            reply = f"Sorry, I do not have information about '{incoming_msg}'."

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
