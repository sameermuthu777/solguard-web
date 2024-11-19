// Initialize Telegram WebApp
document.addEventListener('DOMContentLoaded', function() {
    let tg = window.Telegram.WebApp;
    tg.expand();
    tg.ready();
    tg.MainButton.hide();
});

// Format number with commas and decimals
function formatNumber(num, decimals = 2) {
    if (typeof num !== 'number') return '0';
    return num.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

// Format currency
function formatCurrency(amount) {
    return `$${formatNumber(amount)}`;
}

// Update security score circle
function updateSecurityScore(score) {
    const scoreElement = document.getElementById('securityScore');
    const scoreCircle = document.querySelector('.score-circle');
    const percentage = (score / 100) * 360;
    
    scoreElement.textContent = Math.round(score);
    scoreCircle.style.setProperty('--score', `${percentage}deg`);
    
    // Update color based on score
    let color;
    if (score >= 80) {
        color = 'var(--success-color)';
    } else if (score >= 50) {
        color = 'var(--warning-color)';
    } else {
        color = 'var(--danger-color)';
    }
    
    scoreCircle.style.background = `conic-gradient(${color} ${percentage}deg, transparent 0)`;
}

// Create risk factor element
function createRiskFactor(risk) {
    const riskElement = document.createElement('div');
    riskElement.className = 'risk-item';
    riskElement.innerHTML = `
        <span class="risk-icon">⚠️</span>
        <div class="risk-details">
            <div class="risk-title">${risk.title}</div>
            <div class="risk-description">${risk.description}</div>
        </div>
    `;
    return riskElement;
}

// Create verification link button
function createLinkButton(type, url) {
    const button = document.createElement('a');
    button.href = url;
    button.target = '_blank';
    button.className = 'link-button';
    
    const icons = {
        x: '𝕏',
        telegram: '📱',
        website: '🌐',
        github: '💻',
        discord: '💬'
    };
    
    button.innerHTML = `${icons[type] || '🔗'} ${type.charAt(0).toUpperCase() + type.slice(1)}`;
    return button;
}

// Update UI with token data
function updateUI(data) {
    // Update token info
    document.getElementById('tokenName').textContent = `${data.token_info.name} (${data.token_info.symbol})`;
    document.getElementById('tokenAddress').textContent = data.token_info.mint;
    
    // Update security score
    updateSecurityScore(data.security.security_score);
    
    // Update risk factors
    const riskFactorsContainer = document.getElementById('riskFactors');
    riskFactorsContainer.innerHTML = '';
    
    if (data.security.risks && data.security.risks.length > 0) {
        data.security.risks.forEach(risk => {
            riskFactorsContainer.appendChild(createRiskFactor(risk));
        });
    }
    
    // Update market data
    document.getElementById('totalLiquidity').textContent = formatCurrency(data.market_data.total_liquidity);
    document.getElementById('lpProviders').textContent = data.market_data.lp_providers;
    document.getElementById('totalSupply').textContent = formatNumber(data.token_info.supply, 0);
    
    // Update verification links
    const verificationLinksContainer = document.getElementById('verificationLinks');
    verificationLinksContainer.innerHTML = '';
    
    if (data.verification.links) {
        Object.entries(data.verification.links).forEach(([type, url]) => {
            verificationLinksContainer.appendChild(createLinkButton(type, url));
        });
    }
    
    // Update community votes
    document.getElementById('upvotes').textContent = data.community.upvotes;
    document.getElementById('downvotes').textContent = data.community.downvotes;
    
    // Show results and hide loading
    document.getElementById('loadingView').style.display = 'none';
    document.getElementById('resultsView').style.display = 'block';
}

// Handle errors
function handleError(error) {
    console.error('Error:', error);
    document.getElementById('loadingView').innerHTML = `
        <div class="error-message">
            <h2>⚠️ Error</h2>
            <p>${error.message || 'Failed to analyze token. Please try again.'}</p>
        </div>
    `;
}

// Initialize with data from URL parameters
function init() {
    const urlParams = new URLSearchParams(window.location.search);
    const tokenData = urlParams.get('data');
    
    if (tokenData) {
        try {
            const data = JSON.parse(decodeURIComponent(tokenData));
            updateUI(data);
        } catch (error) {
            handleError(error);
        }
    } else {
        handleError(new Error('No token data provided'));
    }
}

// Start initialization when DOM is ready
document.addEventListener('DOMContentLoaded', init);
