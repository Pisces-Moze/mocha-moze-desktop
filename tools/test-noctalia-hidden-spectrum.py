#!/usr/bin/env python3
"""Exercise real widget scheduling methods with a CPU-only renderer test double."""
import argparse
from pathlib import Path
import subprocess
import tempfile


def method(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--compiler', default='c++')
    args = parser.parse_args()
    root = args.source / 'src/shell/desktop/widgets'
    parts = []
    for cls, name in [('DesktopFancyAudioVisualizerWidget', 'desktop_fancy_audio_visualizer_widget.cpp'),
                      ('DesktopAudioVisualizerWidget', 'desktop_audio_visualizer_widget.cpp')]:
        text = (root / name).read_text()
        for signature in [f'bool {cls}::needsFrameTick() const', f'void {cls}::onFrameTick(float deltaMs, Renderer& renderer)']:
            parts.append(method(text, signature))
    fixture = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <iostream>
struct Renderer {};
struct Visualizer {
  int ticks=0, times=0;
  int textureId() const {return 1;}
  bool converged() const {return true;}
  void tick(float) {++ticks;}
  void setTime(float) {++times;}
};
struct State {
  Visualizer visualizer;
  Visualizer *m_visualizer=&visualizer;
  bool m_pendingSpectrumUpdate=false, m_spectrumTextureInitialized=true;
  bool m_editorPreview=false, m_visible=false, m_fadingOut=false;
  int m_visibilityAnimId=0, syncs=0;
  bool wantVisible=false, animate=false;
  float m_shaderTime=0;
  bool shouldBeVisible() const {return wantVisible;}
  bool shouldAnimateTime() const {return animate;}
  void applyVisibility() {m_visible=wantVisible;}
  void ensureSpectrumTexture(Renderer&) {}
  void syncSpectrum(Renderer&) {m_pendingSpectrumUpdate=false;++syncs;}
  void syncSpectrum(Renderer*) {m_pendingSpectrumUpdate=false;++syncs;}
};
struct DesktopFancyAudioVisualizerWidget:State {
  bool needsFrameTick() const;
  void onFrameTick(float,Renderer&);
};
struct DesktopAudioVisualizerWidget:State {
  bool needsFrameTick() const;
  void onFrameTick(float,Renderer&);
};
''' + '\n'.join(parts) + r'''
template<class Widget> void hiddenFinalUpdate() {
  Renderer renderer;
  Widget widget;
  widget.m_pendingSpectrumUpdate=true;
  assert(widget.needsFrameTick());
  widget.onFrameTick(16,renderer);
  assert(widget.syncs==1);
  assert(!widget.m_pendingSpectrumUpdate);
  assert(!widget.needsFrameTick());
  assert(widget.visualizer.ticks==0 && widget.visualizer.times==0);
  // New audio after idle still wakes the visible widget.
  widget.wantVisible=true;widget.m_pendingSpectrumUpdate=true;widget.animate=true;
  assert(widget.needsFrameTick());
  widget.onFrameTick(16,renderer);
  assert(widget.m_visible && widget.syncs==2);
  assert(widget.visualizer.ticks+widget.visualizer.times==1);
}
int main() {
  hiddenFinalUpdate<DesktopFancyAudioVisualizerWidget>();
  hiddenFinalUpdate<DesktopAudioVisualizerWidget>();
  Renderer renderer;DesktopFancyAudioVisualizerWidget preview;
  preview.wantVisible=true;preview.m_editorPreview=true;preview.animate=true;
  preview.onFrameTick(16,renderer);preview.onFrameTick(16,renderer);
  assert(preview.needsFrameTick() && preview.visualizer.times==2);
  std::cout << "HIDDEN_SPECTRUM_SCHEDULING_PASSED\n";
}
'''
    with tempfile.TemporaryDirectory(prefix='noctalia-hidden-spectrum-') as temporary:
        folder = Path(temporary)
        source, binary = folder / 'test.cpp', folder / 'test'
        source.write_text(fixture)
        subprocess.run([args.compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', '-O1',
                        '-fsanitize=address,undefined', str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
