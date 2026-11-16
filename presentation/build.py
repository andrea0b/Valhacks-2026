"""Assemble the presentation into a single self-contained HTML file.

    python presentation/data.py            # chart data      -> presentation/build/data.json
    python presentation/model/export.py    # model + replay  -> presentation/build/model.json, live.json
    python presentation/build.py           # -> docs/index.html (open it in any browser)

Also writes presentation/build/artifact.html (the same page without the <html> wrapper, for
claude.ai artifacts) and presentation/build/dev.html (with the visual QA helper `__qa()`).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC, BUILD = HERE / "src", HERE / "build"
DOCS = HERE.parent if HERE.parent.name == "docs" else HERE.parent / "docs"   # works from presentation or presentation
SECTIONS = ["opening", "economics", "data", "model", "decision", "results", "live", "closing"]


def read(path: Path) -> str:
    return path.read_text(encoding="utf8") if path.exists() else ""


def embed_json(path: Path, drop: tuple = ()) -> str:
    """JSON safe inside a <script> element (`drop`: top-level keys the page does not need)."""
    if not path.exists():
        return "null"
    obj = json.loads(path.read_text(encoding="utf8"))
    for k in drop:
        obj.pop(k, None)
    return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")


def page(dev: bool) -> str:
    slides = "\n".join(read(SRC / "sections" / f"{s}.html") for s in SECTIONS)
    live = (BUILD / "model.json").exists() and (BUILD / "live.json").exists()
    scripts = [read(SRC / "deck.js"), read(HERE / "model" / "model.js") if live else ""]
    scripts += [read(SRC / "sections" / f"{s}.js") for s in SECTIONS]
    if dev:
        scripts.append(read(SRC / "qa.js"))
    scripts.append("Deck.boot();")
    # one <script> per file, so an error in one section cannot stop the others
    tags = "\n".join("<script>\n" + s.replace("</script", "<\\/script") + "\n</script>" for s in scripts if s.strip())
    html = read(SRC / "shell.html")
    for key, value in [("/*STYLE*/", read(SRC / "styles.css")), ("<!--SLIDES-->", slides),
                       ("/*DATA*/", embed_json(BUILD / "data.json")),
                       ("/*MODEL*/", embed_json(BUILD / "model.json") if live else "null"),
                       ("/*LIVE*/", embed_json(BUILD / "live.json", drop=("policy",)) if live else "null"),
                       ("<!--SCRIPTS-->", tags)]:
        html = html.replace(key, value)
    return html


def standalone(body: str) -> str:
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="description" content="Overbooked: hotel overbooking: deciding which booking requests to accept, '
            'one at a time. Interactive presentation with the live model.">\n'
            + body.replace("</style>", "</style>\n</head>\n<body>", 1) + "\n</body>\n</html>\n")


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    prod = page(dev=False)
    (DOCS / "index.html").write_text(standalone(prod), encoding="utf8")
    (BUILD / "artifact.html").write_text(prod, encoding="utf8")
    (BUILD / "dev.html").write_text(standalone(page(dev=True)), encoding="utf8")
    print(f"docs/index.html · {len(prod.encode()) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
