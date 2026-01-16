### integrations/weather_api.py

import os
import aiohttp
import random
from dotenv import load_dotenv
from utils.logger import log_info, log_error

load_dotenv()

# Load API key from .env
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

FALLBACK_RESPONSES = [
    "The weather today is as bright and sunny as your smile!",
    "It's warm outside, warmer than a fresh plate of jollof rice!",
    "There might be some rain later, enough to make the frogs happy but not enough to cancel playtime!",
    "The sun is playing hide and seek with the clouds today!",
    "It's the perfect weather for eating ice cream before it melts too quickly!",
    "The weather is perfect for flying a kite - if you have one!",
    "It's so nice outside, even the birds are singing extra loud today!",
    "The clouds look like cotton candy floating in the sky!"
]

# Enhanced city mapping with more Nigerian locations
CITY_ALIASES = {
    # Major cities and states
    "abuja": "Abuja,NG",
    "lagos": "Lagos,NG", 
    "kano": "Kano,NG",
    "ph": "Port Harcourt,NG",
    "port harcourt": "Port Harcourt,NG",
    "kaduna": "Kaduna,NG",
    "ibadan": "Ibadan,NG",
    "enugu": "Enugu,NG",
    "jos": "Jos,NG",
    "maiduguri": "Maiduguri,NG",
    "yola": "Yola,NG",
    "calabar": "Calabar,NG",
    "uyo": "Uyo,NG",
    "asaba": "Asaba,NG",
    "benin city": "Benin City,NG",
    "benin": "Benin City,NG",
    "akure": "Akure,NG",
    "osogbo": "Osogbo,NG",
    "ado-ekiti": "Ado-Ekiti,NG",
    "ilorin": "Ilorin,NG",
    "minna": "Minna,NG",
    "birnin kebbi": "Birnin Kebbi,NG",
    "sokoto": "Sokoto,NG",
    "gusau": "Gusau,NG",
    "katsina": "Katsina,NG",
    "dutse": "Dutse,NG",
    "lokoja": "Lokoja,NG",
    "lafia": "Lafia,NG",
    "makurdi": "Makurdi,NG",
    "umuahia": "Umuahia,NG",
    "awka": "Awka,NG",
    "abakaliki": "Abakaliki,NG",
    "owerri": "Owerri,NG",
    "yenagoa": "Yenagoa,NG",
    "damaturu": "Damaturu,NG",
    "bauchi": "Bauchi,NG",
    "gombe": "Gombe,NG",
    "jalingo": "Jalingo,NG",
    "zaria": "Zaria,NG",
    
    # State names mapped to capitals
    "borno": "Maiduguri,NG",
    "borno state": "Maiduguri,NG",
    "lagos state": "Lagos,NG",
    "kano state": "Kano,NG",
    "rivers state": "Port Harcourt,NG",
    "rivers": "Port Harcourt,NG",
    "kaduna state": "Kaduna,NG",
    "oyo state": "Ibadan,NG",
    "oyo": "Ibadan,NG",
    "enugu state": "Enugu,NG",
    "plateau state": "Jos,NG",
    "plateau": "Jos,NG",
    "adamawa state": "Yola,NG",
    "adamawa": "Yola,NG",
    "cross river state": "Calabar,NG",
    "cross river": "Calabar,NG",
    "akwa ibom state": "Uyo,NG",
    "akwa ibom": "Uyo,NG",
    "delta state": "Asaba,NG",
    "delta": "Asaba,NG",
    "edo state": "Benin City,NG",
    "edo": "Benin City,NG",
    "ondo state": "Akure,NG",
    "ondo": "Akure,NG",
    "osun state": "Osogbo,NG",
    "osun": "Osogbo,NG",
    "ekiti state": "Ado-Ekiti,NG",
    "ekiti": "Ado-Ekiti,NG",
    "kwara state": "Ilorin,NG",
    "kwara": "Ilorin,NG",
    "niger state": "Minna,NG",
    "niger": "Minna,NG",
    "kebbi state": "Birnin Kebbi,NG",
    "kebbi": "Birnin Kebbi,NG",
    "sokoto state": "Sokoto,NG",
    "zamfara state": "Gusau,NG",
    "zamfara": "Gusau,NG",
    "katsina state": "Katsina,NG",
    "jigawa state": "Dutse,NG",
    "jigawa": "Dutse,NG",
    "kogi state": "Lokoja,NG",
    "kogi": "Lokoja,NG",
    "nasarawa state": "Lafia,NG",
    "nasarawa": "Lafia,NG",
    "benue state": "Makurdi,NG",
    "benue": "Makurdi,NG",
    "abia state": "Umuahia,NG",
    "abia": "Umuahia,NG",
    "anambra state": "Awka,NG",
    "anambra": "Awka,NG",
    "ebonyi state": "Abakaliki,NG",
    "ebonyi": "Abakaliki,NG",
    "imo state": "Owerri,NG",
    "imo": "Owerri,NG",
    "bayelsa state": "Yenagoa,NG",
    "bayelsa": "Yenagoa,NG",
    "yobe state": "Damaturu,NG",
    "yobe": "Damaturu,NG",
    "bauchi state": "Bauchi,NG",
    "gombe state": "Gombe,NG",
    "taraba state": "Jalingo,NG",
    "taraba": "Jalingo,NG",
    
    # FCT
    "fct": "Abuja,NG",
    "federal capital territory": "Abuja,NG"
}


