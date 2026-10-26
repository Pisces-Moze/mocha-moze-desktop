/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

#ifndef FFmpegV4L2Request_h_
#define FFmpegV4L2Request_h_

#include <cstdint>
#include <limits>

// The caller supplies FFmpeg's DRM and VA DRM descriptor definitions. Keeping
// this conversion independent of Gecko lets the exact production code run in
// the standalone sanitizer test, with the real upstream descriptor layouts.
namespace mozilla {

inline bool ConvertV4L2RequestYUV420(
    const AVDRMFrameDescriptor& aDesc, int aWidth, int aHeight,
    uint64_t aCropRight, uint64_t aCropBottom,
    VADRMPRIMESurfaceDescriptor& aResult) {
  if (aWidth <= 0 || aHeight <= 0 || aCropRight >= uint64_t(aWidth) ||
      aCropBottom >= uint64_t(aHeight) || aDesc.nb_layers != 1 ||
      aDesc.nb_objects < 1 || aDesc.nb_objects > 4 ||
      aDesc.layers[0].format != DRM_FORMAT_YUV420 ||
      aDesc.layers[0].nb_planes != 3) {
    return false;
  }

  VADRMPRIMESurfaceDescriptor out{};
  out.fourcc = VA_FOURCC_I420;
  out.width = aWidth - aCropRight;
  out.height = aHeight - aCropBottom;
  out.num_objects = aDesc.nb_objects;
  out.num_layers = 3;
  for (int i = 0; i < aDesc.nb_objects; ++i) {
    const auto& obj = aDesc.objects[i];
    if (obj.fd < 0 || !obj.size ||
        obj.size > std::numeric_limits<uint32_t>::max()) {
      return false;
    }
    out.objects[i].fd = obj.fd;
    out.objects[i].size = obj.size;
    out.objects[i].drm_format_modifier = obj.format_modifier;
  }
  for (int i = 0; i < 3; ++i) {
    const auto& plane = aDesc.layers[0].planes[i];
    if (plane.object_index < 0 || plane.object_index >= aDesc.nb_objects ||
        plane.offset < 0 || plane.pitch <= 0 ||
        uint64_t(plane.offset) > std::numeric_limits<uint32_t>::max() ||
        uint64_t(plane.pitch) > std::numeric_limits<uint32_t>::max()) {
      return false;
    }
    const uint64_t columns = i ? (uint64_t(aWidth) + 1) / 2 : aWidth;
    const uint64_t rows = i ? (uint64_t(aHeight) + 1) / 2 : aHeight;
    const uint64_t size = aDesc.objects[plane.object_index].size;
    const uint64_t offset = plane.offset;
    const uint64_t pitch = plane.pitch;
    // Use division and subtraction so even malicious descriptor dimensions
    // cannot overflow a pitch*height or offset+extent calculation.
    if (pitch < columns || offset > size || columns > size - offset ||
        rows - 1 > (size - offset - columns) / pitch) {
      return false;
    }
    auto& layer = out.layers[i];
    layer.drm_format = DRM_FORMAT_R8;
    layer.num_planes = 1;
    layer.object_index[0] = plane.object_index;
    layer.offset[0] = plane.offset;
    layer.pitch[0] = plane.pitch;
  }
  // No fd duplication or ownership transfer here. Gecko's DMABufSurface
  // duplicates the fds, and VideoFrameSurface retains FFmpeg's frame buffer.
  aResult = out;
  return true;
}

}  // namespace mozilla
#endif
