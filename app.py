import os
import requests
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# ---------- STATIC DATA URLs ----------
DISEASES_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/diseases.json"
SYMPTOMS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/symptoms.json"
PREVENTIONS_URL = "https://raw.githubusercontent.com/kattaNagasainikhila-wq/health_data/main/preventions.json"

# ---------- WHO Outbreak API ----------
WHO_API_URL = (
    "https://www.who.int/api/emergencies/diseaseoutbreaknews"
    "?sf_provider=dynamicProvider372&sf_culture=en"
    "&$orderby=PublicationDateAndTime%20desc"
    "&$expand=EmergencyEvent"
    "&$select=Title,TitleSuffix,OverrideTitle,UseOverrideTitle,regionscountries,"
    "ItemDefaultUrl,FormattedDate,PublicationDateAndTime"
    "&%24format=json&%24top=10&%24count=true"
)

# Cache for static JSON data
data_cache = {}

# ================== HELPERS ==================
def get_data_from_github(url):
    """Fetch and cache JSON data from GitHub raw URLs."""
    if url in data_cache:
        return data_cache[url]
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        data_cache[url] = data
        return data
    except Exception as e:
        print(f"Error fetching from GitHub: {e}")
        return None


def get_disease_symptoms(disease_info):
    """Get symptoms for a disease."""
    data = get_data_from_github(SYMPTOMS_URL)
    if data:
        return data.get(disease_name, [])
    return []


def get_disease_preventions(disease_info):
    """Get prevention measures for a disease."""
    data = get_data_from_github(PREVENTIONS_URL)
    if data:
        return data.get(disease_name, [])
    return []


def match_symptoms_to_diseases(symptoms_list):
    """Find possible diseases from given symptoms."""
    data = get_data_from_github(SYMPTOMS_URL)
    if not data:
        return []

    matches = {}
    for disease, disease_symptoms in data.items():
        normalized = [s.lower() for s in disease_symptoms]
        count = sum(1 for s in symptoms_list if s.lower() in normalized)
        if count > 0:
            matches[disease] = count

    return sorted(matches.items(), key=lambda x: x[1], reverse=True)


def get_who_outbreak_data():
    """Fetch outbreak news directly from WHO API."""
    try:
        response = requests.get(WHO_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "value" not in data or not data["value"]:
            return None

        outbreaks = []
        for item in data["value"][:5]:  # only latest 5
            title = item.get("OverrideTitle") or item.get("Title")
            date = item.get("FormattedDate", "Unknown date")
            url = "https://www.who.int" + item.get("ItemDefaultUrl", "")
            outbreaks.append(f"🦠 {title} ({date})\n🔗 {url}")

        return outbreaks
    except Exception as e:
        print(f"Error fetching WHO outbreak data: {e}")
        return None


# ================== WEBHOOK (Dialogflow + Twilio) ==================
@app.route('/webhook', methods=['POST'])
def webhook():
    reply = "I'm sorry, I couldn't find that information. Please try again."

    # ---------- Check if request is from Twilio (form-data) ----------
    if request.content_type != "application/json":
        user_message = request.form.get("Body", "").strip().lower()

        if "symptom" in user_message:
            reply = "Please provide your symptoms clearly (e.g., fever, cough)."
        elif "prevent" in user_message:
            reply = "Please provide a disease name to get its prevention measures."
        elif "outbreak" in user_message or "disease" in user_message:
            outbreaks = get_who_outbreak_data()
            if not outbreaks:
                reply = "⚠️ Unable to fetch outbreak data right now."
            else:
                reply = "🌍 Latest WHO Outbreak News:\n\n" + "\n\n".join(outbreaks[:3])
        else:
            reply = "Hi! 👋 You can ask me about disease symptoms, preventions, or latest outbreaks."

        resp = MessagingResponse()
        resp.message(reply)
        return str(resp)

    # ---------- Otherwise it's Dialogflow (JSON) ----------
    req = request.get_json(silent=True, force=True)
    intent = req.get('queryResult', {}).get('intent', {}).get('displayName', '')
    params = req.get('queryResult', {}).get('parameters', {})
    query_text = req.get('queryResult', {}).get('queryText', '').strip()

    # --------- Disease Info Intent ---------
    if intent == 'disease_info':
        disease_name = params.get('diseases') or query_text
        if disease_name:
            symptoms = get_disease_symptoms(disease_info)
            prevention = get_disease_preventions(disease_info)

            reply = f"ℹ️ Information about {disease_info.title()}:\n"
            reply += f"🤒 Symptoms: {', '.join(symptoms)}\n" if symptoms else "No symptoms data available.\n"
            reply += f"🛡 Prevention: {', '.join(prevention)}" if prevention else "No prevention info available."

    # --------- Symptoms Info Intent ---------
    elif intent == 'symptoms_info':
        symptoms_list = params.get('symptoms', [])
        matches = match_symptoms_to_diseases(symptoms_list)

        if matches:
            reply = "🩺 Based on your symptoms, possible diseases are:\n\n"
            for disease, count in matches:
                all_symptoms = get_disease_symptoms(disease)
                percent = round((count / len(all_symptoms)) * 100, 1) if all_symptoms else 0
                prevention = get_disease_preventions(disease)
                prevention_text = f"\n   🛡 Prevention: {', '.join(prevention)}" if prevention else ""
                reply += f"- {disease} ({count} symptom match, {percent}% match){prevention_text}\n"
        else:
            reply = "I couldn't match your symptoms to any disease. Please consult a doctor."

    # --------- WHO Outbreak Intent ---------
    elif intent == 'disease_outbreak.general':
        outbreaks = get_who_outbreak_data()
        if not outbreaks:
            reply = "⚠️ Unable to fetch outbreak data right now."
        else:
            reply = "🌍 Latest WHO Outbreak News:\n\n" + "\n\n".join(outbreaks)

    return jsonify({'fulfillmentText': reply})


# ================== MAIN ==================
if __name__ == '__main__':
    app.run(port=5000, debug=True)
