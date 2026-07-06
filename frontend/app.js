// State & LocalStorage Keys
const API_URL_KEY = 'daily_inspire_api_url';
const AUTH_TOKEN_KEY = 'daily_inspire_auth_token';

// Default values
const DEFAULT_API_URL = 'http://localhost:8000';

// DOM Elements
const apiInput = document.getElementById('api-url');
const tokenInput = document.getElementById('auth-token');
const settingsContent = document.getElementById('settings-content');
const storiesCountEl = document.getElementById('stories-count');
const subsCountEl = document.getElementById('subs-count');
const storiesList = document.getElementById('stories-list');
const storiesSpinner = document.getElementById('stories-spinner');
const subscribeForm = document.getElementById('subscribe-form');
const emailInput = document.getElementById('email');
const successAlert = document.getElementById('success-alert');
const errorAlert = document.getElementById('error-alert');
const btnSubmit = document.getElementById('btn-submit');
const storyDialog = document.getElementById('story-dialog');

// Load settings from LocalStorage
function loadSettings() {
    const savedUrl = localStorage.getItem(API_URL_KEY);
    const savedToken = localStorage.getItem(AUTH_TOKEN_KEY);
    
    apiInput.value = savedUrl || DEFAULT_API_URL;
    tokenInput.value = savedToken || '';
}

// Get API Request Headers
function getRequestHeaders(includeJson = false) {
    const headers = {};
    if (includeJson) {
        headers['Content-Type'] = 'application/json';
    }
    
    const token = tokenInput.value.trim();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

// Save Settings to LocalStorage
function saveSettings() {
    const url = apiInput.value.trim();
    const token = tokenInput.value.trim();
    
    localStorage.setItem(API_URL_KEY, url);
    localStorage.setItem(AUTH_TOKEN_KEY, token);
    
    // Refresh feed and stats
    fetchStats();
    fetchStories();
    
    alert('Settings saved successfully!');
}

// Toggle Settings Panel Visibility
function toggleSettings() {
    if (settingsContent.style.display === 'none') {
        settingsContent.style.display = 'flex';
    } else {
        settingsContent.style.display = 'none';
    }
}

// Fetch Stats from API
async function fetchStats() {
    const baseUrl = apiInput.value.trim();
    try {
        const res = await fetch(`${baseUrl}/api/stats`, {
            headers: getRequestHeaders()
        });
        if (res.ok) {
            const stats = await res.json();
            storiesCountEl.textContent = stats.stories_count;
            subsCountEl.textContent = stats.subscribers_count;
        }
    } catch (err) {
        console.warn("Could not load stats:", err);
    }
}

// Fetch Stories from API
async function fetchStories() {
    const baseUrl = apiInput.value.trim();
    storiesSpinner.style.display = 'block';
    storiesList.innerHTML = '';
    
    try {
        const res = await fetch(`${baseUrl}/api/stories`, {
            headers: getRequestHeaders()
        });
        storiesSpinner.style.display = 'none';
        
        if (res.ok) {
            const stories = await res.json();
            if (!stories || stories.length === 0) {
                storiesList.innerHTML = `
                    <div class="empty-state">
                        <h3>No stories generated yet</h3>
                        <p>Stories will appear here once the scheduled agent runs and publishes them.</p>
                    </div>
                `;
            } else {
                stories.forEach(story => {
                    const dateStr = story.date_sent || 'Recently';
                    const card = document.createElement('div');
                    card.className = 'story-card';
                    card.innerHTML = `
                        <div class="card-meta">
                            <span>🌟 Topic: ${story.topic || 'Motivation'}</span>
                            <span>📅 ${dateStr}</span>
                        </div>
                        <h3 class="card-title">${escapeHtml(story.title)}</h3>
                        <div class="card-moral">💡 Moral: ${escapeHtml(story.moral)}</div>
                        <button class="btn-read" onclick="openStory('${escapeHtml(story.title)}', '${escapeHtml(story.content)}', '${escapeHtml(story.moral)}')">
                            Read Full Story
                        </button>
                    `;
                    storiesList.appendChild(card);
                });
            }
        } else {
            storiesList.innerHTML = '<div class="alert alert-error" style="display:block">Failed to load stories from the backend API.</div>';
        }
    } catch (err) {
        storiesSpinner.style.display = 'none';
        storiesList.innerHTML = `
            <div class="alert alert-error" style="display:block">
                Could not connect to API server at ${baseUrl}.<br>
                Please check if the backend is running and CORS is enabled, or update the API URL in Settings.
            </div>`;
    }
}

// Escape HTML Utility
function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;")
        .replace(/\\n/g, "\n");
}

// Open Story Dialog
function openStory(title, content, moral) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-content').innerHTML = content.replace(/\\n/g, '<br><br>').replace(/\n/g, '<br><br>');
    document.getElementById('modal-moral').innerHTML = `💡 <strong>Moral:</strong> ${moral}`;
    storyDialog.showModal();
}

// Close Story Dialog
function closeStory() {
    storyDialog.close();
}

// Handle Subscription form
subscribeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    successAlert.style.display = 'none';
    errorAlert.style.display = 'none';
    btnSubmit.disabled = true;
    btnSubmit.textContent = 'Subscribing...';
    
    const email = emailInput.value.trim();
    const baseUrl = apiInput.value.trim();
    
    try {
        const res = await fetch(`${baseUrl}/api/subscribe`, {
            method: 'POST',
            headers: getRequestHeaders(true),
            body: JSON.stringify({ email })
        });
        
        btnSubmit.disabled = false;
        btnSubmit.textContent = 'Subscribe Now';
        
        if (res.ok) {
            const data = await res.json();
            if (data.status === 'success' || data.status === 'already_subscribed') {
                successAlert.textContent = data.message;
                successAlert.style.display = 'block';
                emailInput.value = '';
                fetchStats();
            } else {
                errorAlert.textContent = data.message || 'Failed to subscribe.';
                errorAlert.style.display = 'block';
            }
        } else {
            const data = await res.json();
            errorAlert.textContent = data.detail || 'API returned an error. Check your connection or auth token.';
            errorAlert.style.display = 'block';
        }
    } catch (err) {
        btnSubmit.disabled = false;
        btnSubmit.textContent = 'Subscribe Now';
        errorAlert.textContent = 'Could not connect to the API server.';
        errorAlert.style.display = 'block';
    }
});

// Initialization
loadSettings();
fetchStats();
fetchStories();
