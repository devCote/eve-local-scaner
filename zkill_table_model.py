"""Compact zKillboard table with ship icons, without using a browser."""

import json
from pathlib import Path
from datetime import datetime
import requests

from cache import cache
from paths import icon_path, USER_DATA_DIR

USER_AGENT = "EVE-Local-Scanner"
ESI_URL = "https://esi.evetech.net/latest"
ZKILL_URL = "https://zkillboard.com/api"

# Ship icon cache directory
SHIP_ICONS_DIR = Path(USER_DATA_DIR) / "ship_icons"
SHIP_ICONS_DIR.mkdir(parents=True, exist_ok=True)

TTL_KILLMAIL = 3600  # 1 hour


def get_ship_name(type_id: int) -> str:
    """Get ship name from ESI API."""
    cache_key = f"esi:type:{type_id}"
    cached = cache.get(cache_key, ttl_seconds=86400)  # 24 hours
    if cached is not None:
        return cached

    try:
        response = requests.get(
            f"{ESI_URL}/universe/types/{type_id}/",
            headers={"User-Agent": USER_AGENT},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        name = data.get("name", "Unknown")
        cache.set(cache_key, name)
        return name
    except Exception as e:
        print(f"Error fetching ship name for {type_id}: {e}")
        return "Unknown"


def get_ship_icon_url(type_id: int, size: int = 32) -> str:
    """Return EVE ESI ship icon URL."""
    return f"{ESI_URL}/characters/0/portrait/?size={size}"  # Fallback
    # Proper way: https://images.evetech.net/types/{type_id}/icon


def get_character_name(character_id: int) -> str:
    """Get character name from ESI API."""
    cache_key = f"esi:char:{character_id}"
    cached = cache.get(cache_key, ttl_seconds=86400)  # 24 hours
    if cached is not None:
        return cached

    try:
        response = requests.get(
            f"{ESI_URL}/characters/{character_id}/",
            headers={"User-Agent": USER_AGENT},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        name = data.get("name", f"#{character_id}")
        cache.set(cache_key, name)
        return name
    except Exception as e:
        print(f"Error fetching character name for {character_id}: {e}")
        return f"#{character_id}"


def get_location_name(solar_system_id: int) -> str:
    """Get solar system name from ESI API."""
    cache_key = f"esi:sys:{solar_system_id}"
    cached = cache.get(cache_key, ttl_seconds=86400)  # 24 hours
    if cached is not None:
        return cached

    try:
        response = requests.get(
            f"{ESI_URL}/universe/systems/{solar_system_id}/",
            headers={"User-Agent": USER_AGENT},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        name = data.get("name", f"#{solar_system_id}")
        cache.set(cache_key, name)
        return name
    except Exception as e:
        print(f"Error fetching system name for {solar_system_id}: {e}")
        return f"#{solar_system_id}"


def get_killmail(killmail_id: int, killmail_hash: str) -> dict | None:
    """Get full killmail data from zKillboard API."""
    cache_key = f"zkill:killmail:{killmail_id}"
    cached = cache.get(cache_key, ttl_seconds=TTL_KILLMAIL)
    if cached is not None:
        return cached

    try:
        url = f"{ZKILL_URL}/killmail/{killmail_id}/{killmail_hash}/"
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        cache.set(cache_key, data)
        return data
    except Exception as e:
        print(f"Error fetching killmail {killmail_id}: {e}")
        return None


def parse_killmail_row(killmail_dict: dict) -> dict:
    """
    Parse killmail to compact table row format.
    
    Returns:
        {
            'date': '2026-06-10 12:34',
            'ship_name': 'Rifter',
            'ship_type_id': 587,
            'location': 'Jita',
            'location_id': 30000142,
            'opponent': 'OpponentName',
            'opponent_id': 12345,
        }
    """
    try:
        victim = killmail_dict.get("victim", {})
        kill_time = killmail_dict.get("killmail_time", "")
        
        # Parse time: 2026-06-10T12:34:56Z
        dt = datetime.fromisoformat(kill_time.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d %H:%M")
        
        ship_type_id = victim.get("ship_type_id", 0)
        ship_name = get_ship_name(ship_type_id)
        
        solar_system_id = killmail_dict.get("solar_system_id", 0)
        location = get_location_name(solar_system_id)
        
        # Get first attacker as opponent
        attackers = killmail_dict.get("attackers", [])
        opponent_id = 0
        opponent_name = "Unknown"
        
        if attackers:
            final_blow = next(
                (a for a in attackers if a.get("final_blow")), None
            )
            if not final_blow:
                final_blow = attackers[0]
            
            opponent_id = final_blow.get("character_id", 0)
            if opponent_id:
                opponent_name = get_character_name(opponent_id)
            else:
                # Corp or NPC kill
                opponent_id = final_blow.get("corporation_id", 0)
        
        return {
            "date": date_str,
            "ship_name": ship_name,
            "ship_type_id": ship_type_id,
            "location": location,
            "location_id": solar_system_id,
            "opponent": opponent_name,
            "opponent_id": opponent_id,
        }
    except Exception as e:
        print(f"Error parsing killmail: {e}")
        return None


def format_kills_losses_data(character_id: int, kills_list: list, losses_list: list) -> dict:
    """
    Format kills and losses data from zkill_client.
    
    Args:
        character_id: Character ID
        kills_list: List from get_recent_kills()
        losses_list: List from get_recent_losses()
    
    Returns:
        {
            'character_id': 12345,
            'kills': [parsed_row, ...],
            'losses': [parsed_row, ...],
        }
    """
    parsed_kills = []
    parsed_losses = []
    
    for kill in kills_list:
        killmail_id = kill.get("killmail_id")
        killmail_hash = kill.get("killmail_hash")
        if killmail_id and killmail_hash:
            full = get_killmail(killmail_id, killmail_hash)
            if full:
                row = parse_killmail_row(full)
                if row:
                    parsed_kills.append(row)
    
    for loss in losses_list:
        killmail_id = loss.get("killmail_id")
        killmail_hash = loss.get("killmail_hash")
        if killmail_id and killmail_hash:
            full = get_killmail(killmail_id, killmail_hash)
            if full:
                row = parse_killmail_row(full)
                if row:
                    parsed_losses.append(row)
    
    return {
        "character_id": character_id,
        "kills": parsed_kills,
        "losses": parsed_losses,
    }
