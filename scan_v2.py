import requests
import time
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os
import logging

# === SETUP LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# === LOAD ENV ===
load_dotenv()

ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')
DEPLOYER_WALLET = os.getenv('DEPLOYER_WALLET')
CHAIN_ID = os.getenv('CHAIN_ID', '1')  # Default to mainnet
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))  # Default 60 seconds

SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
EMAIL_TO = os.getenv('EMAIL_TO')

if not all([ETHERSCAN_API_KEY, DEPLOYER_WALLET, EMAIL_USER, EMAIL_PASS, EMAIL_TO]):
    logger.error("Missing required environment variables!")
    exit(1)

# Domain mapping for different chains
CHAIN_DOMAINS = {
    '1': 'api.etherscan.io',          # Ethereum Mainnet
    '5': 'api-goerli.etherscan.io',    # Goerli Testnet
    '11155111': 'api-sepolia.etherscan.io',  # Sepolia
    '56': 'api.bscscan.com',           # BSC
    '137': 'api.polygonscan.com'        # Polygon
}

ALREADY_ALERTED = set()

def send_email_alert(tx_hash, to_address, value, chain_id):
    chain_name = {
        '1': 'Ethereum Mainnet',
        '5': 'Goerli Testnet',
        '11155111': 'Sepolia Testnet',
        '56': 'Binance Smart Chain',
        '137': 'Polygon'
    }.get(chain_id, f'Chain ID {chain_id}')
    
    value_eth = int(value) / 10**18
    
    subject = f'🚨 ALERT: Outgoing Transaction Detected on {chain_name}!'
    body = (
        f'⚠️ CRITICAL: Funds movement detected from monitored wallet!\n\n'
        f'🔗 Transaction Hash: {tx_hash}\n'
        f'🏷️ Chain: {chain_name}\n'
        f'📤 From: {DEPLOYER_WALLET}\n'
        f'📥 To: {to_address}\n'
        f'💰 Amount: {value_eth:.6f} ETH\n\n'
        f'🔍 Verify transaction: https://{CHAIN_DOMAINS.get(chain_id, "etherscan.io")}/tx/{tx_hash}'
    )
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_TO

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        logger.info(f"Email alert sent for TX: {tx_hash}")
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")

def check_transactions():
    domain = CHAIN_DOMAINS.get(CHAIN_ID, 'api.etherscan.io')
    url = f'https://{domain}/v2/api?module=account&action=txlist&address={DEPLOYER_WALLET}&sort=desc&apikey={ETHERSCAN_API_KEY}'
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != '1':
            logger.error(f"API Error: {data.get('message', 'Unknown error')}")
            return

        for tx in data.get('result', []):
            tx_hash = tx.get('hash', '')
            if not tx_hash:
                continue
                
            if tx_hash in ALREADY_ALERTED:
                continue

            if (tx.get('from', '').lower() == DEPLOYER_WALLET.lower() and 
                int(tx.get('value', 0)) > 0):
                logger.warning(f"🚨 OUTGOING TX DETECTED: {tx_hash}")
                send_email_alert(
                    tx_hash,
                    tx.get('to', 'Unknown'),
                    tx.get('value', 0),
                    CHAIN_ID
                )
                ALREADY_ALERTED.add(tx_hash)
                
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")

def main():
    logger.info(f"🔍 Starting monitoring on {CHAIN_DOMAINS.get(CHAIN_ID, 'Ethereum')} for wallet: {DEPLOYER_WALLET}")
    logger.info(f"⏰ Check interval: {CHECK_INTERVAL} seconds")
    
    while True:
        check_transactions()
        time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()
