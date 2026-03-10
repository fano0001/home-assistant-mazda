/**
 * Mazda OAuth Helper - Background Service Worker
 *
 * This extension intercepts Mazda mobile OAuth redirects and extracts the
 * authorization code. Two redirect URI schemes are handled:
 *   - msauth.com.mazdausa.mazdaiphone://auth  (iOS / MazdaUSA app)
 *   - msauth://com.interrait.mymazda           (Android / MyMazda app)
 *
 * If the state parameter is a JWT containing a flow_id, it automatically
 * redirects to Home Assistant's OAuth endpoint.
 */

const MAZDA_REDIRECT_PREFIXES = [
  "msauth.com.mazdausa.mazdaiphone://auth",
  "msauth://com.interrait.mymazda",
];

function isMazdaRedirect(url) {
  return MAZDA_REDIRECT_PREFIXES.some((prefix) => url.startsWith(prefix));
}

// Check if state is a JWT with flow_id (for Home Assistant)
function isHomeAssistantFlow(state) {
  if (!state) return false;
  try {
    // JWT has 3 parts separated by dots
    const parts = state.split(".");
    if (parts.length !== 3) return false;

    // Decode the payload (middle part)
    // JWT uses base64url encoding, need to convert to standard base64
    let base64 = parts[1]
      .replace(/-/g, '+')
      .replace(/_/g, '/');
    
    // Add padding if needed
    const remainder = base64.length % 4;
    if (remainder > 0) {
      base64 += '='.repeat(4 - remainder);
    }
    
    console.log('Decoding JWT payload:', base64);
    const payload = JSON.parse(atob(base64));
    console.log('Decoded payload:', payload);
    
    const isHA = payload && typeof payload.flow_id === "string" && payload.flow_id.length > 0;
    console.log('Is Home Assistant flow?', isHA);
    return isHA;
  } catch (e) {
    console.error('Error checking if Home Assistant flow:', e);
    return false;
  }
}

// Track processed URLs to avoid duplicate handling
const processedUrls = new Set();

// Function to handle Mazda redirect
function handleMazdaRedirect(url, tabId, source = 'unknown') {
  // Prevent duplicate processing
  const urlKey = `${tabId}-${url}`;
  if (processedUrls.has(urlKey)) {
    console.log(`[${source}] Already processed:`, url);
    return;
  }
  processedUrls.add(urlKey);
  
  // Clean up old entries after 5 seconds
  setTimeout(() => processedUrls.delete(urlKey), 5000);

  console.log(`[${source}] Handling Mazda redirect:`, url);

  try {
    // Parse the URL to extract the authorization code
    const urlObj = new URL(url);
    const code = urlObj.searchParams.get("code");
    const state = urlObj.searchParams.get("state");

    // Check if this is a Home Assistant flow
    if (code && isHomeAssistantFlow(state)) {
      // Redirect to Home Assistant OAuth endpoint
      const haUrl = new URL("https://my.home-assistant.io/redirect/oauth");
      haUrl.searchParams.set("code", code);
      haUrl.searchParams.set("state", state);

      console.log(`[${source}] Redirecting to Home Assistant`);
      chrome.tabs.update(tabId, { url: haUrl.toString() });
      return;
    }

    // Otherwise, show capture page
    const captureUrl = new URL(chrome.runtime.getURL("capture.html"));
    captureUrl.searchParams.set("code", code || "");
    captureUrl.searchParams.set("state", state || "");
    captureUrl.searchParams.set(
      "error",
      urlObj.searchParams.get("error") || "",
    );
    captureUrl.searchParams.set(
      "error_description",
      urlObj.searchParams.get("error_description") || "",
    );

    if (code) {
      chrome.action.setBadgeText({ text: "✓" });
      chrome.action.setBadgeBackgroundColor({ color: "#4CAF50" });
    }

    console.log(`[${source}] Redirecting to capture page`);
    chrome.tabs.update(tabId, { url: captureUrl.toString() });
  } catch (error) {
    console.error(`[${source}] Error handling Mazda redirect:`, error);
  }
}

// Listen for navigation events that would redirect to a Mazda OAuth URI
chrome.webNavigation.onBeforeNavigate.addListener(
  async (details) => {
    if (isMazdaRedirect(details.url)) {
      handleMazdaRedirect(details.url, details.tabId, 'onBeforeNavigate');
    }
  },
  {
    url: [
      { urlPrefix: "msauth.com.mazdausa.mazdaiphone://auth" },
      { urlPrefix: "msauth://com.interrait.mymazda" },
    ],
  }
);

// Also listen for errors when Safari can't handle a Mazda OAuth URI
chrome.webNavigation.onErrorOccurred.addListener(
  async (details) => {
    if (details.url && isMazdaRedirect(details.url)) {
      handleMazdaRedirect(details.url, details.tabId, 'onErrorOccurred');
    }
  },
  {
    url: [
      { urlPrefix: "msauth.com.mazdausa.mazdaiphone://" },
      { urlPrefix: "msauth://com.interrait.mymazda" },
    ],
  }
);

// Safari-specific: Listen for committed events as a fallback
// This catches navigations that may have already started
chrome.webNavigation.onCommitted.addListener(
  async (details) => {
    if (details.url && isMazdaRedirect(details.url)) {
      handleMazdaRedirect(details.url, details.tabId, 'onCommitted');
    }
  },
  {
    url: [
      { urlPrefix: "msauth.com.mazdausa.mazdaiphone://" },
      { urlPrefix: "msauth://com.interrait.mymazda" },
    ],
  }
);
// Listen for tab updates - catches URL changes that other listeners might miss
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  // Check if the URL changed and is a Mazda redirect
  if (changeInfo.url && isMazdaRedirect(changeInfo.url)) {
    handleMazdaRedirect(changeInfo.url, tabId, 'onUpdated');
  }
});

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'MAZDA_REDIRECT' && message.url && sender.tab) {
    handleMazdaRedirect(message.url, sender.tab.id, 'contentScript');
    sendResponse({ success: true });
  }
  return true; // Keep message channel open for async response
});

