#!/usr/bin/python3
"""Select the input cap from BC1.2 detection, in desktop and charger targets."""
import importlib.util,json,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('charge_detect','/usr/local/libexec/mocha-charge-detect.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
c=Path('/sys/class/power_supply/bq24190-charger')
g=Path('/sys/class/power_supply/bq27520g4-0')
u=Path('/sys/class/udc/ci_hdrc.0')
def read(p):return p.read_text().strip()
def apply(limit):
 if int(read(c/'input_current_limit'))!=limit:
  (c/'input_current_limit').write_text(str(limit)+'\n')
online_before=False;kind='NONE';limit=500000;ready=0;last=None
while True:
 try:
  online=read(c/'online')=='1'
  state=read(u/'state')
  if not online:
   kind='NONE';limit=500000;ready=0
  elif not online_before:
   kind='WAITING';limit=500000;ready=time.monotonic()+3
  if online and state in ('configured','address','default','suspended'):
   kind='USB_HOST';limit=500000
  elif online and kind in ('WAITING','USB_HOST','UNKNOWN') and time.monotonic()>=ready:
   result=mod.detect();print('BC12 '+json.dumps(result),flush=True)
   kind=result['type'];limit=result['limit_ua'];ready=time.monotonic()+15
   if kind=='SDP_OR_UNKNOWN':kind='UNKNOWN'
  selected=limit if online else 500000
  temp=int(read(g/'temp'))
  if temp<0 or temp>=450 or read(c/'health')!='Good':selected=500000
  apply(selected)
  status=(online,kind,selected)
  if status!=last:
   print('CHARGE_POLICY '+json.dumps(dict(online=online,type=kind,input_limit_ua=selected,temperature_deci_c=temp)),flush=True)
   Path('/run/mocha-charge-source.json').write_text(json.dumps(dict(online=online,type=kind,input_limit_ua=selected))+'\n')
   last=status
  online_before=online
 except (OSError,ValueError,RuntimeError) as e:
  print('CHARGE_POLICY_ERROR '+str(e),flush=True)
  kind='UNKNOWN';limit=500000;ready=time.monotonic()+15
 time.sleep(.5)
