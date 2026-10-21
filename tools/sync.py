"""Copy published articles from the Obsidian vault into this Hugo site.

Sources (Markdown with frontmatter title/date/slug/description/publish):
  ~/Documents/ai_workspace/writing/esp32/  -> category ESP32
  ~/Documents/ai_workspace/writing/read/   -> category 导读

Each article with `publish: true` becomes a page bundle at
content/posts/<slug>/index.md. Obsidian image embeds (![[x.jpg]]) and local
Markdown images are looked up in the vault, resized to 1600px, rotated upright
and stripped of EXIF. Chinese–Latin spacing is added with pangu while leaving
Markdown syntax, code and URLs untouched. The vault files are never modified.

Usage: .venv/bin/python tools/sync.py
"""
import os
import re
import shutil
import sys
from pathlib import Path

import pangu
from PIL import Image, ImageOps

VAULT = Path(os.environ.get("VAULT", "~/Documents/ai_workspace")).expanduser()
SOURCES = {
    VAULT / "writing" / "esp32": "ESP32",
    VAULT / "writing" / "read": "导读",
    VAULT / "writing" / "running": "跑步",
}
ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "content" / "posts"
MAX_SIDE = 1600
QUOTES = "“”‘’"
NEUTRAL = ""  # stands in for images: pangu never spaces around it
LATIN = "A"         # stands in for inline code: spaced like a Latin word


# ---------- spacing ----------

INLINE = re.compile(
    r"(?P<img>!\[[^\]]*\]\([^)]*\))"
    r"|(?P<code>`[^`]+`)"
    r"|(?P<lopen>\[)(?=[^\]]*\]\([^)]*\))"
    r"|(?P<lclose>\]\([^)]*\))"
    r"|(?P<html><[^>]+>)"
    r"|(?P<em>\*\*|\*)"
)


def space_line(line):
    """Run pangu on the prose of one Markdown line.

    Markup is lifted out first, pangu runs on the remaining text, and only the
    spaces pangu inserted are kept. Markup goes back in at its old position;
    when a space lands on it, closing markup stays before the space and opening
    markup moves after it (so "是**ESP32**" becomes "是 **ESP32**").
    """
    plain, marks, atoms = [], {}, {}
    em_open = False
    pos = 0
    for m in INLINE.finditer(line):
        plain.append(line[pos:m.start()])
        i = sum(map(len, plain))
        kind = m.lastgroup
        if kind in ("img", "code"):
            atoms[i] = m.group()
            plain.append(NEUTRAL if kind == "img" else LATIN)
        else:
            if kind == "em":
                side = "close" if em_open else "open"
                em_open = not em_open
            else:
                side = {"lopen": "open", "lclose": "close", "html": "open"}[kind]
            marks.setdefault(i, []).append((side, m.group()))
        pos = m.end()
    plain.append(line[pos:])
    plain = "".join(plain)

    spaced = pangu.space_text(plain)
    inserts = set()  # indexes in plain before which a space is inserted
    i = j = 0
    while i < len(plain) and j < len(spaced):
        if plain[i] == spaced[j]:
            i += 1
            j += 1
        elif spaced[j] == " ":
            prev = plain[i - 1] if i else ""
            if prev not in QUOTES and plain[i] not in QUOTES:
                inserts.add(i)
            j += 1
        else:  # pangu changed something other than spacing: ignore it
            i += 1
            j += 1

    out = []
    for k in range(len(plain) + 1):
        here = marks.get(k, [])
        if k in inserts:
            out += [t for s, t in here if s == "close"] + [" "] + [t for s, t in here if s == "open"]
        else:
            out += [t for _, t in here]
        if k < len(plain):
            out.append(atoms.get(k, plain[k]))
    return "".join(out)


NOWRAP_NAMES = ["Muse Gadgets", "Claude Code", "Home Assistant", "Personal Agent",
                "Gadgets Token", "Opus 5.5", "Sonnet 5.5"]
NOWRAP_RE = re.compile("|".join(re.escape(n) for n in NOWRAP_NAMES))


# Short final phrases that would otherwise leave a two-character last line on a phone.
# Static copy only: a phrase that is no longer in the text is simply skipped.
TAIL_PROTECT = ["干正事，刷机。", "也只能这样了。", "对话的感觉。"]


def protect_tails(line):
    for t in TAIL_PROTECT:
        if line.endswith(t):
            line = line[: -len(t)] + f'<span style="white-space:nowrap">{t}</span>'
    return line


def keep_names_together(line):
    """Join the words of product names with a no-break space, outside code and link targets."""
    parts = re.split(r"(`[^`]*`|\]\([^)]*\)|<[^>]+>)", line)
    return "".join(
        p if i % 2 else NOWRAP_RE.sub(lambda m: m.group().replace(" ", "\u00a0"), p)
        for i, p in enumerate(parts)
    )


