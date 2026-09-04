# Xepub security model

Xepub treats every EPUB as untrusted input. Book resources are read directly
from a validated ZIP archive and are exposed to WebKit only through the private
`xepub://book/` URI scheme.

## Offline WebKit context

The reader's ephemeral WebKit context is explicitly sandboxed. HTTP, HTTPS,
FTP, and WebSocket traffic is routed to an unreachable loopback proxy. This is
a coarse offline boundary for WebKit; opening a confirmed external link uses
`Gio.AppInfo` and the system browser, outside this context.

## Network URL filter

A WebKit user-content filter blocks `http:`, `https:`, `ftp:`, `ws:`, `wss:`,
and `file:` URLs. It prevents ordinary book subresources from reaching the
network layer even if malformed markup evades the XHTML and CSS sanitizers.

The filter is compiled into a private temporary directory for each reader
window and is removed with that window.

## Content Security Policy

Every successful `xepub:` scheme response carries a restrictive CSP response
header. A response header cannot be displaced, commented out, or preceded by
hostile markup in the EPUB. The policy denies scripts, connections, media,
objects, frames, workers, manifests, and form submission. Images, styles, and
fonts may load only through the private `xepub:` scheme.

`base-uri xepub:` is intentionally allowed because Xepub inserts an `xepub:`
base element so relative EPUB resources resolve within the book. Using
`base-uri 'none'` would block that element and break publisher stylesheets.
The URI-scheme handler independently verifies that the requested resource is
an entry in the currently open EPUB.

The CSP meta element and active-content sanitization remain as defense in
depth. They are not the primary network boundary.

## JavaScript

JavaScript markup is disabled, so scripts and JavaScript-related attributes
from books are removed during document parsing. Xepub temporarily enables the
JavaScript engine only to evaluate fixed application-owned pagination and
annotation operations. It never evaluates JavaScript supplied by a book.

## Archive and XML handling

EPUBs are never extracted. Archive validation rejects absolute and traversing
paths, duplicate normalized paths, symbolic links, excessive entry counts,
large entries, excessive total expansion, and suspicious compression ratios.
XML inputs have a size limit, external entities are not resolved, and entity
declarations are rejected.
