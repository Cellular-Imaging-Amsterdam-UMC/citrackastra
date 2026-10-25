"""Validate local HTML links, assets, language and theme controls."""

import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.ids, self.theme, self.english = [], set(), False, False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "html":
            self.english = values.get("lang") == "en"
        if "id" in values:
            self.ids.add(values["id"])
        if "data-theme-toggle" in values:
            self.theme = True
        for key in ("src", "href"):
            if key in values:
                self.refs.append(values[key])


def check(root):
    root = Path(root).resolve()
    pages = {}
    for path in root.glob("*.html"):
        parsed = Page()
        parsed.feed(path.read_text(encoding="utf-8"))
        if not parsed.english or not parsed.theme:
            raise ValueError(f"Missing English language or theme control: {path.name}")
        pages[path] = parsed
    if len(pages) != 4:
        raise ValueError("Expected four documentation pages")
    for path, page in pages.items():
        for ref in page.refs:
            parts = urlsplit(ref)
            if parts.scheme or parts.netloc:
                continue
            target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError(f"Broken local reference in {path.name}: {ref}")
            if parts.fragment and target in pages and parts.fragment not in pages[target].ids:
                raise ValueError(f"Missing fragment: {ref}")
    catalog = json.loads((root / "assets/examples.json").read_text(encoding="utf-8"))
    for sample in catalog["samples"]:
        for path in sample["images"]:
            if not (root / path).is_file():
                raise ValueError(f"Missing gallery image: {path}")
    print(f"Verified {len(pages)} English pages, local links, theme controls and {len(catalog['samples'])} galleries")


if __name__ == "__main__":
    check(sys.argv[1] if len(sys.argv) > 1 else "docs")
