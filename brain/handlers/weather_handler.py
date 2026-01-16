# """
# Enhanced Weather handler for Maxi AI Robot.
# Handles complex weather queries for kids and adults.
# """

from integrations.weather_api import fetch_weather, fetch_forecast
from utils.logger import log_info, log_error
from voice.speaker import SmoothTTSEngine
from ui.socket_server import SocketServer
from os import getenv
from brain.handlers.groq_llm_handler import handle_llm as handle_groq
from brain.handlers.ollama_handler import handle_ollama as handle_ollama
import re
from dotenv import load_dotenv
from datetime import datetime, timedelta
from brain.context_manager.context_manager import context_manager


load_dotenv()

# Default location - you can change this to your current location
DEFAULT_LOCATION = "Maiduguri"  # Borno state capital

class WeatherQueryProcessor:
    def __init__(self):
        self.time_patterns = {
            'today': ['today', 'now', 'currently', 'right now', 'at the moment'],
            'tomorrow': ['tomorrow', 'next day'],
            'this_week': ['this week', 'week', 'next week'],
            'tonight': ['tonight', 'this evening', 'evening'],
            'morning': ['morning', 'this morning', 'tomorrow morning'],
            'afternoon': ['afternoon', 'this afternoon', 'tomorrow afternoon']
        }
        
        self.weather_types = {
            'rain': ['rain', 'raining', 'rainy', 'precipitation', 'drizzle', 'shower'],
            'sun': ['sunny', 'sun', 'sunshine', 'bright', 'clear'],
            'cloud': ['cloudy', 'clouds', 'overcast', 'gray', 'grey'],
            'storm': ['storm', 'thunder', 'lightning', 'thunderstorm'],
            'wind': ['windy', 'wind', 'breeze', 'breezy'],
            'hot': ['hot', 'warm', 'heat', 'temperature'],
            'cold': ['cold', 'cool', 'chilly', 'freezing']
        }
        
        self.nigerian_locations = {
            # States and major cities
            'borno': 'Maiduguri',
            'borno state': 'Maiduguri',
            'maiduguri': 'Maiduguri',
            'lagos': 'Lagos',
            'lagos state': 'Lagos',
            'abuja': 'Abuja',
            'fct': 'Abuja',
            'kano': 'Kano',
            'kano state': 'Kano',
            'rivers': 'Port Harcourt',
            'rivers state': 'Port Harcourt',
            'port harcourt': 'Port Harcourt',
            'ph': 'Port Harcourt',
            'kaduna': 'Kaduna',
            'kaduna state': 'Kaduna',
            'oyo': 'Ibadan',
            'oyo state': 'Ibadan',
            'ibadan': 'Ibadan',
            'enugu': 'Enugu',
            'enugu state': 'Enugu',
            'plateau': 'Jos',
            'plateau state': 'Jos',
            'jos': 'Jos',
            'bauchi': 'Bauchi',
            'bauchi state': 'Bauchi',
            'gombe': 'Gombe',
            'gombe state': 'Gombe',
            'yobe': 'Damaturu',
            'yobe state': 'Damaturu',
            'adamawa': 'Yola',
            'adamawa state': 'Yola',
            'yola': 'Yola',
            'taraba': 'Jalingo',
            'taraba state': 'Jalingo',
            'cross river': 'Calabar',
            'cross river state': 'Calabar',
            'calabar': 'Calabar',
            'akwa ibom': 'Uyo',
            'akwa ibom state': 'Uyo',
            'uyo': 'Uyo',
            'delta': 'Asaba',
            'delta state': 'Asaba',
            'asaba': 'Asaba',
            'edo': 'Benin City',
            'edo state': 'Benin City',
            'benin': 'Benin City',
            'benin city': 'Benin City',
            'ondo': 'Akure',
            'ondo state': 'Akure',
            'akure': 'Akure',
            'osun': 'Osogbo',
            'osun state': 'Osogbo',
            'ekiti': 'Ado-Ekiti',
            'ekiti state': 'Ado-Ekiti',
            'kwara': 'Ilorin',
            'kwara state': 'Ilorin',
            'ilorin': 'Ilorin',
            'niger': 'Minna',
            'niger state': 'Minna',
            'minna': 'Minna',
            'kebbi': 'Birnin Kebbi',
            'kebbi state': 'Birnin Kebbi',
            'sokoto': 'Sokoto',
            'sokoto state': 'Sokoto',
            'zamfara': 'Gusau',
            'zamfara state': 'Gusau',
            'gusau': 'Gusau',
            'katsina': 'Katsina',
            'katsina state': 'Katsina',
            'jigawa': 'Dutse',
            'jigawa state': 'Dutse',
            'kogi': 'Lokoja',
            'kogi state': 'Lokoja',
            'lokoja': 'Lokoja',
            'nasarawa': 'Lafia',
            'nasarawa state': 'Lafia',
            'benue': 'Makurdi',
            'benue state': 'Makurdi',
            'makurdi': 'Makurdi',
            'abia': 'Umuahia',
            'abia state': 'Umuahia',
            'umuahia': 'Umuahia',
            'anambra': 'Awka',
            'anambra state': 'Awka',
            'awka': 'Awka',
            'ebonyi': 'Abakaliki',
            'ebonyi state': 'Abakaliki',
            'imo': 'Owerri',
            'imo state': 'Owerri',
            'owerri': 'Owerri',
            'bayelsa': 'Yenagoa',
            'bayelsa state': 'Yenagoa',
            'here': DEFAULT_LOCATION,
            'my location': DEFAULT_LOCATION,
            'current location': DEFAULT_LOCATION,
            'where i am': DEFAULT_LOCATION,
        }

    def extract_location(self, prompt: str) -> str:
        """Extract location from the prompt with better pattern matching."""
        prompt_lower = prompt.lower()
        
        # Check for explicit location mentions
        for phrase, city in self.nigerian_locations.items():
            if phrase in prompt_lower:
                log_info(f"Found location: {phrase} -> {city}")
                return city
        
        # Look for preposition patterns
        location_patterns = [
            r"(?:in|at|for|around)\s+([a-z\s]+?)(?:\s|$|,|\?|!)",
            r"weather\s+(?:in|at|for|around)\s+([a-z\s]+?)(?:\s|$|,|\?|!)",
            r"(?:from|of)\s+([a-z\s]+?)(?:\s|$|,|\?|!)"
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, prompt_lower)
            if match:
                location_text = match.group(1).strip()
                # Check if this matches any of our known locations
                for phrase, city in self.nigerian_locations.items():
                    if phrase in location_text or location_text in phrase:
                        log_info(f"Pattern matched location: {location_text} -> {city}")
                        return city
        
        log_info(f"No location found, using default: {DEFAULT_LOCATION}")
        return DEFAULT_LOCATION

    def detect_time_context(self, prompt: str) -> str:
        """Detect time context from the prompt."""
        prompt_lower = prompt.lower()
        
        for time_key, patterns in self.time_patterns.items():
            for pattern in patterns:
                if pattern in prompt_lower:
                    return time_key
        return 'today'  # default

    def detect_weather_type(self, prompt: str) -> list:
        """Detect what type of weather information is being asked."""
        prompt_lower = prompt.lower()
        detected_types = []
        
        for weather_type, patterns in self.weather_types.items():
            for pattern in patterns:
                if pattern in prompt_lower:
                    detected_types.append(weather_type)
                    break
        
        return detected_types if detected_types else ['general']

    def is_forecast_query(self, prompt: str) -> bool:
        """Check if the query requires forecast data."""
        prompt_lower = prompt.lower()
        forecast_indicators = [
            'tomorrow', 'next', 'will', 'going to', 'later', 'tonight',
            'this week', 'next week', 'forecast', 'predict'
        ]
        return any(indicator in prompt_lower for indicator in forecast_indicators)


