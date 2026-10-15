#!/usr/bin/env python3
"""Headless EGL fence regression on an explicitly identified DRM device.

Uses the installed EGL/GLES/GBM libraries through ctypes; no compiler or
development packages are needed on the tablet. Does not take DRM master,
change a mode, or replace a running desktop. Pixel readback tests ordering,
not zero-copy scanout or panel output. SPDX-License-Identifier: GPL-2.0-only
"""
import argparse
import ctypes as C
import hashlib
import os
import sys
from pathlib import Path


def bind(lib, name, result, *args):
    function = getattr(lib, name)
    function.restype = result
    function.argtypes = args
    return function


def driver(node):
    # Tegra's host1x sysfs driver is called "drm"; query the DRM ABI name.
    class Version(C.Structure):
        _fields_ = [
            ('major', C.c_int), ('minor', C.c_int), ('patchlevel', C.c_int),
            ('name_len', C.c_int), ('name', C.c_char_p),
            ('date_len', C.c_int), ('date', C.c_char_p),
            ('desc_len', C.c_int), ('desc', C.c_char_p),
        ]
    drm = C.CDLL('libdrm.so.2')
    get_version = bind(drm, 'drmGetVersion', C.POINTER(Version), C.c_int)
    free_version = bind(drm, 'drmFreeVersion', None, C.POINTER(Version))
    path = Path(node)
    if not path.is_absolute():
        path = Path('/dev/dri') / path.name
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    version = None
    try:
        version = get_version(fd)
        if not version or not version.contents.name:
            raise RuntimeError('Cannot identify DRM driver: ' + str(path))
        return version.contents.name.decode('ascii')
    finally:
        if version:
            free_version(version)
        os.close(fd)


