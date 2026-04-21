local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local remotes = ReplicatedStorage:WaitForChild("TikTokBridgeRemotes")
local state = ReplicatedStorage:WaitForChild("TikTokBridgeState")
local control = remotes:WaitForChild("Control")
local toastEvent = remotes:WaitForChild("Toast")

local function invoke(action, payload)
    local ok, result = pcall(function()
        return control:InvokeServer(action, payload)
    end)

    if not ok then
        return {
            ok = false,
            message = tostring(result),
        }
    end

    return result
end

local initial = invoke("getState")
if not initial.ok or not initial.isController then
    return
end

local playerGui = player:WaitForChild("PlayerGui")

local screenGui = Instance.new("ScreenGui")
screenGui.Name = "TikTokBridgePanel"
screenGui.ResetOnSpawn = false
screenGui.Parent = playerGui

local toggleButton = Instance.new("TextButton")
toggleButton.Name = "ToggleButton"
toggleButton.Size = UDim2.fromOffset(120, 34)
toggleButton.Position = UDim2.new(0, 16, 0, 16)
toggleButton.Text = "TikTok Panel"
toggleButton.BackgroundColor3 = Color3.fromRGB(30, 30, 35)
toggleButton.TextColor3 = Color3.fromRGB(255, 255, 255)
toggleButton.Font = Enum.Font.GothamBold
toggleButton.TextSize = 14
toggleButton.Parent = screenGui

local panel = Instance.new("Frame")
panel.Name = "Panel"
panel.Size = UDim2.fromOffset(390, 390)
panel.Position = UDim2.new(0, 16, 0, 60)
panel.BackgroundColor3 = Color3.fromRGB(16, 18, 24)
panel.BorderSizePixel = 0
panel.Parent = screenGui

local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 12)
corner.Parent = panel

local stroke = Instance.new("UIStroke")
stroke.Color = Color3.fromRGB(55, 60, 75)
stroke.Parent = panel

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -24, 0, 30)
title.Position = UDim2.new(0, 12, 0, 10)
title.BackgroundTransparency = 1
title.Text = "TikTok Live Control"
title.TextXAlignment = Enum.TextXAlignment.Left
title.TextColor3 = Color3.fromRGB(255, 255, 255)
title.Font = Enum.Font.GothamBold
title.TextSize = 20
title.Parent = panel

local subtitle = Instance.new("TextLabel")
subtitle.Size = UDim2.new(1, -24, 0, 20)
subtitle.Position = UDim2.new(0, 12, 0, 40)
subtitle.BackgroundTransparency = 1
subtitle.Size = UDim2.new(1, -24, 0, 40)
subtitle.TextWrapped = true
subtitle.Text = "Inside Roblox: enter a room code and round time. On your phone: open the pair page and enter the same room code with your TikTok username."
subtitle.TextXAlignment = Enum.TextXAlignment.Left
subtitle.TextColor3 = Color3.fromRGB(170, 175, 190)
subtitle.Font = Enum.Font.Gotham
subtitle.TextSize = 12
subtitle.Parent = panel

local function makeLabel(y, text)
    local label = Instance.new("TextLabel")
    label.Size = UDim2.new(1, -24, 0, 18)
    label.Position = UDim2.new(0, 12, 0, y)
    label.BackgroundTransparency = 1
    label.Text = text
    label.TextXAlignment = Enum.TextXAlignment.Left
    label.TextColor3 = Color3.fromRGB(220, 225, 235)
    label.Font = Enum.Font.GothamMedium
    label.TextSize = 13
    label.Parent = panel
    return label
end

local function makeBox(y, placeholder)
    local box = Instance.new("TextBox")
    box.Size = UDim2.new(1, -24, 0, 34)
    box.Position = UDim2.new(0, 12, 0, y)
    box.BackgroundColor3 = Color3.fromRGB(26, 28, 36)
    box.TextColor3 = Color3.fromRGB(255, 255, 255)
    box.PlaceholderText = placeholder
    box.PlaceholderColor3 = Color3.fromRGB(130, 135, 150)
    box.ClearTextOnFocus = false
    box.Font = Enum.Font.Gotham
    box.TextSize = 14
    box.Parent = panel
    local c = Instance.new("UICorner")
    c.CornerRadius = UDim.new(0, 8)
    c.Parent = box
    return box
