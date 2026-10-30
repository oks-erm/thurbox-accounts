-- Always-visible selected-conversation identity; never authenticates on refresh.
local theme = require("lib.theme")
local BASE = @BASE@
local function quote(s) return "'" .. tostring(s):gsub("'", "'\\''") .. "'" end
local function decode(s) return (s or ""):gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end) end
local function summary(request)
  local selected = store.selected
  if not selected then return "Account: no conversation selected" end
  local session
  for _, row in ipairs(thurbox.sessions or {}) do if row.id == selected then session = row; break end end
  if not session then return "Account: no conversation selected" end
  -- Codex currently has no account routing in this extension.
  if session.agent == "codex" then return "Account: default | Codex" end
  if not run then return "Account: allow account-status in Settings > Interface" end
  local key = "account-status-" .. selected
  if request then run(key, BASE .. " pane-state --session " .. quote(selected), { machine = "local", timeout = 30, ttl = 3 }) end
  local answer = (thurbox.runs or {})[key]
  if not answer or answer.state ~= "done" then return "Account: checking…" end
  if not answer.ok then return "Account: unavailable | F7 for Accounts" end
  for row in (answer.stdout or ""):gmatch("[^\r\n]+") do
    local f = {}; for value in (row .. "\t"):gmatch("(.-)\t") do f[#f + 1] = decode(value) end
    if f[1] == "indicator" and f[2] == selected then
      return "Account: " .. f[4] .. " | " .. f[5] .. " | F7 Accounts"
    end
  end
  return "Account: unverified | F7 Accounts"
end
return {
  name = "account-status", slot = "account-status", strip = true,
  size = { len = 1 }, pure = true, focusable = false,
  capabilities = { "run" },
  ui_state = function() return { label = summary(), selected = store.selected } end,
  render = function(ctx)
    local label=summary(true)
    local node={type="text",text=label,fill=1,role="action:accounts.open",style={fg=theme.accent}}
    if store.selected and not label:find("Codex",1,true) then
      return {type="box",axis="horizontal",children={node,
        {type="text",text="[ Switch account ]",len=20,role="action:account-switch.open",style={fg=theme.accent_bright}}}}
    end
    return node
  end,
}
