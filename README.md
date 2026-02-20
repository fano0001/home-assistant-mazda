
# Introduction
This is a fork of the Mazda Connected Services integration originally written by bdr99 that has been packaged into a HACS compatible custom integration. The original code was part of the Home Assistant core integrations prior to a DMCA takedown notice issue by Mazda Motor Corporation.  It should restore all functionality previously available in the core integration.

# Installation

## With HACS

1. Add this repository as a custom repository in HACS.
2. Download the integration.
3. Restart Home Assistant

## Manual
Copy the `mazda_cs` directory, from `custom_components` in this repository,
and place it inside your Home Assistant Core installation's `custom_components` directory. Restart Home Assistant prior to moving on to the `Setup` section.

`Note`: If installing manually, in order to be alerted about new releases, you will need to subscribe to releases from this repository.

# Authentication

Mazda Connected Services uses OAuth with CAPTCHA protection which blocks automated logins. Authentication requires a browser-based OAuth flow using a Chrome extension to capture the mobile app's custom redirect URL.

## Setup

1. Install the Chrome extension:

   - Download the [latest chrome-extension.zip](https://github.com/crash0verride11/home-assistant-mazda/releases/latest/download/chrome-extension.zip) from releases (or use `./chrome-extension/` from source)
   - Extract the zip file (or use source)
   - Open Chrome and navigate to `chrome://extensions/` or Edge `edge://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked" and select the extracted folder
   - Try to authenticate