end

makeLabel(94, "Room code")
local roomCodeBox = makeBox(114, "example: ROOM123")

makeLabel(156, "Pair this room on your phone")
local pairUrlLabel = Instance.new("TextLabel")
pairUrlLabel.Size = UDim2.new(1, -24, 0, 42)
pairUrlLabel.Position = UDim2.new(0, 12, 0, 178)
pairUrlLabel.BackgroundTransparency = 1
pairUrlLabel.TextXAlignment = Enum.TextXAlignment.Left
pairUrlLabel.TextYAlignment = Enum.TextYAlignment.Top
pairUrlLabel.TextWrapped = true
pairUrlLabel.TextColor3 = Color3.fromRGB(139, 168, 255)
pairUrlLabel.Font = Enum.Font.Gotham
pairUrlLabel.TextSize = 13
pairUrlLabel.Parent = panel

makeLabel(228, "Round time (seconds)")
local roundBox = makeBox(248, "example: 60")

local buttonRow = Instance.new("Frame")
buttonRow.Size = UDim2.new(1, -24, 0, 40)
buttonRow.Position = UDim2.new(0, 12, 0, 292)
buttonRow.BackgroundTransparency = 1
buttonRow.Parent = panel

local layout = Instance.new("UIListLayout")
layout.FillDirection = Enum.FillDirection.Horizontal
layout.HorizontalAlignment = Enum.HorizontalAlignment.Left
layout.Padding = UDim.new(0, 8)
layout.Parent = buttonRow

local function makeButton(text, width)
    local button = Instance.new("TextButton")
    button.Size = UDim2.fromOffset(width, 38)
    button.BackgroundColor3 = Color3.fromRGB(42, 48, 64)
    button.TextColor3 = Color3.fromRGB(255, 255, 255)
    button.Font = Enum.Font.GothamBold
    button.TextSize = 13
    button.Text = text
    button.Parent = buttonRow
    local c = Instance.new("UICorner")
    c.CornerRadius = UDim.new(0, 8)
    c.Parent = button
    return button
end

local connectButton = makeButton("Connect", 90)
local disconnectButton = makeButton("Disconnect", 90)
local applyButton = makeButton("Apply Time", 90)
local startButton = makeButton("Start", 70)
local stopButton = makeButton("Stop", 70)

local statusLabel = Instance.new("TextLabel")
statusLabel.Size = UDim2.new(1, -24, 0, 36)
statusLabel.Position = UDim2.new(0, 12, 0, 338)
statusLabel.TextWrapped = true
statusLabel.BackgroundTransparency = 1
statusLabel.TextXAlignment = Enum.TextXAlignment.Left
statusLabel.TextColor3 = Color3.fromRGB(255, 255, 255)
statusLabel.Font = Enum.Font.GothamMedium
statusLabel.TextSize = 13
statusLabel.Parent = panel

local lastEventLabel = Instance.new("TextLabel")
lastEventLabel.Size = UDim2.new(1, -24, 0, 28)
lastEventLabel.Position = UDim2.new(0, 12, 0, 360)
lastEventLabel.BackgroundTransparency = 1
lastEventLabel.TextXAlignment = Enum.TextXAlignment.Left
lastEventLabel.TextYAlignment = Enum.TextYAlignment.Top
lastEventLabel.TextWrapped = true
lastEventLabel.TextColor3 = Color3.fromRGB(170, 175, 190)
lastEventLabel.Font = Enum.Font.Gotham
lastEventLabel.TextSize = 12
lastEventLabel.Parent = panel

