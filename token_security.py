from typing import Dict, Optional, List, Tuple
import httpx
from dataclasses import dataclass
import asyncio
from datetime import datetime
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TokenSecurityResult:
    def __init__(self):
        self.name = ""
        self.symbol = ""
        self.price_usd = 0.0
        self.price_change_24h = 0.0
        self.liquidity_usd = 0.0
        self.volume_24h = 0.0
        self.market_cap = 0.0
        self.pairs = []
        self.risk_score = 50
        self.risk_level = ""
        self.risk_factors = []
        self.warnings = []
        self.positive_factors = []
        # New fields
        self.total_holders = 0
        self.liquidity_locked = False
        self.liquidity_lock_percentage = 0.0
        self.liquidity_lock_time = 0  # in days
        self.circulating_supply = 0
        self.total_supply = 0
        self.lock_type = ""
        self.token_decimals = 0

class TokenSecurityChecker:
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        pass

    async def _get_dexscreener_data(self, token_address: str) -> Dict:
        """Get token data from DexScreener API"""
        try:
            # First try with Solana chain
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            logger.info(f"Fetching DexScreener data for token: {token_address}")
            
            data = await self._make_request(url)
            logger.info(f"DexScreener response: {data}")
            
            if not data or not data.get('pairs'):
                # Try alternative endpoint for Solana tokens
                url = f"https://api.dexscreener.com/latest/dex/search?q={token_address}"
                logger.info(f"Trying alternative DexScreener endpoint: {url}")
                data = await self._make_request(url)
                logger.info(f"Alternative endpoint response: {data}")
            
            if not data:
                logger.warning(f"No data returned from DexScreener for token {token_address}")
                return None
                
            pairs = data.get('pairs', [])
            if not pairs:
                logger.warning(f"No trading pairs found for token {token_address}")
                return None
                
            # Filter for Solana pairs only
            solana_pairs = [pair for pair in pairs if pair.get('chainId') == 'solana']
            if solana_pairs:
                data['pairs'] = solana_pairs
            else:
                logger.warning(f"No Solana pairs found for token {token_address}")
                return None
                
            # Verify the pairs contain the required data
            valid_pairs = []
            for pair in solana_pairs:
                if pair.get('liquidity', {}).get('usd') and pair.get('priceUsd'):
                    valid_pairs.append(pair)
                    logger.info(f"Found valid pair: {pair.get('pairAddress')} with "
                              f"liquidity: ${pair.get('liquidity', {}).get('usd', 0)}")
                    
            if not valid_pairs:
                logger.warning(f"No valid trading pairs with liquidity found for token {token_address}")
                return None
                
            data['pairs'] = valid_pairs
            return data
                
        except Exception as e:
            logger.error(f"Failed to fetch DexScreener data: {str(e)}", exc_info=True)
            return None

    async def _get_solscan_data(self, token_address: str) -> Dict:
        """Get token data from Solscan API"""
        try:
            url = f"https://public-api.solscan.io/token/meta?tokenAddress={token_address}"
            response = await self._make_request(url)
            return response
        except Exception as e:
            logger.warning(f"Failed to get Solscan data: {str(e)}")
            return {}

    async def _get_birdeye_data(self, token_address: str) -> Dict:
        """Get token data from Birdeye API"""
        try:
            url = f"https://public-api.birdeye.so/public/token_list/solana?address={token_address}"
            headers = {
                "X-API-KEY": "BIRDEYE_PUBLIC",  # Public API key for basic data
                "Accept": "application/json"
            }
            response = await self._make_request(url, headers=headers)
            if not response:
                return {}
            return response.get('data', {}).get('tokens', [{}])[0]
        except Exception as e:
            logger.warning(f"Failed to get Birdeye data: {str(e)}")
            return {}

    async def _get_token_metadata(self, token_address: str) -> Dict:
        """Get token metadata using Solana RPC API"""
        try:
            url = "https://rpc.ankr.com/solana"
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenSupply",
                "params": [token_address]
            }
            headers = {
                "Content-Type": "application/json"
            }
            
            response = await self._make_request(url, method="POST", headers=headers, json=payload)
            if response and 'result' in response:
                logger.info(f"\nToken Supply Info:")
                logger.info(f"Amount: {response['result']['value']['amount']}")
                logger.info(f"Decimals: {response['result']['value']['decimals']}")
                logger.info(f"UI Amount: {response['result']['value']['uiAmount']}")
                return response['result']['value']
            return {}
        except Exception as e:
            logger.warning(f"Failed to get token metadata: {str(e)}")
            return {}

    async def _get_solana_token_holders(self, token_address: str) -> int:
        """Get token holder count using Solana RPC API"""
        try:
            url = "https://rpc.ankr.com/solana"
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getProgramAccounts",
                "params": [
                    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # Token Program ID
                    {
                        "encoding": "jsonParsed",
                        "filters": [
                            {
                                "dataSize": 165  # Size of token account data
                            },
                            {
                                "memcmp": {
                                    "offset": 0,
                                    "bytes": token_address
                                }
                            }
                        ]
                    }
                ]
            }
            headers = {
                "Content-Type": "application/json"
            }
            
            response = await self._make_request(url, method="POST", headers=headers, json=payload)
            if response and 'result' in response:
                accounts = response['result']
                logger.info(f"\nToken Account Details:")
                total_holders = 0
                
                for acc in accounts:
                    try:
                        parsed_data = acc['account']['data']['parsed']['info']
                        amount = float(parsed_data['tokenAmount']['amount'])
                        decimals = parsed_data['tokenAmount']['decimals']
                        
                        if amount > 0:
                            total_holders += 1
                            logger.info(f"Account: {acc['pubkey']}, Amount: {amount}, Decimals: {decimals}")
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Failed to parse account data: {str(e)}")
                        continue
                
                logger.info(f"\nTotal non-zero accounts (holders): {total_holders}")
                return total_holders
            return 0
        except Exception as e:
            logger.warning(f"Failed to get Solana token holders: {str(e)}")
            return 0

    async def _make_request(self, url: str, method: str = "GET", headers: Dict = None, json: Dict = None) -> Dict:
        """Make HTTP request with retry logic and improved error handling"""
        if headers is None:
            headers = {
                'Accept': 'application/json',
                'User-Agent': 'SolanaGuard/1.0'
            }
            
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    logger.info(f"Making request to {url} (Attempt {attempt}/{self.max_retries})")
                    
                    if method == "POST" and json:
                        response = await client.post(url, headers=headers, json=json)
                    else:
                        response = await client.get(url, headers=headers)
                        
                    response.raise_for_status()
                    data = response.json()
                    logger.info(f"Successful response from {url}")
                    return data
                    
            except httpx.TimeoutException:
                logger.warning(f"Timeout on attempt {attempt} for {url}")
                if attempt == self.max_retries:
                    logger.error(f"All attempts timed out for {url}")
                    return {}
                    
            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP error {e.response.status_code} on attempt {attempt} for {url}")
                if e.response.status_code == 429:  # Rate limit
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                elif attempt == self.max_retries:
                    logger.error(f"Failed with status {e.response.status_code} for {url}")
                    return {}
                    
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt} for {url}: {str(e)}")
                if attempt == self.max_retries:
                    return {}
                    
            await asyncio.sleep(self.retry_delay)

    async def _process_dexscreener_data(self, result: TokenSecurityResult, data: Dict):
        """Process DexScreener market data"""
        if not data or 'pairs' not in data:
            return

        pairs = data['pairs']
        if not pairs:
            return

        # Debug: Log the raw data
        logger.info(f"DexScreener Raw Data: {data}")

        # Sort pairs by liquidity
        pairs.sort(key=lambda x: float(x.get('liquidity', {}).get('usd', 0)), reverse=True)
        main_pair = pairs[0]  # Most liquid pair

        # Debug: Log main pair data
        logger.info(f"Main Pair Data: {main_pair}")

        # Store top DEX pairs for display
        unique_dexes = set()
        result.pairs = []
        for pair in pairs:
            dex_id = pair.get('dexId', '').upper()
            if dex_id and float(pair.get('liquidity', {}).get('usd', 0)) > 1000:  # Only count pairs with >$1K liquidity
                unique_dexes.add(dex_id)
                result.pairs.append({
                    'dex': dex_id,
                    'liquidity': float(pair.get('liquidity', {}).get('usd', 0)),
                    'pair_address': pair.get('pairAddress', ''),
                    'price_usd': float(pair.get('priceUsd', 0)),
                    'volume_24h': float(pair.get('volume', {}).get('h24', 0))
                })

        # Add warning if listed on limited DEXes
        if len(unique_dexes) < 3:
            result.warnings.append("Listed on a limited number of DEXes - Lower market presence")

        # Get base token info
        base_token = main_pair.get('baseToken', {})
        result.name = base_token.get('name', 'Unknown')
        result.symbol = base_token.get('symbol', 'Unknown')

        # Process price data
        try:
            result.price_usd = float(main_pair.get('priceUsd', 0))
            result.price_change_24h = float(main_pair.get('priceChange', {}).get('h24', 0))
        except (ValueError, TypeError):
            logger.warning("Failed to process price data")
            result.price_usd = 0
            result.price_change_24h = 0

        # Process liquidity and volume
        try:
            result.liquidity_usd = float(main_pair.get('liquidity', {}).get('usd', 0))
            result.volume_24h = float(main_pair.get('volume', {}).get('h24', 0))
        except (ValueError, TypeError):
            logger.warning("Failed to process liquidity and volume data")
            result.liquidity_usd = 0
            result.volume_24h = 0

        # Process market cap
        try:
            result.market_cap = float(main_pair.get('fdv', 0))
            if result.market_cap == 0:
                result.market_cap = float(main_pair.get('marketCap', 0))
        except (ValueError, TypeError):
            logger.warning("Failed to process market cap data")
            result.market_cap = 0

        # Process social info and website
        try:
            info = main_pair.get('info', {})
            if info:
                websites = info.get('websites', [])
                if websites:
                    result.positive_factors.append(f"Has official website: {websites[0].get('url', '')}")
                
                socials = info.get('socials', [])
                if socials:
                    social_links = []
                    for social in socials:
                        if social.get('type') == 'twitter':
                            social_links.append("Twitter")
                        elif social.get('type') == 'telegram':
                            social_links.append("Telegram")
                    if social_links:
                        result.positive_factors.append(f"Active on: {', '.join(social_links)}")
        except Exception as e:
            logger.warning(f"Failed to process social info: {str(e)}")

        # Check liquidity lock status
        try:
            for pair in pairs:
                liquidity_info = pair.get('liquidity', {})
                
                # Get lock percentage if available
                lock_percentage = liquidity_info.get('lockPercent', 0)
                if isinstance(lock_percentage, str):
                    try:
                        lock_percentage = float(lock_percentage.rstrip('%'))
                    except ValueError:
                        lock_percentage = 0
                
                # Check for managed liquidity pools
                if any(label in pair.get('labels', []) for label in ['DLMM', 'DYN', 'CLMM']):
                    result.liquidity_locked = True
                    result.lock_type = "Managed Pool"
                    break
                # Check explicit liquidity lock
                elif liquidity_info.get('locked') or lock_percentage > 0:
                    result.liquidity_locked = True
                    result.liquidity_lock_percentage = lock_percentage
                    result.liquidity_lock_time = liquidity_info.get('lockDays', 365)
                    result.lock_type = "Traditional Lock"
                    break

        except Exception as e:
            logger.warning(f"Failed to check liquidity lock: {str(e)}")

    def _calculate_risk_score(self, result: TokenSecurityResult):
        """Calculate risk score based on various factors with enhanced rugpull and honeypot detection"""
        score = 100
        risk_factors = []
        warnings = []
        positive_factors = []

        # === LIQUIDITY ANALYSIS (25% weight) ===
        if result.liquidity_usd < 10000:
            score -= 25
            risk_factors.append("🚨 CRITICAL: Extremely low liquidity (< $10K) - High risk of price manipulation and rugpull")
        elif result.liquidity_usd < 50000:
            score -= 15
            risk_factors.append("⚠️ Low liquidity (< $50K) - Moderate risk of price manipulation")
        elif result.liquidity_usd < 100000:
            score -= 10
            warnings.append("⚠️ Moderate liquidity (< $100K) - Some price impact on large trades")
        else:
            positive_factors.append("✅ Healthy liquidity pool (> $100K)")

        # === HONEYPOT DETECTION (20% weight) ===
        # Volume to Liquidity Ratio Analysis
        if result.liquidity_usd > 0:
            vol_liq_ratio = result.volume_24h / result.liquidity_usd
            if vol_liq_ratio < 0.01:  # Almost no trading volume
                score -= 20
                risk_factors.append("🚨 POTENTIAL HONEYPOT: Extremely low trading volume relative to liquidity")
            elif vol_liq_ratio > 15:
                score -= 15
                risk_factors.append("🚨 Suspicious trading: Unusually high volume relative to liquidity - Likely wash trading")
            elif vol_liq_ratio > 10:
                score -= 10
                warnings.append("⚠️ High volume relative to liquidity - Monitor for wash trading")
            elif vol_liq_ratio > 5:
                score -= 5
                warnings.append("⚠️ Moderate volume relative to liquidity")

        # === RUGPULL RISK ANALYSIS (25% weight) ===
        # Liquidity Lock Analysis
        if result.liquidity_locked:
            if result.lock_type == "Traditional Lock":
                if result.liquidity_lock_percentage >= 95 and result.liquidity_lock_time >= 180:
                    positive_factors.append(f"✅ Strong liquidity protection: {result.liquidity_lock_percentage:.1f}% locked for {result.liquidity_lock_time} days")
                elif result.liquidity_lock_percentage >= 80 and result.liquidity_lock_time >= 90:
                    warnings.append(f"⚠️ Moderate liquidity protection: {result.liquidity_lock_percentage:.1f}% locked for {result.liquidity_lock_time} days")
                    score -= 10
                else:
                    risk_factors.append(f"🚨 Weak liquidity protection: Only {result.liquidity_lock_percentage:.1f}% locked for {result.liquidity_lock_time} days")
                    score -= 20
            elif result.lock_type == "Managed Pool":
                positive_factors.append("✅ Protected: Liquidity managed by automated market maker")
        else:
            risk_factors.append("🚨 HIGH RUGPULL RISK: Liquidity is not locked")
            score -= 25

        # Holder Distribution Analysis
        if result.total_holders > 0:
            if result.total_holders < 100:
                score -= 15
                risk_factors.append(f"🚨 Extreme concentration risk: Only {result.total_holders:,} holders")
            elif result.total_holders < 500:
                score -= 10
                warnings.append(f"⚠️ High concentration risk: Only {result.total_holders:,} holders")
            elif result.total_holders > 1000:
                positive_factors.append(f"✅ Healthy distribution: {result.total_holders:,} holders")

        # === MARKET MANIPULATION ANALYSIS (15% weight) ===
        # Price Volatility Analysis
        if abs(result.price_change_24h) > 50:
            score -= 15
            risk_factors.append(f"🚨 Extreme volatility: {result.price_change_24h:+.2f}% in 24h - High manipulation risk")
        elif abs(result.price_change_24h) > 30:
            score -= 10
            warnings.append(f"⚠️ High volatility: {result.price_change_24h:+.2f}% in 24h")
        elif abs(result.price_change_24h) > 15:
            score -= 5
            warnings.append(f"⚠️ Notable price movement: {result.price_change_24h:+.2f}% in 24h")

        # Market Impact Analysis
        if result.liquidity_usd > 0:
            impact_10k = (10000 / result.liquidity_usd) * 100  # Impact of $10K trade
            if impact_10k > 20:
                score -= 10
                risk_factors.append(f"🚨 High price impact: $10K trade affects price by ~{impact_10k:.1f}%")
            elif impact_10k > 10:
                warnings.append(f"⚠️ Moderate price impact: $10K trade affects price by ~{impact_10k:.1f}%")

        # === MARKET PRESENCE ANALYSIS (15% weight) ===
        # DEX Presence Analysis
        if len(result.pairs) < 2:
            score -= 15
            risk_factors.append("🚨 Single DEX listing - High manipulation risk")
        elif len(result.pairs) < 3:
            score -= 10
            warnings.append("⚠️ Limited DEX presence - Consider wider market coverage")
        else:
            positive_factors.append(f"✅ Good market presence: Listed on {len(result.pairs)} DEXes")

        # Market Cap Analysis
        if result.market_cap > 0:
            if result.market_cap < 100000:
                score -= 10
                warnings.append(f"⚠️ Micro-cap token: {self._format_number(result.market_cap)}")
            elif result.market_cap < 500000:
                score -= 5
                warnings.append(f"⚠️ Small-cap token: {self._format_number(result.market_cap)}")
            elif result.market_cap > 1000000:
                positive_factors.append(f"✅ Established market cap: {self._format_number(result.market_cap)}")

        # Ensure score stays within bounds
        score = max(0, min(100, score))

        # Set risk level based on score with more detailed categorization
        if score < 30:
            result.risk_level = "EXTREME RISK ⛔️"
        elif score < 50:
            result.risk_level = "CRITICAL RISK 🚨"
        elif score < 65:
            result.risk_level = "HIGH RISK ⚠️"
        elif score < 80:
            result.risk_level = "MEDIUM RISK ⚡️"
        else:
            result.risk_level = "LOW RISK ✅"

        result.risk_score = score
        result.risk_factors = risk_factors
        result.warnings = warnings
        result.positive_factors = positive_factors

    def format_token_analysis(self, result: TokenSecurityResult) -> str:
        """Format token analysis results into a Telegram-friendly message with HTML formatting"""
        def escape_html(text):
            """Escape HTML special characters"""
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # Format price string based on value
        if result.price_usd < 0.000001:
            price_str = f"${result.price_usd:.8f}"
        elif result.price_usd < 0.01:
            price_str = f"${result.price_usd:.6f}"
        else:
            price_str = f"${result.price_usd:.5f}"

        # Header with token info
        analysis = [
            "<b>🛡️ SOLGUARDIAN ANALYSIS</b>",
            f"<b>{escape_html(result.name)}</b> (<code>{escape_html(result.symbol)}</code>)",
            "",
            "<b>📊 KEY METRICS</b>",
            f"• Price: <code>{escape_html(price_str)}</code>",
            f"• 24h Change: <code>{result.price_change_24h:+.2f}%</code>",
            f"• Volume: <code>{escape_html(self._format_number(result.volume_24h))}</code>",
            f"• Liquidity: <code>{escape_html(self._format_number(result.liquidity_usd))}</code>",
            f"• Market Cap: <code>{escape_html(self._format_number(result.market_cap))}</code>",
            f"• Holders: <code>{result.total_holders:,}</code>" if result.total_holders > 0 else "• Holders: <code>Unknown</code>",
            ""
        ]

        # Security Information
        analysis.append("<b>🔒 SECURITY CHECK</b>")
        if result.liquidity_locked:
            if result.lock_type == "Traditional Lock":
                analysis.append(f"• <code>{result.liquidity_lock_percentage:.1f}%</code> liquidity locked")
                analysis.append(f"• Lock period: <code>{result.liquidity_lock_time}</code> days")
            elif result.lock_type == "Managed Pool":
                analysis.append("• Liquidity managed by pool")
        else:
            analysis.append("• ⚠️ Liquidity not locked")
        analysis.append("")

        # DEX Information
        analysis.append("<b>💱 DEX PRESENCE</b>")
        if result.pairs:
            for pair in result.pairs[:3]:
                analysis.append(f"• {escape_html(pair['dex'])}: <code>{escape_html(self._format_number(pair['liquidity']))}</code>")
        else:
            analysis.append("• No active DEX pairs found")
        analysis.append("")

        # Risk Assessment
        risk_emoji = "🟢" if result.risk_score >= 75 else "🟡" if result.risk_score >= 60 else "🔴"
        analysis.extend([
            "<b>⚖️ RISK ASSESSMENT</b>",
            f"Score: <code>{result.risk_score}/100</code> {risk_emoji}",
            f"Level: <b>{escape_html(result.risk_level)}</b>",
            ""
        ])

        # Risk Factors
        if result.risk_factors:
            analysis.append("<b>❗ CRITICAL RISKS</b>")
            for factor in result.risk_factors:
                analysis.append(f"• {escape_html(factor)}")
            analysis.append("")

        if result.warnings:
            analysis.append("<b>⚠️ WARNINGS</b>")
            for warning in result.warnings:
                analysis.append(f"• {escape_html(warning)}")
            analysis.append("")

        if result.positive_factors:
            analysis.append("<b>✅ POSITIVE FACTORS</b>")
            for factor in result.positive_factors:
                analysis.append(f"• {escape_html(factor)}")
            analysis.append("")

        # Final Verdict
        analysis.extend([
            "<b>🎯 VERDICT</b>",
            f"<b>{escape_html(self._get_investment_recommendation(result))}</b>",
            "",
            "<i>Powered by Solana Guard Bot</i>"
        ])

        return "\n".join(analysis)

    def _get_investment_recommendation(self, result: TokenSecurityResult) -> str:
        """Generate an investment recommendation based on the risk analysis"""
        if result.risk_score >= 75:
            return "SAFE TO TRADE - Low risk profile"
        elif result.risk_score >= 60:
            return "TRADE WITH CAUTION - Medium risk"
        elif result.risk_score >= 40:
            return "HIGH RISK - Trade small or avoid"
        else:
            return "DANGEROUS - Avoid trading"

    def _get_token_type(self, result: TokenSecurityResult) -> str:
        """Determine the token type based on available data"""
        token_type = []
        
        # Check if it's a meme token based on name keywords
        meme_keywords = ['pepe', 'doge', 'shib', 'inu', 'elon', 'moon', 'safe', 'baby', 'chad', 'wojak']
        if any(keyword in result.name.lower() or keyword in result.symbol.lower() for keyword in meme_keywords):
            token_type.append("Meme Token")
        
        # Check if it's a gaming token
        gaming_keywords = ['play', 'game', 'nft', 'meta', 'verse', 'world', 'land', 'quest']
        if any(keyword in result.name.lower() or keyword in result.symbol.lower() for keyword in gaming_keywords):
            token_type.append("Gaming Token")
            
        # Check if it's a DeFi token
        defi_keywords = ['swap', 'yield', 'dao', 'finance', 'defi', 'dex', 'stable', 'lp', 'amm']
        if any(keyword in result.name.lower() or keyword in result.symbol.lower() for keyword in defi_keywords):
            token_type.append("DeFi Token")
            
        # Check if it's a Fan/Social token
        social_keywords = ['fan', 'social', 'community', 'dao', 'gov']
        if any(keyword in result.name.lower() or keyword in result.symbol.lower() for keyword in social_keywords):
            token_type.append("Social Token")

        # If no specific type is identified, mark as Utility Token
        if not token_type:
            token_type.append("Utility Token")
            
        return " & ".join(token_type)

    def _format_number(self, num: float) -> str:
        """Format large numbers to readable format with K, M, B suffixes"""
        if num is None or num == 0:
            return "$0.00"
            
        abs_num = abs(num)
        if abs_num >= 1_000_000_000:  # Billions
            return f"${num / 1_000_000_000:.2f}B"
        elif abs_num >= 1_000_000:  # Millions
            return f"${num / 1_000_000:.2f}M"
        elif abs_num >= 1_000:  # Thousands
            return f"${num / 1_000:.2f}K"
        else:
            return f"${num:.2f}"

    async def check_token(self, token_address: str) -> TokenSecurityResult:
        """Performs comprehensive security analysis of a Solana token"""
        try:
            result = TokenSecurityResult()
            
            # Get token metadata first
            token_metadata = await self._get_token_metadata(token_address)
            if token_metadata:
                result.token_decimals = token_metadata.get('decimals', 0)
                
            # Get data from DexScreener
            dex_data = await self._get_dexscreener_data(token_address)
            if not dex_data:
                raise ValueError(
                    "Token Analysis Failed\n\n"
                    "Unable to fetch token data. Possible reasons:\n"
                    "• Token is not actively trading\n"
                    "• Token has no liquidity\n"
                    "• Token address is incorrect\n"
                    "• Token is too new\n\n"
                    "Try again later or check the token address."
                )
            
            # First try Solana RPC for holder count (most accurate)
            result.total_holders = await self._get_solana_token_holders(token_address)
            if result.total_holders > 0:
                logger.info(f"Using holder count from Solana RPC: {result.total_holders}")
                
            # If Solana RPC fails, try Birdeye as backup
            if result.total_holders == 0:
                birdeye_data = await self._get_birdeye_data(token_address)
                if birdeye_data:
                    try:
                        result.total_holders = int(birdeye_data.get('holder', 0))
                        logger.info(f"Using holder count from Birdeye backup: {result.total_holders}")
                    except (ValueError, TypeError):
                        logger.warning("Failed to get holder count from both Solana RPC and Birdeye")
        
            # Process DexScreener data
            if not dex_data or not dex_data.get('pairs'):
                raise ValueError(
                    "Token Analysis Failed\n\n"
                    "Token not found or not actively trading. Possible reasons:\n"
                    "• Token is not listed on any DEX\n"
                    "• Token has no liquidity\n"
                    "• Token address is incorrect\n"
                    "• Token is not trading on a supported DEX."
                )

            await self._process_dexscreener_data(result, dex_data)
            
            # Calculate risk score
            self._calculate_risk_score(result)
            return result
                
        except ValueError as e:
            logger.warning(str(e))
            raise
        except Exception as e:
            logger.error(f"Error in check_token: {str(e)}", exc_info=True)
            raise ValueError(
                "Token Analysis Failed\n\n"
                "An unexpected error occurred. Please:\n"
                "• Verify the token address\n"
                "• Check if token is actively trading\n"
                "• Try again in a few minutes\n\n"
            )
