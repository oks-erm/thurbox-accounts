-- Thurbox Accounts v2. Guided, clickable setup. Paths filled by ui-install.
local ui = require("lib.ui")
local theme = require("lib.theme")
local textinput = require("lib.textinput")
local widgets = require("lib.widgets")
local hover = require("lib.hover")
local BASE = @BASE@
local EXECUTABLE = @EXECUTABLE@
local ARGS = @ARGS@
local controls, ready_to_confirm, width, displayed_confirmation = {}, false, 70, nil
local dispatch
local function quote(s) return "'" .. tostring(s):gsub("'", "'\\''") .. "'" end
local function decode(s) return (s or ""):gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end) end
local function result() return (thurbox.runs or {})[state.request_key or "none"] end
local function busy() local r = result(); return state.request_key ~= nil and (not r or r.state ~= "done") end
local function data_key()
  return "accounts-data-" .. tostring(state.request_number or 0) .. (busy() and "-pending" or "-done") .. "-" .. tostring(store.selected or "none")
end
local function forget_data()
  if run_forget then
    local prefix = "accounts-data-" .. tostring(state.request_number or 0)
    local suffix = "-" .. tostring(store.selected or "none")
    run_forget(prefix .. "-pending" .. suffix); run_forget(prefix .. "-done" .. suffix)
  end
end
local function refresh()
  forget_data()
  state.request_number = (state.request_number or 0) + 1
  state.request_key = nil
