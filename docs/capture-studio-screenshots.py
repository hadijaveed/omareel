#!/usr/bin/env python3
"""Capture real Studio UI/exports with fictional, non-sensitive demo content.

Requires the installed Omarchy UI, Quickshell and FFmpeg. All recordings,
settings, runtime files and desktop hooks are isolated. Does not access screen,
camera, microphone, clipboard, upload credentials, or the live shell.
Run from any directory: python3 docs/capture-studio-screenshots.py
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
NATIVE = Path('/usr/share/omarchy/shell')


def run(argv, env, timeout=60):
    result = subprocess.run([str(v) for v in argv], env=env, capture_output=True,
                            text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def qml(work, name, source, env):
    directory = work / name
    directory.mkdir()
    for module in ('Commons', 'Ui'):
        (directory / module).symlink_to(NATIVE / module, target_is_directory=True)
    for file in ('StudioEditor.qml', 'PlainDropdown.qml', 'PlainToggle.qml'):
        shutil.copyfile(ROOT / file, directory / file)
    (directory / 'shell.qml').write_text(source)
    output = run(['quickshell', '-p', directory, '--no-color'], env)
    for error in ('ReferenceError', 'TypeError', 'Failed to load configuration', 'Unable to assign'):
        if error in output:
            raise RuntimeError(output)


def main():
    if not NATIVE.is_dir() or not shutil.which('quickshell'):
        raise SystemExit('Run on an Omarchy desktop with native Quickshell installed.')
    with tempfile.TemporaryDirectory(prefix='omareel-docs-') as directory:
        work = Path(directory)
        mocks = work / 'mockbin'
        mocks.mkdir()
        for name, body in (('omarchy-shell', 'exit 0'), ('notify-send', 'exit 0'), ('wl-copy', 'cat >/dev/null')):
            file = mocks / name
            file.write_text('#!/bin/sh\n' + body + '\n')
            file.chmod(0o700)
        config = work / 'config.json'
        config.write_text(json.dumps({'outputDir': directory, 'mic': False,
                                     'studio': {'enabled': True}, 'upload': {'provider': 'none'}}))
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_QPA_PLATFORMTHEME='',
                   XDG_RUNTIME_DIR=directory, XDG_CACHE_HOME=str(work / 'cache'),
                   OMAREEL_CONFIG=str(config), RCLONE_CONFIG=str(work / 'unused.conf'),
                   PATH=str(mocks) + os.pathsep + os.environ['PATH'], PYTHONDONTWRITEBYTECODE='1')
        env.pop('OMAREEL_OPERATION_LOCKED', None)
        demo = work / 'example.png'
        qml(work, 'demo', (DOCS / 'screenshots/demo.qml').read_text().replace('__OUTPUT__', json.dumps(str(demo))), env)
        source = work / 'example.mp4'
        run(['ffmpeg', '-v', 'error', '-loop', '1', '-i', demo, '-t', '3', '-r', '30',
             '-c:v', 'libx264', '-threads', '2', '-pix_fmt', 'yuv420p', source], env)
        # Real recording metadata format, with one explicitly synthetic click.
        (work / 'index.jsonl').write_text(json.dumps({'file': str(source), 'capture': {
            'zoomOnClicks': True, 'clicks': [{'time': .5, 'x': .62, 'y': .59}]}}) + '\n')
        for preset in ('midnight', 'paper'):
            exported = json.loads(run([ROOT / 'bin/omareel', 'studio', 'export', source,
                                       json.dumps({'preset': preset})], env))
            # CLI returns a saved recording entry. Extract frames from the actual MP4.
            video = Path(exported['file'])
            run(['ffmpeg', '-v', 'error', '-i', video, '-frames:v', '1', '-y',
                 DOCS / ('studio-' + preset + '.png')], env)
            if preset == 'midnight':
                run(['ffmpeg', '-v', 'error', '-ss', '1.1', '-i', video, '-frames:v', '1', '-y',
                     DOCS / 'studio-click-zoom.png'], env)
        template = '''import QtQuick
import QtQuick.Window
import Quickshell
import qs.Commons as Commons
ShellRoot {
  property int ticks: 0
  property bool saved: false
  Window {
    id: window
    width: 600; height: editor.implicitHeight + 40
    visible: true; color: Commons.Color.popups.background
    Rectangle { anchors.fill: parent; color: window.color }
    StudioEditor {
      id: editor
      x: 20; y: 20; width: 560
      cli: __CLI__
      Component.onCompleted: begin(__VIDEO__, {})
    }
  }
  Timer {
    interval: 100; repeat: true; running: true
    onTriggered: {
      ticks++
      if (ticks > 450) { console.error("SCREENSHOT FAILED", editor.feedback); Qt.exit(1); return }
      if (!saved && !editor.waiting && editor.renderedRevision === editor.revision && editor.previewUrl) {
        saved = true
        settle.start()
      }
    }
  }
  Timer { id: settle; interval: 500; onTriggered: window.contentItem.grabToImage(function(result) {
    if (!result.saveToFile(__OUTPUT__)) { Qt.exit(1); return }
    Qt.quit()
  }) }
}'''
        for key, value in {'__CLI__': str(ROOT / 'bin/omareel'), '__VIDEO__': str(source),
                           '__OUTPUT__': str(DOCS / 'studio-editor.png')}.items():
            template = template.replace(key, json.dumps(value))
        qml(work, 'editor', template, env)
        for name in ('midnight', 'paper', 'click-zoom', 'editor'):
            file = DOCS / ('studio-' + name + '.png')
            assert file.is_file() and file.stat().st_size > 5000, file
            print('Captured ' + str(file.relative_to(ROOT)))


if __name__ == '__main__':
    main()
