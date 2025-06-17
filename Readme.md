# Crypto Oracle Bot

A Telegram chatbot that provides real-time cryptocurrency prices, conversions, and market insights using GPT-4, Coinbase, and CoinGecko APIs.

---

## Features

- Natural language queries like: _"What’s Bitcoin worth?"_
- Multi-currency support: `BTC`, `ETH`, `SOL`, `XRP`, `ADA`, `DOGE` + fiat
- Pulls data from **Coinbase** and **CoinGecko**
- GPT-4 powered explanations
- Graceful error handling and fallback messages

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/myles4321/cryptoOracleBot.git
cd cryptoOracleBot
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
TELEGRAM_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
```

### 4. Run the Bot

```bash
python bot.py
```

---

## API Highlights

### `CryptoAPI`

```python
get_spot_price(asset: str, currency: str = "USD") -> float
```

Returns the current price from Coinbase.

```python
get_conversion_rate(from_asset: str, to_asset: str) -> float
```

Returns conversion rate from CoinGecko.

### `OpenAIService`

```python
classify_intent(query: str) -> dict
generate_response(query: str, data: dict) -> str
```

Uses GPT-4 to detect user intent and generate natural responses.

---

## Project Structure

```
cryptoOracleBot/
├── bot.py               # Telegram bot logic/Crypto data functions/OpenAI functions
├── Readme.md            # Setup and execution information
├── requirements.txt     # Dependencies
└── .env                 # Env variables

```
