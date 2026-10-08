"""
Gestión de configuración y persistencia del bot.
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

CONFIG_FILE = Path("config.json")

DEFAULT_SETTINGS = {
    "min_ev": 5.0,
    "max_ev": 10.0,
    "channel_id": os.getenv("CHANNEL_ID", ""),
    "admin_ids": [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
}

def load_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                settings.update(saved)
        except Exception as e:
            print(f"Error cargando config.json: {e}")
    else:
        save_settings(settings)
    
    # Prioridad a las variables de entorno si están definidas
    env_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    env_channel = os.getenv("CHANNEL_ID", "")
    if env_channel and not settings.get("channel_id"):
        settings["channel_id"] = env_channel
        
    return settings

def save_settings(settings: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando config.json: {e}")

def update_ev_range(min_ev: float, max_ev: float) -> dict:
    settings = load_settings()
    settings["min_ev"] = round(float(min_ev), 2)
    settings["max_ev"] = round(float(max_ev), 2)
    save_settings(settings)
    return settings

def set_channel_id(channel_id: str) -> dict:
    settings = load_settings()
    settings["channel_id"] = str(channel_id).strip()
    save_settings(settings)
    return settings

def add_admin(admin_id: int) -> dict:
    settings = load_settings()
    if "admin_ids" not in settings:
        settings["admin_ids"] = []
    if admin_id not in settings["admin_ids"]:
        settings["admin_ids"].append(admin_id)
        save_settings(settings)
    return settings