end
local function ask(args, long)
  if not run or busy() then return end
  forget_data()
  if state.request_key and run_forget then run_forget(state.request_key) end
  state.request_number = (state.request_number or 0) + 1
  state.request_key = "accounts-operation-" .. tostring(state.request_number)
  local parts = { BASE, "--desktop-deadline", long and "900" or "180", "pane-run" }
  for _, arg in ipairs(args) do parts[#parts + 1] = quote(arg) end
  state.message = nil
  run(state.request_key, table.concat(parts, " "), { machine = "local", timeout = long and 930 or 210, refresh = true })
end
local function model()
  local answer = (thurbox.runs or {})[data_key()]
  local m = { accounts = {}, conversations = {}, ready = false }
  if not answer or answer.state ~= "done" then return m end
  if not answer.ok then m.error = answer.stderr or answer.error or "Account helper unavailable"; return m end
  m.ready = true
  for row in (answer.stdout or ""):gmatch("[^\r\n]+") do
    local f = {}; for value in (row .. "\t"):gmatch("(.-)\t") do f[#f + 1] = decode(value) end
    if f[1] == "account" and #f == 5 then
      m.accounts[#m.accounts + 1] = { name = f[2], label = f[3], email = f[4], saved = f[5] == "saved" }
    elseif f[1] == "conversation" and (#f == 10 or #f == 12) then
      m.conversations[#m.conversations + 1] = { id = f[2], name = f[3], profile = f[4], shared = f[5] == "shared",
        next = f[6], cwd = f[7], stopped = f[8] == "stopped", conversation = f[9], phase = f[10], mode = f[11] or "on", external = f[12] == "external" }
    elseif f[1] == "indicator" then m.indicator = "Account: " .. f[4] .. " | " .. f[5]
    elseif f[1] == "current" then m.current = f[2]
    elseif f[1] == "unsupported" then m.unsupported = f[3]
    elseif f[1] == "proof" then m.proof = f[2] end
  end
  return m
end
local function account(m)
  for _, p in ipairs(m.accounts) do if p.label == state.added_label then return p end end
  for _, p in ipairs(m.accounts) do if p.name == state.account then return p end end
  return m.accounts[1]
end
local function conversation(m)
  local explicit = state.selection_base == store.selected and state.conversation or nil
  if m.unsupported and not explicit then return nil end
  for _, c in ipairs(m.conversations) do if c.id == explicit then return c end end
  for _, c in ipairs(m.conversations) do if c.id == m.current or c.id == store.selected then return c end end
  if m.current then return nil end
  return m.conversations[1]
end
local function label(m, name)
  for _, p in ipairs(m.accounts) do if p.name == name then return p.label end end
  return name
end
local function field(name, fallback) return state[name] or textinput.new(fallback or "") end
local function value(name, fallback) return field(name, fallback).value end
local function register(id) controls[#controls + 1] = id; return #controls == (state.focus or 1) end
local function line(text, rows)
  return { type = "text", len = rows or math.max(1, math.ceil(widgets.len(text) / width)), text = text, wrap = true, style = { fg = theme.text } }
end
local function button(text, id)
  local focused = register(id)
  return { type = "text", len = 1, id = id, role = "button", text = "[ " .. text .. " ]",
    style = (focused or hover.id(id)) and { fg = theme.inverted_fg, bg = theme.accent_bright } or { fg = theme.accent } }
end
local function input(name, title, fallback)
  register("field:" .. name)
  return textinput.node(field(name, fallback), { label = title, placeholder = fallback or "", id = "field:" .. name,
    focused = controls[state.focus or 1] == "field:" .. name })
end
local function group(m)
  local selected = state.sharing or {}; local names = {}
  for _, name in ipairs(selected) do for _, p in ipairs(m.accounts) do if p.name == name then names[#names + 1] = name end end end
  return names
end
local function projects()
  local list, seen = {}, {}
  for _, row in ipairs(thurbox.sessions or {}) do
    if type(row.cwd) == "string" and not row.host and not seen[row.cwd] then list[#list + 1] = row.cwd; seen[row.cwd] = true end
  end
  return list
end
local function default_folder()
  for _, row in ipairs(thurbox.sessions or {}) do if row.id == store.selected then return row.cwd or "" end end
  return projects()[1] or ""
end
local function profile_args(names)
  local args = {}; for _, name in ipairs(names) do args[#args + 1] = "--profile"; args[#args + 1] = name end; return args
end
local function launch_login(p)
  if not p then return end
  if not thurbox.granted.program then state.message = "Login needs Program permission. Open Settings, choose Interface, then trust Accounts for Run and Program."; return end
  local args = {}; for _, arg in ipairs(ARGS) do args[#args + 1] = arg end
  args[#args + 1] = "login"; args[#args + 1] = p.name
  state.account = p.name
  state.login_profile = p.name
  command("program", { text = "accounts-" .. p.name, repo = EXECUTABLE, args = args })
end
local function navigate(screen) state.screen = screen; state.focus = 1; state.message = nil; state.pending = nil end
local function start_confirmation(kind, m)
  local c = conversation(m)
  state.confirmation_number = (state.confirmation_number or 0) + 1
  state.pending = { token = state.confirmation_number, kind = kind, profiles = group(m), source = c and c.id, title = c and c.name }
  state.focus = 1
end
local function page_rows(rows, page)
  local first = (page or 0) * 4 + 1; local visible = {}
  for i = first, math.min(#rows, first + 3) do visible[#visible + 1] = rows[i] end
  return visible
end
local function mode_review()
  local answer = result()
  if not answer or answer.state ~= "done" or not answer.ok then return nil end
  local pending
  for row in (answer.stdout or ""):gmatch("[^\r\n]+") do
    local f = {}; for item in (row .. "\t"):gmatch("(.-)\t") do f[#f + 1] = decode(item) end
    if f[1] == "mode-plan" and #f == 8 then
      pending = { kind = "modeenable", token = f[2], source = f[3], conversation = f[4], title = f[5],
        source_profile = f[6], expires = tonumber(f[7]), proof_ready = f[8] == "ready", profiles = {}, identities = {} }
    elseif f[1] == "mode-account" and #f == 5 and pending then
      pending.profiles[#pending.profiles + 1] = f[2]
      pending.identities[f[2]] = f[3] .. " — " .. f[4] .. " — " .. f[5]
    end
  end
  return pending
end
local function pending_review() return state.pending or mode_review() end
local function submit_confirmation()
  local p = pending_review()
  if not p or not ready_to_confirm or p.token ~= displayed_confirmation then return end
  state.pending = nil; state.focus = 1
  if p.kind == "modeenable" then
    ask({ "mode-enable", p.token, "--consent" }); state.screen = "conversations"
  elseif p.kind == "verify" then
    local args = { "verify-shared" }; for _, name in ipairs(p.profiles) do args[#args + 1] = name end; ask(args, true)
  elseif p.kind == "enable" then
    local args = { "enable-shared", "--session", p.source, "--consent" }
    for _, arg in ipairs(profile_args(p.profiles)) do args[#args + 1] = arg end
    ask(args); state.screen = "conversations"
  elseif p.kind == "stop" then ask({ "desktop-stop", p.source }) end
end

dispatch = function(id)
  if id == "accounts.open" then
    if state.login_profile then state.login_profile = nil; state.screen = "accounts"; refresh(); command("focus", { text = "accounts" })
    else state.conversation = nil; state.screen = store.selected and "conversations" or "accounts"; command("focus", { text = "accounts", toggle = true }) end
    return true
  end
  if id:sub(1, 9) == "accounts." then id = id:sub(10) end
  if id == "settings" then command("action", { text = "settings.open" }); return true end
  if id == "done-login" then state.login_profile = nil; refresh(); return true end
  if id == "cancel" then state.pending = nil; refresh(); state.focus = 1; return true end
  if busy() then return true end
  if id == "confirm" then submit_confirmation(); return true end
  local m, p = model(), account(model()); local c = conversation(m)
  if id == "refresh" then refresh()
  elseif id == "accounts" or id == "conversations" then navigate(id)
  elseif id == "add-form" then state.add_form = not state.add_form; state.focus = 1
  elseif id == "add" then state.added_label = value("nickname"); ask({ "pane-add", value("nickname") })
  elseif id == "login" then launch_login(p)
  elseif id == "status" and p then ask({ "status", p.name })
  elseif id == "new-form" then
    if not p or not p.saved then navigate("accounts"); state.message = "Choose an account and click Log in before starting a conversation."
    else state.screen = "conversations"; state.new_form = not state.new_form; state.focus = 1 end
  elseif id == "create" and p then
    local folder = value("repo", default_folder())
    if folder == "" then state.message = "Choose a project below or paste its folder path."; return true end
    local name = value("title"); if name == "" then name = p.label .. " - " .. (folder:gsub("/+$", ""):match("[^/]+$") or "Conversation") end
    ask({ "start", p.name, "--repo", folder, "--name", name }); state.new_form = false
  elseif (id == "open" or id == "open-conversation") and c then store.selected = c.id; command("focus", { text = "agent" })
  elseif id == "stop" and c then start_confirmation("stop", m)
  elseif id == "resume" and c then ask({ "desktop-start", c.id })
  elseif id == "mode-off" and c and c.shared then ask({ "mode-off", "--session", c.id })
  elseif id == "mode-on" and c and c.shared then ask({ "mode-on", "--session", c.id })
  elseif id == "switch" and c and c.shared and c.mode ~= "off" and c.next ~= "" then ask({ "switch", "--session", c.id, "--expected-profile", c.next })
  elseif id == "recover" and c and c.conversation ~= "" then ask({ "recover-shared", c.conversation })
  elseif id == "sharing" and c then navigate("sharing")
  elseif id == "mode-verify" then
    local review = mode_review()
    if review then
      state.confirmation_number = (state.confirmation_number or 0) + 1
      state.pending = {kind = "verify", token = state.confirmation_number, profiles = review.profiles,
        identities = review.identities, title = review.title}
      state.focus = 1
    end
  elseif id == "verify" or id == "enable" then
    if #group(m) < 2 then state.message = "Select at least two accounts, in the order you want to use them."
    elseif id == "enable" and (not c or not c.stopped or c.shared) then state.message = "Select an ordinary conversation and stop it after its tools finish."
    elseif id == "enable" then
      local args = { "mode-preview", "--session", c.id }
      for _, arg in ipairs(profile_args(group(m))) do args[#args + 1] = arg end
      ask(args)
    else start_confirmation(id, m) end
  elseif id == "more-accounts" then state.account_page = ((state.account_page or 0) + 1) % math.max(1, math.ceil(#m.accounts / 4))
  elseif id == "more-conversations" then state.conversation_page = ((state.conversation_page or 0) + 1) % math.max(1, math.ceil(#m.conversations / 4))
  elseif id:sub(1, 8) == "account:" then state.account = id:sub(9); state.added_label = nil
  elseif id:sub(1, 13) == "conversation:" then state.conversation = id:sub(14); state.selection_base = store.selected
  elseif id:sub(1, 6) == "share:" then
    local name, found, names = id:sub(7), false, {}
    for _, selected in ipairs(group(m)) do if selected == name then found = true else names[#names + 1] = selected end end
    if not found then names[#names + 1] = name end; state.sharing = names
  elseif id:sub(1, 8) == "project:" then
    local path = projects()[tonumber(id:sub(9)) or 0]; if path then state.repo = textinput.new(path) end
  elseif id:sub(1, 6) == "field:" then
    for index, name in ipairs(controls) do if name == id then state.focus = index end end
  elseif id == "details" then state.details = not state.details
  else return false end
  return true
end

return {
  name = "accounts", slot = "center", slot_mode = "switch", pure = true,
  focusable = true, input = "session", capabilities = { "run", "program" },
  keys = { { key = "f7", action = "accounts.open", desc = "Accounts", scope = "global" } },
  commands = {
    { action = "accounts.mode-on", desc = "Enable approved switching mode for this conversation" },
    { action = "accounts.mode-off", desc = "Disable account switches for this conversation" },
    { action = "accounts.mode-verify", desc = "Review paid compatibility check for switching mode" },
    { action = "accounts.accounts", desc = "Show logins and account for new conversations" },
    { action = "accounts.conversations", desc = "Show account conversations" },
    { action = "accounts.add-form", desc = "Add another account" },
    { action = "accounts.add", desc = "Add the named account" },
    { action = "accounts.login", desc = "Log in to the selected account" },
    { action = "accounts.status", desc = "Check selected account login" },
    { action = "accounts.new-form", desc = "Start a new account conversation" },
    { action = "accounts.create", desc = "Create the configured conversation" },
    { action = "accounts.open-conversation", desc = "Open selected conversation" },
    { action = "accounts.stop", desc = "Review stopping selected conversation" },
    { action = "accounts.resume", desc = "Resume selected conversation" },
    { action = "accounts.switch", desc = "Switch selected conversation to next account" },
    { action = "accounts.sharing", desc = "Set up account switching" },
    { action = "accounts.verify", desc = "Review compatibility check" },
    { action = "accounts.enable", desc = "Review selected account sharing" },
    { action = "accounts.confirm", desc = "Confirm the displayed operation" },
    { action = "accounts.cancel", desc = "Cancel the displayed operation" },
    { action = "accounts.refresh", desc = "Refresh account information" },
  },
  pills = { { action = "accounts.open", label = "Accounts", priority = 10 } },
  render = function(ctx)
    controls = {}; width = math.max(16, (ctx.width or 80) - 4); ready_to_confirm = false; displayed_confirmation = nil
    local children = {}
    local function add(node) children[#children + 1] = node end
    local function say(text) add(line(text)) end
    local function click(text, id) add(button(text, id)) end
    if not run then
      say("One-time setup: allow Accounts to connect to Claude.")
      say("1. Open Settings below. Choose Interface and select Accounts.")
      say("2. Choose Trust and allow Run and Program, then return here.")
      say("Run checks your accounts; Program opens Claude's native login. You choose which accounts to connect.")
      click("Open Settings", "settings"); click("Back to conversation", "accounts.open")
    elseif state.login_profile then
      say("Sign in to " .. state.login_profile .. " using the native Claude prompt and browser below.")
      click("Done / Back to accounts (F7)", "done-login")
      add({ type = "surface", program = "accounts-" .. state.login_profile })
    else
      run(data_key(), BASE .. " pane-state" .. (store.selected and " --session " .. quote(store.selected) or ""), { machine = "local", timeout = 30, ttl = 3 })
      local m = model(); local p, c = account(m), conversation(m)
      if m.indicator then say(m.indicator) end
      if not m.ready then
        say(m.error and "Couldn't connect to the account helper installed in this terminal." or "Loading your accounts…")
        if m.error then
          say("If this is Windows, run Thurbox and this extension inside WSL. Update/install the extension in that same terminal.")
          click(state.details and "Hide details" or "Show details", "details")
          if state.details then say(m.error:sub(1, 1500)) end
        end
        click("Refresh", "refresh"); click("Back to conversation", "accounts.open")
      elseif pending_review() then
        local pending = pending_review()
        say(pending.kind == "verify" and "Check these accounts before enabling switching?" or (pending.kind == "enable" or pending.kind == "modeenable") and "Enable switching mode for this conversation?" or "Stop this conversation?")
        if pending.title then say("Conversation: " .. pending.title) end
        local rows = 0; for _, node in ipairs(children) do rows = rows + node.len end
        for index, name in ipairs(pending.profiles) do
          local identity = pending.identities and pending.identities[name] or name
          if not pending.identities then for _, item in ipairs(m.accounts) do if item.name == name then identity = name .. " — " .. item.email end end end
          local node = line(tostring(index) .. ". " .. identity); add(node); rows = rows + node.len
        end
        local explanation = pending.kind == "verify" and "This uses account allowance for synthetic checks (six requests plus a subagent for two accounts, up to $0.25 per top-level request). It does not send an existing conversation. It may take several minutes."
          or (pending.kind == "enable" or pending.kind == "modeenable") and "These accounts and their organizations can use this conversation's context. Only this history and its sidecars are shared. Logins stay separate. This approval applies to later one-click switches."
          or "Stop only after tools and subagents finish. Conversation history is retained."
        if pending.kind == "modeenable" then
          explanation = explanation .. " An untracked original keeps its files; already account-managed history uses the existing move/link setup. Off later prevents switches without erasing prior access."
          if not pending.proof_ready then explanation = explanation .. " Compatibility check is required first; an exhausted account can block it." end
        end
        local node = line(explanation); add(node); rows = rows + node.len
        ready_to_confirm = (ctx.height or 0) >= rows + 7
        displayed_confirmation = pending.token
        if pending.kind == "modeenable" and not pending.proof_ready then
          ready_to_confirm = false
          if (ctx.height or 0) >= rows + 7 then click("Review compatibility check…", "mode-verify")
          else say("Enlarge this pane to read the compatibility notice.") end
        elseif ready_to_confirm then click(pending.kind == "verify" and "Run compatibility check" or (pending.kind == "enable" or pending.kind == "modeenable") and "Allow switching for these accounts" or "Stop conversation", "confirm")
        else say("Enlarge this pane to read all details before continuing.") end
        click("Cancel", "cancel")
      else
        click("Logins / new conversations", "accounts"); click("Current conversation / conversations", "conversations")
        if busy() then say("Working… Please wait. Compatibility checks can take several minutes.")
        elseif state.message then say(state.message)
        else
          local answer = result()
          if answer and answer.state == "done" then say((answer.ok and answer.stdout or answer.stderr or answer.error or "Operation failed"):sub(1, 500)) end
        end
        if (state.screen or (m.current and "conversations" or "accounts")) == "accounts" then
          say(#m.accounts == 0 and "1. Add your first account" or "Accounts for login / new conversations. Selecting one does not switch existing work.")
          for _, item in ipairs(page_rows(m.accounts, state.account_page)) do
            click((p and p.name == item.name and "Selected: " or "") .. item.label .. " — " .. (item.saved and item.email or "Login required"), "account:" .. item.name)
          end
          if #m.accounts > 4 then click("More accounts", "more-accounts") end
          if p then click("Log in to " .. p.label, "login"); click("Check login", "status"); click("Add another account", "add-form") end
          if #m.accounts == 0 or state.add_form then
            say("Give this account a name you will recognize, for example Work A.")
            add(input("nickname", "Account name")); click("Add account", "add")
          end
          if p then say("Finish native browser/SSO login for each account, then open Conversations.") end
        elseif state.screen == "sharing" then
          say("3. Set up switching for " .. (c and c.name or "a conversation"))
          say("Select accounts below in the order you want to use them.")
          local names = group(m)
          for _, item in ipairs(page_rows(m.accounts, state.account_page)) do
            local order; for i, name in ipairs(names) do if name == item.name then order = i end end
            click((order and tostring(order) .. ". " or "+ ") .. item.label, "share:" .. item.name)
          end
          if #m.accounts > 4 then click("More accounts", "more-accounts") end
          say("Check compatibility once, then approve sharing for this conversation.")
          click("Check compatibility…", "verify"); click("Review and enable mode…", "enable")
          if c and not c.stopped then say("Finish tools and shell jobs, then stop this conversation in Thurbox before enabling."); if not c.external then click("Stop conversation…", "stop") end end
          click("Back to conversations", "conversations")
        else
          if state.new_form and p then
            say("New conversation using " .. p.label)
            for i, path in ipairs(projects()) do if i <= 1 then click("Use project: " .. path, "project:" .. tostring(i)) end end
            add(input("repo", "Project folder — choose above or paste a path", default_folder()))
            add(input("title", "Conversation name (optional)")); click("Create conversation", "create"); click("Cancel", "new-form")
          else
            say(m.unsupported or "Current conversation and account-managed conversations")
            for _, item in ipairs(page_rows(m.conversations, state.conversation_page)) do
              click((c and c.id == item.id and "Selected: " or "") .. item.name .. " — " .. (item.external and "Existing conversation" or label(m, item.profile)), "conversation:" .. item.id)
            end
            if #m.conversations > 4 then click("More conversations", "more-conversations") end
            if c then
              say("Conversation: " .. c.name)
              say((c.shared and c.phase ~= "active" and "Last confirmed account: " or "Current account: ") .. ((c.external or c.profile == "") and "unverified" or label(m, c.profile)) .. " | " .. (c.stopped and "Stopped" or "Running"))
              say("Account switching: " .. (c.shared and c.phase ~= "active" and "Needs recovery" or c.shared and c.mode ~= "off" and "On" or "Off"))
              if c.shared and c.phase == "active" then click(c.mode == "off" and "Turn switching On" or "Turn switching Off", c.mode == "off" and "mode-on" or "mode-off") end
              if c.shared and c.mode ~= "off" and c.phase == "active" and c.next ~= "" then click("Switch to " .. label(m, c.next), "switch") end
              if c.phase == "failed" or c.phase == "switching" then click("Recover conversation", "recover")
              elseif c.external then click("Back to this conversation", "open")
              elseif c.stopped then click("Resume conversation", "resume") else click("Open conversation", "open"); click("Stop conversation…", "stop") end
              if not c.shared then click("Turn switching mode On…", "sharing") end
            else say("Start a conversation here to use it with your selected account.") end
            if p then click("New conversation using " .. p.label, "new-form") else say("Add and log in to an account first.") end

          end
        end
        click("Refresh", "refresh"); click("Back to conversation", "accounts.open")
        say("Click a button or field. Tab moves focus; Enter chooses. F7 opens/closes Accounts.")
      end
    end
    return ui.panel({ title = "Claude Accounts", focused = ctx.focused, body = children })
  end,
  ui_state = function()
    local m = model(); local c = conversation(m); local p = pending_review()
    return { conversation = c and c.id, current_profile = c and c.profile,
      switching_mode = c and c.shared and (c.mode == "off" and "off" or "on") or "off",
      pending = p and p.kind, busy = busy() }
  end,
  on_action = dispatch,
  on_click = function(hit) if hit.id then return dispatch(hit.id) end return false end,
  on_key = function(key)
    if state.login_profile then return false end
    if key.key == "tab" then state.focus = ((state.focus or 1) % math.max(1, #controls)) + 1; return true end
    local id = controls[state.focus or 1] or ""
    if key.key == "enter" then
      if id == "field:nickname" then return dispatch("add") end
      if id == "field:repo" or id == "field:title" then return dispatch("create") end
      return dispatch(id)
    end
    if id:sub(1, 6) == "field:" then
      local name = id:sub(7); local input = field(name, name == "repo" and default_folder() or "")
      if textinput.key(input, key) then state[name] = input; return true end
    end
    return false
  end,
}
