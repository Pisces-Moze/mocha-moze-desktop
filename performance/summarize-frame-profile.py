import json
import re
import sys
from pathlib import Path

for file in sys.argv[1:]:
    frames=[]
    for line in Path(file).read_text().splitlines():
        if 'MOCHA_FRAME ' not in line: continue
        row={k:float(v) for k,v in re.findall(r'(\w+_ms)=([\d.]+)',line)}
        row['needs_sync']='needs_sync=true' in line
        frames.append(row)
    if not frames: raise SystemExit(f'No frames: {file}')
    result={'file':file,'frames':len(frames),'cpu_wait_frames':sum(x['needs_sync'] for x in frames)}
    for key in ('render_ms','wait_ms','queue_ms','total_ms'):
        values=sorted(x[key] for x in frames)
        result[key]={'mean':round(sum(values)/len(values),3),'p50':values[int(len(values)*.5)],'p95':values[min(len(values)-1,int(len(values)*.95))],'p99':values[min(len(values)-1,int(len(values)*.99))],'max':max(values)}
    result['over_16_65ms']=sum(x['total_ms']>16.65 for x in frames)
    result['startup_over_16_65ms']=sum(x['total_ms']>16.65 for x in frames[:2])
    print(json.dumps(result,indent=2))
