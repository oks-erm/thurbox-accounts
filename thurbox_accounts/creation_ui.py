"""A checked, reversible adapter for the stock New session picker."""
import hashlib
import re

PRISTINE={'fe1fdea7ff2466f0db8b3e2e37880bda46e4467248ce7cc464303f1ffc51dde1'}
_ORIGINAL='local function agents()\n  return (thurbox and thurbox.agents) or {}\nend'
_ADAPTER='''-- BEGIN Thurbox Accounts picker
local function agents()
  local rows = {}
  for _, agent in ipairs((thurbox and thurbox.agents) or {}) do
    if agent.name ~= "claude-accounts" then
      local row = {}; for k, v in pairs(agent) do row[k] = v end
      if row.name:sub(1, #"Claude — ") == "Claude — " then
        row.command = row.name -- show the account, not the private wrapper path
      elseif row.name == "codex" then
        row.command = "default"
      elseif row.name == "claude" then
        row.command = "default / unmanaged"
      end
      rows[#rows + 1] = row
    end
  end
  return rows
end
local function accounts_creation_allowed()
  return thurbox.granted and thurbox.granted.sessions == true
end
-- END Thurbox Accounts picker'''


def adapt(source, *, owned=False):
    if not owned and hashlib.sha256(source.encode()).hexdigest() not in PRISTINE:
        raise ValueError('New session pane has custom edits or an unsupported version; preserved. Restore the stock pane in Settings → Interface, then rerun install.')
    if owned:
        pattern=r'-- BEGIN Thurbox Accounts picker\n.*?-- END Thurbox Accounts picker'
        if len(re.findall(pattern,source,flags=re.S))!=1:
            raise ValueError('Owned New session adapter markers changed; preserved')
        source=re.sub(pattern,lambda _: _ADAPTER,source,count=1,flags=re.S)
    else:
        if source.count(_ORIGINAL)!=1:
            raise ValueError('Unsupported New session picker; preserved')
        source=source.replace(_ORIGINAL,_ADAPTER,1)
    if '-- Thurbox Accounts creation permission' not in source:
        render_anchor='    local flow = load()\n    if not flow and type(store.fork)'
        gate='''    local flow = load()
    -- Thurbox Accounts creation permission
    if flow and not accounts_creation_allowed() then
      return modal.frame("One-time New session permission", {cols=70,rows=9,children={
        {type="text",len=3,wrap=true,text="Allow Sessions for new_session in Settings → Interface. This lets the normal picker create sessions with your selected account."},
        {type="text",len=1,text="[ Open Settings ]",role="action:settings.open"},
        {type="text",len=1,text="Enter opens Settings. Esc closes this dialog."},
      }})
    end
    if not flow and type(store.fork)'''
        source=source.replace(render_anchor,gate,1)
        source=source.replace('  on_key = function(key)','''  on_key = function(key)
    if load() and not accounts_creation_allowed() then
      if key.key=="esc" then save(nil); ask(nil)
      elseif key.key=="enter" then command("action",{text="settings.open"}) end
      return true
    end''',1)
        source=source.replace('  on_action = function(action)','''  on_action = function(action)
    if action:sub(1,12) == "new_session." and action ~= "new_session.open" and load() and not accounts_creation_allowed() then
      command("action",{text="settings.open"}); return true
    end''',1)
    return source.replace('frame("Coding Agent", height + 4,','frame("Agent / account", height + 4,')
