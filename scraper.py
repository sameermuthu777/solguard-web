from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from bs4 import BeautifulSoup
import httpx
import json
from typing import Dict, Any
import logging
import asyncio
from datetime import datetime
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global httpx client with custom configuration
async def get_client():
    return httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    )

@app.get("/health")
async def health_check():
    """Health check endpoint to verify service is running"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom exception handler for HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail)}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler for all other exceptions"""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again later."}
    )

def validate_token_address(token_address: str) -> bool:
    """Validate Solana token address format"""
    if not token_address:
        return False
    if len(token_address) < 32 or len(token_address) > 44:
        return False
    return bool(re.match("^[1-9A-HJ-NP-Za-km-z]{32,44}$", token_address))

async def scrape_rugcheck(token_address: str) -> Dict[str, Any]:
    """Scrape token information from Rugcheck"""
    if not validate_token_address(token_address):
        raise HTTPException(status_code=400, detail="Invalid token address format")

    url = f"https://rugcheck.xyz/tokens/{token_address}"
    logger.info(f"Scraping data for token: {token_address}")
    
    async with await get_client() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            logger.info(f"Successfully fetched webpage for token {token_address}")
            
            if "text/html" not in response.headers.get("content-type", ""):
                raise HTTPException(status_code=500, detail="Invalid response from Rugcheck")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check if the page indicates the token doesn't exist
            error_msg = soup.find(string=lambda text: text and "token not found" in text.lower())
            if error_msg:
                raise HTTPException(status_code=404, detail="Token not found on Rugcheck")
            
            # Initialize data structure
            data = {
                "token_info": {},
                "risk_analysis": {},
                "security_checks": [],
                "contract_analysis": []
            }
            
            try:
                # Extract token info with more flexible selectors
                token_name = soup.find(['h1', 'div'], string=lambda text: text and ('Token Analysis' in text or token_address in text))
                if token_name:
                    name_text = token_name.text.replace('Token Analysis:', '').strip()
                    data["token_info"] = {
                        "name": name_text if name_text else "Unknown Token",
                        "address": token_address
                    }
                else:
                    raise HTTPException(status_code=500, detail="Failed to extract token information")
                
                # Extract risk score with multiple fallback patterns
                risk_patterns = [
                    lambda s: s.find(['div', 'span'], class_=lambda x: x and 'risk' in x.lower()),
                    lambda s: s.find(string=lambda text: text and 'risk score' in text.lower()),
                    lambda s: s.find(['div', 'span'], string=lambda text: text and 'risk' in text.lower())
                ]
                
                risk_score = None
                for pattern in risk_patterns:
                    risk_score = pattern(soup)
                    if risk_score:
                        data["risk_analysis"]["score"] = risk_score.text.strip()
                        break
                
                if not risk_score:
                    logger.warning(f"Could not find risk score for token {token_address}")
                    data["risk_analysis"]["score"] = "Unknown"
                
                # Extract security checks with more flexible selectors
                security_sections = soup.find_all(
                    ['div', 'section'], 
                    class_=lambda x: x and ('security' in str(x).lower() or 'check' in str(x).lower())
                )
                
                for section in security_sections:
                    title = section.find(['h2', 'h3', 'h4', 'div'], class_=lambda x: x and 'title' in str(x).lower())
                    description = section.find(['p', 'div'], class_=lambda x: x and 'description' in str(x).lower())
                    
                    if title:
                        check_data = {
                            "title": title.text.strip(),
                            "status": "passed" if any(c for c in section.get('class', []) if 'pass' in c.lower()) else "failed",
                            "description": description.text.strip() if description else ""
                        }
                        data["security_checks"].append(check_data)
                
                # Extract contract analysis with fallback patterns
                analysis_sections = soup.find_all(
                    ['div', 'section'], 
                    class_=lambda x: x and 'analysis' in str(x).lower()
                )
                
                for section in analysis_sections:
                    title = section.find(['h2', 'h3', 'h4', 'div'])
                    details = section.find(['p', 'div'])
                    
                    if title and details:
                        item_data = {
                            "title": title.text.strip(),
                            "details": details.text.strip(),
                            "risk_level": "high" if "high" in str(section).lower() else 
                                        "medium" if "medium" in str(section).lower() else "low"
                        }
                        data["contract_analysis"].append(item_data)
                
                if not any([data["security_checks"], data["contract_analysis"]]):
                    logger.warning(f"No security checks or contract analysis found for token {token_address}")
                
                logger.info(f"Successfully parsed data for token {token_address}")
                return data
                
            except Exception as parse_error:
                logger.error(f"Error parsing HTML for token {token_address}: {str(parse_error)}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to parse token information. Please try again later."
                )
            
        except httpx.HTTPStatusError as http_error:
            logger.error(f"HTTP error for token {token_address}: {str(http_error)}")
            if http_error.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Token not found")
            raise HTTPException(
                status_code=500,
                detail="Failed to fetch token data from Rugcheck"
            )
        except httpx.RequestError as request_error:
            logger.error(f"Request error for token {token_address}: {str(request_error)}")
            raise HTTPException(
                status_code=503,
                detail="Failed to connect to Rugcheck. Please try again later."
            )
        except Exception as e:
            logger.error(f"Unexpected error for token {token_address}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred. Please try again later."
            )

@app.get("/api/analyze/{token_address}")
async def analyze_token(token_address: str):
    """Analyze a token by scraping Rugcheck"""
    try:
        data = await scrape_rugcheck(token_address)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analyze_token: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to analyze token. Please try again later."
        )

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting scraper server on port 8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
