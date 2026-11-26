#!/usr/bin/env python3
"""cutroom step 2: decide the edit. Fast, no rendering - run it as often as you like.

reads  work/source.json  (from transcribe.py)
       work/edit.json    (your decisions; created with defaults on the first run)
writes work/transcript.md (numbered sentences + flags - read this to make decisions)
       work/timeline.json (what render.py cuts, zooms and mixes)
       work/captions.ass  (word-by-word captions on the OUTPUT timeline)

usage: python plan.py WORK_DIR
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cards as cardlib

DEFAULT_EDIT = {
    "_help": "Edit this file, then run plan.py again. Times are SOURCE seconds (as shown in transcript.md).",
    "aspect": "source",            # "source" | "16:9" | "9:16" | "1:1"
    "frame_focus": [0.5, 0.5],     # where to keep when cropping to another aspect (0..1, 0..1)
    "cut": {
        "max_pause": 0.45,         # pauses longer than this get shortened
        "keep_after": 0.14,        # silence kept after a word before a cut
        "keep_before": 0.08,       # silence kept before the next word
        "remove_fillers": True,
        "auto_drop_retakes": True, # a sentence that starts like the next one is a failed take: drop it
        "fillers": ["um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "ahh", "hmm", "mm", "mhm"]
    },
    "drop": [],                    # sentence numbers (e.g. 4) or [start, end] source ranges - retakes, mistakes
    "captions": {
        "on": True,
        "font": "Montserrat ExtraBold",
        "size": None,              # fraction of the short side; None = auto (0.066 wide, 0.085 vertical)
        "color": "#FFFFFF",
        "accent": "#FFD23F",       # colour of the word being spoken
        "upper": True,
        "highlight": True,         # spoken word in the accent colour (karaoke); False = plain
        "scale": 1.0,              # size multiplier on top of "size"
        "position": "low",         # "low" | "middle" (used when "y" is None)
        "max_words": 3,
        "max_dur": 1.4,
        "y": None                  # baseline height 0..1 from the top; None = auto (0.88 wide, 0.72 vertical)
    },
    "zoom": {
        "auto_punch": True,        # alternate 100% / punch at jump cuts, hides the jump
        "punch": 1.10,
        "transition": "punch",     # at cuts: "punch" | "smooth" | "flash" | "none"
        "push_every": 6.0,         # no cut for this long? ease in/out on the next sentence start (0 = off)
        "min_gap": 2.0,            # seconds between two auto punches
        "focus": [0.5, 0.45]       # zoom centre for auto punches
    },
    "zooms": [],                   # manual: {"at": 12.3 or "sentence": 5, "to": 1.35, "focus": [0.7, 0.3], "hold": 2.5}
    "music": {"file": None, "db": -24, "duck": True},
    "cards": {
        "mode": "auto",            # "auto" (rules: numbers, steps, call to action) | "manual" (only add_cards) | "off"
        "look": "solid",           # "solid" (accent box) | "dark" (dark glass box) | "minimal" (text only)
        "font": None,              # None = caption font
        "bg": "#111111", "fg": "#FFFFFF", "ink": "#111111",
        "min_gap": 1.0             # seconds between two auto cards of different types
    },
    "title": None,                 # {"text": "...", "sub": "..."} -> title card at the start
    "broll": {"fit": "full", "border": "#FFFFFF"},  # pictures / B-roll: "full" | "window"; border for window ("accent" = caption accent)
    "background": ["#0E0E12", "#24203A"],  # sound-only files: slowly moving gradient behind the captions
    "add_cards": []                # [{"type": "keyword", "text": "FREE", "sentence": 4}, {"type": "lower", "text": "Name", "sub": "Role", "at": 3.2}, ...]
}

PUNCT_END = re.compile(r"[.?!]$")


def norm(w):
    return re.sub(r"[^\w']", "", w.lower())


def merge(rs):
    rs = sorted([r for r in rs if r[1] - r[0] > 0.001])
    out = []
    for a, b in rs:
        if out and a <= out[-1][1] + 0.001:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def deep_defaults(d, ref):
    for k, v in ref.items():
        if k not in d:
            d[k] = v
        elif isinstance(v, dict) and isinstance(d[k], dict):
            deep_defaults(d[k], v)
    return d


EDIT_HELP = ("Per-video changes only. Anything not set here comes from the house style "
             "(<skill>/style.json) and the defaults in plan.py. Times are SOURCE seconds.")


def overlay(base, top):
    for k, v in top.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            overlay(base[k], v)
        else:
            base[k] = v
    return base


def sentences_of(words):
    sents, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or PUNCT_END.search(w["w"]) or nxt["s"] - w["e"] > 0.8 or len(cur) >= 40:
            sents.append(cur)
            cur = []
    return sents


def hex_ass(h, alpha=0):
    h = h.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ass_time(t):
    t = max(0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    work = os.path.abspath(sys.argv[1])
    src = json.load(open(os.path.join(work, "source.json"), encoding="utf-8"))
    # effective settings = defaults <- house style (style.json) <- this video (edit.json)
    base = json.loads(json.dumps(DEFAULT_EDIT))
    style_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "style.json")
    if os.path.exists(style_path):
        overlay(base, json.load(open(style_path, encoding="utf-8")))
    edit_path = os.path.join(work, "edit.json")
    if not os.path.exists(edit_path):
        json.dump({"_help": EDIT_HELP, "drop": []}, open(edit_path, "w", encoding="utf-8"), indent=2)
        print("created", edit_path)
    edit = overlay(base, json.load(open(edit_path, encoding="utf-8")))

    dur = src["duration"]
    words = src["words"]
    cut = edit["cut"]
    fillers = set(cut["fillers"]) if cut["remove_fillers"] else set()
    sents = sentences_of(words)

    def key3(idx):
        return [norm(words[i]["w"]) for i in sents[idx] if norm(words[i]["w"]) not in fillers][:3]

    retake_of = {}
    for n in range(1, len(sents) + 1):
        k = key3(n - 1)
        for m in (n, n + 1):
            if m < len(sents) and len(k) >= 2 and key3(m)[:2] == k[:2]:
                retake_of[n] = m + 1
                break
    drops = list(edit["drop"])
    if cut.get("auto_drop_retakes", True):
        for n, later in retake_of.items():
            # the failed take is everything from n up to the sentence that restarts it
            drops += [k for k in range(n, later) if k not in drops]

    # ---------------- what to remove (source time) ----------------
    remove = []
    if words:
        remove.append([0, words[0]["s"] - cut["keep_before"]])
        remove.append([words[-1]["e"] + cut["keep_after"], dur])
    for a, b in src["silences"]:
        if b - a > cut["max_pause"]:
            remove.append([a + cut["keep_after"], b - cut["keep_before"]])
    filler_idx = set()
    for i, w in enumerate(words):
        if norm(w["w"]) in fillers:
            filler_idx.add(i)
            a = max(w["s"], words[i - 1]["e"] if i else 0)
            b = min(w["e"], words[i + 1]["s"] if i + 1 < len(words) else dur)
            remove.append([a, b])
    dropped_sents = set()
    for d in drops:
        if isinstance(d, int):
            if 1 <= d <= len(sents):
                dropped_sents.add(d)
                s = sents[d - 1]
                a = words[s[0]]["s"]
                b = words[sents[d][0]]["s"] if d < len(sents) else dur
                remove.append([a, b])
        elif isinstance(d, (list, tuple)) and len(d) == 2:
            remove.append([float(d[0]), float(d[1])])
    remove = merge([[max(0, a), min(dur, b)] for a, b in remove])

    keeps, t = [], 0.0
    for a, b in remove:
        if a > t:
            keeps.append([t, a])
        t = max(t, b)
    if t < dur:
        keeps.append([t, dur])
    keeps = [k for k in keeps if k[1] - k[0] >= 0.12]
    if not keeps:
        sys.exit("everything was cut - check edit.json")

    segs, o = [], 0.0
    for a, b in keeps:
        segs.append({"s": round(a, 3), "e": round(b, 3), "o": round(o, 3)})
        o += b - a
    out_dur = o

    def to_out(t, snap_forward=True):
        for s in segs:
            if s["s"] <= t <= s["e"]:
                return s["o"] + t - s["s"]
            if snap_forward and t < s["s"]:
                return s["o"]
        return out_dur

    def kept(t):
        return any(s["s"] <= t <= s["e"] for s in segs)

    # ---------------- output frame ----------------
    W, H = src["width"], src["height"]
    asp = edit["aspect"]
    if asp == "source":
        OW, OH = W - W % 2, H - H % 2
    else:
        rw, rh = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1)}[asp]
        long_side = max(1080 * max(rw, rh) // min(rw, rh), 1080)
        OW, OH = (long_side, 1080) if rw > rh else ((1080, long_side) if rh > rw else (1080, 1080))
    vertical = OH > OW
    has_video, has_audio = src.get("has_video", True), src.get("has_audio", True)
    if not has_video:  # sound only: cutroom draws the whole picture at the output size
        W, H = OW, OH

    # ---------------- zoom events (output time) ----------------
    zc = edit["zoom"]
    if not has_video:
        zc = dict(zc, auto_punch=False)
    manual = []
    for z in edit["zooms"]:
        if "sentence" in z and 1 <= z["sentence"] <= len(sents):
            at = words[sents[z["sentence"] - 1][0]]["s"]
        else:
            at = float(z.get("at", 0))
        t_in = to_out(at)
        manual.append({"in": t_in, "out": min(out_dur, t_in + float(z.get("hold", 2.5))),
                       "to": float(z.get("to", 1.3)), "focus": z.get("focus", zc["focus"]),
                       "ease": float(z.get("ease", 0.45))})
    points = []
    trans = zc.get("transition", "punch")
    if zc["auto_punch"] and trans != "none":
        for s in segs[1:]:
            points.append((s["o"], "auto", None))
    if zc["auto_punch"] and zc.get("push_every", 0) > 0:
        for s in sents:
            w0 = words[s[0]]
            if kept(w0["s"]):
                points.append((to_out(w0["s"]), "push", None))
    for m in manual:
        points.append((m["in"], "in", m))
        points.append((m["out"], "out", m))
    points.sort(key=lambda p: (p[0], {"out": 0, "auto": 1, "push": 1, "in": 2}[p[1]]))
    level, last_auto, active = 1.0, -99, 0
    events = []  # [t, zoom, fx, fy, ease]
    for t, kind, m in points:
        if kind == "auto":
            if active == 0 and t - last_auto >= zc["min_gap"]:
                level = zc["punch"] if level == 1.0 else 1.0
                events.append([t, level, zc["focus"][0], zc["focus"][1], 0.3 if trans == "smooth" else 0])
                last_auto = t
        elif kind == "push":
            if active == 0 and t - last_auto >= zc["push_every"]:
                level = zc["punch"] if level == 1.0 else 1.0
                events.append([t, level, zc["focus"][0], zc["focus"][1], 0.6])
                last_auto = t
        elif kind == "in":
            active += 1
            events.append([t, m["to"], m["focus"][0], m["focus"][1], m["ease"]])
        else:
            active -= 1
            events.append([t, level, zc["focus"][0], zc["focus"][1], m["ease"]])
            last_auto = t

    # ---------------- captions ----------------
    cc = edit["captions"]
    out_words = []
    for i, w in enumerate(words):
        if i in filler_idx:
            continue
        mid = (w["s"] + w["e"]) / 2
        if not kept(mid):
            continue
        s_o, e_o = to_out(max(w["s"], 0)), to_out(w["e"])
        if e_o <= s_o:
            e_o = s_o + 0.1
        txt = re.sub(r"[.,;:\"]+", "", w["w"]).strip()
        if txt:
            out_words.append({"w": txt.upper() if cc["upper"] else txt, "s": s_o, "e": e_o,
                              "end": bool(PUNCT_END.search(w["w"]) or w["w"].endswith(","))})
    max_chars = 18 if vertical else 30
    chunks, cur = [], []
    for w in out_words:
        if cur and (len(cur) >= cc["max_words"] or cur[-1]["end"]
                    or w["s"] - cur[-1]["e"] > 0.5 or w["e"] - cur[0]["s"] > cc["max_dur"]
                    or len(" ".join(x["w"] for x in cur + [w])) > max_chars):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)

    size = (cc["size"] or (0.085 if vertical else 0.066)) * float(cc.get("scale", 1.0))
    if not has_video and not cc["y"]:  # nothing else on screen: big captions in the middle
        size *= 1.3
        cc = dict(cc, position="middle")
    fs = round(size * min(OW, OH))
    y = cc["y"] or ((0.62 if vertical else 0.66) if cc.get("position") == "middle" else (0.72 if vertical else 0.88))
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {OW}", f"PlayResY: {OH}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{cc['font']},{fs},{hex_ass(cc['color'])},{hex_ass(cc['accent'])},&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,{max(2, round(fs * 0.07))},{max(1, round(fs * 0.05))},2,60,60,{round((1 - y) * OH)},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    acc, col = hex_ass(cc["accent"]), hex_ass(cc["color"])
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else out_dur
        chunk_end = min(nxt, ch[-1]["e"] + 0.35)
        for wi, w in enumerate(ch):
            st = ch[0]["s"] if wi == 0 else w["s"]
            en = ch[wi + 1]["s"] if wi + 1 < len(ch) else chunk_end
            if en - st < 0.02:
                continue
            pop = r"{\fscx90\fscy90\t(0,90,\fscx100\fscy100)}" if wi == 0 else ""
            parts = [(r"{\c" + acc + "}" + x["w"] + r"{\c" + col + "}") if j == wi and cc.get("highlight", True) else x["w"]
                     for j, x in enumerate(ch)]
            lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    # ---------------- cards ----------------
    kc = edit["cards"]
    placed, overlays, drawn = [], [], []
    if kc["mode"] != "off":
        wanted = []
        if edit.get("title"):
            t = edit["title"] if isinstance(edit["title"], dict) else {"text": str(edit["title"])}
            wanted.append(dict(t, type="title", at=None, prio=0))
        for c in edit["add_cards"]:
            wanted.append(dict(c, prio=1))
        if kc["mode"] == "auto":
            for c in cardlib.auto_cards(words, sents, kept, fillers):
                wanted.append(dict(c, prio={"cta": 1.5, "step": 1.6}.get(c["type"], 2)))
        for c in wanted:
            if c["type"] == "title" or c.get("at") is None and "sentence" not in c and "word" not in c:
                o = 0.0
            elif "sentence" in c and 1 <= int(c["sentence"]) <= len(sents):
                o = to_out(words[sents[int(c["sentence"]) - 1][0]]["s"])
            elif "word" in c:
                hit = next((w for w in words if norm(w["w"]) == norm(c["word"]) and kept(w["s"])), None)
                if not hit:
                    continue
                o = to_out(hit["s"])
            else:
                o = to_out(float(c["at"]))
            c["o"] = round(o, 3)
            c["dur"] = float(c.get("dur", cardlib.DUR.get(c["type"], {"image": 3.0, "video": 4.0}.get(c["type"], 2.0))))
        wanted = [c for c in wanted if "o" in c and (c["type"] in cardlib.DUR or c["type"] in ("image", "video"))]
        for c in sorted(wanted, key=lambda c: (c["prio"], c["o"])):
            if out_dur - c["o"] < 1.6:  # too close to the end to read: start it earlier
                c["o"] = max(0.0, out_dur - 1.6)
            c["dur"] = min(c["dur"], out_dur - c["o"])
            def gap(p):
                if c["prio"] < 1.5 or p["prio"] < 1.5 or (c["type"] == p["type"] == "step"):
                    return 0.3
                return kc["min_gap"]
            if c["type"] == "step":  # a step stays up until the next step starts
                c["dur"] = min(c["dur"], max(0.8, min([q["o"] for q in wanted if q["type"] == "step" and q["o"] > c["o"]]
                                                      or [c["o"] + c["dur"] + 1]) - c["o"] - 0.3))
            # cards asked for by hand may overlap each other; auto cards never overlap anything
            if all((c["prio"] < 1.5 and p["prio"] < 1.5) or c["o"] >= p["o"] + p["dur"] + gap(p)
                   or c["o"] + c["dur"] + gap(p) <= p["o"] for p in placed):
                placed.append(c)
        placed.sort(key=lambda c: c["o"])
        base_dir = os.path.dirname(src["video"])
        for c in placed:
            if c["type"] in ("image", "video"):
                f = c.get("file", "")
                c["file"] = f if os.path.isabs(f) else os.path.join(base_dir, f)
                if not os.path.exists(c["file"]):
                    print("warning: file not found for", c["type"], "card:", c["file"])
        overlays = [c for c in placed if c["type"] in ("image", "video") and os.path.exists(c["file"])]
        drawn = [c for c in placed if c["type"] in cardlib.DUR]
        if drawn:
            look = dict(kc, accent=cc["accent"], font=kc.get("font") or cc["font"],
                        cap_top=(y - fs * 1.6 / OH) if cc["on"] else 0.92)
            style_line, card_lines = cardlib.build(drawn, OW, OH, src["fps"], look)
            si = next(i for i, l in enumerate(lines) if l.startswith("Style: Cap"))
            lines.insert(si + 1, style_line)
            lines.extend(card_lines)
    if not cc["on"]:
        lines = [l for l in lines if not l.startswith("Dialogue: 0,")]

    with open(os.path.join(work, "captions.ass"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # ---------------- transcript.md ----------------
    md = ["# cutroom transcript", "",
          f"Source {dur:.1f}s -> output {out_dur:.1f}s  ({len(segs)} pieces, {len(segs) - 1} cuts, "
          f"{len(filler_idx)} fillers removed, aspect {asp} {OW}x{OH})", "",
          "Drop a sentence: put its number in edit.json \"drop\". Times are source seconds.",
          "RETAKE = starts like a later sentence; dropped automatically unless cut.auto_drop_retakes is false.", ""]
    for n, s in enumerate(sents, 1):
        a, b = words[s[0]]["s"], words[s[-1]]["e"]
        txt = " ".join(("(" + words[i]["w"] + ")") if i in filler_idx else words[i]["w"] for i in s)
        flags = []
        if n in dropped_sents:
            flags.append("DROPPED")
        if n in retake_of:
            flags.append(f"RETAKE of #{retake_of[n]}")
        low = [words[i]["w"] for i in s if words[i]["p"] < 0.4]
        if low:
            flags.append("unclear: " + ", ".join(low))
        md.append(f"#{n} [{a:.2f}-{b:.2f}] {txt}" + ("   <- " + "; ".join(flags) if flags else ""))
    with open(os.path.join(work, "transcript.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    timeline = {"video": src["video"], "fps": src["fps"], "src_w": W, "src_h": H,
                "out_w": OW, "out_h": OH, "frame_focus": edit["frame_focus"],
                "duration": round(out_dur, 3), "segments": segs, "zoom": events,
                "captions": (bool(cc["on"]) and bool(chunks)) or bool(drawn), "music": edit["music"],
                "has_video": has_video, "has_audio": has_audio, "src_duration": dur,
                "background": edit.get("background", ["#0E0E12", "#24203A"]),
                "overlays": [{"type": c["type"], "file": c["file"], "o": c["o"], "dur": c["dur"],
                              "fit": c.get("fit", edit["broll"]["fit"]),
                              "border": (cc["accent"] if edit["broll"]["border"] == "accent" else edit["broll"]["border"])}
                             for c in overlays],
                "flashes": [s["o"] for s in segs[1:]] if trans == "flash" else []}
    with open(os.path.join(work, "timeline.json"), "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=1)

    print(f"source {dur:.1f}s -> output {out_dur:.1f}s | {len(segs) - 1} cuts | "
          f"{len(filler_idx)} fillers | {len(retake_of)} retakes | {len(events)} zoom moves | {len(placed)} cards | {len(chunks)} caption chunks")
    print("read", os.path.join(work, "transcript.md"))


if __name__ == "__main__":
    main()
