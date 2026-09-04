import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "xepub"))
from epub import EpubBook, EpubError, normalize_path, sanitize_css, sanitize_xhtml, xhtml_text


CONTAINER = b'''<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
 <rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>'''

OPF3 = b'''<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" page-progression-direction="ltr">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test Book</dc:title><dc:creator>A. Reader</dc:creator></metadata>
 <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest>
 <spine page-progression-direction="rtl"><itemref idref="chapter"/></spine>
</package>'''

NAV = b'''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol><li><a href="chapter.xhtml#start">Chapter One</a></li></ol></nav></body></html>'''

CHAPTER = b'''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>x</title>
<script>alert(1)</script></head><body onload="steal()"><h1 id="start">Hello</h1>
<a href="javascript:steal()">bad</a><img src="cover.jpg"/></body></html>'''

OPF2 = b'''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>EPUB Two</dc:title></metadata>
<manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="n" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>
<spine toc="n"><itemref idref="c"/></spine></package>'''
NCX = b'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint><navLabel><text>NCX Chapter</text></navLabel><content src="chapter.xhtml#start"/></navPoint></navMap></ncx>'''


def write_epub(path, entries=None):
    content = {"mimetype": b"application/epub+zip", "META-INF/container.xml": CONTAINER,
               "OPS/book.opf": OPF3, "OPS/nav.xhtml": NAV, "OPS/chapter.xhtml": CHAPTER,
               "OPS/cover.jpg": b"not-a-real-image"}
    if entries: content.update(entries)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in content.items(): archive.writestr(name, data)


class EpubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = Path(self.temp.name) / "book.epub"
        write_epub(self.path)

    def tearDown(self): self.temp.cleanup()

    def test_epub3_metadata_spine_nav_and_rtl(self):
        book = EpubBook(self.path)
        self.assertEqual(book.metadata["title"], "Test Book")
        self.assertEqual(book.spine, ["OPS/chapter.xhtml"])
        self.assertEqual(book.toc[0].label, "Chapter One")
        self.assertEqual(book.toc[0].href, "OPS/chapter.xhtml#start")
        self.assertEqual(book.page_progression, "rtl")
        book.close()

    def test_active_content_is_removed_and_csp_added(self):
        book = EpubBook(self.path); body, mime = book.resource("OPS/chapter.xhtml")
        text = body.decode()
        self.assertEqual(mime, "text/html")
        self.assertNotIn("<script", text.lower()); self.assertNotIn("onload", text.lower())
        self.assertNotIn("javascript:", text.lower()); self.assertIn("Content-Security-Policy", text)
        self.assertIn('base href="xepub://book/OPS/"', text)

    def test_epub2_ncx(self):
        old = Path(self.temp.name) / "old.epub"
        write_epub(old, {"OPS/book.opf": OPF2, "OPS/toc.ncx": NCX})
        book = EpubBook(old)
        self.assertEqual(book.metadata["title"], "EPUB Two")
        self.assertEqual(book.toc[0].label, "NCX Chapter")
        self.assertEqual(book.toc[0].href, "OPS/chapter.xhtml#start")

    def test_resource_is_confined_to_archive(self):
        book = EpubBook(self.path)
        with self.assertRaises(EpubError): book.read("../etc/passwd")
        with self.assertRaises(EpubError): book.read("missing")

    def test_rejects_zip_path_traversal(self):
        bad = Path(self.temp.name) / "bad.epub"; write_epub(bad, {"../escape": b"bad"})
        with self.assertRaises(EpubError): EpubBook(bad)

    def test_rejects_symlink(self):
        bad = Path(self.temp.name) / "link.epub"
        with zipfile.ZipFile(bad, "w") as archive:
            link = zipfile.ZipInfo("link"); link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16; archive.writestr(link, "target")
        with self.assertRaises(EpubError): EpubBook(bad)

    def test_rejects_entities(self):
        bad = Path(self.temp.name) / "entity.epub"
        write_epub(bad, {"META-INF/container.xml": b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><x>&y;</x>'})
        with self.assertRaises(EpubError): EpubBook(bad)

    def test_external_entity_declaration_is_rejected(self):
        bad = Path(self.temp.name) / "xxe.epub"
        payload = b'<!DOCTYPE container [<!ENTITY secret SYSTEM "file:///etc/passwd">]><container>&secret;</container>'
        write_epub(bad, {"META-INF/container.xml": payload})
        with self.assertRaises(EpubError): EpubBook(bad)

    def test_normalization(self):
        self.assertEqual(normalize_path("OPS/book.opf", "Text/one.xhtml"), "OPS/Text/one.xhtml")
        for unsafe in ("/etc/passwd", "../../escape", "C:/evil"):
            with self.assertRaises(EpubError): normalize_path("OPS/book.opf", unsafe)

    def test_css_sanitizer(self):
        clean = sanitize_css('@import "http://evil"; x{background:url(https://evil/x);width:expression(x)}')
        self.assertNotIn("@import", clean); self.assertNotIn("https:", clean); self.assertNotIn("expression", clean)

    def test_search_text_tolerates_html_entities(self):
        source = b'<html><style>.door{}</style><body>Open&nbsp;the <b>door</b>.</body></html>'
        self.assertEqual(xhtml_text(source), "Open the door .")


if __name__ == "__main__": unittest.main()
