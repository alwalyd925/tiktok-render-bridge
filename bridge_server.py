local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local BRIDGE_BASE_URL = "https://YOUR-RENDER-SERVICE.onrender.com"
local SHARED_SECRET = "CHANGE_ME"
local DEFAULT_ROUND_DURATION = 60
local POLL_INTERVAL_SECONDS = 1

local remotesFolder = ReplicatedStorage:FindFirstChild("TikTokBridgeRemotes") or Instance.new("Folder")
remotesFolder.Name = "TikTokBridgeRemotes"
remotesFolder.Parent = ReplicatedStorage

local controlFunction = remotesFolder:FindFirstChild("Control") or Instance.new("RemoteFunction")
controlFunction.Name = "Control"
controlFunction.Parent = remotesFolder

local toastEvent = remotesFolder:FindFirstChild("Toast") or Instance.new("RemoteEvent")
toastEvent.Name = "Toast"
toastEvent.Parent = remotesFolder

local stateFolder = ReplicatedStorage:FindFirstChild("TikTokBridgeState") or Instance.new("Folder")
stateFolder.Name = "TikTokBridgeState"
stateFolder.Parent = ReplicatedStorage

local function ensureValue(className, name, defaultValue)
    local existing = stateFolder:FindFirstChild(name)
    if existing and existing.ClassName == className then
        return existing
    end

    if existing then
        existing:Destroy()
    end

    local value = Instance.new(className)
    value.Name = name
    value.Value = defaultValue
    value.Parent = stateFolder
    return value
end

local linkedStreamerValue = ensureValue("StringValue", "LinkedStreamer", "")
local roomCodeValue = ensureValue("StringValue", "RoomCode", "")
local sessionKeyValue = ensureValue("StringValue", "SessionKey", "")
local bridgeStatusValue = ensureValue("StringValue", "BridgeStatus", "Idle")
local roundDurationValue = ensureValue("IntValue", "RoundDurationSeconds", DEFAULT_ROUND_DURATION)
local roundRemainingValue = ensureValue("IntValue", "RoundRemainingSeconds", DEFAULT_ROUND_DURATION)
local roundRunningValue = ensureValue("BoolValue", "IsRoundRunning", false)
local lastEventValue = ensureValue("StringValue", "LastEventText", "No events yet")
local totalLikesValue = ensureValue("IntValue", "TotalLikes", 0)
local pairUrlValue = ensureValue("StringValue", "PairUrl", BRIDGE_BASE_URL .. "/pair")

local currentSessionKey = nil
local currentStreamerId = nil
local currentRoomCode = nil
local roundLoopToken = 0

local function normalizeRoomCode(value)
    value = tostring(value or "")
    value = string.upper(value)
    value = string.gsub(value, "[^%w_-]", "")
    return string.sub(value, 1, 32)
end

local function pushToast(targetPlayer, text, kind)
    if targetPlayer then
        toastEvent:FireClient(targetPlayer, text, kind or "info")
    else
        toastEvent:FireAllClients(text, kind or "info")
    end
end

local function updateBridgeState(status)
    bridgeStatusValue.Value = status
end

local function snapshotState(player)
    return {
        ok = true,
        isController = player and (player.UserId == game.CreatorId or (game.PrivateServerOwnerId ~= 0 and player.UserId == game.PrivateServerOwnerId) or (RunService:IsStudio() and player == Players:GetPlayers()[1])) or false,
        linkedStreamer = linkedStreamerValue.Value,
        roomCode = roomCodeValue.Value,
        bridgeStatus = bridgeStatusValue.Value,
        roundDurationSeconds = roundDurationValue.Value,
        roundRemainingSeconds = roundRemainingValue.Value,
        isRoundRunning = roundRunningValue.Value,
        totalLikes = totalLikesValue.Value,
        lastEventText = lastEventValue.Value,
        pairUrl = pairUrlValue.Value,
    }
end

local function requestJson(path, body, method)
    local response = HttpService:RequestAsync({
        Url = BRIDGE_BASE_URL .. path,
        Method = method or "POST",
        Headers = {
            ["Content-Type"] = "application/json",
            ["x-bridge-secret"] = SHARED_SECRET,
        },
        Body = body and HttpService:JSONEncode(body) or "",
    })

    if not response.Success then
        error(string.format("HTTP %s %s", tostring(response.StatusCode), tostring(response.Body)))
    end

    return HttpService:JSONDecode(response.Body)
end

local function canControl(player)
    if not player then
        return false
    end

    if player.UserId == game.CreatorId then
        return true
    end

    if game.PrivateServerOwnerId and game.PrivateServerOwnerId ~= 0 and player.UserId == game.PrivateServerOwnerId then
        return true
    end

    if RunService:IsStudio() then
        return player == Players:GetPlayers()[1]
    end

    return false
