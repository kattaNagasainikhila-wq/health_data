from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Raw GitHub URLs of your files
DISEASES_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/diseases_data.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/symptoms_data.json"
PREVENTIONS_URL ="https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/preventions_data.json" 
# Function to load JSON from GitHub
def load_json(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return {}

# Function to find disease by name or synonym
def find_disease(user_input, diseases_data):
    user_input_lower = user_input.lower()
    for disease, info in diseases_data.items():
        if disease.lower() == user_input_lower:
            return disease
        for syn in info.get("synonyms", []):
            if syn.lower() == user_input_lower:
                return disease
    return None

@app.route("/webhook", methods=["POST"])
def webhook():
    req = request.get_json(force=True)
    intent_name = req['queryResult']['intent']['displayName']
    response_text = ""

    if intent_name == "disease_info":
        disease_input = req['queryResult']['parameters'].get('diseases')

        # Load all JSON files from GitHub
        diseases_data = load_json(DISEASES_URL)
        symptoms_data = load_json(SYMPTOMS_URL)
        preventions_data = load_json(PREVENTIONS_URL)

        # Find the disease
        disease_found = find_disease(disease_input, diseases_data)

        if disease_found:
            symptoms = ", ".join(symptoms_data.get(disease_found, []))
            preventions = "; ".join(preventions_data.get(disease_found, []))
            response_text = f"**{disease_found}**\nSymptoms: {symptoms}\nPrevention: {preventions}"
        else:
            response_text = f"Sorry, I don't have information about '{disease_input}'."

    return jsonify({"fulfillmentText": response_text})

if __name__ == "__main__":
    app.run(port=5000, debug=True)
