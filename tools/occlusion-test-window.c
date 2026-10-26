// SPDX-License-Identifier: GPL-3.0-only
// An opaque, CPU-filled diagnostic toplevel; no input capture or display modeset.
#define _GNU_SOURCE
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"

static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct xdg_wm_base *wm;
static struct wl_surface *surface;
static struct xdg_surface *xdg;
static int width = 640, height = 480;
static bool running = true;

struct buffer {
    struct wl_buffer *buffer;
    void *data;
    size_t size;
};
static void released(void *data, struct wl_buffer *wl_buffer) {
    struct buffer *buffer = data;
    wl_buffer_destroy(wl_buffer);
    munmap(buffer->data, buffer->size);
    free(buffer);
}
static const struct wl_buffer_listener buffer_listener = {.release = released};

static void draw(void) {
    if (width < 1 || height < 1 || width > 8192 || height > 8192) exit(2);
    struct buffer *buffer = calloc(1, sizeof(*buffer));
    if (!buffer) exit(2);
    buffer->size = (size_t)width * height * 4;
    int fd = memfd_create("mocha-occlusion-window", MFD_CLOEXEC);
    if (fd < 0 || ftruncate(fd, (off_t)buffer->size)) exit(2);
    buffer->data = mmap(NULL, buffer->size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (buffer->data == MAP_FAILED) exit(2);
    for (size_t i = 0; i < buffer->size / 4; i++) ((uint32_t *)buffer->data)[i] = 0xff203854;
    struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, (int)buffer->size);
    buffer->buffer = wl_shm_pool_create_buffer(pool, 0, width, height, width * 4, WL_SHM_FORMAT_XRGB8888);
    wl_shm_pool_destroy(pool);
    close(fd);
    wl_buffer_add_listener(buffer->buffer, &buffer_listener, buffer);
    struct wl_region *opaque = wl_compositor_create_region(compositor);
    wl_region_add(opaque, 0, 0, width, height);
    wl_surface_set_opaque_region(surface, opaque);
    wl_region_destroy(opaque);
    wl_surface_attach(surface, buffer->buffer, 0, 0);
    wl_surface_damage(surface, 0, 0, width, height);
    wl_surface_commit(surface);
}
static void configured(void *data, struct xdg_surface *s, uint32_t serial) {
    (void)data;
    xdg_surface_ack_configure(s, serial);
    draw();
}
static const struct xdg_surface_listener xdg_listener = {.configure = configured};
static void resized(void *data, struct xdg_toplevel *top, int32_t w, int32_t h, struct wl_array *states) {
    (void)data; (void)top; (void)states;
    if (w > 0) width = w;
    if (h > 0) height = h;
}
static void closed(void *data, struct xdg_toplevel *top) {
    (void)data; (void)top; running = false;
}
static const struct xdg_toplevel_listener top_listener = {.configure = resized, .close = closed};
static void pinged(void *data, struct xdg_wm_base *base, uint32_t serial) {
    (void)data; xdg_wm_base_pong(base, serial);
}
static const struct xdg_wm_base_listener wm_listener = {.ping = pinged};
static void global(void *data, struct wl_registry *registry, uint32_t name, const char *interface, uint32_t version) {
    (void)data; (void)version;
    if (!strcmp(interface, "wl_compositor")) compositor = wl_registry_bind(registry, name, &wl_compositor_interface, 1);
    if (!strcmp(interface, "wl_shm")) shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
    if (!strcmp(interface, "xdg_wm_base")) {
        wm = wl_registry_bind(registry, name, &xdg_wm_base_interface, 1);
        xdg_wm_base_add_listener(wm, &wm_listener, NULL);
    }
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {
    (void)data; (void)registry; (void)name;
}
static const struct wl_registry_listener registry_listener = {.global = global, .global_remove = removed};
int main(int argc, char **argv) {
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) return 1;
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    wl_display_roundtrip(display);
    if (!wm || !shm || !compositor) return 1;
    surface = wl_compositor_create_surface(compositor);
    xdg = xdg_wm_base_get_xdg_surface(wm, surface);
    xdg_surface_add_listener(xdg, &xdg_listener, NULL);
    struct xdg_toplevel *top = xdg_surface_get_toplevel(xdg);
    xdg_toplevel_add_listener(top, &top_listener, NULL);
    xdg_toplevel_set_title(top, "Mocha wallpaper occlusion check");
    xdg_toplevel_set_app_id(top, argc > 1 ? argv[1] : "mocha-occlusion-probe");
    if (argc > 2 && !strcmp(argv[2], "--fullscreen")) xdg_toplevel_set_fullscreen(top, NULL);
    wl_surface_commit(surface);
    while (running && wl_display_dispatch(display) != -1) {}
    wl_display_disconnect(display);
    return 0;
}