end

local function stopCurrentSession()
    if currentSessionKey then
        pcall(function()
            requestJson("/session/stop", {
                sessionKey = currentSessionKey,
                roomCode = currentRoomCode,
            })
        end)
    end

    currentSessionKey = nil
    currentStreamerId = nil
    currentRoomCode = nil
    linkedStreamerValue.Value = ""
    roomCodeValue.Value = ""
    sessionKeyValue.Value = ""
    updateBridgeState("Disconnected")
end

local function startSessionForRoom(roomCode)
    roomCode = normalizeRoomCode(roomCode)

    if roomCode == "" then
        return false, "Room code is required"
    end

    currentRoomCode = roomCode
    roomCodeValue.Value = roomCode
    pairUrlValue.Value = BRIDGE_BASE_URL .. "/pair?room=" .. roomCode

    stopCurrentSession()
    currentRoomCode = roomCode
    roomCodeValue.Value = roomCode
    pairUrlValue.Value = BRIDGE_BASE_URL .. "/pair?room=" .. roomCode

    local ok, result = pcall(function()
        return requestJson("/session/start", {
            roomCode = roomCode,
            placeId = game.PlaceId,
            jobId = game.JobId,
        })
    end)

    if not ok then
        updateBridgeState("Waiting for pairing")
        local pairUrl = BRIDGE_BASE_URL .. "/pair?room=" .. roomCode
        pairUrlValue.Value = pairUrl
        lastEventValue.Value = "Pair this room on your phone: " .. pairUrl
        return false, tostring(result)
    end

    if not result or not result.sessionKey then
        updateBridgeState("Connect failed")
        return false, "invalid response from bridge"
    end

    currentSessionKey = result.sessionKey
    currentStreamerId = result.streamerId or ""
    currentRoomCode = result.roomCode or roomCode

    linkedStreamerValue.Value = currentStreamerId
    roomCodeValue.Value = currentRoomCode
    sessionKeyValue.Value = currentSessionKey
    pairUrlValue.Value = BRIDGE_BASE_URL .. "/pair?room=" .. currentRoomCode
    updateBridgeState("Connected")
    lastEventValue.Value = "Room " .. currentRoomCode .. " linked to @" .. currentStreamerId

    return true, "Connected"
end

local function grantCoins(amount)
    for _, player in ipairs(Players:GetPlayers()) do
        local leaderstats = player:FindFirstChild("leaderstats")
        if leaderstats and leaderstats:FindFirstChild("Coins") then
            leaderstats.Coins.Value += amount
        end
    end
end

local function applySpeedBoost(seconds)
    for _, player in ipairs(Players:GetPlayers()) do
        local character = player.Character
        local humanoid = character and character:FindFirstChildOfClass("Humanoid")
        if humanoid then
            local originalSpeed = humanoid.WalkSpeed
            humanoid.WalkSpeed = math.max(originalSpeed, 20)
            task.delay(seconds, function()
                if humanoid and humanoid.Parent then
                    humanoid.WalkSpeed = originalSpeed
                end
            end)
        end
    end
end

local function stopRoundInternal(reason)
    roundLoopToken += 1
    roundRunningValue.Value = false
    roundRemainingValue.Value = roundDurationValue.Value
    if reason and reason ~= "" then
        lastEventValue.Value = reason
    end
end

local function startRoundInternal()
    roundLoopToken += 1
    local token = roundLoopToken
    roundRunningValue.Value = true
    roundRemainingValue.Value = roundDurationValue.Value
    lastEventValue.Value = "Round started"

    task.spawn(function()
        while roundRunningValue.Value and token == roundLoopToken and roundRemainingValue.Value > 0 do
            task.wait(1)
            if not roundRunningValue.Value or token ~= roundLoopToken then
                break
            end
            roundRemainingValue.Value -= 1
        end

        if token ~= roundLoopToken then
            return
        end

        if roundRemainingValue.Value <= 0 then
            roundRunningValue.Value = false
            roundRemainingValue.Value = 0
            lastEventValue.Value = "Round ended"
            pushToast(nil, "Round ended", "info")
        end
    end)
end

