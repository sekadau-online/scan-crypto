import requests
import time
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os
import logging
import json

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

DEPLOYER_WALLET = os.getenv('DEPLOYER_WALLET')
CHAIN_ID = os.getenv('CHAIN_ID', '1')  # Default to Ethereum mainnet
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 300))  # Default 300 seconds

SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
EMAIL_TO = os.getenv('EMAIL_TO')

# Chain configuration with V2 API endpoints
CHAIN_CONFIG = {
    # Ethereum
    '1': {
        'name': 'Ethereum Mainnet',
        'domain': 'api.etherscan.io',
        'api_key_var': 'ETHERSCAN_API_KEY',
        'symbol': 'ETH',
        'explorer': 'https://etherscan.io'
    },
    # Binance Smart Chain
    '56': {
        'name': 'Binance Smart Chain',
        'domain': 'api.bscscan.com',
        'api_key_var': 'BSCSCAN_API_KEY',
        'symbol': 'BNB',
        'explorer': 'https://bscscan.com'
    },
    # Polygon
    '137': {
        'name': 'Polygon',
        'domain': 'api.polygonscan.com',
        'api_key_var': 'POLYGONSCAN_API_KEY',
        'symbol': 'MATIC',
        'explorer': 'https://polygonscan.com'
    },
    # Testnets
    '5': {
        'name': 'Goerli Testnet',
        'domain': 'api-goerli.etherscan.io',
        'api_key_var': 'ETHERSCAN_API_KEY',
        'symbol': 'ETH',
        'explorer': 'https://goerli.etherscan.io'
    },
    '11155111': {
        'name': 'Sepolia Testnet',
        'domain': 'api-sepolia.etherscan.io',
        'api_key_var': 'ETHERSCAN_API_KEY',
        'symbol': 'ETH',
        'explorer': 'https://sepolia.etherscan.io'
    }
}

# Validate chain configuration
chain_cfg = CHAIN_CONFIG.get(CHAIN_ID)
if not chain_cfg:
    logger.error(f"❌ Unsupported CHAIN_ID: {CHAIN_ID}")
    exit(1)

API_KEY = os.getenv(chain_cfg['api_key_var'])
if not API_KEY:
    logger.error(f"❌ Missing API key for {chain_cfg['name']}. Set {chain_cfg['api_key_var']} in .env")
    exit(1)

# Validate required email settings
if not all([EMAIL_USER, EMAIL_PASS, EMAIL_TO]):
    logger.error("❌ Missing email configuration in .env file")
    exit(1)

# Validate wallet address
if not DEPLOYER_WALLET or not DEPLOYER_WALLET.startswith('0x') or len(DEPLOYER_WALLET) != 42:
    logger.error("❌ Invalid wallet address format. Must start with 0x and be 42 characters long")
    exit(1)

ALREADY_ALERTED = set()

def send_email_alert(tx_data, chain_cfg):
    """Send email alert for detected transaction"""
    try:
        # Convert values
        value_wei = int(tx_data['value'])
        value_main = value_wei / 10**18
        gas_price_gwei = int(tx_data['gasPrice']) / 10**9
        
        subject = f'🚨 ALERT: Outgoing Transaction on {chain_cfg["name"]}!'
        body = (
            f'⚠️ CRITICAL: Funds movement detected from monitored wallet!\n\n'
            f'🔗 Transaction Hash: {tx_data["hash"]}\n'
            f'🏷️ Chain: {chain_cfg["name"]}\n'
            f'📤 From: {tx_data["from"]}\n'
            f'📥 To: {tx_data["to"]}\n'
            f'💰 Amount: {value_main:.6f} {chain_cfg["symbol"]}\n'
            f'⛽ Gas Price: {gas_price_gwei:.2f} Gwei\n'
            f'📅 Date: {time.ctime(int(tx_data["timeStamp"]))}\n\n'
            f'🔍 Verify transaction: {chain_cfg["explorer"]}/tx/{tx_data["hash"]}'
        )
        
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_TO

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        
        logger.info(f"📧 Email alert sent for TX: {tx_data['hash']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send email for TX {tx_data.get('hash', 'unknown')}: {str(e)}")
        return False

def get_transactions():
    """Fetch transactions using Etherscan V2 API"""
    base_url = f"https://{chain_cfg['domain']}/v2/api"
    params = {
        'chainid': CHAIN_ID,
        'module': 'account',
        'action': 'txlist',
        'address': DEPLOYER_WALLET,
        'startblock': 0,
        'endblock': 99999999,
        'sort': 'desc',
        'apikey': API_KEY
    }
    
    try:
        logger.debug(f"🌐 Request URL: {base_url}?{'&'.join([f'{k}={v}' for k,v in params.items()])}")
        
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # Log the API response for debugging
        logger.debug(f"🔁 API Response: {json.dumps(data, indent=2)}")
        
        if data.get('status') != '1' or data.get('message') != 'OK':
            error_msg = data.get('message', 'Unknown error')
            result_msg = data.get('result', 'No additional info')
            logger.error(f"❌ API Error: {error_msg} - {result_msg}")
            return []
        
        transactions = data.get('result', [])
        if not isinstance(transactions, list):
            logger.error(f"❌ Unexpected API response format: {type(transactions)}")
            return []
            
        logger.info(f"📥 Received {len(transactions)} transactions")
        return transactions
        
    except requests.exceptions.RequestException as e:
        logger.error(f"🌐 Network error: {str(e)}")
    except Exception as e:
        logger.error(f"⚠️ Unexpected error: {str(e)}")
    
    return []

def check_transactions():
    """Check for new outgoing transactions"""
    transactions = get_transactions()
    new_alerts = 0
    
    for tx in transactions:
        tx_hash = tx.get('hash', '')
        if not tx_hash:
            continue
            
        if tx_hash in ALREADY_ALERTED:
            continue
            
        # Check if outgoing transaction with value
        if (tx.get('from', '').lower() == DEPLOYER_WALLET.lower() and 
            int(tx.get('value', 0)) > 0):
            logger.warning(f"🚨 OUTGOING TX DETECTED: {tx_hash}")
            if send_email_alert(tx, chain_cfg):
                ALREADY_ALERTED.add(tx_hash)
                new_alerts += 1
    
    logger.info(f"✅ Checked {len(transactions)} transactions. New alerts: {new_alerts}")
    return new_alerts

def main():
    logger.info(f"🔍 Starting Etherscan V2 API Monitoring")
    logger.info(f"🏷️ Chain: {chain_cfg['name']}")
    logger.info(f"👛 Wallet: {DEPLOYER_WALLET}")
    logger.info(f"⏰ Check interval: {CHECK_INTERVAL} seconds")
    logger.info(f"🔑 API Key: {API_KEY[:4]}...{API_KEY[-4:]}")
    
    # Initial check
    check_transactions()
    
    # Main monitoring loop
    try:
        while True:
            time.sleep(CHECK_INTERVAL)
            check_transactions()
    except KeyboardInterrupt:
        logger.info("🛑 Monitoring stopped by user")
    except Exception as e:
        logger.error(f"🔴 Critical error in main loop: {str(e)}")

if __name__ == '__main__':
    main()