def normalize_location(text: str) -> str:
    """Enhanced location normalization for Nigerian cities and states."""
    text_lower = text.lower().strip()
    
    # Direct match first
    if text_lower in CITY_ALIASES:
        return CITY_ALIASES[text_lower]
    
    # Partial match for compound names
    for alias, city in CITY_ALIASES.items():
        if alias in text_lower or text_lower in alias:
            return city
    
    # Default fallback
    return "Maiduguri,NG"  # Borno state capital


async def fetch_weather(city: str) -> dict:
    """
    Fetch current weather data for a given city using OpenWeatherMap.

    Args:
        city: City name (e.g., "Lagos" or "Maiduguri")

    Returns:
        A dictionary with weather data or an error/fallback message.
    """
    if not OPENWEATHER_API_KEY:
        log_error("OpenWeatherMap API key not found")
        return {"error": "API key missing", "fallback": random.choice(FALLBACK_RESPONSES)}

    # Normalize the city name
    normalized_city = normalize_location(city)
    log_info(f"Fetching weather for: {city} -> {normalized_city}")

    params = {
        "q": normalized_city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(BASE_URL, params=params, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    log_info(f"Successfully fetched weather for {normalized_city}")
                    return data
                elif resp.status == 404:
                    log_error(f"City not found: {normalized_city}")
                    return {"error": "City not found", "fallback": random.choice(FALLBACK_RESPONSES)}
                else:
                    log_error(f"API error {resp.status} for {normalized_city}")
                    return {"error": f"API error {resp.status}", "fallback": random.choice(FALLBACK_RESPONSES)}
                    
        except aiohttp.ClientTimeout:
            log_error(f"Timeout fetching weather for {normalized_city}")
            return {"error": "Request timeout", "fallback": random.choice(FALLBACK_RESPONSES)}
        except Exception as e:
            log_error(f"Exception fetching weather for {normalized_city}: {str(e)}")
            return {"error": str(e), "fallback": random.choice(FALLBACK_RESPONSES)}


async def fetch_forecast(city: str, days: int = 5) -> dict:
    """
    Fetch weather forecast data for a given city.

    Args:
        city: City name (e.g., "Lagos" or "Maiduguri")
        days: Number of days to forecast (max 5 for free tier)

    Returns:
        A dictionary with forecast data or an error/fallback message.
    """
    if not OPENWEATHER_API_KEY:
        log_error("OpenWeatherMap API key not found")
        return {"error": "API key missing", "fallback": random.choice(FALLBACK_RESPONSES)}

    # Normalize the city name
    normalized_city = normalize_location(city)
    log_info(f"Fetching forecast for: {city} -> {normalized_city}")

    params = {
        "q": normalized_city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "cnt": min(days * 8, 40)  # 8 forecasts per day (3-hour intervals), max 40
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(FORECAST_URL, params=params, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    log_info(f"Successfully fetched forecast for {normalized_city}")
                    return data
                elif resp.status == 404:
                    log_error(f"City not found for forecast: {normalized_city}")
                    return {"error": "City not found", "fallback": random.choice(FALLBACK_RESPONSES)}
                else:
                    log_error(f"Forecast API error {resp.status} for {normalized_city}")
                    return {"error": f"API error {resp.status}", "fallback": random.choice(FALLBACK_RESPONSES)}
                    
        except aiohttp.ClientTimeout:
            log_error(f"Timeout fetching forecast for {normalized_city}")
            return {"error": "Request timeout", "fallback": random.choice(FALLBACK_RESPONSES)}
        except Exception as e:
            log_error(f"Exception fetching forecast for {normalized_city}: {str(e)}")
            return {"error": str(e), "fallback": random.choice(FALLBACK_RESPONSES)}


async def get_weather_for_query(query: str, location: str = None) -> dict:
    """
    High-level function to get appropriate weather data based on query type.
    
    Args:
        query: The original weather query
        location: Specific location (optional)
    
    Returns:
        Dictionary with weather data
    """
    query_lower = query.lower()
    
    # Determine if forecast is needed
    forecast_keywords = ['tomorrow', 'next', 'will', 'going to', 'later', 'tonight', 'forecast']
    needs_forecast = any(keyword in query_lower for keyword in forecast_keywords)
    
    # Use provided location or try to extract from query
    if not location:
        location = "Maiduguri"  # Default to Borno state capital
    
    if needs_forecast:
        return await fetch_forecast(location)
    else:
        return await fetch_weather(location)