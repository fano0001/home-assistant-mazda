
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

> [!IMPORTANT]
> All steps below must be performed in a Chromium based browser (tested in Edge and Vivaldi).
> This chrome extension is required to successfully authenticate with Mazda. Do not skip this step!

Mazda Connected Services uses OAuth with CAPTCHA protection which blocks automated logins. Authentication requires a browser-based OAuth flow using a Chrome extension to capture the android mobile app's redirect URL.

## Setup
   - Download the [latest chrome-extension.zip](https://github.com/crash0verride11/home-assistant-mazda/releases/latest/download/chrome-extension.zip) from releases (or use `./chrome-extension/` from source)
   - Extract the zip file (or use source)
   - Open Google Chrome and navigate to `chrome://extensions/` or Edge `edge://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked" and select the extracted folder
   - Try to authenticate

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=crash0verride11&repository=home-assistant-mazda&category=integration)
