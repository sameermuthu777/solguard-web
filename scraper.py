import os
import re
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScraperException(Exception):
    """Custom exception for scraper errors"""
    pass

class TokenReport:
    def __init__(self, data: dict):
        self.mint = data.get('mint')
        self.name = data.get('tokenMeta', {}).get('name')
        self.symbol = data.get('tokenMeta', {}).get('symbol')
        self.supply = float(data.get('token', {}).get('supply', 0)) / 10 ** data.get('token', {}).get('decimals', 9)
        self.total_liquidity = data.get('totalMarketLiquidity', 0)
        self.lp_providers = data.get('totalLPProviders', 0)
        self.is_rugged = data.get('rugged', False)
        self.transfer_fee = data.get('transferFee', {}).get('pct', 0)
        self.risks = data.get('risks', [])
        self.score = data.get('score', 0)
        self.markets = self._process_markets(data.get('markets', []))
        self.verification = self._process_verification(data.get('verification', {}))
        
    def _process_markets(self, markets: list) -> list:
        processed = []
        for market in markets:
            processed.append({
                'type': market.get('marketType'),
                'base_mint': market.get('mintA'),
                'quote_mint': market.get('mintB'),
                'liquidity_usd': market.get('lp', {}).get('quoteUSD', 0) + market.get('lp', {}).get('baseUSD', 0)
            })
        return processed
        
    def _process_verification(self, verification: dict) -> dict:
        return {
            'is_verified': verification.get('jup_verified', False),
            'links': {link['provider']: link['value'] for link in verification.get('links', [])}
        }
        
    def get_security_score(self) -> float:
        """Calculate a security score based on various factors"""
        score = 100.0  # Start with perfect score
        
        # Deduct for low liquidity
        if self.total_liquidity < 10000:  # Less than $10k
            score -= 30
        elif self.total_liquidity < 50000:  # Less than $50k
            score -= 15
            
        # Deduct for low LP providers
        if self.lp_providers < 3:
            score -= 20
        elif self.lp_providers < 10:
            score -= 10
            
        # Automatic fail conditions
        if self.is_rugged:
            return 0
        if self.transfer_fee > 0:
            score -= 40
            
        # Deduct for each risk factor
        score -= len(self.risks) * 15
        
        # Bonus for verification
        if self.verification['is_verified']:
            score += 10
            
        return max(0, min(score, 100))  # Ensure score is between 0 and 100

    def to_dict(self) -> dict:
        """Convert report to a structured dictionary"""
        return {
            'token_info': {
                'mint': self.mint,
                'name': self.name,
                'symbol': self.symbol,
                'supply': self.supply
            },
            'market_data': {
                'total_liquidity': self.total_liquidity,
                'lp_providers': self.lp_providers,
                'markets': self.markets
            },
            'security': {
                'is_rugged': self.is_rugged,
                'transfer_fee': self.transfer_fee,
                'risks': self.risks,
                'score': self.score,
                'security_score': self.get_security_score()
            },
            'verification': self.verification
        }

class RugcheckScraper:
    def __init__(self):
        self.base_url = "https://api.rugcheck.xyz/v1"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Origin': 'https://rugcheck.xyz',
            'Referer': 'https://rugcheck.xyz/'
        }

    async def _fetch_token_report(self, token_address: str) -> dict:
        """Fetch token report from Rugcheck API"""
        url = f"{self.base_url}/tokens/{token_address}/report"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def _fetch_token_votes(self, token_address: str) -> dict:
        """Fetch token votes from Rugcheck API"""
        url = f"{self.base_url}/tokens/{token_address}/votes"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def analyze_token(self, token_address: str) -> dict:
        """Analyze a token using Rugcheck API"""
        try:
            report_data = await self._fetch_token_report(token_address)
            votes_data = await self._fetch_token_votes(token_address)
            
            # Process the data through our TokenReport class
            token_report = TokenReport(report_data)
            
            # Add voting data
            analysis = token_report.to_dict()
            analysis['community'] = {
                'upvotes': votes_data.get('up', 0),
                'downvotes': votes_data.get('down', 0)
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing token {token_address}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to analyze token: {str(e)}"
            )

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/analyze/{token_address}")
async def analyze_token(token_address: str):
    """Analyze a token by scraping Rugcheck"""
    scraper = RugcheckScraper()
    return await scraper.analyze_token(token_address)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to the Rugcheck Scraper API"}

@app.get("/health")
async def health_check():
    """Health check endpoint to verify service is running"""
    return {"status": "ok"}

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom exception handler for HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler for all other exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting scraper server on port 8001")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
