#!/usr/bin/env python3
"""cutroom setup - save the user's house style once, in <skill>/style.json.

Every later edit starts from this style, so the agent never has to ask again.
Give only the answers you have; the rest keep their current/default value.

usage:
  python setup.py --show
  python setup.py --aspect 9:16 --captions karaoke --accent "#FFD23F" --font "Montserrat ExtraBold"
                  --case upper --words 3 --position low --transition punch --zoom normal
                  --pace tight --lang en
  python setup.py --font-file "C:/path/MyFont.ttf"     # copies it into <skill>/fonts and uses it
  python setup.py --reset                               # delete style.json (next run asks again)

answers:
  --aspect      source | 16:9 | 9:16 | 1:1
  --captions    karaoke (spoken word in accent colour) | plain | off
  --accent      any hex colour            --color  main caption colour (default #FFFFFF)
  --font        a font family installed on the computer, or the bundled "Montserrat ExtraBold"
  --case        upper | normal            --words  1 | 2 | 3 | 4 (max words on screen)
  --size        small | medium | large    --position low | middle
  --transition  punch (instant zoom change at cuts) | smooth (eased zoom) | flash (punch + white flash) | none
  --zoom        subtle | normal | strong | off
  --pace        natural | tight | fast
  --lang        speaker language code, e.g. en, tr, es (empty = auto)
  --cards       auto (numbers, steps, call to action placed by rules) | manual (only cards you ask for) | off
  --card-look   solid (accent-colour box) | dark (dark glass box) | minimal (text only)
  --card-size   box (small card on the video) | full (keyword, stat and step cards fill the screen)
  --broll       full (pictures/B-roll fill the frame) | window (float in the middle with a border)
  --broll-border  border colour for window, e.g. "#FFFFFF" or "accent"
"""
import argparse, json, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STYLE = os.path.join(ROOT, "style.json")
FONTS = os.path.join(ROOT, "fonts")

PACE = {"natural": {"max_pause": 0.65, "keep_after": 0.2, "keep_before": 0.1},
        "tight": {"max_pause": 0.45, "keep_after": 0.14, "keep_before": 0.08},
        "fast": {"max_pause": 0.3, "keep_after": 0.1, "keep_before": 0.06}}
ZOOM = {"subtle": 1.06, "normal": 1.10, "strong": 1.16}
SIZE = {"small": 0.8, "medium": 1.0, "large": 1.25}


def font_name(path):
    """Full font name from a .ttf/.otf name table (nameID 4, else 1)."""
    data = open(path, "rb").read()
    num = struct.unpack(">H", data[4:6])[0]
    for i in range(num):
        tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
        if tag == b"name":
            count, str_off = struct.unpack(">HH", data[off + 2: off + 6])
            found = {}
            for j in range(count):
                pid, eid, lid, nid, ln, so = struct.unpack(">6H", data[off + 6 + 12 * j: off + 18 + 12 * j])
                raw = data[off + str_off + so: off + str_off + so + ln]
                if nid in (1, 4):
                    txt = raw.decode("utf-16-be", "ignore") if pid in (0, 3) else raw.decode("latin-1")
                    found.setdefault(nid, txt)
            return found.get(4) or found.get(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    for k in ("aspect", "captions", "accent", "color", "font", "font-file", "case", "words",
              "size", "position", "transition", "zoom", "pace", "lang", "cards", "card-look", "card-size", "broll", "broll-border"):
        ap.add_argument("--" + k)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()

    if a.reset:
        if os.path.exists(STYLE):
            os.remove(STYLE)
        print("style reset - the next edit will ask the setup questions again")
        return
    st = json.load(open(STYLE, encoding="utf-8")) if os.path.exists(STYLE) else {}
    if a.show:
        print(json.dumps(st, indent=2) if st else "no style saved yet (first run)")
        return

    cap = st.setdefault("captions", {})
    cut = st.setdefault("cut", {})
    zoom = st.setdefault("zoom", {})
    if a.aspect:
        st["aspect"] = a.aspect
    if a.captions:
        cap["on"] = a.captions != "off"
        cap["highlight"] = a.captions == "karaoke"
    if a.accent:
        cap["accent"] = a.accent
    if a.color:
        cap["color"] = a.color
    if a.font_file:
        os.makedirs(FONTS, exist_ok=True)
        shutil.copy2(a.font_file, FONTS)
        name = font_name(a.font_file)
        if not name:
            sys.exit("could not read the font name from that file")
        cap["font"] = name
        print("font installed:", name)
    elif a.font:
        cap["font"] = a.font
    if a.case:
        cap["upper"] = a.case == "upper"
    if a.words:
        cap["max_words"] = int(a.words)
    if a.size:
        cap["scale"] = SIZE[a.size]
    if a.position:
        cap["position"] = a.position
    if a.transition:
        zoom["transition"] = a.transition
    if a.zoom:
        zoom["auto_punch"] = a.zoom != "off"
        zoom["push_every"] = 0 if a.zoom == "off" else zoom.get("push_every", 6.0)
        if a.zoom in ZOOM:
            zoom["punch"] = ZOOM[a.zoom]
    if a.pace:
        cut.update(PACE[a.pace])
        st["pace"] = a.pace
    if a.cards:
        st.setdefault("cards", {})["mode"] = a.cards
    if a.card_size:
        st.setdefault("cards", {})["size"] = a.card_size
    if a.card_look:
        st.setdefault("cards", {})["look"] = a.card_look
    if a.broll:
        st.setdefault("broll", {})["fit"] = a.broll
    if a.broll_border:
        st.setdefault("broll", {})["border"] = a.broll_border
    if a.lang is not None:
        st["lang"] = a.lang
    st["_note"] = "cutroom house style. Change with scripts/setup.py; per-video changes go in <video>_cutroom/edit.json."
    json.dump(st, open(STYLE, "w", encoding="utf-8"), indent=2)
    print("saved", STYLE)
    print(json.dumps({k: v for k, v in st.items() if k != "_note"}, indent=2))


if __name__ == "__main__":
    main()
