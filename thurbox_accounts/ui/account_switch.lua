-- Conversation account strip and inline switch chooser. All writes use the CLI.
local theme = require("lib.theme")
local modal = require("lib.modal")
local widgets = require("lib.widgets")
local BASE = @BASE@
local controls, displayed_plan, ready = {}, nil, false
local dispatch
local function quote(s) return "'" .. tostring(s):gsub("'", "'\\''") .. "'" end
local function decode(s) return (s or ""):gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end) end
local function fields(row)
  local f = {}; for value in (row .. "\t"):gmatch("(.-)\t") do f[#f + 1] = decode(value) end; return f
end
local function result() return (thurbox.runs or {})[state.request_key or "none"] end
local function busy() local r=result(); return state.request_key ~= nil and (not r or r.state ~= "done") end
local function completed()
  local r=result()
  return r and r.state=="done" and r.ok and (state.operation=="confirm" or state.operation=="select" and (r.stdout or ""):match("^switch%-complete"))
end
local function opened() return state.open and not completed() end
local function model(request)
  local m={accounts={}}
  local selected = store.selected
  if not selected then m.label="Account: no conversation selected"; return m end
  local session
  for _, row in ipairs(thurbox.sessions or {}) do if row.id == selected then session = row; break end end
  if not session then m.label="Account: no conversation selected"; return m end
  if session.agent == "codex" then m.label="Account: default | Codex"; return m end
  if not run then m.label="Account: allow account-switch in Settings > Interface"; return m end
  local key = "account-status-" .. selected .. "-" .. tostring(state.number or 0) .. (busy() and "-pending" or "-done")
  if request then run(key, BASE .. " pane-state --session " .. quote(selected), { machine = "local", timeout = 30, ttl = 3 }) end
  local answer = (thurbox.runs or {})[key]
  if not answer or answer.state ~= "done" then m.label="Account: checking…"; return m end
  if not answer.ok then m.label="Account: unavailable | F7 for Accounts"; return m end
  m.label="Account: unverified | F7 Accounts"; m.loaded=true
  for row in (answer.stdout or ""):gmatch("[^\r\n]+") do
    local f=fields(row)
    if f[1]=="indicator" and f[2]==selected then m.label="Account: "..f[4].." | "..f[5].." | F7 Accounts"
    elseif f[1]=="account" then m.accounts[#m.accounts+1]={name=f[2],label=f[3],email=f[4],saved=f[5]=="saved"}
    elseif f[1]=="inline" and f[2]==selected then m.current=f[3]; m.kind=f[4]; m.phase=f[5]; m.mode=f[6]
    elseif f[1]=="conversation" and f[2]==selected then m.native=f[9] end
  end
  return m
end
local function summary(request) return model(request).label end
local function plan()
  if state.operation~="select" then return nil end
  local r=result(); if not r or r.state~="done" or not r.ok then return nil end
  local p
  for row in (r.stdout or ""):gmatch("[^\r\n]+") do
    local f=fields(row)
    if f[1]=="switch-plan" then p={id=f[2],session=f[3],source=f[4],target=f[5],proof=f[6]=="ready",approved=f[7]=="approved",title=f[8],accounts={}}
    elseif f[1]=="switch-account" and p then p.accounts[#p.accounts+1]={name=f[2],label=f[3],email=f[4],org=f[5]} end
  end
  return p
end
local function ask(operation,args,long)
  if not run or busy() then return end
  if state.request_key and run_forget then run_forget(state.request_key) end
  state.number=(state.number or 0)+1; state.operation=operation; state.request_key="account-switch-"..state.number
  state.focus=1
  local parts={BASE,"--desktop-deadline",long and "900" or "180","pane-run"}
  for _,arg in ipairs(args) do parts[#parts+1]=quote(arg) end
  run(state.request_key,table.concat(parts," "),{machine="local",timeout=long and 930 or 210,refresh=true})
end
local function reset()
  state.request_key=nil; state.operation=nil; state.review_check=nil; state.focus=1
end
local function targets(m)
  local rows={}; for _,p in ipairs(m.accounts) do if p.saved and p.name~=m.current then rows[#rows+1]=p end end; return rows
end
dispatch=function(id)
  if id=="account-switch.open" then
    if busy() then return true end
    reset(); state.open=true; state.session=store.selected; state.page=0; return true
  end
  if not opened() then return false end
  id=id:gsub("^account%-switch%.","")
  if busy() then return true end
  if id=="close" then state.open=false; reset(); return true end
  if id=="settings" then state.open=false; command("action",{text="settings.open"}); return true end
  if store.selected~=state.session then return true end
  local m=model(); local p=plan()
  if id=="back" then reset(); return true
  elseif id=="accounts" then state.open=false; command("action",{text="accounts.open"}); return true
  elseif id=="attach" then state.open=false; command("action",{text="accounts.conversations"}); command("focus",{text="accounts"}); return true
  elseif id=="on" and m.mode=="off" then ask("on",{"mode-on","--session",state.session})
  elseif id=="recover" and m.phase and m.phase~="active" then ask("recover",{"recover-shared","--session",state.session})
  elseif id=="more" then state.page=((state.page or 0)+1)%math.max(1,math.ceil(#targets(m)/4)); state.focus=1
  elseif id:sub(1,7)=="target:" and m.phase=="active" and m.mode~="off" then
    for _,target in ipairs(targets(m)) do
      if target.name==id:sub(8) then state.target=target.name; ask("select",{"simple-select","--session",state.session,"--to",target.name}); return true end
    end
  elseif id=="check" and p and not p.proof then state.review_check=true; state.focus=1
  elseif id=="verify" and p and state.review_check and ready and displayed_plan==p.id then
    local args={"verify-shared"}; for _,account in ipairs(p.accounts) do args[#args+1]=account.name end
    state.review_check=nil; ask("verify",args,true)
  elseif id=="review" and state.target then
    state.review_check=nil; ask("select",{"simple-select","--session",state.session,"--to",state.target})
  elseif id=="confirm" and p and p.proof and ready and displayed_plan==p.id then ask("confirm",{"simple-confirm",p.id,"--consent"}) end
  return true
end
return {
  name="account-switch",slot="float",order=63,pure=true,focusable=false,floats=true,
  capabilities={"run"},
  commands={
    {action="account-switch.open",desc="Switch account for the current conversation"},
    {action="account-switch.confirm",desc="Approve the displayed conversation account switch"},
    {action="account-switch.verify",desc="Run the displayed paid compatibility check"},
    {action="account-switch.close",desc="Close the account chooser"},
  },
  ui_state=function() local p=plan(); return {label=opened() and summary() or "",selected=store.selected,open=opened() or false,
    busy=busy(),operation=state.operation,plan=p and p.id,ready=ready,source=state.session,target=state.target} end,
  on_action=function(action) if action:sub(1,15)=="account-switch." then return dispatch(action) end; return false end,
  on_click=function(hit) if hit.id then return dispatch(hit.id) end; return opened() or false end,
  on_outside=function() if opened() then if not busy() then state.open=false; reset() end; return true end; return false end,
  on_key=function(key)
    if not opened() then return false end
    if busy() then return true end
    if key.key=="esc" then dispatch("close")
    elseif key.key=="tab" or key.key=="down" then state.focus=((state.focus or 1)%math.max(1,#controls))+1
    elseif key.key=="up" then state.focus=((state.focus or 1)-2)%math.max(1,#controls)+1
    elseif key.key=="enter" and controls[state.focus or 1] then dispatch(controls[state.focus or 1]) end
    return true
  end,
  render=function(ctx)
    controls={}; ready=false; displayed_plan=nil
    if not opened() then return {type="text",text=""} end
    local m=model(true)
    local body={}; local cols=math.max(24,math.min(78,(ctx.width or 80)-2)); local width=cols-4; local rows=2
    local function say(value)
      -- Explicit column wrapping keeps the consent height exact. Word wrapping
      -- can require more rows than ceil(total_columns / width).
      local lines,chars,used={},{},0
      for _,codepoint in utf8.codes(value) do
        local char=utf8.char(codepoint); local columns=widgets.len(char)
        if char=="\n" or used+columns>width then
          lines[#lines+1]=table.concat(chars); chars={}; used=0
        end
        if char~="\n" then chars[#chars+1]=char; used=used+columns end
      end
      lines[#lines+1]=table.concat(chars)
      local n=#lines; body[#body+1]={type="text",text=table.concat(lines,"\n"),len=n,wrap=false}; rows=rows+n
    end
    local function button(label,id)
      controls[#controls+1]=id
      body[#body+1]={type="text",text="[ "..label.." ]",len=1,id=id,role="button",
        style={fg=theme.accent,bg=#controls==(state.focus or 1) and theme.selection_bg or nil}}; rows=rows+1
    end
    local p=plan(); local answer=result()
    if busy() then
      say(state.operation=="verify" and "Checking account compatibility… This can take several minutes." or "Waiting for Claude to pause safely… Idle confirmation can take about a minute.")
      say("The operation is in progress. Its result will appear here.")
    elseif not run then
      say("One-time setup: allow Run for account-switch in Settings → Interface.")
      button("Open Settings","settings"); button("Close","close")
    elseif store.selected~=state.session then
      say("The selected conversation changed. Open Switch account again for the conversation you want.")
      button("Close","close")
    elseif answer and answer.state=="done" and not answer.ok then
      say((answer.stderr or answer.error or "Account operation failed"):sub(1,900))
      button("Choose account again","back"); button("Close","close")
    elseif p then
      say("Conversation: "..p.title)
      local source_label,target_label=p.source,p.target
      for _,a in ipairs(p.accounts) do if a.name==p.source then source_label=a.label end; if a.name==p.target then target_label=a.label end end
      say("Switch "..source_label.." → "..target_label)
      say(state.review_check and "Run the compatibility check?" or "Allow these accounts to use this conversation?")
      for _,account in ipairs(p.accounts) do say(account.label.." — "..account.email.." — "..account.org) end
      if state.review_check then
        say("This sends synthetic test requests using these accounts' allowance (up to $0.25 per top-level request). It sends no existing conversation. An exhausted account can prevent this check.")
      else
        say("These accounts and organizations can access this conversation's context. Its history stays local; logins remain separate. Later switches between these approved accounts reuse this approval.")
        if not p.proof then say("A one-time compatibility check is required first. Prepare accounts before they reach their usage limit.") end
      end
      -- Only a fully visible frozen account list and notice may be confirmed.
      ready=(ctx.height or 0)>=rows+3; displayed_plan=p.id
      if ready then
        if state.review_check then button("Run compatibility check","verify")
        elseif p.proof then button("Allow and switch account","confirm") else button("Review compatibility check…","check") end
        button("Choose a different account","back"); button("Cancel","close")
      else
        body={}; rows=2; controls={}
        say("Enlarge the window to review the account identities and sharing notice before continuing.")
        button("Cancel","close")
      end
    elseif state.operation=="verify" then
      say("Compatibility check passed. Review the conversation's sharing approval to continue.")
      button("Continue","review"); button("Cancel","close")
    elseif not m.loaded then
      say(m.label); button("Close","close")
    elseif not m.current then
      say("This conversation was started without a named account and has no switching guard.")
      say("For easy switching, use Ctrl+N and choose a named Claude account. An existing conversation can only be attached after its source is safely stopped and verified.")
      button("Existing conversation setup","attach"); button("Manage logins","accounts"); button("Close","close")
    elseif m.phase~="active" then
      say("The previous switch needs recovery. History is preserved; another account will not be started until ownership is confirmed.")
      button("Recover conversation","recover"); button("Close","close")
    elseif m.mode=="off" then
      say("Switching is Off for this conversation. Turn it on to use its previously approved accounts.")
      button("Turn switching On","on"); button("Close","close")
    else
      say(m.label); say("Choose the account to continue this conversation with:")
      local list=targets(m); local first=(state.page or 0)*4+1
      for i=first,math.min(#list,first+3) do button("Switch to "..list[i].label,"target:"..list[i].name) end
      if #list==0 then say("Add and sign in to another account first."); button("Manage accounts","accounts") end
      if #list>4 then button("More accounts","more") end
      button("Close","close")
    end
    return modal.frame("Switch account",{cols=cols,rows=rows,children=body})
  end,
}
