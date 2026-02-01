from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import requests
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configuración de la API (Igual que en tu Predictor)
API_KEY = os.getenv('FOOTBALL_API_KEY')
HEADERS = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}
LIGA_I_ID = 283

def init_db():
    """Crea la base de datos de auditoría si no existe."""
    conn = sqlite3.connect('accuracy.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            partido TEXT,
            eleccion TEXT, -- '1', 'X', o '2'
            cuota REAL,
            esperanza REAL,
            resultado_real TEXT, -- '1', 'X', '2' o None
            estado TEXT DEFAULT 'PENDIENTE' -- 'PENDIENTE', 'GANADA', 'PERDIDA'
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/api/registrar', methods=['POST'])
def registrar():
    """Recibe y guarda una nueva apuesta del Predictor."""
    data = request.json
    try:
        conn = sqlite3.connect('accuracy.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO historial (partido, eleccion, cuota, esperanza)
            VALUES (?, ?, ?, ?)
        ''', (data['partido'], data['eleccion'], data['cuota'], data['esperanza']))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Apuesta registrada"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/auditar', methods=['GET'])
def auditar():
    """Compara las apuestas pendientes con los resultados reales de la API."""
    conn = sqlite3.connect('accuracy.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, partido, eleccion FROM historial WHERE estado = 'PENDIENTE'")
    pendientes = cursor.fetchall()

    if not pendientes:
        return jsonify({"message": "No hay apuestas pendientes para auditar"})

    # Obtenemos resultados recientes de la liga
    url = "https://v3.football.api-sports.io/fixtures"
    # Buscamos partidos de la temporada actual que ya terminaron
    params = {"league": LIGA_I_ID, "season": 2025, "status": "FT"}
    resp = requests.get(url, headers=HEADERS, params=params).json()
    partidos_terminados = resp.get('response', [])

    actualizaciones = 0
    for id_apuesta, nombre_partido, eleccion in pendientes:
        for p in partidos_terminados:
            nombre_api = f"{p['teams']['home']['name']} vs {p['teams']['away']['name']}"
            
            # Si encontramos el partido en la lista de terminados
            if nombre_api == nombre_partido:
                goles_h = p['goals']['home']
                goles_a = p['goals']['away']
                
                # Determinamos resultado real
                res_real = "1" if goles_h > goles_a else ("X" if goles_h == goles_a else "2")
                nuevo_estado = "GANADA" if res_real == eleccion else "PERDIDA"
                
                cursor.execute("UPDATE historial SET resultado_real = ?, estado = ? WHERE id = ?", 
                               (res_real, nuevo_estado, id_apuesta))
                actualizaciones += 1

    conn.commit()
    conn.close()
    return jsonify({"message": f"Auditoría terminada. {actualizaciones} apuestas actualizadas."})

@app.route('/api/stats', methods=['GET'])
def stats():
    """Calcula el Accuracy y estadísticas de rendimiento."""
    conn = sqlite3.connect('accuracy.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM historial WHERE estado = 'GANADA'")
    ganadas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM historial WHERE estado != 'PENDIENTE'")
    totales = cursor.fetchone()[0]
    
    accuracy = (ganadas / totales * 100) if totales > 0 else 0
    
    # Cálculo de rentabilidad (Profit/Loss)
    cursor.execute("SELECT cuota FROM historial WHERE estado = 'GANADA'")
    cuotas_ganadas = cursor.fetchall()
    profit = sum([c[0] for c in cuotas_ganadas]) - totales
    
    conn.close()
    return jsonify({
        "accuracy": f"{round(accuracy, 2)}%",
        "ganadas": ganadas,
        "totales": totales,
        "rendimiento_unidades": round(profit, 2)
    })

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5002))
    app.run(host='0.0.0.0', port=port)