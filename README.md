
# Introduction
This is a fork of the Mazda Connected Services integration originally written by bdr99 that has been packaged into a HACS compatible custom integration. The original code was part of the Home Assistant core integrations prior to a DMCA takedown notice issue by Mazda Motor Corporation.  It should restore all functionality previously available in the core integration.

# Installation

## With HACS

1. Add this repository as a custom repository in HACS.
2. Download the integration.
3. Restart Home Assistant

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=fano0001&repository=home-assistant-mazda&category=integration)

## Manual
Copy the `mazda_cs` directory, from `custom_components` in this repository,
and place it inside your Home Assistant Core installation's `custom_components` directory. Restart Home Assistant prior to moving on to the `Setup` section.

`Note`: If installing manually, in order to be alerted about new releases, you will need to subscribe to releases from this repository.

# Authentication

Mazda Connected Services uses OAuth authentication which blocks automated logins. Sign-in ends with `msauth://` callback address that the mobile app would typically open and which a browser cannot open. Use a browser extension or follow the steps below to capture the requisite code to complete authentication.

> [!IMPORTANT]
> A browser extension is recommended for the easiest sign-in to the integration, but a manual option is now available, instructions below the extensions.

## Browser extension

### OAuth Assist for HA (Chrome and Firefox extensions)

The new extension does the same job as the original Mazda OAuth Helper, but is generic, designed for use across multiple authentication platforms, and available in the Chrome Web Store. Future extension development will be focused on this one moving forward.

