// Initialize Telegram WebApp
const webapp = window.Telegram?.WebApp;
if (webapp) {
    webapp.ready();
    webapp.expand();
    // Add back button functionality
    webapp.BackButton.show();
    webapp.BackButton.onClick(() => {
        webapp.navigate('index.html');
    });
}

// Get token address from URL parameters
const urlParams = new URLSearchParams(window.location.search);
const tokenAddress = urlParams.get('address');

async function fetchTokenData(address) {
    try {
        // Fetch data from Rugcheck API
        const response = await fetch(`https://api.rugcheck.xyz/v1/tokens/${address}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error fetching token data:', error);
        return null;
    }
}

function updateRiskScore(score) {
    const riskScoreElement = document.getElementById('riskScore');
    let riskClass = 'score-low';
    let riskText = 'Low Risk';
    
    if (score >= 70) {
        riskClass = 'score-high';
        riskText = 'High Risk';
    } else if (score >= 30) {
        riskClass = 'score-medium';
        riskText = 'Medium Risk';
    }
    
    riskScoreElement.className = `risk-score ${riskClass}`;
    riskScoreElement.textContent = `Risk Score: ${score} - ${riskText}`;
}

function createRiskItem(icon, title, description) {
    return `
        <div class="risk-item">
            <div class="risk-icon">${icon}</div>
            <div class="risk-details">
                <h4 class="risk-title">${title}</h4>
                <p class="risk-description">${description}</p>
            </div>
        </div>
    `;
}

function displayResults() {
    try {
        // Get data from sessionStorage
        const data = JSON.parse(sessionStorage.getItem('tokenData'));
        if (!data) {
            throw new Error('No token data found');
        }

        // Hide loading view and show results
        document.getElementById('loadingView').style.display = 'none';
        document.getElementById('resultsView').style.display = 'block';
        
        // Update token info
        const tokenInfo = data.token_info;
        document.getElementById('tokenName').textContent = tokenInfo.name || 'Unknown Token';
        document.getElementById('tokenAddress').textContent = tokenInfo.address;
        
        // Update risk score
        const riskScore = data.risk_analysis.score;
        updateRiskScore(riskScore ? parseInt(riskScore) : 0);
        
        // Update security analysis
        const securityResults = document.getElementById('securityResults');
        securityResults.innerHTML = '';
        
        if (data.security_checks) {
            data.security_checks.forEach(check => {
                const icon = check.status === 'passed' ? '✅' : '⚠️';
                securityResults.innerHTML += createRiskItem(
                    icon,
                    check.title,
                    check.description
                );
            });
        }
        
        // Update contract analysis
        const contractResults = document.getElementById('contractResults');
        contractResults.innerHTML = '';
        
        if (data.contract_analysis) {
            data.contract_analysis.forEach(item => {
                const icon = item.risk_level === 'high' ? '🔴' : 
                           item.risk_level === 'medium' ? '🟡' : '🟢';
                contractResults.innerHTML += createRiskItem(
                    icon,
                    item.title,
                    item.details
                );
            });
        }
    } catch (error) {
        console.error('Error:', error);
        document.body.innerHTML = '<div class="error">Failed to load token analysis results</div>';
    }
}

async function init() {
    if (!tokenAddress) {
        document.body.innerHTML = '<div class="error">No token address provided</div>';
        return;
    }
    
    try {
        const data = await fetchTokenData(tokenAddress);
        if (data) {
            sessionStorage.setItem('tokenData', JSON.stringify(data));
            displayResults();
        } else {
            document.body.innerHTML = '<div class="error">Failed to load token data</div>';
        }
    } catch (error) {
        console.error('Error:', error);
        document.body.innerHTML = '<div class="error">An error occurred while analyzing the token</div>';
    }
}

if (!tokenAddress) {
    document.body.innerHTML = '<div class="error">No token address provided</div>';
} else {
    displayResults();
}