local function handleInteraction(event)
    if not event or not event.type then
        return
    end

    local army = _G.ArmyGame

    if event.type == "comment" then
        local username = tostring(event.username or "TikTokUser")
        local text = tostring(event.text or "")
        lastEventValue.Value = string.format("%s commented: %s", username, text)
        pushToast(nil, lastEventValue.Value, "comment")

        if army and army.ProcessComment then
            local ok, err = pcall(function()
                army.ProcessComment(username, text)
            end)
            if not ok then
                warn("Army ProcessComment failed:", err)
            end
        end

    elseif event.type == "gift" then
        local username = tostring(event.username or "TikTokUser")
        local coinCount = tonumber(event.coinCount) or tonumber(event.repeatCount) or 1

        lastEventValue.Value = string.format("%s sent %s (%d coins)", username, tostring(event.giftName or "Gift"), coinCount)
        pushToast(nil, lastEventValue.Value, "gift")

        if army and army.ProcessGift then
            local ok, err = pcall(function()
                army.ProcessGift(username, coinCount)
            end)
            if not ok then
                warn("Army ProcessGift failed:", err)
            end
        end

    elseif event.type == "like" then
        local username = tostring(event.username or "TikTokUser")
        local likeCount = tonumber(event.likeCount) or 1

        totalLikesValue.Value += likeCount
        lastEventValue.Value = string.format("%s sent likes (+%d)", username, likeCount)

        if army and army.ProcessLikes then
            local ok, err = pcall(function()
                army.ProcessLikes(username, likeCount)
            end)
            if not ok then
                warn("Army ProcessLikes failed:", err)
            end
        end

    elseif event.type == "follow" then
        local username = tostring(event.username or "TikTokUser")
        lastEventValue.Value = string.format("%s followed the live", username)
        pushToast(nil, lastEventValue.Value, "follow")

        if army and army.ProcessFollow then
            local ok, err = pcall(function()
                army.ProcessFollow(username)
            end)
            if not ok then
                warn("Army ProcessFollow failed:", err)
            end
        end

    elseif event.type == "status" then
        local state = tostring(event.state or "unknown")
        updateBridgeState("TikTok " .. state)
        lastEventValue.Value = "TikTok status: " .. state
    end
end


local function pollLoop()
    while true do
        if currentSessionKey then
            local ok, result = pcall(function()
                return requestJson("/poll", {
                    sessionKey = currentSessionKey,
                })
            end)

            if ok and result and result.events then
                for _, event in ipairs(result.events) do
                    handleInteraction(event)
                end
            elseif not ok then
                updateBridgeState("Poll failed")
                warn("Bridge poll failed", result)
            end
        end

        task.wait(POLL_INTERVAL_SECONDS)
    end
end

controlFunction.OnServerInvoke = function(player, action, payload)
    payload = payload or {}

    if action == "getState" then
        return snapshotState(player)
    end

    if not canControl(player) then
        return {
            ok = false,
            message = "You are not allowed to control this panel",
        }
    end

    if action == "connect" then
        local ok, message = startSessionForRoom(payload.roomCode)
        if ok then
            pushToast(nil, "Linked TikTok @" .. linkedStreamerValue.Value .. " / room " .. roomCodeValue.Value, "success")
        else
            pushToast(player, message, "error")
        end
        local state = snapshotState(player)
        state.ok = ok
        state.message = message
        return state
    elseif action == "disconnect" then
        stopCurrentSession()
        pushToast(nil, "TikTok disconnected", "info")
        local state = snapshotState(player)
        state.message = "Disconnected"
        return state
    elseif action == "setRoundDuration" then
        local seconds = math.floor(tonumber(payload.seconds) or 0)
        if seconds < 10 or seconds > 3600 then
            return {
                ok = false,
                message = "Round time must be between 10 and 3600 seconds",
            }
        end
        roundDurationValue.Value = seconds
        if not roundRunningValue.Value then
            roundRemainingValue.Value = seconds
        end
        lastEventValue.Value = "Round time set to " .. seconds .. "s"
        local state = snapshotState(player)
        state.message = "Round time updated"
        return state
    elseif action == "startRound" then
        if roundRunningValue.Value then
            return {
                ok = false,
                message = "Round is already running",
            }
        end
        startRoundInternal()
        local state = snapshotState(player)
        state.message = "Round started"
        return state
    elseif action == "stopRound" then
        stopRoundInternal("Round stopped")
        local state = snapshotState(player)
        state.message = "Round stopped"
        return state
    end

    return {
        ok = false,
        message = "Unknown action",
    }
end

Players.PlayerRemoving:Connect(function(player)
    if player.UserId == game.PrivateServerOwnerId then
        -- Keep the room alive; do nothing automatically.
    end
end)

task.spawn(pollLoop)

updateBridgeState("Idle")

if RunService:IsStudio() then
    warn("Remember to enable HTTP Requests in Game Settings > Security")
end

game:BindToClose(function()
    stopCurrentSession()
end)