def space_markdown(text):
    out, fence, in_list = [], False, False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
            out.append(line)
            continue
        is_bullet = bool(re.match(r"\s*(?:[-*+]|\d+\.)\s+", line))
        if line.strip() and not line.startswith(" ") and not is_bullet:
            in_list = False
        elif is_bullet:
            in_list = True
        # Lines indented under a list item continue that item; they are prose, not code.
        indented_code = line.startswith("    ") and not in_list
        if fence or indented_code or line.lstrip().startswith("<"):
            out.append(line)
        else:
            # Keep list bullets, quote markers and heading hashes out of the
            # emphasis scan ("* item" is a bullet, not an opening "*").
            prefix = re.match(r"(\s*(?:>\s?)*(?:[-*+]\s+|\d+\.\s+|#+\s+)?)", line).group(1)
            out.append(prefix + protect_tails(keep_names_together(space_line(line[len(prefix):]))))
    return "\n".join(out)


# ---------- images ----------

def find_in_vault(name):
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if name in files:
            return Path(root) / name
    return None


def export_image(src, dest_dir):
    im = ImageOps.exif_transpose(Image.open(src))
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    if im.mode in ("RGBA", "LA", "P"):
        name = src.stem + ".png"
        im.save(dest_dir / name, optimize=True)
    else:
        name = src.stem + ".jpg"
        im.convert("RGB").save(dest_dir / name, quality=82, optimize=True)
    return name


def convert_images(text, src_file, dest_dir):
    def locate(target):
        path = src_file.parent / target
        if path.exists():
            return path
        path = find_in_vault(Path(target).name)
        if not path:
            sys.exit(f"图片找不到: {target} ({src_file.name})")
        return path

    def embed(m):
        target, _, alt = m.group(1).partition("|")
        alt = alt.strip() if alt and not alt.strip().isdigit() else ""
        return f"![{alt}]({export_image(locate(target.strip()), dest_dir)})"

    def local(m):
        if re.match(r"https?://", m.group(2)) or (dest_dir / m.group(2)).exists():
            return m.group(0)  # remote, or already exported by the embed pass
        return f"![{m.group(1)}]({export_image(locate(m.group(2)), dest_dir)})"

    text = re.sub(r"!\[\[([^\]]+)\]\]", embed, text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", local, text)
    return text


def convert_wikilinks(text, links):
    """[[note]] / [[note|text]] / [[note#heading]]: a link when note is a
    published article (by file name or title), plain text otherwise."""
    def repl(m):
        target, _, label = m.group(1).partition("|")
        note = target.split("#", 1)[0].strip()
        label = label.strip() or note
        slug = links.get(note)
        return f"[{label}](/posts/{slug}/)" if slug else label

    return re.sub(r"(?<!!)\[\[([^\]]+)\]\]", repl, text)


# ---------- articles ----------

def parse_frontmatter(text):
    meta = {}
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip("\"'")
            text = text[end + 4:].lstrip("\n")
    return meta, text


def yaml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    found = []
    for folder, category in SOURCES.items():
        for f in sorted(folder.glob("*.md")):
            meta, body = parse_frontmatter(f.read_text())
            if meta.get("publish", "").lower() != "true":
                continue
            for key in ("slug", "date"):
                if not meta.get(key):
                    sys.exit(f"{f.name} 缺少 {key}")
            if not re.fullmatch(r"[a-z0-9-]+", meta["slug"]):
                sys.exit(f"{f.name} 的 slug 只能用小写字母、数字和连字符")
            found.append((meta, body, f, category))

    slugs = [m["slug"] for m, *_ in found]
    if len(set(slugs)) != len(slugs):
        sys.exit("slug 重复")

    # Bundles synced earlier but no longer published are removed.
    if POSTS.exists():
        for d in POSTS.iterdir():
            if d.is_dir() and d.name not in slugs and (d / ".synced").exists():
                shutil.rmtree(d)
                print(f"  删除 {d.name}")

    links = {}
    for meta, _, f, _ in found:
        links[f.stem] = meta["slug"]
        links[meta.get("title", f.stem)] = meta["slug"]

    for meta, body, f, category in found:
        d = POSTS / meta["slug"]
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        (d / ".synced").write_text(str(f.relative_to(VAULT)) + "\n")
        body = space_markdown(convert_wikilinks(convert_images(body, f, d), links))
        title = pangu.space_text(meta.get("title", f.stem))
        fm = [
            "---",
            f"title: {yaml_str(title)}",
            f"date: {meta['date']}",
            f"slug: {meta['slug']}",
            f"categories: [{yaml_str(category)}]",
        ]
        if meta.get("description"):
            fm.append(f"description: {yaml_str(meta['description'])}")
        fm.append("---")
        (d / "index.md").write_text("\n".join(fm) + "\n\n" + body.rstrip() + "\n")
        print(f"  {category}  /posts/{meta['slug']}/  {title}")
    print(f"共 {len(found)} 篇")


if __name__ == "__main__":
    main()
