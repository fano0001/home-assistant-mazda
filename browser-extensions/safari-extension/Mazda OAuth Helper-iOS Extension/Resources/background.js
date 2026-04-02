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
    const parts = state.split(".");
    if (parts.length !== 3) return false;

    let base64 = parts[1]
      .replace(/-/g, '+')
      .replace(/_/g, '/');

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

function handleMazdaRedirect(url, tabId, source = 'unknown') {
  const urlKey = `${tabId}-${url}`;
  if (processedUrls.has(urlKey)) {
    console.log(`[${source}] Already processed:`, url);
    return;
  }
  processedUrls.add(urlKey);
  setTimeout(() => processedUrls.delete(urlKey), 5000);

  console.log(`[${source}] Handling Mazda redirect:`, url);

  try {
    const urlObj = new URL(url);
    const code = urlObj.searchParams.get("code");
    const state = urlObj.searchParams.get("state");

    if (code && isHomeAssistantFlow(state)) {
      const haUrl = new URL("https://my.home-assistant.io/redirect/oauth");
      haUrl.searchParams.set("code", code);
      haUrl.searchParams.set("state", state);

      console.log(`[${source}] Redirecting to Home Assistant`);
      chrome.tabs.update(tabId, { url: haUrl.toString() });
      return;
    }

    const captureUrl = new URL(chrome.runtime.getURL("capture.html"));
    captureUrl.searchParams.set("code", code || "");
    captureUrl.searchParams.set("state", state || "");
    captureUrl.searchParams.set("error", urlObj.searchParams.get("error") || "");
    captureUrl.searchParams.set("error_description", urlObj.searchParams.get("error_description") || "");

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

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url && isMazdaRedirect(changeInfo.url)) {
    handleMazdaRedirect(changeInfo.url, tabId, 'onUpdated');
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'MAZDA_REDIRECT' && message.url && sender.tab) {
    handleMazdaRedirect(message.url, sender.tab.id, 'contentScript');
    sendResponse({ success: true });
  }
  return true;
});
