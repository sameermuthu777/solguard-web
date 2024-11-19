# 🛡️ SolGuard - Solana Token Safety Bot

A Telegram bot that helps users analyze and verify the safety of Solana tokens using the RugCheck API.

## Features

- Token safety analysis and risk assessment
- Detailed token reports with risk factors
- Two-tier pricing model (Free trial and Premium)
- MongoDB integration for user management
- Real-time token monitoring

## Prerequisites

- Python 3.8+
- MongoDB
- Telegram Bot Token
- Solana RPC URL
- RugCheck API access

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd 🛡️SolGuardian
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables in `.env`:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
MONGO_URI=your_mongodb_uri
SOLANA_RPC_URL=your_solana_rpc_url
PAYMENT_WALLET=your_payment_wallet_address
```

4. Start the bot:
```bash
python bot.py
```

## Usage

1. Start the bot: `/start`
2. Check a token: `/check [token_address]`
3. View subscription options: `/subscribe`
4. Check subscription status: `/status`

## Subscription Plans

- Free Trial (1 day)
  - Basic token checks
  - Limited daily usage

- Premium Plan
  - Monthly ($9.99) or Annual ($99.99)
  - Unlimited token checks
  - Real-time monitoring
  - Detailed risk analysis
  - Priority support

## Security

- Environment variables for sensitive data
- Secure MongoDB authentication
- Protected API endpoints

## License

[Your License]
