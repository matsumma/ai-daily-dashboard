import os
import requests
import re
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone


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
    "origin": HOME,
    "destination": WORK
}
print(MORNING_ROUTE)

EVENING_ROUTE = {
    "origin": WORK,
    "destination": HOME
}

# Baseline (we’ll improve this later with real data)
BASELINE_MINUTES = 18

def get_current_route():
    HST = timezone(timedelta(hours=-10))
    now = datetime.now(HST)
    #now = datetime.now()
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
    #print (data)
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
    #print("TELEGRAM STATUS:", response.status_code)
    #print("TELEGRAM RESPONSE:", response.text)  # 👈 ADD THIS
    
    return response.json()

def extract_key_roads(steps):
    roads = []

    for step in steps:
        instruction = step.get("navigationInstruction", {}).get("instructions", "")

        # Extract road names using regex patterns
        matches = []

        # Highways (H-1, I-95, etc.)
        matches += re.findall(r'\bH-\d+\s?[EWNS]?\b', instruction)

        # Common road types
        matches += re.findall(r'\b[A-Z][a-zA-Z\s]+(?:St|Street|Rd|Road|Ave|Avenue|Blvd|Highway|Hwy)\b', instruction)

        for match in matches:
            cleaned = match.strip()
            roads.append(cleaned)

    # Remove duplicates while preserving order
    seen = set()
    unique_roads = []
    for r in roads:
        if r not in seen:
            seen.add(r)
            unique_roads.append(r)

    return unique_roads[:10]

def get_unique_route_segments(primary_roads, alternate_roads):
    primary_set = set(primary_roads)
    alternate_set = set(alternate_roads)

    primary_unique = [r for r in primary_roads if r not in alternate_set]
    alternate_unique = [r for r in alternate_roads if r not in primary_set]

    return primary_unique, alternate_unique


def get_commute_routes(origin, destination):
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.routeLabels,routes.legs.steps.navigationInstruction"
    }

    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True
    }

    response = requests.post(url, json=body, headers=headers)
    data = response.json()
    #print("STEP DEBUG:", data["routes"][0]["legs"][0]["steps"][:2])
    print("DEBUG ROUTES:", data)  # keep for now

    routes = []

    try:
        for route in data.get("routes", []):
            duration_seconds = int(route["duration"].replace("s", ""))
            distance_meters = route["distanceMeters"]
            steps = route["legs"][0]["steps"]
            key_roads = extract_key_roads(steps)
            routes.append({
                "duration_minutes": round(duration_seconds / 60, 1),
                "distance_miles": round(distance_meters / 1609, 2),
                "labels": route.get("routeLabels", []),
                "key_roads": key_roads
            })
            print("KEY ROADS:", key_roads) 

        return routes[:2]  # only return top 2

    except Exception as e:
        print("Error parsing routes:", e)
        return None
        
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
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True
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

    HST = timezone(timedelta(hours=-10))
    now = datetime.now(HST)
    #now = datetime.now()
    print("DEBUG CURRENT TIME:", now.strftime("%Y-%m-%d %I:%M %p"))

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

def format_message(analysis, leave_plan, weather_analysis, route_type, route, primary_route, alternate_route):
    origin = route["origin"]
    destination = route["destination"]
    origin_short = shorten_location(origin)
    destination_short = shorten_location(destination)
    primary_route_text = format_route_summary(primary_route.get("key_roads", []))

    route_label = "🌅 Morning Commute" if route_type == "morning" else "🌇 Evening Commute"

    # Compute time diff ONCE
    time_diff = None
    if alternate_route:
        time_diff = round(
            alternate_route["duration_minutes"] - analysis["current_minutes"], 
            1
        )

    # Alternate section (ONLY ONE BLOCK)
    alt_section = ""

    if alternate_route:
        diff_text = f"+{time_diff} min" if time_diff > 0 else f"{time_diff} min"
        alt_route_text = format_route_summary(alternate_route.get("key_roads", []))

        alt_section = f"""
🛣️ Alternate: {alternate_route['duration_minutes']} min ({diff_text})
Route: {alt_route_text}
"""
    

    weather_text = ""
    if weather_analysis:
        weather_text = f"\n🌦️ Weather: {weather_analysis['condition']}\n{weather_analysis['impact']}\n"

    message = f"""
    {route_label}

    🚗 {origin_short} → {destination_short}

    🚗 Primary: {analysis['current_minutes']} min
    Route: {primary_route_text}

    {alt_section}

    Traffic: {analysis['status']}

    {weather_text}

    ⏰ Leave Plan:
    {leave_plan['status']}
    Arrive by {leave_plan['arrival_time']}
    """

    return message

def format_route_summary(roads):
    if not roads:
        return "Route unavailable"

    # Keep it short and clean
    return " → ".join(roads)

def shorten_location(address):
    return address.split(",")[0]

if __name__ == "__main__":
    print("Using Routes API...")
    #print("SCRIPT STARTED")

    weather = get_weather()
    weather_analysis = analyze_weather(weather)
    route_type, route = get_current_route()
    routes = get_commute_routes(route["origin"], route["destination"])

    primary_route = routes[0] if routes else None
    alternate_route = routes[1] if routes and len(routes) > 1 else None
    
    # Default values
    primary_unique = primary_route.get("key_roads", []) if primary_route else []
    alternate_unique = []

    if primary_route and alternate_route:
        primary_unique, alternate_unique = get_unique_route_segments(
            primary_route.get("key_roads", []),
            alternate_route.get("key_roads", [])
        )

    # Store back into route objects
    if primary_route:
        primary_route["unique_roads"] = primary_unique

    if alternate_route:
        alternate_route["unique_roads"] = alternate_unique

    print("PRIMARY UNIQUE:", primary_route.get("unique_roads"))
    if alternate_route:
        print("ALT UNIQUE:", alternate_route.get("unique_roads"))
    

    analysis = analyze_commute(primary_route)
    leave_plan = get_leave_recommendation(analysis)

    message = format_message(analysis, leave_plan, weather_analysis, route_type, route, primary_route, alternate_route)

    print("MESSAGE GENERATED")
    print(message)

    print("SENDING TELEGRAM MESSAGE...")
    send_telegram_message(message)

    print("DONE")