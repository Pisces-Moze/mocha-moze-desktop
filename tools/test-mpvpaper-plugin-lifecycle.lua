-- Test the actual patched service with a sandbox API double; no player launches.
local source = assert(arg[1], "service source required")
local commands, persisted = {}, nil
local function copy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for k, v in pairs(value) do result[k] = copy(v) end
  return result
end
local config = {hardware_decode=true, hardware_backend="v4l2request",
  release_when_fullscreen=true, auto_pause="full", mute=true,
  run_as_systemd=false, extract_last_frame=false, mpv_options="profile=fast"}
noctalia = {
  setUpdateInterval=function() end,
  getenv=function(name) if name == "HOME" then return "/mock-home" end end,
  getConfig=function(key) return config[key] end,
  commandExists=function() return true end,
  outputs=function() return {{name="DSI-1"}} end,
  fileExists=function(path) return type(path) == "string" and path:match("%.mp4$") ~= nil end,
  readFile=function() return persisted and "saved-state" or nil end,
  writeFile=function(_, content) assert(content == "saved-state") end,
  json={encode=function(value) persisted=copy(value);return "saved-state" end,
        decode=function() return copy(persisted) end},
  state={set=function() end, watch=function() end},
  setWallpaper=function() end, setWallpaperEnabled=function() end,
  notifyError=function(_, message) error(message) end, log=function() end,
  listDir=function() return {} end,
  runAsync=function(command, callback)
    table.insert(commands, command)
    if callback then callback({stdout="--auto-mode", exitCode=0}) end
  end,
}
local function has_command(fragment)
  for _, command in ipairs(commands) do
    if command:find(fragment, 1, true) then return true end
  end
  return false
end
local video="/mock-home/video/动画 wallpaper 'a'.mp4"
dofile(source)
onIpc("set-video", video)
assert(persisted.assignments["*"] == video)
assert(has_command("--auto-stop --auto-mode FULL"))
assert(has_command("hwdec=v4l2request"))
assert(has_command("mpvpaper(-holder)?"))
onIpc("clear-all", "")
assert(next(persisted.assignments) == nil)
assert(persisted.lastAssignments["*"] == video)
onIpc("reapply", "")
assert(persisted.assignments["*"] == video)
onExit(15)
assert(persisted.assignments["*"] == video)
commands={}
dofile(source)
assert(has_command("--auto-stop --auto-mode FULL"))
assert(has_command("hwdec=v4l2request"))
assert(persisted.assignments["*"] == video)
print("PLUGIN_MANAGED_SELECTION_CLEAR_REAPPLY_AND_RESTART_PASSED")
