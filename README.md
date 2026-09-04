# Xepub

Xepub is an EPUB reader for Linux.

It's an XApp, so it works in any desktop and any distro.

## Build and run

```sh
meson setup build
meson test -C build
meson install -C build
xepub my-book.epub
```

Runtime requirements are Python 3, PyGObject, GTK 3, XApp, and WebKitGTK 4.1.

## Controls

- Left/Right, Page Up/Page Down, Space/Backspace: turn pages
- Ctrl+Up/Ctrl+Down: change chapters
- Ctrl+O: open; Ctrl+F: find; Ctrl+B: bookmark
- F11: distraction-free fullscreen; Ctrl+Q: quit

EPUB archives are never extracted. Xepub rejects unsafe ZIP structures and
dangerous XML declarations, sanitizes active content, serves only current-book
resources through its private `xepub:` origin, disables unnecessary WebKit
features, and confirms external links before opening them outside the reader.
