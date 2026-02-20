# Mazda OAuth Helper - Chrome Extension

This Chrome extension captures OAuth authorization codes from Mazda's mobile app login flow, which uses a custom `cma-prod://` URL scheme that browsers cannot normally handle.

## Why is this needed?

Mazda's mobile app uses Auth0 for authentication with a custom redirect URI (`cma-prod://login.duke-energy.com/android/com.dukeenergy.customerapp.release/callback`). Standard browsers cannot handle this custom scheme, so this extension intercepts the redirect and captures the authorization code for you.

## Installation

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in the top right)
3. Click "Load unpacked"
4. Select this `chrome-extension` folder
5. The extension icon should appear in your toolbar

## Usage

### With browser_auth.py script

1. Run the `browser_auth.py` script:

   ```bash
   cd examples
   python browser_auth.py
   ```

2. The script will:

   - Generate an authorization URL
   - Open your browser to the Mazda login page
   - Wait for you to paste the authorization code

3. Complete the login in your browser:

   - Enter your Mazda credentials
   - Complete any MFA/verification steps

4. After successful login:

   - The extension will capture the `cma-prod://` redirect
   - A page will show with your authorization code
   - Copy the code

5. Paste the code back into the terminal when prompted

6. The script will exchange the code for Mazda API tokens

### Manual Usage

1. Open the extension popup to see if any code has been captured
2. Click "View Full Details" to see the complete authorization data
3. Click "Copy Code" to copy the authorization code to clipboard
4. Click "Clear" to reset for a new login attempt

## How it works

1. When you complete the Mazda login, Auth0 redirects to `cma-prod://...?code=...`
2. Chrome cannot handle this URL scheme and would normally show an error
3. This extension intercepts that navigation attempt
4. It extracts the `code` and `state` parameters
5. It redirects you to a capture page showing the extracted data

## Files

- `manifest.json` - Extension configuration
- `background.js` - Service worker that intercepts redirects
- `popup.html` - Extension popup UI
- `capture.html` - Page displayed after capturing the code

## Security Notes

- The authorization code is only stored temporarily in the extension
- Codes expire after a few minutes and can only be used once
- The extension only has permission to access Mazda login URLs
- Use "Clear" to remove captured codes after use

## Troubleshooting

**Extension not capturing the code:**

- Make sure Developer mode is enabled
- Reload the extension
- Check that the extension has the required permissions

**Code not working:**

- Authorization codes expire quickly (usually within 5 minutes)
- Each code can only be used once
- Make sure to use the code immediately after capture

**Login page not loading:**

- Clear browser cookies for duke-energy.com
- Try an incognito window
- Disable other extensions that might interfere
