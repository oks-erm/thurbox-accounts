-- Thurbox Accounts v1. Generated paths are filled by accounts ui-install.
local ui = require("lib.ui")
local theme = require("lib.theme")
local textinput = require("lib.textinput")
local BASE = @BASE@
local EXECUTABLE = @EXECUTABLE@
local ARGS = @ARGS@
local function quote(value)
  return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end
local function field(name, fallback)
  return state[name] or textinput.new(fallback or "")
end
local function value(name) return field(name).value end
local function ask(args, preview)
  if not run then return end
  local parts = { BASE }
  for _, arg in ipairs(args) do parts[#parts + 1] = quote(arg) end
  if state.request_key and run_forget then run_forget(state.request_key) end
  state.request_number = (state.request_number or 0) + 1
  state.request_key = "operation-" .. tostring(state.request_number)
  state.preview = preview == true
  run(state.request_key, table.concat(parts, " "), { machine = "local", timeout = 210, refresh = true })
end
local function launch_login()
  if not thurbox.granted.program then
    command("message", { text = "Grant Accounts program capability in Interface settings for SSO.", level = "error" })
    return
  end
  local args = {}
  for _, arg in ipairs(ARGS) do args[#args + 1] = arg end
  args[#args + 1] = "login"
  args[#args + 1] = value("profile")
  command("program", { text = "accounts", repo = EXECUTABLE, args = args })
  state.login = true
end
local view_height = 0
local function next_account()
  local selected = store.selected
  if not selected then return nil end
  local answer = (thurbox.runs or {})["shared-status-" .. selected]
  if answer and answer.state == "done" and answer.ok then
    return (answer.stdout or ""):match('"next_profile"%s*:%s*"([a-z0-9-]+)"')
  end
end
local labels = { "Profile / target (type a listed name)", "Repository (absolute path)", "New session name", "Sharing order: account-a,account-b (approves context access)" }
local fields = { "profile", "repo", "session_name", "sharing_order" }
local function line(s, height)
  return { type = "text", len = height or 1, text = s, style = { fg = theme.text } }
end
return {
  name = "accounts", slot = "center", slot_mode = "switch", pure = true,
  focusable = true, input = "session", capabilities = { "run", "program" },
  keys = {
    { key = "f7", action = "accounts.open", desc = "Accounts", scope = "global" },
    { key = "alt+r", action = "accounts.list", desc = "List profiles" },
    { key = "alt+a", action = "accounts.add", desc = "Add profile" },
    { key = "alt+l", action = "accounts.login", desc = "Enterprise SSO login" },
    { key = "alt+s", action = "accounts.status", desc = "Check account identity" },
    { key = "alt+n", action = "accounts.start", desc = "New account session" },
    { key = "alt+p", action = "accounts.preview", desc = "Preview selected session handoff" },
    { key = "alt+y", action = "accounts.confirm", desc = "Confirm displayed transfer" },
    { key = "alt+v", action = "accounts.verify", desc = "Verify native handoff (two test requests)" },
    { key = "alt+e", action = "accounts.enable_shared", desc = "Enable shared history for entered account order" },
    { key = "alt+x", action = "accounts.switch", desc = "Switch selected shared conversation to next account" },
    { key = "alt+i", action = "accounts.shared_status", desc = "Shared conversation status and next account" },
    { key = "alt+b", action = "accounts.back", desc = "Back from login" },
  },
  pills = { { action = "accounts.open", label = "Accounts", priority = 10 } },
  render = function(ctx)
    view_height = ctx.height or 0
    if state.login then
      return ui.panel({ title = "Enterprise SSO — Alt+b returns", focused = ctx.focused,
                        body = { { type = "surface", program = "accounts" } } })
    end
    if not run then
      return ui.panel({ title = "Accounts", focused = ctx.focused, body = {
        line("Grant Accounts run/program capabilities: Ctrl+, → ] → t.", 2),
        line("Each Enterprise login has a separate private Claude configuration directory.", 2),
        line("F7 returns to the previous pane.") } })
    end
    local selected = store.selected
    if selected then
      run("shared-status-" .. selected, BASE .. " shared-status --session " .. quote(selected),
          { machine = "local", timeout = 30, ttl = 5 })
    end
    local next = next_account()
    local switch_line = next and ui.row({ width = ctx.width }):button(
      "[ Alt+x Switch to " .. next .. " ]", nil, "key:alt+x", "switch-account"):spans_list()
      or "Select a shared session to switch accounts."
    local children = { line(switch_line) }
    for i, name in ipairs(fields) do
      children[#children + 1] = textinput.node(field(name), {
        label = labels[i], focused = ctx.focused and (state.field or 1) == i })
    end
    children[#children + 1] = line("Tab: next field  |  Alt+r list  Alt+a add  Alt+l SSO  Alt+s status")
    children[#children + 1] = line("Alt+n new session  |  Alt+p preview selected stopped session")
    children[#children + 1] = line("Alt+y CONFIRM displayed transfer  |  Alt+v native test (two model requests)")
    children[#children + 1] = line("Alt+e approves entered sharing order  |  Alt+i shared status")
    children[#children + 1] = line("Selected source: " .. (store.selected or "none"))
    local answer = (thurbox.runs or {})[state.request_key or "none"]
    local output = answer and (answer.state == "done" and
      ((answer.stdout or "") .. (answer.stderr or "")) or (answer.error or "Working…")) or "Alt+r lists profiles. Add a profile, then log in with SSO."
    if state.preview and answer and answer.state == "done" and answer.ok then
      local source = output:match('"source"%s*:%s*"([^"\n]+)"')
      local target = output:match('"target"%s*:%s*"([^"\n]+)"')
      local email = output:match('"target_identity"%s*:%s*{%s*"email"%s*:%s*"([^"\n]+)"')
      local plan = output:match('"id"%s*:%s*"([a-f0-9]+)"')
      output = "TRANSFER source: " .. (source or "unknown") .. "\nTO: " .. (target or "unknown") ..
        " / " .. (email or "read CLI preview for identity") .. "\nContext and working directory become visible to target organization.\n" ..
        "Plan: " .. (plan or "none") .. " (5 min). Alt+y confirms.\n" .. output
    end
    children[#children + 1] = { type = "text", text = output, style = { fg = theme.text } }
    return ui.panel({ title = "Claude Enterprise Accounts", focused = ctx.focused, body = children })
  end,
  on_action = function(action)
    if action == "accounts.open" then
      command("focus", { text = "accounts", toggle = true })
      return true
    elseif action == "accounts.back" then
      state.login = false
      return true
    elseif action == "accounts.list" then ask({ "list", "--text" })
    elseif action == "accounts.add" then ask({ "add", value("profile") })
    elseif action == "accounts.status" then ask({ "status", value("profile") })
    elseif action == "accounts.login" then launch_login()
    elseif action == "accounts.start" then
      ask({ "start", value("profile"), "--repo", value("repo"), "--name", value("session_name") })
    elseif action == "accounts.switch" then
      local next = next_account()
      if next then
        ask({ "switch", "--session", store.selected or "", "--expected-profile", next })
      else
        command("message", { text = "Select an enabled shared session and wait for its next account to appear.", level = "error" })
      end
    elseif action == "accounts.shared_status" then
      ask({ "shared-status", "--session", store.selected or "" })
    elseif action == "accounts.enable_shared" then
      local args = { "enable-shared", "--session", store.selected or "", "--consent" }
      for profile in value("sharing_order"):gmatch("[^,]+") do
        args[#args + 1] = "--profile"
        args[#args + 1] = profile:match("^%s*(.-)%s*$")
      end
      ask(args)
    elseif action == "accounts.preview" then
      state.source = store.selected
      state.target = value("profile")
      ask({ "handoff", "--session", state.source or "", "--to", state.target }, true)
    elseif action == "accounts.confirm" then
      local answer = (thurbox.runs or {})[state.request_key or "none"]
      local plan = answer and answer.state == "done" and answer.ok and state.preview and
        (answer.stdout or ""):match('"id"%s*:%s*"([a-f0-9]+)"')
      local output = answer and answer.stdout or ""
      local source = output:match('"source"%s*:%s*"([^"\n]+)"')
      local target = output:match('"target"%s*:%s*"([^"\n]+)"')
      if view_height >= 30 and plan and source == state.source and target == state.target and
        state.source == store.selected and state.target == value("profile") then
        ask({ "handoff", "--confirm", plan })
      else
        command("message", { text = "Preview this source and target first. Use a 30-row pane or CLI to review and confirm all details.", level = "error" })
      end
    elseif action == "accounts.verify" then ask({ "verify-handoff", value("profile") })
    else return false end
    return true
  end,
  on_key = function(key)
    if state.login then return false end
    if key.key == "tab" then
      state.field = ((state.field or 1) % #fields) + 1
      return true
    end
    local name = fields[state.field or 1]
    local input = field(name)
    if textinput.key(input, key) then
      state[name] = input
      state.preview = false
      return true
    end
    return false
  end,
}
