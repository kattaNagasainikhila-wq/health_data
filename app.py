import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ---------- GITHUB RAW FILES ----------
DISEASES_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/diseases.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/symptoms.json"
#PREVENTIONS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/preventions.json"

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

"""def get_preventions(disease_name):
    Get prevention list from prevention JSON.
    data = fetch_json(PREVENTIONS_URL)
    return data.get(disease_name, [])"""

# ================== WEBHOOK ==================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        req = request.get_json(force=True)
        intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "")
        params = req.get("queryResult", {}).get("parameters", {})

        disease_input = None
        if params.get("diseases"):
            disease_input = params["diseases"]

        response_text = "Sorry, I could not find information for that disease."

        if disease_input:
            # Load diseases JSON
            diseases_data = fetch_json(DISEASES_URL)
            disease_key = find_disease_key(disease_input, diseases_data)
            if disease_key:
                if intent in ["ask_symptoms", "disease_info"]:
                    symptoms = get_symptoms(disease_key)
                    if symptoms:
                        response_text = f"🤒 Symptoms of {disease_key}: {', '.join(symptoms)}."
                    else:
                        response_text = f"Sorry, symptoms for {disease_key} are not available."
                if intent in ["ask_preventions", "disease_info"]:
                    preventions = get_preventions(disease_key)
                    if preventions:
                        response_text += f"\n🛡 Prevention measures: {', '.join(preventions)}"
                    else:
                        response_text += f"\nPrevention info for {disease_key} is not available."
            else:
                response_text = f"Sorry, I do not have information about '{disease_input}'."

        return jsonify({"fulfillmentText": response_text})

    except Exception as e:
        print("Webhook Error:", e)
        return jsonify({"fulfillmentText": "Sorry, something went wrong on the server."})

# ================== MAIN ==================
if __name__ == "__main__":
    app.run(port=5000, debug=True)
