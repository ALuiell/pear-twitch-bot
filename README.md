l# PearRequests

Desktop app for Twitch song requests with Pear Desktop integration.

`PearRequests` connects to Twitch chat, accepts `!song` requests, keeps its own viewer queue, and controls Pear Desktop through the built-in API Server.  
Instead of relying on YouTube Music's endless autoplay queue, the app tries to keep the next viewer track directly after the currently playing song.

## Features

- Twitch OAuth login and IRC bot connection
- Commands: `!song`, `!queue`, `!current`, `!skip`, `!remove`
- Local viewer queue with FIFO behavior
- Search by plain text or direct YouTube link
- Pear Desktop API auth support
- Cleaner in-app logs and connection statuses
- Basic playback controls in the desktop UI

## How It Works

1. A viewer sends `!song <youtube-link>` or `!song <search text>` in Twitch chat.
2. The app validates the request and adds it to the local viewer queue.
3. The app watches Pear Desktop state and keeps the next viewer request immediately after the current song.
4. When the current viewer song starts, it is removed from the local queue and the next one is prepared.

This makes requests predictable and avoids burying viewer songs inside YouTube Music autoplay.

## Commands

- `!song <youtube-link>`: add a song by YouTube URL
- `!song <search text>`: search and add a song
- `!queue`: show the current viewer queue
- `!current`: show the currently playing track
- `!skip`: skip the current track, mod/vip only
- `!remove <number>`: remove an item from the viewer queue, mod/vip only

## Requirements

- Windows
- Python 3.12+
- Pear Desktop with the `API Server` plugin enabled
- Twitch application `Client ID`

## Setup

1. Install dependencies:

```powershell
pip install -r requirements.txt
```

2. Start Pear Desktop and enable the `API Server` plugin.

Recommended Pear API settings:

- `hostname`: `127.0.0.1`
- `port`: `26538`
- `authorization`: Disabled (recommended for simplicity; if enabled, you must approve the connection pop-up in Pear Desktop upon the first request)

3. Run the app:

```powershell
python main.py
```

4. In the app:

- connect your Twitch account
- set the target Twitch channel if needed
- start the bot

## Configuration

The app stores settings in `config.json`.

Important fields:

- `twitch.client_id`: Twitch application client ID
- `twitch.target_channel`: channel to listen to
- `pear.base_url`: Pear API address, default `http://127.0.0.1:26538`
- `pear.auth_client_id`: client ID used for Pear API auth
- `song_requests.global_cooldown_seconds`
- `song_requests.user_cooldown_seconds`

## Project Structure

```text
app/
  config.py
  pear_client.py
  song_requests.py
  twitch_auth.py
  twitch_controller.py
  twitch_credentials.py
  twitch_irc.py
  ui/
main.py
config.json
requirements.txt
```

## Notes

- The current viewer queue is kept in memory.
- If the app is restarted, the local queue is lost.
- Pear Desktop remains the playback engine, but queue order is controlled by this app.

## Roadmap

- persistent viewer queue
- WebSocket-based Pear state sync
- queue history and moderation tools
- packaging for release

## Repository Description

Short GitHub repo description:

`Twitch song request desktop app for Pear Desktop with a local viewer queue and Twitch chat integration.`