async def handle_weather(prompt: str, tts_engine: SmoothTTSEngine, socket: SocketServer):
    """Enhanced weather handler that processes complex queries."""
    log_info(f"🌦️ Handling weather request: {prompt}")
    
    processor = WeatherQueryProcessor()
    
    # Extract query components
    location = processor.extract_location(prompt)
    time_context = processor.detect_time_context(prompt)
    weather_types = processor.detect_weather_type(prompt)
    needs_forecast = processor.is_forecast_query(prompt)
    
    log_info(f"Query analysis - Location: {location}, Time: {time_context}, Types: {weather_types}, Forecast: {needs_forecast}")
    
    try:
        # Fetch appropriate weather data
        if needs_forecast or time_context != 'today':
            weather_data = await fetch_forecast(location)
            if "error" in weather_data:
                # Fallback to current weather
                weather_data = await fetch_weather(location)
        else:
            weather_data = await fetch_weather(location)
        
        if "error" in weather_data:
            fallback = f"Sorry, I couldn't check the weather in {location}. But I bet it's robot-approved! Maybe try asking about a different city?"
            await socket.emit_response(fallback)
            await tts_engine.speak_text(fallback)
            return

        log_info(f"Weather data received for {location}")

        # Build comprehensive weather summary
        weather_summary = build_weather_summary(weather_data, location, time_context, weather_types, needs_forecast)
        
        # Create LLM instruction based on query type
        instruction = create_llm_instruction(prompt, weather_summary, location, time_context, weather_types)
        
        log_info(f"✅ Weather Instruction: {instruction}")

        # Get LLM response
        model = getenv("LLM_PROVIDER", "ollama").lower()

        if model == "groq":
            response = await handle_groq(instruction, tts_engine, socket)
        else:
            response = await handle_ollama(instruction, tts_engine, socket)

        log_info(f"✅ Weather explained for {location}")

    except Exception as e:
        log_error(f"Error in weather handler: {str(e)}")
        error_response = "Oops! My weather sensors are having a little hiccup. Let me try that again in a moment!"
        await socket.emit_response(error_response)
        await tts_engine.speak_text(error_response)


