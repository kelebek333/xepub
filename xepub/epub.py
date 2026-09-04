"""Defensive, dependency-free EPUB parsing.

Books are never extracted.  Entries are validated once and read on demand from
the archive, which keeps the trust boundary small and avoids temporary files.
"""
from __future__ import annotations

import hashlib
import html
import mimetypes
import posixpath
import re
import stat
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree as ET

MAX_ENTRIES = 10_000
MAX_ENTRY_SIZE = 64 * 1024 * 1024
MAX_TOTAL_SIZE = 512 * 1024 * 1024
MAX_RATIO = 200
MAX_XML_SIZE = 8 * 1024 * 1024
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; img-src xepub:; style-src xepub: 'unsafe-inline'; "
    "font-src xepub:; script-src 'none'; connect-src 'none'; media-src 'none'; "
    "object-src 'none'; frame-src 'none'; child-src 'none'; worker-src 'none'; "
    "manifest-src 'none'; base-uri xepub:; form-action 'none'; frame-ancestors 'none'"
)

# ElementTree does not fetch external DTDs.  EPUB 2 NCX documents commonly
# carry the official NCX DOCTYPE, so allow declarations while rejecting the
# entity definitions that enable expansion attacks or external entity access.
_XML_DANGEROUS = re.compile(br"<!\s*ENTITY\b", re.I)
_SCRIPT = re.compile(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>|<\s*script\b[^>]*/\s*>", re.I | re.S)
_EVENT = re.compile(r"\s+on[a-z][\w:-]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_JS_URL = re.compile(r"(?P<a>\b(?:href|src)\s*=\s*)(?P<q>['\"]?)\s*(?:javascript|vbscript)\s*:[^\s>]*(?P=q)", re.I)
_META_REFRESH = re.compile(r"<\s*meta\b(?=[^>]*http-equiv\s*=\s*['\"]?refresh\b)[^>]*>", re.I)


class EpubError(ValueError):
    pass


@dataclass(frozen=True)
class ManifestItem:
    id: str
    path: str
    media_type: str
    properties: frozenset[str]


@dataclass(frozen=True)
class TocEntry:
    label: str
    href: str
    children: tuple["TocEntry", ...] = ()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def normalize_path(base: str, target: str) -> str:
    """Resolve an EPUB-internal path and reject escaping/absolute paths."""
    target = unquote(urlsplit(target).path).replace("\\", "/")
    if not target or target.startswith("/") or re.match(r"^[A-Za-z]:", target):
        raise EpubError("Invalid absolute or empty archive path")
    combined = posixpath.normpath(posixpath.join(posixpath.dirname(base), target))
    if combined == ".." or combined.startswith("../") or combined.startswith("/"):
        raise EpubError("Archive path escapes the book")
    return combined


def safe_xml(data: bytes, context: str) -> ET.Element:
    if len(data) > MAX_XML_SIZE:
        raise EpubError(f"{context} is too large")
    if _XML_DANGEROUS.search(data):
        raise EpubError(f"Unsafe XML declaration in {context}")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise EpubError(f"Malformed XML in {context}: {exc}") from exc


class EpubBook:
    def __init__(self, filename: str | Path):
        self.filename = Path(filename).resolve()
        try:
            self.archive = zipfile.ZipFile(self.filename)
        except (OSError, zipfile.BadZipFile) as exc:
            raise EpubError("Not a readable EPUB archive") from exc
        self.entries = self._validate_archive()
        digest = hashlib.sha256()
        with self.filename.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        self.identifier = digest.hexdigest()
        self.package_path = self._find_package()
        self.metadata: dict[str, str] = {}
        self.manifest: dict[str, ManifestItem] = {}
        self.spine: list[str] = []
        self.page_progression = "default"
        self.toc: tuple[TocEntry, ...] = ()
        self._parse_package()

    def close(self) -> None:
        self.archive.close()

    def _validate_archive(self) -> frozenset[str]:
        infos = self.archive.infolist()
        if not infos or len(infos) > MAX_ENTRIES:
            raise EpubError("Archive has an unsafe number of entries")
        total = 0
        names: set[str] = set()
        for info in infos:
            raw = info.filename.replace("\\", "/")
            path = PurePosixPath(raw)
            if (not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw)
                    or ".." in path.parts or "" in path.parts):
                raise EpubError(f"Unsafe ZIP path: {raw!r}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise EpubError(f"ZIP symlink is not allowed: {raw}")
            if info.file_size > MAX_ENTRY_SIZE:
                raise EpubError(f"ZIP entry is too large: {raw}")
            total += info.file_size
            if total > MAX_TOTAL_SIZE:
                raise EpubError("Expanded EPUB is too large")
            if info.file_size and info.compress_size == 0:
                raise EpubError(f"Invalid compression size: {raw}")
            if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
                raise EpubError(f"Suspicious compression ratio: {raw}")
            normalized = posixpath.normpath(raw)
            if normalized in names:
                raise EpubError(f"Duplicate ZIP entry: {normalized}")
            names.add(normalized)
        return frozenset(names)

    def read(self, path: str, limit: int = MAX_ENTRY_SIZE) -> bytes:
        path = posixpath.normpath(unquote(path).lstrip("/"))
        if path not in self.entries or path.startswith("../"):
            raise EpubError("Resource does not belong to this EPUB")
        info = self.archive.getinfo(path)
        if info.file_size > limit:
            raise EpubError("Resource exceeds its size limit")
        with self.archive.open(info) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise EpubError("Resource exceeded its declared limit")
        return data

    def _find_package(self) -> str:
        root = safe_xml(self.read("META-INF/container.xml", MAX_XML_SIZE), "container.xml")
        for element in root.iter():
            if _local(element.tag) == "rootfile":
                value = element.get("full-path", "")
                return normalize_path("root", value)
        raise EpubError("EPUB container has no package document")

    def _parse_package(self) -> None:
        root = safe_xml(self.read(self.package_path, MAX_XML_SIZE), "package document")
        spine_ids: list[str] = []
        toc_id = ""
        for node in root.iter():
            kind = _local(node.tag)
            if kind in {"title", "creator", "language", "publisher", "description", "identifier"}:
                text = " ".join("".join(node.itertext()).split())
                if text and kind not in self.metadata:
                    self.metadata[kind] = text
            elif kind == "item":
                item_id, href = node.get("id", ""), node.get("href", "")
                if item_id and href:
                    path = normalize_path(self.package_path, href)
                    self.manifest[item_id] = ManifestItem(
                        item_id, path, node.get("media-type", "application/octet-stream"),
                        frozenset(node.get("properties", "").split()))
            elif kind == "spine":
                toc_id = node.get("toc", "")
                self.page_progression = node.get("page-progression-direction", "default")
            elif kind == "itemref" and node.get("linear", "yes") != "no":
                spine_ids.append(node.get("idref", ""))
        self.spine = [self.manifest[i].path for i in spine_ids if i in self.manifest]
        if not self.spine:
            raise EpubError("EPUB has no readable spine")
        nav = next((x for x in self.manifest.values() if "nav" in x.properties), None)
        if nav:
            self.toc = self._parse_nav(nav.path)
        elif toc_id in self.manifest:
            self.toc = self._parse_ncx(self.manifest[toc_id].path)
        if not self.toc:
            self.toc = tuple(TocEntry(Path(p).stem, p) for p in self.spine)

    def _parse_nav(self, path: str) -> tuple[TocEntry, ...]:
        root = safe_xml(self.read(path, MAX_XML_SIZE), "navigation document")
        nav = next((n for n in root.iter() if _local(n.tag) == "nav" and
                    ("toc" in n.get("{http://www.idpf.org/2007/ops}type", "").split()
                     or n.get("role") == "doc-toc")), None)
        if nav is None:
            return ()

        def walk(parent: ET.Element) -> tuple[TocEntry, ...]:
            result = []
            for li in [n for n in list(parent) if _local(n.tag) == "li"]:
                link = next((n for n in list(li) if _local(n.tag) == "a"), None)
                nested = next((n for n in list(li) if _local(n.tag) in {"ol", "ul"}), None)
                if link is not None and link.get("href"):
                    result.append(TocEntry(" ".join("".join(link.itertext()).split()),
                                           urljoin(path, link.get("href")), walk(nested) if nested is not None else ()))
            return tuple(result)
        listing = next((n for n in nav.iter() if _local(n.tag) in {"ol", "ul"}), None)
        return walk(listing) if listing is not None else ()

    def _parse_ncx(self, path: str) -> tuple[TocEntry, ...]:
        root = safe_xml(self.read(path, MAX_XML_SIZE), "NCX document")
        navmap = next((n for n in root.iter() if _local(n.tag) == "navmap"), None)
        if navmap is None:
            return ()

        def walk(parent: ET.Element) -> tuple[TocEntry, ...]:
            result = []
            for point in [n for n in list(parent) if _local(n.tag) == "navpoint"]:
                label_node = next((n for n in point.iter() if _local(n.tag) == "text"), None)
                content = next((n for n in point.iter() if _local(n.tag) == "content"), None)
                if content is not None and content.get("src"):
                    label = " ".join("".join(label_node.itertext()).split()) if label_node is not None else "Untitled"
                    result.append(TocEntry(label, urljoin(path, content.get("src")), walk(point)))
            return tuple(result)
        return walk(navmap)

    def resource(self, path: str) -> tuple[bytes, str]:
        data = self.read(path)
        item = next((x for x in self.manifest.values() if x.path == path), None)
        mime = item.media_type if item else (mimetypes.guess_type(path)[0] or "application/octet-stream")
        if mime in {"application/xhtml+xml", "text/html"}:
            data = sanitize_xhtml(data, path).encode("utf-8")
            mime = "text/html"
        elif mime == "text/css":
            data = sanitize_css(data.decode("utf-8", "replace"), path).encode("utf-8")
        elif mime == "image/svg+xml":
            data = sanitize_svg(data).encode("utf-8")
        return data, mime


def sanitize_css(css: str, path: str = "") -> str:
    css = re.sub(r"@import\s+[^;]+;", "", css, flags=re.I)
    css = re.sub(r"expression\s*\([^)]*\)", "", css, flags=re.I)
    css = re.sub(r"url\s*\(\s*(['\"]?)\s*(?:https?|file|javascript|data):.*?\1\s*\)", "none", css, flags=re.I)
    return css


def sanitize_svg(data: bytes) -> str:
    text = data.decode("utf-8", "replace")
    text = _SCRIPT.sub("", text)
    text = _EVENT.sub("", text)
    text = _JS_URL.sub(lambda m: m.group("a") + '"#"', text)
    text = re.sub(r"(?P<a>\b(?:href|xlink:href)\s*=\s*)(?P<q>['\"])(?:https?|file|data):.*?(?P=q)",
                  lambda m: m.group("a") + '"#"', text, flags=re.I)
    text = sanitize_css(text)
    return text


def sanitize_xhtml(data: bytes, path: str) -> str:
    text = data.decode("utf-8", "replace")
    text = _SCRIPT.sub("", text)
    text = _META_REFRESH.sub("", text)
    text = _EVENT.sub("", text)
    text = _JS_URL.sub(lambda m: m.group("a") + '"#"', text)
    base = posixpath.dirname(path).rstrip("/") + "/"
    head = (f'<meta http-equiv="Content-Security-Policy" content="{html.escape(CONTENT_SECURITY_POLICY, quote=True)}">'
            f'<base href="xepub://book/{html.escape(base, quote=True)}">')
    if re.search(r"<head\b[^>]*>", text, re.I):
        text = re.sub(r"(<head\b[^>]*>)", r"\1" + head, text, count=1, flags=re.I)
    else:
        text = head + text
    return text


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)


def xhtml_text(data: bytes) -> str:
    """Extract searchable text without fetching or resolving any resources."""
    parser = _TextExtractor()
    parser.feed(data.decode("utf-8", "replace"))
    parser.close()
    return " ".join(" ".join(parser.parts).split())
