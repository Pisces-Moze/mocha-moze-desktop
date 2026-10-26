/* MPL-2.0; tests the production header, using actual FFmpeg/VA structures. */
#include <cassert>
#include <climits>
#include <cstdio>
#include <cstring>
#include <libdrm/drm_fourcc.h>
#include <va/va.h>
extern "C" {
#include <libavutil/hwcontext_drm.h>
}
#include "va_drmcommon.h"
#include "FFmpegV4L2Request.h"

static AVDRMFrameDescriptor ThreePlanes(int width = 640, int height = 360) {
  AVDRMFrameDescriptor d{};
  d.nb_objects = 3;
  d.nb_layers = 1;
  d.layers[0].format = DRM_FORMAT_YUV420;
  d.layers[0].nb_planes = 3;
  for (int i = 0; i < 3; ++i) {
    const int pitch = i ? (width + 1) / 2 : width;
    const int rows = i ? (height + 1) / 2 : height;
    d.objects[i].fd = 40 + i;
    d.objects[i].size = pitch * rows;
    d.objects[i].format_modifier = DRM_FORMAT_MOD_LINEAR;
    d.layers[0].planes[i].object_index = i;
    d.layers[0].planes[i].pitch = pitch;
  }
  return d;
}

int main() {
  int cases = 0;
  auto check = [&](AVDRMFrameDescriptor d, bool valid, int w = 640, int h = 360,
                   uint64_t right = 0, uint64_t bottom = 0) {
    VADRMPRIMESurfaceDescriptor out{};
    std::memset(&out, 0x5a, sizeof(out));
    auto previous = out;
    bool ok = mozilla::ConvertV4L2RequestYUV420(d, w, h, right, bottom, out);
    assert(ok == valid);
    if (!ok) {
      assert(!std::memcmp(&previous, &out, sizeof(out)));
    } else {
      assert(out.width == uint64_t(w) - right);
      assert(out.height == uint64_t(h) - bottom);
      assert(out.num_objects == unsigned(d.nb_objects));
      for (int i = 0; i < 3; ++i) {
        assert(out.layers[i].object_index[0] ==
               unsigned(d.layers[0].planes[i].object_index));
        assert(out.layers[i].pitch[0] == unsigned(d.layers[0].planes[i].pitch));
        assert(out.layers[i].offset[0] == unsigned(d.layers[0].planes[i].offset));
        assert(out.objects[i].fd == d.objects[i].fd || i >= d.nb_objects);
      }
    }
    ++cases;
  };
  auto d = ThreePlanes();
  check(d, true); // Actual Mocha three-object YUV420M export.
  auto v = d;
  v.layers[0].planes[1].object_index = 2;
  v.layers[0].planes[2].object_index = 1;
  check(v, true); // YVU export: preserve the supplied U/V object mapping.
  v = d;
  for (int i = 0; i < 3; ++i) {
    v.layers[0].planes[i].offset = 128;
    v.layers[0].planes[i].pitch += 32;
    v.objects[i].size += 128 + 32 * (i ? 180 : 360);
  }
  check(v, true); // Padding and real offsets must survive import.
  v = d;
  v.nb_objects = 1;
  v.objects[0].size = 640 * 360 * 3 / 2;
  for (int i = 0; i < 3; ++i) v.layers[0].planes[i].object_index = 0;
  v.layers[0].planes[1].offset = 640 * 360;
  v.layers[0].planes[2].offset = 640 * 360 * 5 / 4;
  check(v, true); // Explicit three planes sharing a contiguous object.
  check(ThreePlanes(641, 361), true, 641, 361);
  check(d, true, 640, 360, 2, 4);
  check(d, false, 640, 360, 640, 0);
  check(d, false, 640, 360, 0, UINT64_MAX);
  check(d, false, -1, 360);
  check(d, false, INT_MAX, INT_MAX);
  v = d; v.nb_objects = 0; check(v, false);
  v = d; v.nb_objects = 5; check(v, false);
  v = d; v.nb_layers = 0; check(v, false);
  v = d; v.nb_layers = 2; check(v, false);
  v = d; v.layers[0].nb_planes = 1; check(v, false);
  v = d; v.layers[0].format = DRM_FORMAT_NV12; check(v, false);
  v = d; v.layers[0].planes[2].object_index = 3; check(v, false);
  v = d; v.layers[0].planes[0].object_index = -1; check(v, false);
  v = d; v.layers[0].planes[1].offset = -1; check(v, false);
  v = d; v.layers[0].planes[1].pitch = 0; check(v, false);
  v = d; v.layers[0].planes[0].pitch = 639; check(v, false);
  v = d; v.objects[1].size--; check(v, false);
  v = d; v.objects[2].fd = -1; check(v, false);
  v = d; v.objects[0].size = 0; check(v, false);
  v = d; v.objects[0].size = uint64_t(UINT32_MAX) + 1; check(v, false);
  v = d; v.layers[0].planes[0].offset = PTRDIFF_MAX; check(v, false);
  v = d; v.layers[0].planes[0].pitch = PTRDIFF_MAX; check(v, false);
  std::printf("PASS %d descriptor cases\n", cases);
}
