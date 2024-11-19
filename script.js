// Initialize Telegram WebApp
const webapp = window.Telegram?.WebApp;
if (webapp) {
    webapp.ready();
    webapp.expand();
}

// API Configuration
const API_BASE_URL = window.location.hostname === 'localhost' 
    ? 'http://localhost:8000'
    : window.location.protocol + '//' + window.location.hostname + ':8000'; // Replace with your actual deployed API URL
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
            console.error('Health check failed');
            throw new Error('Analysis service is currently unavailable. Please try again later.');
        }

        console.log('Analyzing token:', tokenAddress);
        console.log('API URL:', `${API_BASE_URL}/api/analyze/${tokenAddress}`);

        // Call the analysis endpoint
        const response = await fetchWithTimeout(`${API_BASE_URL}/api/analyze/${tokenAddress}`);
        const contentType = response.headers.get('content-type');
        
        console.log('Response status:', response.status);
        console.log('Content type:', contentType);

        if (!response.ok) {
            let errorMessage = 'Failed to analyze token';
            let errorDetails = '';
            
            if (contentType && contentType.includes('application/json')) {
                const errorData = await response.json();
                console.error('Error data:', errorData);
                errorMessage = errorData.detail || errorMessage;
            } else {
                const textError = await response.text();
                console.error('Error response:', textError);
                errorDetails = 'Server returned an unexpected response';
            }
            
            throw new Error(`${errorMessage}${errorDetails ? ': ' + errorDetails : ''}`);
        }

        if (!contentType || !contentType.includes('application/json')) {
            const textResponse = await response.text();
            console.error('Invalid content type. Response:', textResponse);
            throw new Error('Invalid response from server: Unexpected content type');
        }

        const data = await response.json();
        console.log('Scraped data:', data);

        // Validate response data
        if (!data || typeof data !== 'object') {
            throw new Error('Invalid data received from server');
        }

        // Store the data and navigate
        sessionStorage.setItem('tokenData', JSON.stringify(data));
        const resultsUrl = `results.html?address=${encodeURIComponent(tokenAddress)}`;
        
        if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.navigate(resultsUrl);
        } else {
            window.location.href = resultsUrl;
        }
    } catch (error) {
        console.error('Error:', error);
        if (error.name === 'AbortError') {
            showError('Request timeout', 'The analysis is taking too long. Please try again.');
        } else if (error.message === 'Failed to fetch' || error.message.includes('NetworkError')) {
            showError(
                'Connection error', 
                `Cannot connect to the analysis service at ${API_BASE_URL}. Please check your connection and try again.`
            );
        } else if (error.message.includes('currently unavailable')) {
            showError(
                'Service unavailable',
                'The analysis service is currently down for maintenance. Please try again in a few minutes.'
            );
        } else {
            showError(
                'Analysis failed',
                `Error: ${error.message}\nPlease try again or contact support if the issue persists.`
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
