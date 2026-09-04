# Xepub

<img width="1446" height="979" alt="xepub" src="https://github.com/user-attachments/assets/5c6ef2c5-5152-4359-8a7c-4d00bcf209f7" />

EPUB reader for Linux desktops.

Xepub is an XApp, so it works in any desktop and any distro.

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

## Security

Xepub is built with security in mind.

The security design and measures are documented in [SECURITY.md](SECURITY.md).
