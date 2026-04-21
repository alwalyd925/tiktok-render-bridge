# TikTok Roblox Room-Code Pairing Bridge

This version uses **room code only inside Roblox**.

## Flow
1. In Roblox, enter a room code.
2. On your phone, open `/pair` on the Render site.
3. Enter the same room code + your TikTok username.
4. Back in Roblox, press **Connect**.

## Roblox placement
- `TikTokBridgeServer.lua` -> ServerScriptService
- `TikTokBridgeClient.lua` -> StarterPlayer > StarterPlayerScripts

## Render env vars
- `SHARED_SECRET`
