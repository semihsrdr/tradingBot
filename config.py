import os
from dotenv import load_dotenv

# .env dosyasındaki değişkenleri yükle
load_dotenv()

# LLM Ayarları
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME_OPENROUTER") # User wants to use this model

if not OPENROUTER_API_KEY:
    raise ValueError("UYARI: .env dosyasında OPENROUTER_API_KEY bulunamadı!")
if not LLM_MODEL_NAME:
    raise ValueError("UYARI: .env dosyasında LLM_MODEL_NAME_OPENROUTER bulunamadı!")

print(f"LLM Provider: OpenRouter, Model: {LLM_MODEL_NAME}")

# Binance Ayarları
BINANCE_API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_TESTNET_API_SECRET")
# TRADING_SYMBOL'ı TRADING_SYMBOLS olarak değiştirip listeye çeviriyoruz.
# .env dosyasından "BTC/USDT,ETH/USDT" gibi virgülle ayrılmış bir string olarak okunabilir.
symbols_from_env = os.getenv("TRADING_SYMBOLS", "BTC/USDT,ETH/USDT,DOGE/USDT,SOL/USDT,XRP/USDT")
TRADING_SYMBOLS = [symbol.strip() for symbol in symbols_from_env.split(',')]


if not BINANCE_API_KEY:
    print("UYARI: API anahtarları .env dosyasında eksik!")

# Simülasyon Ayarları
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "True").lower() in ('true', '1', 't')
SIMULATION_STARTING_BALANCE = float(os.getenv("SIMULATION_STARTING_BALANCE", 1000.0))

# Email Ayarları
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# Trade Strateji Ayarları
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", 25.0)) # Yüzde olarak
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 15.0))   # Yüzde olarak (Dinamik SL aktifken kullanılmayacak)
ATR_MULTIPLIER = float(os.getenv("ATR_MULTIPLIER", 2.0))    # Dinamik Stop-Loss için ATR çarpanı