1. Install the extension
   - Chrome / Edge / other Chromium browsers:
      - Install [OAuth Assist for HA](https://chromewebstore.google.com/detail/oauth-assist-for-ha/mdoleppdlojmeeogmmocmjnkemecaofh) from the Chrome Web Store
   - Firefox (store listing is under review; install manually until it's approved):
      - Download the Firefox zip from the [latest release](https://github.com/crash0verride11/ha-oauth-assist/releases/latest/) page and extract it
      - Go to about:debugging → Load Temporary Add-on and select a file in the extracted extension/ folder
      > A manually loaded extension is tied to the folder location on your computer and may 'disappear' if you move the folder.
2. In a new tab, click the extension's icon to open its popup
3. Select `Manage providers...`
4. Download and import the [mazda_ha-oauth-assist.json](https://github.com/fano0001/home-assistant-mazda/blob/main/browser-extensions/mazda_ha-oauth-assist.json) provider profile
5. Enable the Mazda provider profile
6. Start the authentication process in Home Assistant and choose **Automated sign-in (browser extension)**

### Legacy Chrome Extension
Instructions for the original Mazda OAuth Helper Chrome extension are [available here](examples/legacy-extension.md), though it will no longer be actively maintained.

### Safari Extension

> Requires Xcode and a free developer account. A Safari version of OAuth Assist for HA is planned; once published, it will replace this integration-specific extension, so these steps may change.

- Download the [latest safari-extension.zip](https://github.com/fano0001/home-assistant-mazda/releases/latest/download/safari-extension.zip) from releases (or use `./browser-extensions/safari-extension/` from source)
- Extract the zip file
- Open the Xcode project
- Go to project settings and set your free developer account as the 'Team' for both Targets (`com.mazda.oauth-helper` and `com.mazda.oauth-helper.extension`). Also ensure 'Signing Certificate' is set to 'Development'
- Quit Safari if open and build the extension
- Open Safari and enable the extension in Safari settings
- Build the extension again
- The app window should indicate the extension is 'On'.
- Start the authentication process in Home Assistant and choose **Automated sign-in (browser extension)**

## Manual Authentication
> No extension is required, but the process is not intuitive. These steps are written for Chrome and Edge; other browsers may word the console message differently. Look for the a message containing `msauth://`.

1. Start the integration (or reauthentication), select your region, and choose **Manual sign-in (copy from the browser console)**.
2. Open the sign-in link from the form. If no sign-in page loads at all, clear any mazda.com cookies from your browser first.
3. Complete the Mazda sign-in form and click **LOGIN**. After clicking the button, **no new page loads and the browser appears to do nothing**. That is expected.
4. Open the browser's developer tools (`F12`, or `⌥⌘I` on a Mac) in that same tab and open the **Console** tab.
5. Find a similar to the below (exact wording may vary by browser):
   ```
   Failed to launch 'msauth://com.interrait.mymazda/…?state=…&code=…' because the scheme does not have a registered handler.
   ```
6. Right-click the `msauth://` address, select **Copy link address**, and paste it into **Callback URL**.

Keep the setup form open until you submit the URL. Treat that URL as a sign-in credential and keep it out of issue reports and screenshots.

### If the sign-in fails

| What you see | Cause | What to do |
| --- | --- | --- |
| The sign-in link opens but no sign-in page loads | Leftover mazda.com cookies from an earlier sign-in | Clear any mazda.com cookies from your browser, then open the sign-in link from the current form again |
| No `Failed to launch 'msauth://…'` line in the console | The console is open in a different tab, or the sign-in did not finish | Open the console in the sign-in tab; if the line still is not there, open the sign-in link from the current form and sign in again |
| "The address belongs to another sign-in attempt" | The pasted line came from an older sign-in, for example an earlier attempt in the same tab | Copy the newest `msauth://` line, or open the sign-in link from the current form again |
| "Mazda returned an error instead of a sign-in code" | The sign-in was cancelled or Mazda reported an error | Open the sign-in link from the current form and sign in again |
| "The pasted callback URL was not valid" | Only part of the address was copied, or it has no `code` | Copy the entire `msauth://` address, including everything after the `?` |
| Setup ends with "Error while obtaining access token" | The code was already used or expired before it was submitted | Start the setup again and paste the new address promptly |

# Push Notification Events

Push notification events allow the integration to receive real-time updates from Mazda — for example, confirmation that a remote lock or unlock command was completed — without waiting for the next scheduled poll.

## How it works

When enabled, the integration registers with the andoid app's notification service via Google. Push notifications are then sent to your Home Assistant, such as:

- A remote command (lock, unlock, start engine, etc.) success and failure
- A door being opened or left unlocked
- Charging completing or starting

After push events arrive the integration triggers an immediate refresh.

Events are fired as Home Assistant events under `mazda_cs_push`, which can be used as an automation trigger.

## Configuration 

### Integration options

Optional entities are turned on or off via **Devices & Services → Mazda Connected Services → ⚙️ (Configure)**. Saving reloads the integration.

| Option | Default | What it does |
|---|---|---|
| MyMazda vehicle images | Off | Adds a **Vehicle image** entity and a select for choosing between the vehicle images displayed in the mobile app for your model. |
| Development sensors (δ) | Off | Adds experimental sensors that read raw, undocumented vehicle status fields. Intended for development and troubleshooting. All development sensors are prefixed with `δ \|`. |

### Disable / enable push notification events

> [!IMPORTANT]
> Push notification events are **enabled by default** but can be disabled in the event of issues.

**After setup**, you can enable or disable it at any time via **Settings → Devices & Services → Mazda Connected Services → Three Dots → Reconfigure**.

### Example Automations YAML

Example yaml for sending Home Assistant notifications can be found in the example folder [HERE](https://github.com/fano0001/home-assistant-mazda/blob/v2.2.0-push/examples/mazda_cs_push_events.md).

## Known limitations

### Asymmetric events between accounts

If two accounts are used (primary + secondary driver):

- The **primary driver** receives push notification events for actions triggered by the secondary driver.
- The **secondary driver does not** receive push notification events for actions triggered by the primary driver.

# mazda_cs_remote_service_result Event Deprecation
The previous mazda_cs_remote_service_result events are removed and have been superseded by the above mazda_cs_push events. Please [migrate automations](https://github.com/fano0001/home-assistant-mazda/blob/v2.2.0-push/examples/mazda_cs_push_events.md).

# FAQ

## How often does the integration check for updates

**Vehicle Status:** Every 6 minutes and when triggered by a push notification. If the integration fails to register for push notifactions, 3 minutes.
**Health Report Status:** Every 24 hours or when triggered by a push notification
**Vehicle Images:** When the integration loads, if enabled. A failed fetch is retried hourly, up to 6 times.

## When does the vehicle send status updates?
Information on when the vehicle sends updates is sourced from the [Mazda Connected Services Manual (USA)](https://www.mazda.ca/globalassets/digitalownersmanual/en_connected-vehicle-service-manual_2025/chapter4/section4.html) and validated with testing:

### Vehicles Status updates
The vehicle sends an update to Mazda when:

* The engine is stopped/powered off.
* A few minutes after the engine is stopped/powered off (door, lock, and alert status notifications).
* When vehicle status alerts are triggered

**EVs / PHEVs:** Battery and climate imformation can be updated on demand via 'Pull to Refresh' in the official app or the 'Refresh Vehicle Status' button in this integration.

### Vehicle Status **does not update**
* When the engine is on
* **During a timed integration data refresh (6 min)**.
    * These refreshes only pull the last information sent by the vehicle to Mazda when last turned off or a status alert was sent.
* When in power save mode

Even if you pull to refresh in mymazda, the latest timestamp for vehicle status is the last time the vehicle was switched off (excluding climate / charge). 

## Does the integration drain vehicle battery?
**No**, not under normal conditions. Only remote commands (start/stop/locks/etc) wake the vehicle, otherwise the integration talks to the servers only.

**EV / PHEVS:** The "Refresh Vehicle Status" button also wakes the vehicle. Only overuse or frequent automation of this feature should be able cause a measurable impact.

## Multiple Devices Detected
Each MyMazda account can only be signed into one device at a time. To use the integration and the MyMazda app simultaneously, a secondary driver account can be created just for Home Assistant and provide access to the vehicle.
