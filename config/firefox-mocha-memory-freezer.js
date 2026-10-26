// Mocha: native low-memory tab unloading complements Auto Tab Discard.
// Editable defaults. Requires Firefox restart; no sandbox/isolation changes.
pref("browser.tabs.unloadOnLowMemory", true);
pref("browser.tabs.min_inactive_duration_before_unload", 60000);
pref("browser.low_commit_space_threshold_mb", 256);
