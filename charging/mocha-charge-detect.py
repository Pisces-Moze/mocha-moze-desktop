#!/usr/bin/python3
"""Mocha BC1.2 probe, using MiCode Tegra124 PHY primary/secondary detection.

Only the USB charger-detection and termination fields are touched. Register
state and gadget connection are restored. No QC voltage negotiation is used.
"""
import fcntl, json, mmap, os, struct, time
from pathlib import Path

UDC=Path('/sys/class/udc/ci_hdrc.0')
CHARGER=Path('/sys/class/power_supply/bq24190-charger')
def detect():
    if (CHARGER/'online').read_text().strip()!='1':return {'type':'NONE','limit_ua':500000}
    state=(UDC/'state').read_text().strip()
    if state in ('configured','address','default','suspended'):
        return {'type':'USB_HOST','limit_ua':500000,'state':state}
    lock=open('/run/mocha-charge-detect.lock','w')
    fcntl.flock(lock,fcntl.LOCK_EX)
    if (UDC/'device/power/runtime_status').read_text().strip()!='active':
        return {'type':'UNKNOWN','limit_ua':500000,'reason':'PHY runtime inactive'}
    soft=UDC/'soft_connect'
    fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
    with mmap.mmap(fd,4096,access=mmap.ACCESS_WRITE,offset=0x7d000000) as m:
        rd=lambda off:struct.unpack_from('<I',m,off)[0]
        def wr(off,value):struct.pack_into('<I',m,off,value);rd(off)
        saved={off:rd(off) for off in (0x824,0x830)}
        def terms(flags):wr(0x824,(saved[0x824]&~0xff00)|flags);time.sleep(.002)
        report={'initial':{hex(off):hex(rd(off)) for off in (0x174,0x400,0x408,0x824,0x830)}}
        disconnected=False
        try:
            soft.write_text('disconnect\n');disconnected=True
            if not rd(0x400)&(1<<7):
                return {'type':'UNKNOWN','limit_ua':500000,'reason':'PHY clock invalid'}
            wr(0x830,0);terms(0)
            deadline=time.monotonic()+.9
            contact=False
            while time.monotonic()<deadline:
                wr(0x830,1<<5)
                terms((1<<15)|(1<<14)|(1<<13)|(1<<8))
                time.sleep(.025)
                low=(rd(0x174)>>10)&3==0
                if low:time.sleep(.012);contact=((rd(0x174)>>10)&3)==0
                wr(0x830,0);terms(0)
                if contact:break
                terms(0xf000)
                high=((rd(0x174)>>10)&3)==3
                terms(0)
                if high:break
                time.sleep(.022)
            report['dcd']=contact
            terms(0xf000)
            wr(0x830,(1<<3)|(1<<2));time.sleep(.1)
            primary=bool(rd(0x408)&(1<<18))
            report['primary_vdat']=primary
            if primary:
                wr(0x830,(1<<4)|(1<<1));time.sleep(.01)
                secondary=bool(rd(0x408)&(1<<18))
                report['secondary_vdat']=secondary
                report.update(type='DCP' if secondary else 'CDP',limit_ua=2000000 if secondary else 1500000)
            else:
                report.update(type='SDP_OR_UNKNOWN',limit_ua=500000)
            return report
        finally:
            wr(0x830,0);time.sleep(.04)
            wr(0x824,saved[0x824]);wr(0x830,saved[0x830])
            if disconnected:soft.write_text('connect\n')
            os.close(fd)

if __name__=='__main__':
    print(json.dumps(detect(),sort_keys=True),flush=True)
