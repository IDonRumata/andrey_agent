"""
Получение актуальных цен активов.
Крипто: CoinGecko API (бесплатно, без ключа)
Акции/ETF: Yahoo Finance (неофициальный API)
"""
import logging
import aiohttp

logger = logging.getLogger(__name__)

# Крипто тикеры → CoinGecko ID
CRYPTO_IDS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "USDT": "tether",
    "USDC": "usd-coin",
    "XRP": "ripple",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "TON": "the-open-network",
    "NOT": "notcoin",
    "TRX": "tron",
    "LTC": "litecoin",
    "DOGE": "dogecoin",
    "SHIB": "shiba-inu",
    "PEPE": "pepe",
}

CRYPTO_TICKERS = set(CRYPTO_IDS.keys())


def detect_asset_type(asset: str) -> str:
    """Определить тип актива: crypto, stock, etf."""
    if asset.upper() in CRYPTO_TICKERS:
        return "crypto"
    # Известные ETF
    etf_tickers = {"SPY", "QQQ", "VTI", "VOO", "IVV", "GLD", "FXUS", "FXGD", "SBSP", "TMOS"}
    if asset.upper() in etf_tickers:
        return "etf"
    return "stock"


async def get_crypto_price(ticker: str, currency: str = "usd") -> float | None:
    """Цена крипты через CoinGecko."""
    ticker = ticker.upper()
    coin_id = CRYPTO_IDS.get(ticker, ticker.lower())
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": coin_id, "vs_currencies": currency.lower()}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    if coin_id in data:
                        return float(data[coin_id][currency.lower()])
    except Exception as e:
        logger.warning(f"CoinGecko error {ticker}: {e}")
    return None


async def get_stock_price(ticker: str) -> float | None:
    """Цена акции/ETF через Yahoo Finance."""
    # Для российских акций пробуем .ME суффикс
    ru_exchanges = {"SBER", "GAZP", "LKOH", "GMKN", "YNDX", "VTBR", "ROSN", "NVTK", "MGNT", "TATN"}
    if ticker.upper() in ru_exchanges:
        ticker = ticker.upper() + ".ME"

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    result = data.get("chart", {}).get("result")
                    if result:
                        return float(result[0]["meta"]["regularMarketPrice"])
    except Exception as e:
        logger.warning(f"Yahoo Finance error {ticker}: {e}")
    return None


async def get_price(asset: str, asset_type: str | None = None) -> tuple[float | None, str]:
    """
    Универсальное получение цены.
    Возвращает (цена, валюта) или (None, '').
    """
    if asset_type is None:
        asset_type = detect_asset_type(asset)

    if asset_type == "crypto":
        price = await get_crypto_price(asset, "usd")
        return price, "USD"
    else:
        price = await get_stock_price(asset)
        # Определяем валюту по бирже
        ru = {"SBER", "GAZP", "LKOH", "GMKN", "YNDX", "VTBR", "ROSN", "NVTK", "MGNT", "TATN"}
        currency = "RUB" if asset.upper() in ru else "USD"
        return price, currency