def verify_mesa_libraries(prefix):
    """Check live mappings so a system/candidate mixture cannot pass unnoticed."""
    prefix = prefix.resolve(strict=True)
    required = ('libEGL_mesa.so', 'libgbm.so', 'libgallium')
    found = set()
    libraries = set()
    for line in Path('/proc/self/maps').read_text(encoding='utf-8').splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or not fields[5].startswith('/'):
            continue
        path = Path(fields[5])
        for name in required:
            if path.name.startswith(name):
                found.add(name)
                path = path.resolve(strict=True)
                if not path.is_relative_to(prefix):
                    raise RuntimeError('Mesa library outside candidate prefix: ' + str(path))
                libraries.add(path)
    missing = set(required) - found
    if missing:
        raise RuntimeError('Missing live Mesa library mappings: ' + ', '.join(sorted(missing)))
    for path in sorted(libraries):
        with path.open('rb') as library:
            digest = hashlib.file_digest(library, 'sha256').hexdigest()
        print(f'MESA_LIBRARY={path}\nMESA_LIBRARY_SHA256={digest}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', help='DRM node; defaults to the Nouveau render node')
    parser.add_argument('--require-tegra', action='store_true', help='refuse a non-Tegra device')
    parser.add_argument('--iterations', type=int, default=16)
    parser.add_argument('--trace', action='store_true', help='print completed EGL stages and GL operations to stderr')
    parser.add_argument('--expected-mesa-prefix', type=Path,
                        help='require live EGL Mesa, GBM and Gallium libraries to come from this candidate directory')
    args = parser.parse_args()
    if not 1 <= args.iterations <= 1000:
        parser.error('iterations must be between 1 and 1000')
    device = args.device
    if not device:
        nodes = sorted(Path('/sys/class/drm').glob('renderD*'))
        device = next(('/dev/dri/' + n.name for n in nodes if driver(n.name) == 'nouveau'), None)
    if not device:
        raise SystemExit('No Nouveau render node; specify --device for a Tegra test')
    name = driver(device)
    if name not in ('nouveau', 'tegra') or (args.require_tegra and name != 'tegra'):
        raise SystemExit('Unexpected DRM driver: ' + name)
    print(f'DRM_DEVICE={device}\nDRM_DRIVER={name}', flush=True)

    p, i, u = C.c_void_p, C.c_int, C.c_uint
    egl = C.CDLL('libEGL.so.1')
    gl = C.CDLL('libGLESv2.so.2')
    gbm = C.CDLL('libgbm.so.1')
    create_device = bind(gbm, 'gbm_create_device', p, i)
    destroy_device = bind(gbm, 'gbm_device_destroy', None, p)
    get_display = bind(egl, 'eglGetPlatformDisplay', p, u, p, p)
    initialize = bind(egl, 'eglInitialize', u, p, C.POINTER(i), C.POINTER(i))
    query = bind(egl, 'eglQueryString', C.c_char_p, p, i)
    api = bind(egl, 'eglBindAPI', u, u)
    choose = bind(egl, 'eglChooseConfig', u, p, C.POINTER(i), C.POINTER(p), i, C.POINTER(i))
    create_context = bind(egl, 'eglCreateContext', p, p, p, p, C.POINTER(i))
    current = bind(egl, 'eglMakeCurrent', u, p, p, p, p)
    destroy_context = bind(egl, 'eglDestroyContext', u, p, p)
    terminate = bind(egl, 'eglTerminate', u, p)
    error = bind(egl, 'eglGetError', u)
    get_proc = bind(egl, 'eglGetProcAddress', p, C.c_char_p)

    def extension(symbol, result, *arguments):
        address = get_proc(symbol.encode())
        if not address:
            raise RuntimeError('Missing function: ' + symbol)
        return C.CFUNCTYPE(result, *arguments)(address)

    create_sync = extension('eglCreateSyncKHR', p, p, u, C.POINTER(i))
    server_wait = extension('eglWaitSyncKHR', u, p, p, i)
    client_wait = extension('eglClientWaitSyncKHR', i, p, p, i, C.c_uint64)
    destroy_sync = extension('eglDestroySyncKHR', u, p, p)
    string = bind(gl, 'glGetString', C.c_char_p, u)
    gen_tex = bind(gl, 'glGenTextures', None, i, C.POINTER(u))
    tex = bind(gl, 'glBindTexture', None, u, u)
    image = bind(gl, 'glTexImage2D', None, u, i, i, i, i, i, u, u, p)
    gen_fb = bind(gl, 'glGenFramebuffers', None, i, C.POINTER(u))
    fb = bind(gl, 'glBindFramebuffer', None, u, u)
    attach = bind(gl, 'glFramebufferTexture2D', None, u, u, u, u, i)
    status = bind(gl, 'glCheckFramebufferStatus', u, u)
    clear_color = bind(gl, 'glClearColor', None, C.c_float, C.c_float, C.c_float, C.c_float)
    clear = bind(gl, 'glClear', None, u)
    flush = bind(gl, 'glFlush', None)
    read = bind(gl, 'glReadPixels', None, i, i, i, i, u, u, p)
    gl_error = bind(gl, 'glGetError', u)

    def check(ok, operation):
        if not ok:
            raise RuntimeError(f'{operation}: EGL error 0x{error():x}')
        trace(operation)

    def trace(operation):
        if args.trace:
            print('PROBE_STAGE=' + operation, file=sys.stderr, flush=True)

    fd = os.open(device, os.O_RDWR | os.O_CLOEXEC)
    dev = display = None
    contexts = []
    fence = None
    try:
        dev = create_device(fd)
        check(dev, 'gbm_create_device')
        display = get_display(0x31D7, dev, None)  # EGL_PLATFORM_GBM_KHR
        major, minor = i(), i()
        check(initialize(display, C.byref(major), C.byref(minor)), 'eglInitialize')
        extensions = set(query(display, 0x3055).decode().split())
        for required in ('EGL_KHR_surfaceless_context', 'EGL_KHR_fence_sync', 'EGL_KHR_wait_sync'):
            if required not in extensions:
                raise RuntimeError('Missing extension: ' + required)
        check(api(0x30A0), 'eglBindAPI')
        attributes = (i * 5)(0x3040, 4, 0x3033, 4, 0x3038)  # ES2, window-capable config
        config, count = p(), i()
        check(choose(display, attributes, C.byref(config), 1, C.byref(count)) and count.value, 'eglChooseConfig')
        version = (i * 3)(0x3098, 2, 0x3038)
        context = create_context(display, config, None, version)
        check(context, 'eglCreateContext producer')
        contexts.append(context)
        check(current(display, None, None, contexts[0]), 'eglMakeCurrent producer')
        renderer = string(0x1F01).decode()
        print(f'EGL_VERSION={major.value}.{minor.value}\nRENDERER={renderer}', flush=True)
        if any(word in renderer.lower() for word in ('llvmpipe', 'softpipe', 'software')):
            raise RuntimeError('Software renderer does not validate the hardware path')
        if args.expected_mesa_prefix:
            verify_mesa_libraries(args.expected_mesa_prefix)
        texture = u()
        gen_tex(1, C.byref(texture))
        trace('glGenTextures')
        tex(0x0DE1, texture)
        trace('glBindTexture')
        image(0x0DE1, 0, 0x1908, 1, 1, 0, 0x1908, 0x1401, None)
        trace('glTexImage2D')
        flush()
        trace('glFlush texture')
        context = create_context(display, config, contexts[0], version)
        check(context, 'eglCreateContext consumer')
        contexts.append(context)
        framebuffers = []
        for context in contexts:
            check(current(display, None, None, context), 'eglMakeCurrent setup')
            framebuffer = u()
            gen_fb(1, C.byref(framebuffer))
            fb(0x8D40, framebuffer)
            attach(0x8D40, 0x8CE0, 0x0DE1, texture, 0)
            if status(0x8D40) != 0x8CD5:
                raise RuntimeError('Incomplete framebuffer')
            framebuffers.append(framebuffer)
            trace('framebuffer setup')
        for step in range(args.iterations):
            check(current(display, None, None, contexts[0]), 'eglMakeCurrent producer')
            fb(0x8D40, framebuffers[0])
            expected = (255, 0, 0, 255) if step % 2 == 0 else (0, 255, 0, 255)
            clear_color(*(v / 255 for v in expected))
            clear(0x4000)
            trace('glClear producer')
            fence = create_sync(display, 0x30F9, (i * 1)(0x3038))
            check(fence, 'eglCreateSyncKHR')
            flush()
            check(current(display, None, None, contexts[1]), 'eglMakeCurrent consumer')
            trace('enter eglWaitSyncKHR')
            check(server_wait(display, fence, 0), 'eglWaitSyncKHR')
            result = client_wait(display, fence, 0, 500_000_000)
            if result != 0x30F6:  # EGL_CONDITION_SATISFIED_KHR
                raise RuntimeError(f'Fence wait did not complete: 0x{result:x}')
            fb(0x8D40, framebuffers[1])
            pixel = (C.c_ubyte * 4)()
            read(0, 0, 1, 1, 0x1908, 0x1401, pixel)
            code = gl_error()
            if code or tuple(pixel) != expected:
                raise RuntimeError(f'Pixel mismatch: {tuple(pixel)}, expected {expected}; GL error 0x{code:x}')
            check(destroy_sync(display, fence), 'eglDestroySyncKHR')
            fence = None
        print(f'FENCE_ITERATIONS={args.iterations}\nEGL_FENCE_TEST=PASS\n'
              f'TEGRA_WRAPPER_TESTED={"YES" if name == "tegra" or renderer == "tegra" else "NO"}\n'
              'PANEL_SCANOUT_TESTED=NO', flush=True)
    finally:
        if display:
            if fence:
                destroy_sync(display, fence)
            current(display, None, None, None)
            for context in reversed(contexts):
                destroy_context(display, context)
            terminate(display)
        if dev:
            destroy_device(dev)
        os.close(fd)


if __name__ == '__main__':
    main()
