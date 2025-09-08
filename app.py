import os
import json
import requests
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ---------- GITHUB RAW FILES ----------
DISEASES_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/diseases.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/symptoms.json"
PREVENTIONS_URL ="https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/preventions.json"

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

def find_diseases_by_symptoms(user_symptoms):
    """Given a list of symptoms, return matching diseases."""
    symptoms_data = fetch_json(SYMPTOMS_URL)
    matched_diseases = []

    for disease, symptoms in symptoms_data.items():
        matches = [s for s in user_symptoms if s.lower() in [sym.lower() for sym in symptoms]]
        if matches:
            matched_diseases.append({
                "disease": disease,
                "matched_symptoms": matches
            })

    return matched_diseases

# ================== DIALOGFLOW WEBHOOK ==================
# ================== DIALOGFLOW WEBHOOK ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    """Dialogflow webhook for fulfillment."""
    try:
        req = request.get_json(force=True)
        intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "")
        params = req.get("queryResult", {}).get("parameters", {})

        response_text = "Sorry, I could not find relevant information."

        # Case 1: User provides a disease name
        if params.get("diseases"):
            disease_input = params.get("diseases")
            response_text = process_disease_query(disease_input)

        # Case 2: User provides symptoms
        elif params.get("symptoms"):
            user_symptoms = params.get("symptoms")
            matches = find_diseases_by_symptoms(user_symptoms)
            if matches:
                response_text = "Based on the symptoms, possible diseases are:\n"
                for match in matches:
                    response_text += f"\n🦠 {match['disease']} (matched: {', '.join(match['matched_symptoms'])})"
            else:
                response_text = "I couldn't find any diseases matching those symptoms."

        # Always return fulfillmentText (never blank)
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
            reply = "Please enter a disease name or symptoms."
        else:
            # Check if multiple symptoms provided (comma-separated)
            if "," in incoming_msg:
                symptoms = [s.strip() for s in incoming_msg.split(",")]
                matches = find_diseases_by_symptoms(symptoms)
                if matches:
                    reply = "Possible diseases based on your symptoms:\n"
                    for match in matches:
                        reply += f"\n🦠 {match['disease']} (matched: {', '.join(match['matched_symptoms'])})"
                else:
                    reply = "No diseases found for those symptoms."
            else:
                # Assume it's a disease query
                reply = process_disease_query(incoming_msg)

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
