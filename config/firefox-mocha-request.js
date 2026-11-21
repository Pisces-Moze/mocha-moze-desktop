// Matched Mocha Firefox Request runtime only. Editable defaults; RDD retained.
// Unsupported H.264 profiles and other codecs retain software fallback.
pref("media.hardware-video-decoding.enabled", true);
// This validated device needs the platform decode feature enabled as well as
// Request direct import; otherwise later rendering stages retain extra work.
pref("media.hardware-video-decoding.force-enabled", true);
pref("media.ffmpeg.v4l2-request.enabled", true);
pref("media.ffmpeg.vaapi.enabled", false);
pref("media.ffmpeg.vaapi.force-surface-zero-copy", 1);
pref("media.rdd-ffmpeg.enabled", true);