local toastLabel = Instance.new("TextLabel")
toastLabel.Size = UDim2.fromOffset(390, 34)
toastLabel.Position = UDim2.new(0, 16, 0, 462)
toastLabel.BackgroundColor3 = Color3.fromRGB(30, 30, 35)
toastLabel.BackgroundTransparency = 0.1
toastLabel.TextColor3 = Color3.fromRGB(255, 255, 255)
toastLabel.Text = ""
toastLabel.Visible = false
toastLabel.Font = Enum.Font.GothamMedium
toastLabel.TextSize = 13
toastLabel.Parent = screenGui
local toastCorner = Instance.new("UICorner")
toastCorner.CornerRadius = UDim.new(0, 8)
toastCorner.Parent = toastLabel

local function setStatus(text)
    statusLabel.Text = text
end

local function refreshFromValues()
    local linkedStreamer = state:WaitForChild("LinkedStreamer").Value
    local roomCode = state:WaitForChild("RoomCode").Value
    local bridgeStatus = state:WaitForChild("BridgeStatus").Value
    local roundDuration = state:WaitForChild("RoundDurationSeconds").Value
    local roundRemaining = state:WaitForChild("RoundRemainingSeconds").Value
    local isRoundRunning = state:WaitForChild("IsRoundRunning").Value
    local totalLikes = state:WaitForChild("TotalLikes").Value
    local lastEventText = state:WaitForChild("LastEventText").Value
    local pairUrl = state:WaitForChild("PairUrl").Value

    if roomCodeBox.Text == "" and roomCode ~= "" then
        roomCodeBox.Text = roomCode
    end
    if roundBox.Text == "" or tonumber(roundBox.Text) == nil then
        roundBox.Text = tostring(roundDuration)
    end

    pairUrlLabel.Text = pairUrl ~= "" and pairUrl or "Set a room code to generate your pair page"
    local roundText = isRoundRunning and ("running / remaining: " .. tostring(roundRemaining) .. "s") or ("stopped / duration: " .. tostring(roundDuration) .. "s")
    local linkText = linkedStreamer ~= "" and ("@" .. linkedStreamer .. " / room " .. roomCode) or "not linked yet"
    setStatus("Status: " .. bridgeStatus .. " | Link: " .. linkText .. " | Round: " .. roundText .. " | Likes: " .. tostring(totalLikes))
    lastEventLabel.Text = lastEventText ~= "" and lastEventText or "No events yet"
end

for _, child in ipairs(state:GetChildren()) do
    if child:IsA("ValueBase") then
        child.Changed:Connect(refreshFromValues)
    end
end
refreshFromValues()

local function showToast(text)
    toastLabel.Text = text
    toastLabel.Visible = true
    local token = tick()
    toastLabel:SetAttribute("token", token)
    task.delay(3, function()
        if toastLabel:GetAttribute("token") == token then
            toastLabel.Visible = false
        end
    end)
end

toastEvent.OnClientEvent:Connect(function(text)
    showToast(tostring(text))
end)

toggleButton.MouseButton1Click:Connect(function()
    panel.Visible = not panel.Visible
end)

connectButton.MouseButton1Click:Connect(function()
    local result = invoke("connect", {
        roomCode = roomCodeBox.Text,
    })
    showToast(result.message or (result.ok and "Connected" or "Failed"))
    refreshFromValues()
end)

disconnectButton.MouseButton1Click:Connect(function()
    local result = invoke("disconnect")
    showToast(result.message or "Disconnected")
    refreshFromValues()
end)

applyButton.MouseButton1Click:Connect(function()
    local result = invoke("setRoundDuration", {
        seconds = tonumber(roundBox.Text) or 0,
    })
    showToast(result.message or (result.ok and "Saved" or "Failed"))
    refreshFromValues()
end)

startButton.MouseButton1Click:Connect(function()
    local result = invoke("startRound")
    showToast(result.message or (result.ok and "Round started" or "Failed"))
    refreshFromValues()
end)

stopButton.MouseButton1Click:Connect(function()
    local result = invoke("stopRound")
    showToast(result.message or (result.ok and "Round stopped" or "Failed"))
    refreshFromValues()
end)
