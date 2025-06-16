import os
import json
import logging
import requests
import re
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters
)
import openai
from dotenv import load_dotenv

#Load environment variables
load_dotenv()

#Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

#API Configuration
COINBASE_API = "https://api.coinbase.com/v2/prices"
COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price"
OPENAI_MODEL = "gpt-4-turbo"

#System Prompts
INTENT_PROMPT = """
You are an intent classifier for a crypto assistant. Analyze the user's message and output JSON with:
- intent: "price", "convert", "trend", or "error"
- parameters: Extract relevant entities

Output ONLY JSON with these possible structures:
{"intent": "price", "crypto_symbol": "BTC", "fiat_currency": "USD"}
{"intent": "convert", "amount": 0.5, "from_asset": "ETH", "to_asset": "USD"}
{"intent": "trend", "crypto_symbol": "SOL", "timeframe": "7d"}
{"intent": "error", "reason": "message"}

Rules:
1. Default fiat: USD
2. Default timeframe: 7d
3. For price checks: Extract crypto symbol
4. For conversions: Extract amount, from_asset, to_asset
5. For trends: Extract crypto_symbol and timeframe
6. If unsure, return error intent

Examples:
User: "What's bitcoin worth?" → {"intent": "price", "crypto_symbol": "BTC"}
User: "Convert 1 ethereum to dollars" → {"intent": "convert", "amount": 1, "from_asset": "ETH", "to_asset": "USD"}
User: "How did solana perform last month?" → {"intent": "trend", "crypto_symbol": "SOL", "timeframe": "30d"}
"""

#Natural conversation prompt
RESPONSE_PROMPT = """
You're a friendly crypto expert. Answer the user's question naturally and conversationally. Follow these guidelines:

1. Be concise (1-2 sentences maximum)
2. Use everyday language, not financial jargon
3. Format numbers clearly (e.g., $12,000.50)
4. Only include risk warnings if there's unusual volatility
5. Add personality with occasional emojis (max 1 per response)
6. NEVER use markdown, bullet points, or numbered lists

Examples:
User: "Price of BTC?"
Good: "Bitcoin is currently trading at $61,200 - up 2% today!"
Bad: "The current price of Bitcoin is $61,200. It has increased by 2% in the last 24 hours."

User: "Convert 5 ETH to USD"
Good: "5 Ethereum would be about $15,250 right now at $3,050 per ETH. Crypto prices move fast though!"
Bad: "Converting 5 ETH to USD gives $15,250. The current exchange rate is $3,050 per ETH."

Data: {data}
"""

class CryptoAPI:
    @staticmethod
    def get_spot_price(asset: str, currency: str = "USD") -> float:
        """Fetch current price from Coinbase"""
        try:
            #Normalize asset symbols
            asset = asset.upper()
            currency = currency.upper()
            
            response = requests.get(
                f"{COINBASE_API}/{asset}-{currency}/spot"
            )
            response.raise_for_status()
            return float(response.json()["data"]["amount"])
        except (requests.RequestException, KeyError, ValueError) as e:
            logger.error(f"Coinbase error: {e}")
            raise

    @staticmethod
    def get_conversion_rate(from_asset: str, to_asset: str) -> float:
        """Get conversion rate using CoinGecko"""
        try:
            #Map common names to CoinGecko IDs
            coin_mapping = {
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "SOL": "solana",
                "DOGE": "dogecoin",
                "XRP": "ripple",
                "ADA": "cardano",
                "USD": "usd",
                "USDT": "tether",
                "USDC": "usd-coin"
            }
            
            from_id = coin_mapping.get(from_asset.upper(), from_asset.lower())
            to_id = coin_mapping.get(to_asset.upper(), to_asset.lower())
            
            params = {
                "ids": from_id,
                "vs_currencies": to_id
            }
            response = requests.get(COINGECKO_API, params=params)
            response.raise_for_status()
            data = response.json()
            return data[from_id][to_id]
        except (requests.RequestException, KeyError) as e:
            logger.error(f"CoinGecko error: {e}")
            raise

