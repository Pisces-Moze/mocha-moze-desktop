-- Run the real service with delayed process and thumbnail callbacks.
local queue, commands, files, saved, versions = {}, {}, {}, {}, {}
local enabled, wallpaper = true, nil
local config = {hardware_decode=true,hardware_backend="v4l2request",auto_pause="full",
  release_when_fullscreen=true,extract_last_frame=true,run_as_systemd=false}
local function copy(v)
  if type(v)~="table" then return v end
  local out={};for k,x in pairs(v) do out[k]=copy(x) end;return out
end
local serial=0
noctalia={
  setUpdateInterval=function()end,getenv=function(n)if n=="HOME" then return "/mock" end end,
  getConfig=function(k)return config[k] end,commandExists=function()return true end,
  outputs=function()return {{name="DSI-1"}} end,
  fileExists=function(p)return files[p] or false end,
  readFile=function(p)return saved[p] end,
  writeFile=function(p,s)saved[p]=s end,
  json={encode=function(v)serial=serial+1;versions[tostring(serial)]=copy(v);return tostring(serial) end,
    decode=function(s)return copy(versions[s]) end},
  state={set=function()end,watch=function()end},
  setWallpaper=function(_,p)wallpaper=p end,
  setWallpaperEnabled=function(_,v)enabled=v end,
  notifyError=function(_,m)error(m)end,log=function()end,listDir=function()return {} end,
  runAsync=function(cmd,callback)
    commands[#commands+1]=cmd
    if callback then queue[#queue+1]={cmd,callback} end
  end,
}
local function flush(fragment)
  for i,item in ipairs(queue) do
    if item[1]:find(fragment,1,true) then
      table.remove(queue,i);item[2]({stdout="--auto-mode",exitCode=0});return
    end
  end
  error("missing callback: "..fragment)
end
local function state()
  return versions[saved["/mock/.local/state/noctalia/mpvpaper/assignments.json"]]
end
local video="/mock/动画 'video'.mp4"
local static="/mock/still.png"
files[video]=true;files[static]=true;files["/mock/other.png"]=true
dofile(assert(arg[1]))
flush("mpvpaper --help")

-- A pending video handover cannot launch after a newer static selection.
onIpc("set-video",video)
onIpc("set-static",static)
flush("pkill") -- superseded video stop callback
for _,cmd in ipairs(commands) do assert(not cmd:find("exec mpvpaper ",1,true)) end
flush("pkill")
assert(wallpaper==static and enabled and state().staticSelection==static)

-- The old 800 ms callback must not hide a newer static wallpaper.
onIpc("set-video",video);flush("pkill")
onIpc("set-static",static);flush("pkill")
flush("sleep 0.8")
assert(wallpaper==static and enabled and next(state().assignments)==nil)

-- A delayed frame extraction from clear-all must not overwrite static.
onIpc("set-video",video);flush("pkill")
onIpc("clear-all","");flush("pkill");flush("mkdir -p")
onIpc("set-static",static);flush("pkill")
files["/mock/.cache/noctalia/mpvpaper/__static.jpg"]=true
flush("ffmpeg -y")
assert(wallpaper==static and enabled)

-- Out-of-order requests obey the most recent selection.
onIpc("set-static",static);onIpc("set-static","/mock/other.png")
flush("pkill");flush("pkill")
assert(wallpaper=="/mock/other.png" and state().staticSelection==wallpaper)
onIpc("reapply","")
assert(next(state().assignments)==nil, "unlock must preserve an explicit static selection")
print("STATIC_HANDOVER_AND_DELAYED_CALLBACK_RACES_PASSED")
