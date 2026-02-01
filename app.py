from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import math
import os

app = Flask(__name__)
CORS(app)

# Configuración de API
API_KEY = os.getenv('FOOTBALL_API_KEY')
HEADERS = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}
LIGA_I_ID = 283

def poisson(lmbda, k):
    if lmbda <= 0: return 1.0 if k == 0 else 0.0
    return (math.exp(-lmbda) * (lmbda**k)) / math.factorial(k)

def get_matches():
    """Obtiene el historial para los cálculos. Mantenemos 2024 y 2025 para tener datos."""
    matches = []
    for year in [2024, 2025]:
        try:
            url = "https://v3.football.api-sports.io/fixtures"
            params = {"league": LIGA_I_ID, "season": year, "status": "FT"}
            resp = requests.get(url, headers=HEADERS, params=params).json()
            for item in resp.get('response', []):
                matches.append({
                    'h': item['teams']['home']['name'],
                    'a': item['teams']['away']['name'],
                    'gh': item['goals']['home'],
                    'ga': item['goals']['away']
                })
        except: continue
    return matches

@app.route('/api/predict', methods=['POST'])
def predict():
    data = request.json
    h_name, a_name = data.get('home_team'), data.get('away_team')
    matches = get_matches()
    
    if not matches: return jsonify({"error": "No hay datos"}), 500
    
    avg_l = sum(m['gh'] + m['ga'] for m in matches) / (len(matches) * 2)

    def stats(name):
        t_m = [m for m in matches if m['h'] == name or m['a'] == name]
        if not t_m: return {'att': 1.0, 'def': 1.0}
        sc = sum(m['gh'] if m['h'] == name else m['ga'] for m in t_m)
        co = sum(m['ga'] if m['h'] == name else m['gh'] for m in t_m)
        return {'att': (sc/len(t_m))/avg_l, 'def': (co/len(t_m))/avg_l}

    s_h, s_a = stats(h_name), stats(a_name)
    ex_h, ex_a = s_h['att'] * s_a['def'] * avg_l, s_a['att'] * s_h['def'] * avg_l

    pw, pd, pl, po = 0.0, 0.0, 0.0, 0.0
    for hg in range(8):
        for ag in range(8):
            prob = poisson(ex_h, hg) * poisson(ex_a, ag)
            if hg > ag: pw += prob
            elif hg == ag: pd += prob
            else: pl += prob
            if (hg + ag) > 2.5: po += prob

    return jsonify({
        'expected_goals': {'total': round(ex_h + ex_a, 2)},
        'market_1x2': {'home': round(pw*100, 1), 'draw': round(pd*100, 1), 'away': round(pl*100, 1)},
        'market_goals': {'over_25': round(po*100, 1)}
    })

@app.route('/api/teams')
def teams():
    """LISTA FIJA DE LOS 16 EQUIPOS OFICIALES 2025/2026."""
    # Esta lista elimina a los de segunda y añade a los nuevos ascendidos.
    equipos_reales = [
        "CFR Cluj", "FCSB", "Universitatea Craiova", "Farul Constanta", 
        "Rapid Bucuresti", "Sepsi OSK", "Otelul Galati", "UTA Arad", 
        "FC Hermannstadt", "Universitatea Cluj", "Petrolul 52", "Dinamo Bucuresti", 
        "Politehnica Iasi", "FC Botosani", "Unirea Slobozia", "Gloria Buzau"
    ]
    return jsonify({'teams': [{'team': x} for x in sorted(equipos_reales)]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5001)))