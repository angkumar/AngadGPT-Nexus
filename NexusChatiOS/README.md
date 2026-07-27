# NexusChat iOS

A native SwiftUI iOS client for AngadGPT Nexus.

## Run

1. Start the backend from the repo root:

```bash
scripts/dev_backend.sh
```

2. Open `NexusChat.xcodeproj` in Xcode.
3. Run the `NexusChat` scheme on an iPhone simulator or device.
4. In the app settings, set the API base URL:

```text
http://127.0.0.1:8000/api
```

Use that URL for the simulator. For a physical iPhone, use your Mac's LAN IP:

```text
http://<your-mac-ip>:8000/api
```

If `ANGADGPT_AUTH_TOKEN` is set in `.env`, enter the same token in app settings.
