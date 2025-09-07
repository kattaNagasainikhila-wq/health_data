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
    symptoms_data = fetch_json(SYMPTOMS_URL)
    if not symptoms_list:
        return None

    symptoms_given = [s.lower().strip() for s in symptoms_list]

    matched_diseases = {}
    for disease, disease_symptoms in symptoms_data.items():
        normalized_symptoms = [s.lower().strip() for s in disease_symptoms]
        for symptom in symptoms_given:
            if symptom in normalized_symptoms:
                matched_diseases[disease] = matched_diseases.get(disease, 0) + 1

    if not matched_diseases:
        return None

    sorted_diseases = sorted(matched_diseases.items(), key=lambda x: x[1], reverse=True)
    response = "🩺 Based on your symptoms, possible diseases are:\n"
    for disease, count in sorted_diseases:
        total = len(symptoms_data.get(disease, []))
        percent = round((count / total) * 100, 1) if total else 0
        response += f"- {disease} ({count} symptom match, {percent}% match)\n"
    return response.strip()

def process_disease_query(disease_name):
    diseases_data = fetch_json(DISEASES_URL)
    symptoms_data = fetch_json(SYMPTOMS_URL)
    preventions_data = fetch_json(PREVENTIONS_URL)

    disease_key = disease_name.strip()
    if not disease_key:
        return None

    # Match disease ignoring case
    matched_key = None
    for key in diseases_data.keys():
        if key.lower() == disease_key.lower():
            matched_key = key
            break
    if not matched_key:
        return None

    symptoms = symptoms_data.get(matched_key, [])
    preventions = preventions_data.get(matched_key, [])

    response = f"Here’s what I found about {matched_key}:"
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
            response_text = process_symptom_query([query_text]) or process_disease_query(query_text)

        if not response_text:
            response_text = f"Sorry, I do not have information about '{query_text}'."

        # Return fulfillmentMessages for Dialogflow
        return jsonify({
            "fulfillmentMessages": [
                {"text": {"text": [response_text]}}
            ]
        })

    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({"fulfillmentMessages": [{"text": {"text": ["Sorry, something went wrong."]}}]})

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
