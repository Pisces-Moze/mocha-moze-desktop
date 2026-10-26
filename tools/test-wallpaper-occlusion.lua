-- SPDX-License-Identifier: GPL-3.0-only
-- Exercise the actual service against session, multi-output and pressure changes.
local now, memory = 0, 512
local commands, state, persisted, hints = {}, {}, nil, {}
local outputs = {{name="DSI-1"}}
local config = {release_when_covered=true,covered_hold_seconds=2,pause_on_pressure=true,
  pause_on_cpu_pressure=false,pressure_hold_seconds=3,pressure_recovery_seconds=15,
  pressure_low_mib=128,pressure_resume_mib=256,hardware_decode=true,
  hardware_backend="v4l2request",auto_pause="full",release_when_fullscreen=true}
local function copy(v)
  if type(v)~="table" then return v end
  local t={};for k,x in pairs(v) do t[k]=copy(x) end;return t
end
noctalia={
  nowMs=function()return now*1000 end,setUpdateInterval=function()end,
  getenv=function(k)return ({HOME="/mock",NIRI_SOCKET="/run/user/1000/niri.wayland-1.42.sock",XDG_RUNTIME_DIR="/run/user/1000"})[k]end,
  getConfig=function(k)return config[k]end,commandExists=function()return true end,
  outputs=function()return outputs end,fileExists=function()return true end,
  readFile=function(p)
    if p=="/proc/42/comm" then return "niri\n" end
    if p=="/proc/meminfo" then return "MemAvailable: " .. (memory*1024) .. " kB\n" end
    if p:find("/proc/pressure/",1,true) then return "some avg10=0\nfull avg10=0\n" end
    local encoded=p:match("background%-42%-(%x+)%.json$")
    if encoded then return hints[encoded] and encoded or nil end
    return nil
  end,
  writeFile=function()end,
  json={encode=function(v)persisted=copy(v);return "saved-state"end,
    decode=function(v)return hints[v] and copy(hints[v]) or nil end},
  state={set=function(k,v)state[k]=copy(v)end,watch=function()end},
  setWallpaper=function()end,setWallpaperEnabled=function()end,
  notifyError=function(_,v)error(v)end,log=function()end,listDir=function()return {}end,
  runAsync=function(cmd,callback)
    commands[#commands+1]=cmd
    if callback then callback({exitCode=0,stdout=cmd:find("socat",1,true) and '{"data":12.5}' or "--auto-mode"}) end
  end,
}
local function launches()
  local n=0;for _,c in ipairs(commands) do if c:find("exec mpvpaper ",1,true) then n=n+1 end end;return n
end
local function tick(t)now=t;update()end
local function hint(name, visible, extra)
  local encoded=name:gsub(".",function(c)return string.format("%02x",c:byte())end)
  hints[encoded]={schema=1,pid=42,output=name,visible=visible}
  for k,v in pairs(extra or {})do hints[encoded][k]=v end
end
dofile(assert(arg[1]))
onIpc("set-video","/mock/video.mp4")
tick(0);tick(3);assert(launches()==1,"missing producer must leave playback running")
hint("DSI-1",false);tick(4);tick(5);assert(not state.covered["*"])
tick(6);assert(state.covered["*"] and state.paused["*"],"fully hidden background releases resources")
local n=#commands;tick(9);assert(#commands==n,"do not repeatedly stop an already released player")
hint("DSI-1",false,{overview=true});tick(10)
assert(launches()==2 and not state.covered["*"],"overview restores playback")
hint("DSI-1",false,{shell_overlay=true});tick(11);tick(14)
assert(launches()==2 and not state.covered["*"],"shell panel must not pause playback")
hint("DSI-1",true);tick(15);assert(launches()==2,"X-Ray-visible background stays running")
outputs={{name="DSI-1"},{name="HDMI-A-1"}}
hint("DSI-1",false);hint("HDMI-A-1",true);tick(16);tick(20)
assert(not state.covered["*"],"one visible output keeps a wildcard player running")
hint("HDMI-A-1",false);tick(21);tick(23);assert(state.covered["*"])
memory=50;tick(24);hint("DSI-1",true);tick(25)
assert(state.resourcePaused and launches()==2,"revealing a window must not bypass memory pressure")
memory=512;tick(26);tick(41);assert(launches()==3)
hint("DSI-1",false);tick(42);tick(44);assert(state.covered["*"])
hint("DSI-1",false,{pid=123});tick(45)
assert(launches()==4 and not state.covered["*"],"a stale compositor generation fails open")
hint("DSI-1",false);tick(46);tick(48);assert(state.covered["*"])
onIpc("set-static","/mock/static.png");hint("DSI-1",true);tick(49)
assert(launches()==4 and next(persisted.assignments)==nil,"occlusion recovery must not resurrect a cleared video")
print("OCCLUSION_OVERVIEW_PANELS_XRAY_MULTIOUTPUT_PRESSURE_AND_STALE_SESSION_PASSED")
outputs={{name="DSI-1"}}
onIpc("set-video","/mock/video.mp4")
local started=launches()
hint("DSI-1",true,{schema=2,workarea_covered=true});tick(50);tick(52)
assert(state.covered["*"] and state.paused["*"],"covered workspace releases despite visible blur/gaps")
hint("DSI-1",true,{schema=2,workarea_covered=true,overview=true});tick(53)
assert(launches()==started+1 and not state.covered["*"],"overview overrides workarea coverage")
hint("DSI-1",true,{schema=2,workarea_covered=true,shell_overlay=true});tick(54);tick(57)
assert(not state.covered["*"],"panels preserve live wallpaper")
hint("DSI-1",true,{schema=2,workarea_covered=true});tick(58);tick(60)
assert(state.covered["*"])
hint("DSI-1",true,{schema=3,workarea_covered=true});tick(61)
assert(not state.covered["*"],"unknown schema cannot freeze playback")
hint("DSI-1",true,{schema=2,workarea_covered=false});tick(62);tick(65)
assert(not state.covered["*"],"partially exposed workspace stays live")
config.release_when_covered=false
hint("DSI-1",true,{schema=2,workarea_covered=true});tick(66);tick(70)
assert(not state.covered["*"],"user coverage switch remains authoritative")
onIpc("set-static","/mock/static.png")
print("WORKSPACE_COVERAGE_SCHEMA2_OVERVIEW_PANELS_SETTINGS_AND_FUTURE_SCHEMA_PASSED")
