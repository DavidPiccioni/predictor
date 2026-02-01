from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import math
import os
import logging
from datetime import datetime
from typing import Dict, List, Any
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuración Liga I Rumania
API_KEY = os.getenv('FOOTBALL_API_KEY')
HEADERS = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}
LIGA_I_ID = 283

cache = {}

def get_weight(match_date_str: str) -> float:
    """Calcula el peso del partido según su antigüedad."""
    try:
        match_date = datetime.fromisoformat(match_date_str.replace('Z', '+00:00'))
        days_diff = (datetime.now(match_date.tzinfo) - match_date).days
        return max(0.25, math.exp(-0.001 * days_diff))
    except: return 1.0

def get_all_matches():
    """Carga solo temporadas 2024 y 2025 (318 partidos)."""
    now = datetime.now().timestamp()
    if 'all_matches' in cache and now - cache.get('timestamp', 0) < 3600:
        return cache['all_matches']
    
    all_matches = []
    # Filtro de temporadas para precisión
    for year in [2024, 2025]:
        try:
            url = "https://v3.football.api-sports.io/fixtures"
            resp = requests.get(url, headers=HEADERS, params={"league": LIGA_I_ID, "season": year}, timeout=10)
            data = resp.json()
            for item in data.get('response', []):
                if item['fixture']['status']['short'] == 'FT':
                    all_matches.append({
                        'home': item['teams']['home']['name'],
                        'away': item['teams']['away']['name'],
                        'home_goals': item['goals']['home'],
                        'away_goals': item['goals']['away'],
                        'date': item['fixture']['date']
                    })
        except Exception as e: logger.error(f"Error API: {e}")

    if all_matches:
        cache['all_matches'] = all_matches
        cache['timestamp'] = now
    return all_matches

def poisson(lmbda, k):
    return (math.exp(-lmbda) * (lmbda**k)) / math.factorial(k) if lmbda > 0 else (1.0 if k==0 else 0.0)

def dixon_coles_rho(h_g, a_g, h_exp, a_exp, rho=-0.10):
    """Ajuste de correlación para empates realistas."""
    if h_g == 0 and a_g == 0: return 1 - h_exp * a_exp * rho
    if h_g == 0 and a_g == 1: return 1 + h_exp * rho
    if h_g == 1 and a_g == 0: return 1 + a_exp * rho
    if h_g == 1 and a_g == 1: return 1 - rho
    return 1.0

@app.route('/api/predict', methods=['POST'])
def predict():
    data = request.json
    h_name, a_name = data.get('home_team'), data.get('away_team')
    matches = get_all_matches()
    
    # Cálculo de promedios globales (318 partidos)
    sum_w = sum(get_weight(m['date']) for m in matches)
    avg_h_g = sum(m['home_goals'] * get_weight(m['date']) for m in matches) / sum_w
    avg_a_g = sum(m['away_goals'] * get_weight(m['date']) for m in matches) / sum_w

    def get_stats(name):
        team_m = [m for m in matches if m['home'] == name or m['away'] == name]
        w_t = sum(get_weight(m['date']) for m in team_m) or 1
        scored = sum((m['home_goals'] if m['home']==name else m['away_goals']) * get_weight(m['date']) for m in team_m)
        conceded = sum((m['away_goals'] if m['home']==name else m['home_goals']) * get_weight(m['date']) for m in team_m)
        return {'att': (scored/w_t)/( (avg_h_g+avg_a_g)/2 ), 'def': (conceded/w_t)/( (avg_h_g+avg_a_g)/2 )}

    s_h, s_a = get_stats(h_name), get_stats(a_name)
    exp_h, exp_a = s_h['att'] * s_a['def'] * avg_h_g, s_a['att'] * s_h['def'] * avg_a_g

    p_win, p_draw, p_loss, p_over = 0.0, 0.0, 0.0, 0.0
    for h_g in range(7):
        for a_g in range(7):
            prob = poisson(exp_h, h_g) * poisson(exp_a, a_g) * dixon_coles_rho(h_g, a_g, exp_h, exp_a)
            if h_g > a_g: p_win += prob
            elif h_g == a_g: p_draw += prob
            else: p_loss += prob
            if (h_g + a_g) > 2.5: p_over += prob

    return jsonify({
        'expected_goals': {'total': round(exp_h + exp_a, 2)},
        'market_1x2': {'home': round(p_win*100, 1), 'draw': round(p_draw*100, 1), 'away': round(p_loss*100, 1)},
        'market_goals': {'over_25': round(p_over*100, 1)}
    })

@app.route('/api/teams')
def get_teams():
    m = get_all_matches()
    return jsonify({'teams': [{'team': t} for t in sorted(list(set([x['home'] for x in m])))]})

@app.route('/api/league-stats')
def league_stats():
    m = get_all_matches()
    return jsonify({'total_matches': len(m), 'avg_goals': round(sum(x['home_goals']+x['away_goals'] for x in m)/len(m), 2)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)