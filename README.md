
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

> [!IMPORTANT]
> A browser extension is required to successfully authenticate with Mazda. Do not skip this step!

Mazda Connected Services uses OAuth authentication which blocks automated logins. Authentication requires a browser-based OAuth flow using a browser extension to capture the mobile app redirect URL.

## Setup

   ### chrome-extension
   > The chrome extension is tied to the folder location on your computer and may disappear if you move the folder.
   - Download the [latest chrome-extension.zip](https://github.com/fano0001/home-assistant-mazda/releases/latest/download/chrome-extension.zip) from releases (or use `./browser-extensions/chrome-extension/` from source)
   - Extract the zip file (or use source)
   - Open Google Chrome and navigate to `chrome://extensions/` or Edge `edge://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked" and select the extracted folder
   - Try to authenticate

   ### safari-extension

   > Requires Xcode and a free developer account

   - Download the [latest safari-extension.zip](https://github.com/fano0001/home-assistant-mazda/releases/latest/download/safari-extension.zip) from releases (or use `./browser-extensions/safari-extension/` from source)
   - Extract the zip file
   - Open the Xcode project
   - Go to project settings and set your free developer account as the 'Team' for both Targets (`com.mazda.oauth-helper` and `com.mazda.oauth-helper.extension`). Also ensure 'Signing Certificate' is set to 'Development'
   - Quit Safari if open and build the extension
   - Open Safari and enable the extension in Safari settings
   - Build the extension again
   - The app window should indicate the extension is 'On'.

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

### Disable / enable push notification events

> [!IMPORTANT]
> Push notification events are **enabled by default** but can be disabled in the event of issues.

**During initial setup**, a toggle to enable appears on setup alongside the region selector. 

**After setup**, you can enable or disable it at any time via **Settings → Devices & Services → Mazda Connected Services → Three Dots → Reconfigure**. No re-login is required.

**"Push notification events" switch** has been added to each vehicle's device page to temporarily increase discovery for existing users. Toggling it will reload the integration.

### Example Automations YAML

Example yaml for sending Home Assistant notifications can be found in the example folder [HERE](https://github.com/fano0001/home-assistant-mazda/blob/v2.2.0-push/examples/mazda_cs_push_events.md).

## Known limitations

### Asymmetric events between accounts

If two accounts are used (primary + secondary driver):

- The **primary driver** receives push notification events for actions triggered by the secondary driver.
- The **secondary driver does not** receive push notification events for actions triggered by the primary driver.

# mazda_cs_remote_service_result Event Deprecation
The previous mazda_cs_remote_service_result events are deprecated and have been superseded by the above mazda_cs_push events. These events will continue to work until the legacy patch is removed in 2027. Please [begin migrating automations](https://github.com/fano0001/home-assistant-mazda/blob/v2.2.0-push/examples/mazda_cs_push_events.md).

# FAQ

## How often does the integration check for updates

**Vehicle Status:** Every 6 minutes and when triggered by a push notification. If the integration fails to register for push notifactions, 3 minutes.
**Health Report Status:** Every 24 hours or when triggered by a push notification

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
