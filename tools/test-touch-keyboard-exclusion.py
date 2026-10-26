#!/usr/bin/env python3
"""Exercise the actual shield geometry parser without a Wayland connection."""
import argparse,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--compiler',default='g++');a=p.parse_args()
header=a.source/'src/shell/panel/touch_keyboard_exclusion.h'
assert header.is_file()
code=r'''
#include "touch_keyboard_exclusion.h"
#include <cassert>
#include <climits>
using nlohmann::json;
int main() {
  json j={{"pid",123},{"visible",true},{"monitor",{{"x",0},{"y",0},{"width",1365},{"height",1024}}},
    {"rects", {{{"width",1365},{"height",264},{"bottom",0}},{{"width",620},{"height",58},{"bottom",280}}}}};
  auto s=touch_keyboard::parse(j);assert(s);
  auto r=touch_keyboard::rectangles(*s,0,0,1365,1024,1365,1024);
  assert(r.size()==2);
  assert((r[0]==std::array<int,4>{0,760,1365,264}));
  assert((r[1]==std::array<int,4>{372,686,620,58}));
  assert(touch_keyboard::rectangles(*s,1365,0,1365,1024,1365,1024).empty());
  assert(touch_keyboard::rectangles(*s,0,0,1536,2048,1536,2048).empty());
  assert(touch_keyboard::rectangles(*s,0,0,1365,1024,1365,960).empty());
  auto bad=j;bad["visible"]=false;assert(!touch_keyboard::parse(bad));
  bad=j;bad.erase("monitor");assert(!touch_keyboard::parse(bad));
  bad=j;bad["pid"]=-1;assert(!touch_keyboard::parse(bad));
  bad=j;bad["rects"][0]["height"]=INT_MAX;assert(!touch_keyboard::parse(bad));
  bad=j;bad["rects"][1]["bottom"]=-1;assert(!touch_keyboard::parse(bad));
  bad=j;bad["rects"][1]["bottom"]=1024;assert(!touch_keyboard::parse(bad));
  bad=j;bad["monitor"]["height"]="wrong type";assert(!touch_keyboard::parse(bad));
  bad=j;bad["rects"]=json::array();assert(!touch_keyboard::parse(bad));
  assert(!touch_keyboard::parse(json::parse("{bad",nullptr,false)));
}
'''
with tempfile.TemporaryDirectory() as temp:
 b=Path(temp);(b/'test.cpp').write_text(code,encoding='utf-8')
 subprocess.run([a.compiler,'-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(header.parent),str(b/'test.cpp'),'-o',str(b/'test')],check=True)
 subprocess.run([str(b/'test')],check=True)
print('Actual keyboard exclusion parser: rotated logical geometry, candidates, other outputs, hidden/invalid input passed')
