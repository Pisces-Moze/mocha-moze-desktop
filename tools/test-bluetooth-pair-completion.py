#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise real Noctalia pairing callbacks against a controllable D-Bus proxy."""
import argparse
from pathlib import Path
import subprocess
import tempfile


def method(text, signature):
    start = text.index(signature)
    begin = text.index('{', start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('source', type=Path)
p.add_argument('--compiler', default='c++')
args = p.parse_args()
pair = method((args.source / 'src/dbus/bluetooth/bluetooth_service.cpp').read_text(encoding='utf-8'), 'bool BluetoothService::pair(')
display = method((args.source / 'src/dbus/bluetooth/bluetooth_agent.cpp').read_text(encoding='utf-8'), '  void finishDisplayFor(')
stub = r'''
#include <cassert>
#include <deque>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>
namespace sdbus {
using ObjectPath = std::string;
struct Error { const char* what() const { return "test error"; } };
}
using Reply = std::function<void(std::optional<sdbus::Error>)>;
struct Proxy {
  struct Pending {
    Proxy& owner; std::string operation;
    Pending& onInterface(const char*) { return *this; }
    Pending& toValue(bool value) { assert(value); return *this; }
    void uponReplyInvoke(Reply reply) { owner.calls.emplace_back(operation, std::move(reply)); }
  };
  std::deque<std::pair<std::string, Reply>> calls;
  Pending callMethodAsync(const char* operation) { return {*this, operation}; }
  Pending setPropertyAsync(const char* name) { assert(std::string(name)=="Trusted"); return {*this,"Trusted"}; }
  void reply(const char* operation, bool failure=false) {
    assert(!calls.empty() && calls.front().first==operation);
    auto callback=std::move(calls.front().second); calls.pop_front();
    callback(failure ? std::optional{sdbus::Error{}} : std::nullopt);
  }
};
struct Log { template<class... T> void warn(const char*, T&&...) {} } kLog;
constexpr auto kDeviceInterface = "org.bluez.Device1";
struct Device { bool connecting=false, connected=false; };
struct BluetoothService {
  struct Impl { Proxy proxy; bool present=true; Proxy* deviceProxy(const std::string&) { return present ? &proxy : nullptr; } };
  std::unique_ptr<Impl> m_impl=std::make_unique<Impl>();
  Device device; int connections=0, emissions=0;
  Device* findDevice(const std::string&) { return m_impl->present ? &device : nullptr; }
  void emitDevices() { ++emissions; }
  bool connect(const std::string&) { ++connections; return true; }
  bool pair(const std::string&);
};
enum class BluetoothPairingKind { None, DisplayPinCode, DisplayPasskey, Confirm, Passkey };
struct DisplayState {
  struct Pending { std::string devicePath; BluetoothPairingKind kind=BluetoothPairingKind::None; } pending;
  void clearPending() { pending={}; }
  DISPLAY_METHOD
};
PAIR_METHOD
int main() {
  { BluetoothService s; assert(s.pair("keyboard")); assert(s.device.connecting);
    s.m_impl->proxy.reply("Pair"); assert(s.connections==0);
    s.m_impl->proxy.reply("Trusted"); assert(s.connections==1); }
  { BluetoothService s; s.pair("keyboard"); s.m_impl->proxy.reply("Pair",true);
    assert(s.connections==0 && s.m_impl->proxy.calls.empty() && !s.device.connecting); }
  { BluetoothService s; s.pair("keyboard"); s.m_impl->proxy.reply("Pair");
    s.m_impl->proxy.reply("Trusted",true); assert(s.connections==0 && !s.device.connecting); }
  { BluetoothService s; s.device.connected=true; s.pair("keyboard");
    s.m_impl->proxy.reply("Pair"); s.m_impl->proxy.reply("Trusted");
    assert(s.connections==0 && !s.device.connecting); }
  { BluetoothService s; s.m_impl->present=false; assert(!s.pair("gone")); }
  { BluetoothService s; s.pair("keyboard"); s.m_impl->present=false;
    s.m_impl->proxy.reply("Pair"); assert(s.connections==0 && s.m_impl->proxy.calls.empty()); }
  for (auto kind : {BluetoothPairingKind::DisplayPinCode,BluetoothPairingKind::DisplayPasskey}) {
    DisplayState d; d.pending={"keyboard",kind}; d.finishDisplayFor("mouse"); assert(d.pending.kind==kind);
    d.finishDisplayFor("keyboard"); assert(d.pending.kind==BluetoothPairingKind::None);
  }
  for (auto kind : {BluetoothPairingKind::Confirm,BluetoothPairingKind::Passkey}) {
    DisplayState d; d.pending={"keyboard",kind}; d.finishDisplayFor("keyboard"); assert(d.pending.kind==kind);
  }
}
'''.replace('PAIR_METHOD', pair).replace('DISPLAY_METHOD', display)
with tempfile.TemporaryDirectory(prefix='mocha-pair-') as temp:
    root = Path(temp)
    (root / 'test.cpp').write_text(stub, encoding='utf-8')
    subprocess.run([args.compiler, '-std=c++23', '-O0', '-g', str(root / 'test.cpp'), '-o', str(root / 'test')], check=True)
    subprocess.run([str(root / 'test')], check=True)
print('Pair/trust/connect ordering, failure paths, duplicate connection and display-state checks passed')
