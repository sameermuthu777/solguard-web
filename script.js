// Initialize Telegram WebApp
const webapp = window.Telegram?.WebApp;
if (webapp) {
    webapp.ready();
    webapp.expand();
}

// API Configuration
const API_BASE_URL = window.location.hostname === 'localhost' 
    ? 'http://localhost:8000'
    : `${window.location.protocol}//${window.location.hostname}:8000`; // Replace with your actual deployed API URL
const API_TIMEOUT = 30000; // 30 seconds

function showLoading() {
    const button = document.getElementById('scanButton');
    button.classList.add('loading');
    button.disabled = true;
    button.innerHTML = '<div class="spinner"></div> Scanning...';
    hideError();
}

function hideLoading() {
    const button = document.getElementById('scanButton');
    button.classList.remove('loading');
    button.disabled = false;
    button.innerHTML = 'Scan Token';
}

function showError(message, details = '') {
    const errorDiv = document.getElementById('error');
    errorDiv.innerHTML = `<strong>${message}</strong>${details ? `<br><small>${details}</small>` : ''}`;
    errorDiv.style.display = 'block';
    hideLoading();
}

function hideError() {
    const errorDiv = document.getElementById('error');
    errorDiv.style.display = 'none';
}

function isValidSolanaAddress(address) {
    if (!address) return false;
    if (address.length < 32 || address.length > 44) return false;
    return address.match(/^[1-9A-HJ-NP-Za-km-z]{32,44}$/);
}

async function fetchWithTimeout(url, options = {}) {
    const controller = new AbortController();
    const timeout = options.timeout || API_TIMEOUT;
    const id = setTimeout(() => controller.abort(), timeout);

    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal,
            mode: 'cors',
            headers: {
                'Accept': 'application/json',
                ...options.headers
            }
        });
        clearTimeout(id);
        return response;
    } catch (error) {
        clearTimeout(id);
        throw error;
    }
}

async function checkServiceHealth() {
    try {
        const response = await fetchWithTimeout(`${API_BASE_URL}/health`, {
            timeout: 5000 // Shorter timeout for health check
        });
        return response.ok;
    } catch (error) {
        console.error('Health check failed:', error);
        return false;
    }
}

async function fetchTokenData(address) {
    try {
        // Fetch data from Rugcheck API
        const response = await fetch(`${API_BASE_URL}/analyze/${address}`, {
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

async function scanToken() {
    hideError();
    const tokenInput = document.getElementById('tokenAddress');
    const tokenAddress = tokenInput.value.trim();

    // Input validation
    if (!tokenAddress) {
        showError('Please enter a token address');
        return;
    }

    if (!isValidSolanaAddress(tokenAddress)) {
        showError('Invalid Solana token address', 'Please enter a valid Solana token address (32-44 characters)');
        return;
    }

    showLoading();

    try {
        // Check if service is available
        const isHealthy = await checkServiceHealth();
        if (!isHealthy) {
            throw new Error('Service unavailable');
        }

        // Call the analysis endpoint
        const response = await fetchWithTimeout(`${API_BASE_URL}/analyze/${tokenAddress}`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to analyze token');
        }

        const data = await response.json();
        
        // Store the data and navigate
        sessionStorage.setItem('tokenData', JSON.stringify(data));
        window.location.href = `results.html?address=${encodeURIComponent(tokenAddress)}`;
        
    } catch (error) {
        console.error('Error:', error);
        if (error.message === 'Service unavailable') {
            showError(
                'Service unavailable',
                'The analysis service is currently down for maintenance. Please try again in a few minutes.'
            );
        } else {
            showError(
                'Analysis failed',
                error.message || 'An unexpected error occurred. Please try again.'
            );
        }
    } finally {
        hideLoading();
    }
}

// Event Listeners
document.getElementById('tokenAddress').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        scanToken();
    }
});

document.getElementById('tokenAddress').addEventListener('input', function(e) {
    const value = e.target.value.trim();
    if (value && !isValidSolanaAddress(value)) {
        e.target.classList.add('invalid');
    } else {
        e.target.classList.remove('invalid');
    }
    hideError();
});