class OpenAIService:
    @staticmethod
    def classify_intent(query: str) -> dict:
        """Classify user intent using GPT with robust error handling"""
        try:
            response = openai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": INTENT_PROMPT},
                    {"role": "user", "content": query}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            return json.loads(response.choices[0].message.content)
        except (openai.OpenAIError, json.JSONDecodeError) as e:
            logger.error(f"Intent classification failed: {e}")
            #Fallback: Simple regex-based intent detection
            if re.search(r'\b(price|worth|value)\b', query, re.IGNORECASE):
                symbols = re.findall(r'\b(BTC|ETH|SOL|BNB|XRP|ADA|DOGE)\b', query, re.IGNORECASE)
                return {
                    "intent": "price",
                    "crypto_symbol": symbols[0] if symbols else "BTC"
                }
            elif re.search(r'\b(convert|how much|equivalent)\b', query, re.IGNORECASE):
                return {"intent": "convert", "amount": 1, "from_asset": "ETH", "to_asset": "USD"}
            return {"intent": "error", "reason": "Classification failed"}

    @staticmethod
    def generate_response(query: str, data: dict) -> str:
        """Generate natural language response"""
        try:
            system_content = RESPONSE_PROMPT.format(data=json.dumps(data))
            
            response = openai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": query}
                ],
                temperature=0.8
            )
            return response.choices[0].message.content
        except openai.OpenAIError as e:
            logger.error(f"Response generation failed: {e}")
            #Fallback with natural language
            if 'price' in data:
                return f"{data.get('asset', 'Crypto')} is currently at ${data['price']:,.2f}"
            elif 'result' in data:
                return f"{data['amount']} {data['from']} ≈ {data['result']:,.2f} {data['to']}"
            return "Having trouble checking prices right now. Try again in a minute!"

class CryptoOracleBot:
    def __init__(self):
        self.api = CryptoAPI()
        self.ai = OpenAIService()

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main message handler with improved intent handling"""
        user_query = update.message.text
        user = update.effective_user
        logger.info(f"User {user.id}: {user_query}")
        
        try:
            #Classify intent
            intent_data = self.ai.classify_intent(user_query)
            intent = intent_data.get("intent", "error")
            logger.info(f"Classified intent: {intent_data}")
            
            #Process based on intent
            if intent == "price":
                asset = intent_data.get("crypto_symbol", "BTC")
                currency = intent_data.get("fiat_currency", "USD")
                price = self.api.get_spot_price(asset, currency)
                response = self.ai.generate_response(
                    user_query,
                    {"price": price, "asset": asset, "currency": currency}
                )
                
            elif intent == "convert":
                amount = float(intent_data.get("amount", 1))
                from_asset = intent_data.get("from_asset", "BTC")
                to_asset = intent_data.get("to_asset", "USD")
                
                #Special case for fiat conversions
                if to_asset.upper() in ["USD", "USDT", "USDC"]:
                    rate = self.api.get_spot_price(from_asset, "USD")
                else:
                    rate = self.api.get_conversion_rate(from_asset, to_asset)
                    
                converted = amount * rate
                response = self.ai.generate_response(
                    user_query,
                    {
                        "amount": amount, 
                        "from": from_asset, 
                        "to": to_asset, 
                        "result": converted,
                        "rate": rate
                    }
                )
                
            else:
                #Handle errors and unknown intents
                if intent == "error":
                    reason = intent_data.get("reason", "Unclear query")
                    response = f"Sorry, I didn't understand that. Try something like:\n• 'ETH price'\n• 'Convert 1 BTC to USD'"
                else:
                    response = "What cryptocurrency are you asking about? Try:\n• 'BTC price'\n• 'Convert 0.5 ETH to SOL'"
                
        except Exception as e:
            logger.exception("Processing error")
            response = f"Oops! Ran into an issue: {str(e)}. Try asking differently?"
        
        await update.message.reply_text(response)

#Bot Initialization
def main():
    application = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    bot = CryptoOracleBot()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    #Start command handler
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Hi! I'm your Crypto Oracle. Ask me things like:\n"
            "• \"What's Bitcoin worth?\"\n"
            "• \"Convert 0.5 ETH to USD\"\n"
            "• \"SOL price\"\n\n"
            "I'll give you quick, friendly answers!"
        )
    
    application.add_handler(CommandHandler("start", start))
    
    #Help command handler
    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Just ask naturally! Examples:\n"
            "\"What's Ethereum worth?\"\n"
            "\"Convert 1 Bitcoin to US dollars\"\n"
            "\"Price of Solana\"\n\n"
            "I support: BTC, ETH, SOL, XRP, ADA, DOGE"
        )
    
    application.add_handler(CommandHandler("help", help_cmd))
    application.run_polling()

if __name__ == "__main__":
    main()