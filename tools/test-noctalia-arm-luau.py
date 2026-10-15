#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Cross-build an ARM Luau regression using the actual patched host allocator.

Usage: test-noctalia-arm-luau.py NOCTALIA_SOURCE OUTPUT_BINARY
Run OUTPUT_BINARY on the ARM board. It checks resize/failure accounting and
creates 1000 real Luau states under varying heap fragmentation.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

source, output = map(Path, sys.argv[1:])
text = (source / 'src/scripting/luau_host.cpp').read_text()
start = text.index('void* LuauHost::allocate(')
end = text.index('\nLuauHost::LuauHost(', start)
allocator = text[start:end]
prefix = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
#include "lua.h"
#include "lualib.h"
constexpr std::size_t kMemoryCeilingBytes = 128 * 1024 * 1024;
struct LuauHost {
    std::size_t m_memUsed = 0;
    static void* allocate(void*, void*, std::size_t, std::size_t);
};
'''
main = r'''
int main() {
    static_assert(sizeof(void*) == 4, "Run the 32-bit ARM regression");
    LuauHost host;
    void* p = LuauHost::allocate(&host, nullptr, 0, 37);
    assert(p && reinterpret_cast<std::uintptr_t>(p) % 16 == 0);
    std::memset(p, 0x5a, 37);
    p = LuauHost::allocate(&host, p, 37, 97);
    assert(p && host.m_memUsed == 97 && reinterpret_cast<std::uintptr_t>(p) % 16 == 0);
    for (int i = 0; i < 37; i++) assert(static_cast<unsigned char*>(p)[i] == 0x5a);
    assert(!LuauHost::allocate(&host, p, 97, kMemoryCeilingBytes + 1));
    assert(host.m_memUsed == 97 && static_cast<unsigned char*>(p)[0] == 0x5a);
    p = LuauHost::allocate(&host, p, 97, 13);
    assert(p && host.m_memUsed == 13 && static_cast<unsigned char*>(p)[12] == 0x5a);
    LuauHost::allocate(&host, p, 13, 0);
    assert(host.m_memUsed == 0);
    for (int round = 0; round < 1000; round++) {
        std::vector<void*> fragments;
        for (int i = 0; i < 31; i++) fragments.push_back(std::malloc(1 + ((round + i * 7) % 255)));
        for (int i = 0; i < 31; i += 2) { std::free(fragments[i]); fragments[i] = nullptr; }
        lua_State* L = lua_newstate(&LuauHost::allocate, &host);
        assert(L);
        luaL_openlibs(L);
        lua_newtable(L);
        for (int i = 0; i < 64; i++) {
            lua_pushstring(L, "ARM plugin allocation regression");
            lua_rawseti(L, -2, i + 1);
        }
        lua_close(L);
        assert(host.m_memUsed == 0);
        for (auto fragment : fragments) std::free(fragment);
    }
    std::cout << "ARM_LUAU_1000_STATES_PASSED\n";
}
'''
with tempfile.TemporaryDirectory() as directory:
    test = Path(directory) / 'allocator-regression.cpp'
    test.write_text(prefix + allocator + main)
    subprocess.run(['arm-linux-gnueabihf-g++', '-O2', '-march=armv7-a', '-mfpu=neon-vfpv4',
        '-mfloat-abi=hard', '-I' + str(source / 'third_party/luau/VM/include'), str(test),
        str(source / 'build/libluau.a'), '-lm', '-latomic', '-o', str(output)], check=True)