def build_weather_summary(weather_data: dict, location: str, time_context: str, weather_types: list, needs_forecast: bool) -> str:
    """Build a comprehensive weather summary from the API data."""
    
    if "fallback" in weather_data:
        return weather_data["fallback"]
    
    summary_parts = []
    
    if needs_forecast and "list" in weather_data:
        # Handle forecast data
        forecast_items = weather_data["list"][:3]  # Get first 3 forecast periods
        
        for i, item in enumerate(forecast_items):
            time_label = "later today" if i == 0 else f"in {(i+1)*3} hours"
            if time_context == "tomorrow" and i == 0:
                time_label = "tomorrow"
            
            temp = item.get("main", {}).get("temp", "unknown")
            desc = item.get("weather", [{}])[0].get("description", "clear")
            humidity = item.get("main", {}).get("humidity", "unknown")
            
            summary_parts.append(f"{time_label}: {desc}, {temp}°C, {humidity}% humidity")
    
    else:
        # Handle current weather data
        main_weather = weather_data.get("weather", [{}])[0]
        main_data = weather_data.get("main", {})
        wind_data = weather_data.get("wind", {})
        
        desc = main_weather.get("description", "clear sky")
        temp = main_data.get("temp", "unknown")
        feels_like = main_data.get("feels_like", "unknown")
        humidity = main_data.get("humidity", "unknown")
        pressure = main_data.get("pressure", "unknown")
        wind_speed = wind_data.get("speed", 0)
        
        summary_parts.append(f"Current weather in {location}: {desc}")
        summary_parts.append(f"Temperature: {temp}°C (feels like {feels_like}°C)")
        summary_parts.append(f"Humidity: {humidity}%")
        
        if wind_speed > 0:
            summary_parts.append(f"Wind speed: {wind_speed} m/s")
        
        # Add specific details based on requested weather types
        if "rain" in weather_types:
            rain_data = weather_data.get("rain", {})
            if rain_data:
                rain_1h = rain_data.get("1h", 0)
                summary_parts.append(f"Rainfall in last hour: {rain_1h}mm")
            else:
                summary_parts.append("No rain currently")
    
    return ". ".join(summary_parts)


def create_llm_instruction(original_prompt: str, weather_summary: str, location: str, time_context: str, weather_types: list) -> str:
    """Create appropriate instruction for the LLM based on the query type."""
    
    base_instruction = f"A child asked: '{original_prompt}'. Here's the weather data: {weather_summary}"
    
    # Customize instruction based on query characteristics
    if "rain" in weather_types:
        instruction_suffix = "Focus on explaining about rain, whether it's raining or will rain, and what that means for outdoor activities."
    elif "hot" in weather_types or "cold" in weather_types:
        instruction_suffix = "Focus on the temperature and how it feels, and suggest appropriate clothing or activities."
    elif "storm" in weather_types:
        instruction_suffix = "Explain about storms in a way that's informative but not scary for children."
    elif time_context == "tomorrow":
        instruction_suffix = "Focus on tomorrow's weather and help them plan their day."
    else:
        instruction_suffix = "Give a friendly, educational explanation that answers their question completely."
    
    return f"{base_instruction} {instruction_suffix} Keep it simple, fun, and educational for Nigerian children, be brief, short and precise."