from kickbase_api.constants import BASE_URL
import pandas as pd
import requests

def get_leagues_infos(token):
    url = f"{BASE_URL}/leagues/selection"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    result = []

    for item in data.get("it", []):
        result.append({
            "id": item.get("i"),
            "name": item.get("n")
        })

    return result

def get_players_on_market(token, league_id):
    url = f"{BASE_URL}/leagues/{league_id}/market"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    result = []

    for player in data.get('it', []):
        result.append({
            'id': player.get('i'),
            'prob': player.get('prob'),
            "exp": player.get("exs"),
        })

    return result

def get_budget(token, league_id):
    url = f"{BASE_URL}/leagues/{league_id}/me/budget"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    print(data)


def get_league_id(token, league_name):
    league_infos = get_leagues_infos(token)

    if not league_infos:
        print("Warning: You are not part of any league.")
        return None

    # Try to find leagues matching the given name
    selected_league = [league for league in league_infos if league["name"] == league_name]

    if not selected_league:
        fallback_league = league_infos[0]
        print(
            f"Warning: No league found with name '{league_name}'. "
            f"Falling back to the first available league: '{fallback_league['name']}'"
        )
        return fallback_league["id"]

    return selected_league[0]["id"]


def get_activities(token, league_id, league_start_date):
    # TODO magic number with 5000, have to find a better solution
    url = f"{BASE_URL}/leagues/{league_id}/activitiesFeed?max=5000"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    # Filter out entries prior to reset_Date
    filtered_activities = []
    for entry in data["af"]:
        entry_date = entry.get("dt", "")
        if entry_date >= league_start_date:
            filtered_activities.append(entry)

    login = [entry for entry in filtered_activities if entry.get("t") == 22]
    achievements = [entry for entry in filtered_activities if entry.get("t") == 26]
    trade = [entry for entry in filtered_activities if entry.get("t") == 15]
    trading = [
        {k: entry["data"].get(k) for k in ["byr", "slr", "pi", "pn", "tid", "trp"]}
        for entry in trade
        if entry.get("t") == 15
    ]

    return trading, login, achievements


def get_achievement_reward(token, league_id, achievement_id):
    url = f"{BASE_URL}/leagues/{league_id}/user/achievements/{achievement_id}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    amount = data["ac"]
    reward = data["er"]

    return amount, reward


def get_managers(token, league_id):
    url = f"{BASE_URL}/leagues/{league_id}/ranking"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    user_info = [(user["n"], user["i"]) for user in data["us"]]

    return user_info

def get_manager_performance(token, league_id, manager_id, manager_name):
    url = f"{BASE_URL}/leagues/{league_id}/managers/{manager_id}/performance"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    
    # Look for season ID "34" (current season 2025/2026)
    tp_value = 0
    for season in data["it"]:
        if season["sid"] == "34":
            tp_value = season["tp"]
            break
    else:
        # Fallback to first season if sid "34" not found
        tp_value = data["it"][0]["tp"]
        print(f"Warning: Season ID '34' not found for {manager_name}, using first season")
    

    return {
        "name": manager_name,
        "tp": tp_value
    }

def get_manager_info(token, league_id, manager_id):
    url = f"{BASE_URL}/leagues/{league_id}/managers/{manager_id}/dashboard"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    return data