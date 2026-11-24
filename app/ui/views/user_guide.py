"""User Guide view: renders docs/user_guide.md with lossless Retina HiDPI screenshots."""
from __future__ import annotations

import base64
import html
import re
import struct
from pathlib import Path

import streamlit as st

from app.config import ROOT

IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
CAPTURE_SCALE = 2.5


def _png_logical_width(path: Path) -> int:
    data = path.read_bytes()[:24]
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        w, _ = struct.unpack(">II", data[16:24])
        return max(320, int(round(w / CAPTURE_SCALE)))
    return 1100


def _render_lossless_png(path: Path, caption: str) -> None:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    lw = _png_logical_width(path)
    cap_html = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
    st.markdown(
        f"<figure class='ug-fig'>"
        f"<img src='data:image/png;base64,{b64}' alt='{html.escape(caption)}' "
        f"style='width: min(100%, {lw}px);'/>"
        f"{cap_html}</figure>",
        unsafe_allow_html=True,
    )


def render() -> None:
    guide_path = ROOT / "docs" / "user_guide.md"
    if not guide_path.exists():
        st.info("User Guide markdown (`docs/user_guide.md`) not yet generated.")
        return

    content = guide_path.read_text(encoding="utf-8")
    pos = 0
    for m in IMG_RE.finditer(content):
        before = content[pos:m.start()].strip()
        if before:
            st.markdown(before)
        caption, rel_path = m.group(1), m.group(2)
        img_file = (guide_path.parent / rel_path).resolve()
        if img_file.exists() and img_file.is_relative_to(guide_path.parent):
            _render_lossless_png(img_file, caption)
        else:
            st.caption(f"*(Screenshot `{rel_path}` — {caption})*")
        pos = m.end()
    tail = content[pos:].strip()
    if tail:
        st.markdown(tail)
