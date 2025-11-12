import time
import market
import trader
import config
import json
from datetime import datetime
import trade_logger
from flask import Flask, render_template, jsonify

# ÖNCE trade modülünü import et
import trade

# Initialize portfolio ONCE at startup
portfolio = None
if config.SIMULATION_MODE:
    from simulation import SimulatedPortfolio
    portfolio = SimulatedPortfolio()
    # Şimdi portfolio'yu trade modülüne set et
    trade.set_portfolio(portfolio)
    print(f"[INIT] Portfolio initialized and shared with trade module.")

# --- Flask Web Server ---
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

def get_state_from_file():
    """Helper function to read the state file."""
    try:
        with open('portfolio_state.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

@app.route('/api/portfolio_summary')
def api_portfolio_summary():
    state = get_state_from_file()
    return jsonify(state.get("portfolio_summary", {}))

@app.route('/api/open_positions')
def api_open_positions():
    state = get_state_from_file()
    return jsonify(state.get("open_positions", {}))

@app.route('/api/trade_log')
def api_trade_log():
    try:
        with open(trade_logger.LOG_FILE, 'r') as f:
            return jsonify({"log_content": f.read()})
    except FileNotFoundError:
        return jsonify({"log_content": "Log file not found."})

@app.route('/api/portfolio_history')
def api_portfolio_history():
    state = get_state_from_file()
    return jsonify(state.get("equity_history", []))

# --- End Flask Web Server ---
