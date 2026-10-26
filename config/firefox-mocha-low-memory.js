// Mocha/Tegra124: conservative defaults for a 2 GiB ARMhf tablet.
// Install as /etc/firefox-esr/mocha-low-memory.js and link it into defaults/pref/.
// A companion default policy overrides the later-loaded process-prelaunch default.
// These are editable defaults, not locked preferences. Restart Firefox to apply.

// Neither AV1 nor HEVC is implemented by this tablet's VDE decoder. Prefer the
// site's AVC alternative; this does not turn Firefox AVC into V4L2 Request HW decode.
pref("media.av1.enabled", false);
pref("media.hevc.enabled", false);

// Keep site isolation and sandboxes. Avoid idle spare content processes and
// limit same-origin process fanout, rather than collapsing security boundaries.
pref("dom.ipc.processPrelaunch.enabled", false);
pref("dom.ipc.processPrelaunch.fission.number", 0);
pref("dom.ipc.processCount", 2);
pref("dom.ipc.processCount.webIsolated", 1);

// Bound reusable caches; visible frames and active site allocations are separate.
pref("browser.cache.memory.capacity", 16384);
pref("image.mem.surfacecache.max_size_kb", 65536);
pref("media.memory_caches_combined_limit_kb", 32768);
pref("browser.sessionhistory.max_total_viewers", 2);
