local now, available, memoryPsi, cpuPsi = 0, 512, 0, 0
local commands, state, saved = {}, {}, nil
local config={hardware_decode=true,hardware_backend="v4l2request",auto_pause="full",
  release_when_fullscreen=true,extract_last_frame=false,run_as_systemd=false,
  pause_on_pressure=true,pause_on_cpu_pressure=true,pressure_low_mib=128,
  pressure_resume_mib=256,pressure_hold_seconds=3,pressure_recovery_seconds=15}
local function copy(v)
  if type(v)~="table" then return v end
  local out={};for k,x in pairs(v) do out[k]=copy(x) end;return out
end
local video="/mock/video.mp4"
noctalia={
  nowMs=function()return now*1000 end,setUpdateInterval=function()end,
  getenv=function(n)if n=="HOME" then return "/mock" end end,
  getConfig=function(k)return config[k]end,commandExists=function()return true end,
  outputs=function()return {{name="DSI-1"}}end,
  fileExists=function(p)return p==video or p=="/mock/static.png" or p:find("ipc-",1,true)~=nil end,
  readFile=function(p)
    if p=="/proc/meminfo" then return "MemAvailable: "..tostring(available*1024).." kB\n" end
    if p=="/proc/pressure/memory" then return "full avg10="..memoryPsi.." avg60=0 total=0\n" end
    if p=="/proc/pressure/cpu" then return "some avg10="..cpuPsi.." avg60=0 total=0\n" end
    return nil
  end,
  writeFile=function(_,v)assert(v=="state")end,
  json={encode=function(v)saved=copy(v);return "state"end,decode=function()return copy(saved)end},
  state={set=function(k,v)state[k]=copy(v)end,watch=function()end},
  setWallpaper=function()end,setWallpaperEnabled=function()end,
  notifyError=function(_,m)error(m)end,log=function()end,listDir=function()return {}end,
  runAsync=function(cmd,callback)
    commands[#commands+1]=cmd
    if callback then callback({exitCode=0,stdout=cmd:find("socat",1,true) and '{"data":37.5,"error":"success"}' or "--auto-mode"}) end
  end,
}
local function launches()
  local count=0;for _,cmd in ipairs(commands) do if cmd:find("exec mpvpaper ",1,true) then count=count+1 end end;return count
end
local function tick(t)now=t;update()end
dofile(assert(arg[1]))
onIpc("set-video",video);assert(launches()==1)
available=50;tick(0)
assert(state.resourcePaused and state.paused["*"],"critical pressure must release immediately")
local count=#commands;tick(1);assert(#commands==count,"do not respawn/release every tick")
available=200;tick(20);assert(launches()==1,"recovery must cross the high watermark")
onConfigChanged("mute",true)
available=512;tick(30);tick(44);assert(launches()==1)
tick(45);assert(launches()==2 and not state.resourcePaused)
local seek=false;for _,cmd in ipairs(commands) do if cmd:find("start=37.5",1,true) then seek=true end end
assert(seek,"restore saved playback position")
available=100;tick(50);available=512;tick(51)
assert(not state.resourcePaused,"ignore short pressure spikes")
cpuPsi=90;tick(60);tick(64);assert(state.resourcePaused)
config.pause_on_cpu_pressure=false;tick(65);tick(80)
assert(not state.resourcePaused,"disabled CPU policy must not block memory recovery")
config.pause_on_cpu_pressure=true;tick(81);tick(85);assert(state.resourcePaused)
onIpc("set-static","/mock/static.png")
cpuPsi=0;tick(90);tick(106)
assert(launches()==3 and next(saved.assignments)==nil,"recovery must not revive a user-cleared video")
onIpc("reapply","");assert(launches()==3)
print("RESOURCE_RELEASE_HYSTERESIS_SEEK_AND_STATIC_OVERRIDE_PASSED")
