import smtplib
import config
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
from datetime import datetime

def send_email(subject, body):
    """
    Connects to the SMTP server and sends an email with verbose logging.
    """
    if not all([config.SENDER_EMAIL, config.SENDER_PASSWORD, config.RECEIVER_EMAIL]):
        print("[MAILER] Email configuration is incomplete. Cannot send email.")
        return

    print(f"[MAILER] Attempting to connect to SMTP server: {config.SMTP_SERVER}:{config.SMTP_PORT}")
    try:
        # Use a 'with' statement for robust connection handling
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            print("[MAILER] SMTP connection successful. Starting TLS...")
            server.starttls()
            print("[MAILER] TLS started. Logging in...")
            server.login(config.SENDER_EMAIL, config.SENDER_PASSWORD)
            print("[MAILER] Login successful. Sending email...")
            
            # Create the email message
            msg = MIMEMultipart()
            msg['From'] = config.SENDER_EMAIL
            msg['To'] = config.RECEIVER_EMAIL
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            text = msg.as_string()
            server.sendmail(config.SENDER_EMAIL, config.RECEIVER_EMAIL, text)
            print(f"[MAILER] Email sent successfully to {config.RECEIVER_EMAIL}.")

    except Exception as e:
        print(f"[MAILER] An error occurred during the email process: {e}")

def send_error_email(errors):
    """
    Formats and sends an email notification for consecutive errors.
    """
    subject = "Trading Bot Alert: Consecutive Errors Detected"
    
    body = "The trading bot has encountered 10 consecutive cycles with errors and requires attention.\n\n"
    body += "--- Collected Errors ---\n"
    for error in errors:
        body += f"- {error}\n"
    body += "\nPlease check the bot's logs for more details."
    
    send_email(subject, body)

def send_summary_email(portfolio_summary, open_positions):
    """
    Formats and sends a periodic summary email with detailed position info.
    """
    subject = f"Trading Bot Periodic Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    # --- Build The Email Body ---
    body = "This is a scheduled summary of the trading bot's performance.\n\n"
    
    # 1. Portfolio Summary Section
    body += "--- Portfolio Summary ---\n"
    body += f"Total Equity: ${portfolio_summary.get('total_equity_usd', 0):.2f}\n"
    body += f"Available Balance: ${portfolio_summary.get('available_balance_usd', 0):.2f}\n"
    body += f"Unrealized PnL: ${portfolio_summary.get('unrealized_pnl_usd', 0):.2f}\n"
    body += f"Open Positions Count: {portfolio_summary.get('open_positions_count', 0)}\n\n"

    # 2. Open Positions Section
    body += "--- Open Positions ---\n"
    if not open_positions:
        body += "No open positions at the moment.\n"
    else:
        for symbol, pos in open_positions.items():
            pnl = pos.get('unrealized_pnl', 0)
            pnl_pct = (pnl / pos['margin']) * 100 if pos.get('margin', 0) > 0 else 0
            
            body += f"Symbol: {symbol}\n"
            body += f"  Side: {pos.get('side', 'N/A').upper()}\n"
            body += f"  Quantity: {pos.get('quantity', 0):.6f}\n"
            body += f"  Leverage: {pos.get('leverage', 0)}x\n"
            body += f"  Entry Price: ${pos.get('entry_price', 0):.4f}\n"
            body += f"  Current Price: ${pos.get('current_price', 0):.4f}\n"
            body += f"  Unrealized PnL: ${pnl:.4f} ({pnl_pct:.2f}%)\n"
            body += "---\n"

    body += "\nBot continues to operate normally."

    send_email(subject, body)
