import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta


# Load environment variables
load_dotenv()

API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HOME = os.getenv("HOME_ADDRESS")
WORK = os.getenv("WORK_ADDRESS")
# Debug check (VERY IMPORTANT for GitHub)
if not API_KEY:
    raise ValueError("Missing GOOGLE_MAPS_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")

if not CHAT_ID:
    raise ValueError("Missing TELEGRAM_CHAT_ID")

# Set your target arrival time (adjust as needed)
WORK_START_HOUR = 9
WORK_START_MINUTE = 0

# Buffer time (parking, walking, etc.)
BUFFER_MINUTES = 15

# Your commute routes
MORNING_ROUTE = {
    "origin": HOME
    "destination": WORK
}

EVENING_ROUTE = {
    "origin": WORK
    "destination": HOME
}

# Baseline (we’ll improve this later with real data)
BASELINE_MINUTES = 18

def get_current_route():
    now = datetime.now()
    hour = now.hour

    # Morning commute (3 AM – 12 PM)
    if 3 <= hour < 12:
        return "morning", MORNING_ROUTE
    
    # Afternoon/evening commute
    else:
        return "evening", EVENING_ROUTE

def get_weather():
    api_key = os.getenv("OPENWEATHER_API_KEY")

    url = "https://api.openweathermap.org/data/2.5/weather"

    params = {
        "q": "Honolulu,US",
        "appid": api_key,
        "units": "imperial"
    }

    response = requests.get(url, params=params)
    data = response.json()
    print (data)
    try:
        weather_main = data["weather"][0]["main"]
        description = data["weather"][0]["description"]
        temp = data["main"]["temp"]

        return {
            "condition": weather_main,
            "description": description,
            "temperature": temp
        }

    except Exception as e:
        print("Weather error:", e)
        return None

def analyze_weather(weather):
    if not weather:
        return None

    condition = weather["condition"]

    if condition in ["Rain", "Drizzle", "Thunderstorm"]:
        impact = "🔴 Weather may slow commute"
    elif condition in ["Clouds"]:
        impact = "🟡 Minor impact possible"
    else:
        impact = "🟢 No weather impact"

    return {
        "condition": weather["description"],
        "impact": impact
    }

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    response = requests.post(url, data=payload)
    print("TELEGRAM STATUS:", response.status_code)
    print("TELEGRAM RESPONSE:", response.text)  # 👈 ADD THIS
    
    return response.json()

def get_commute_time(origin, destination):
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"
    }

    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE"
    }

    response = requests.post(url, json=body, headers=headers)
    data = response.json()

    try:
        route = data["routes"][0]

        duration_seconds = int(route["duration"].replace("s", ""))
        distance_meters = route["distanceMeters"]

        return {
            "distance_miles": round(distance_meters / 1609, 2),
            "duration_minutes": round(duration_seconds / 60, 1)
        }

    except Exception as e:
        print("Error parsing response:", e)
        return None


def analyze_commute(commute_data):
    if not commute_data:
        return None

    current = commute_data["duration_minutes"]
    ratio = current / BASELINE_MINUTES

    if ratio < 1.1:
        status = "🟢 Light traffic"
    elif ratio < 1.4:
        status = "🟡 Moderate traffic"
    else:
        status = "🔴 Heavy traffic"

    # Simple recommendation logic
    if ratio > 1.3:
        recommendation = "Leave earlier than usual"
    elif ratio < 1.0:
        recommendation = "Traffic is better than usual"
    else:
        recommendation = "Normal commute conditions"

    return {
        "current_minutes": current,
        "baseline_minutes": BASELINE_MINUTES,
        "ratio": round(ratio, 2),
        "status": status,
        "recommendation": recommendation
    }

def get_leave_recommendation(commute_analysis):
    if not commute_analysis:
        return None

    now = datetime.now()

    # Target arrival time (today)
    arrival_time = now.replace(
        hour=WORK_START_HOUR,
        minute=WORK_START_MINUTE,
        second=0,
        microsecond=0
    )

    # If it's already past work start, assume tomorrow
    if now > arrival_time:
        arrival_time += timedelta(days=1)

    commute_minutes = commute_analysis["current_minutes"]
    total_travel_time = commute_minutes + BUFFER_MINUTES

    leave_time = arrival_time - timedelta(minutes=total_travel_time)

    minutes_until_leave = (leave_time - now).total_seconds() / 60

    # Decision logic
    if minutes_until_leave <= 0:
        status = "🚨 Leave NOW (you’re late)"
    elif minutes_until_leave <= 10:
        status = f"⚠️ Leave in {int(minutes_until_leave)} min"
    else:
        status = f"🕒 Leave in {int(minutes_until_leave)} min"

    return {
        "current_time": now.strftime("%I:%M %p"),
        "leave_time": leave_time.strftime("%I:%M %p"),
        "arrival_time": arrival_time.strftime("%I:%M %p"),
        "minutes_until_leave": int(minutes_until_leave),
        "status": status
    }

def format_message(analysis, leave_plan, weather_analysis, route_type):
    route_label = "🌅 Morning Commute" if route_type == "morning" else "🌇 Evening Commute"

    weather_text = ""
    if weather_analysis:
        weather_text = f"\n🌦️ Weather: {weather_analysis['condition']}\n{weather_analysis['impact']}\n"

    message = f"""
{route_label}

🚗 Commute Update
Traffic: {analysis['status']}
Commute: {analysis['current_minutes']} min

{weather_text}

⏰ Leave Plan:
{leave_plan['status']}
Arrive by {leave_plan['arrival_time']}
"""

    return message

if __name__ == "__main__":
    print("Using Routes API...")
    print("SCRIPT STARTED")

    weather = get_weather()
    weather_analysis = analyze_weather(weather)
    route_type, route = get_current_route()
    commute = get_commute_time(
    route["origin"],
    route["destination"]
    )   
    analysis = analyze_commute(commute)
    leave_plan = get_leave_recommendation(analysis)

    message = format_message(analysis, leave_plan, weather_analysis, route_type)

    print("MESSAGE GENERATED")
    print(message)

    print("SENDING TELEGRAM MESSAGE...")
    send_telegram_message(message)

    print("DONE")