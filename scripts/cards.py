#!/usr/bin/env python3
"""cutroom cards: animated motion-graphics cards drawn as ASS (libass) events, so they
burn in during the same ffmpeg pass as the captions - no extra render, no extra tools.

Card types:
  title    big centred title (+ "sub")                       start of the video
  lower    lower third: name ("text") + role ("sub")         when someone is introduced
  keyword  one word or short phrase that pops                the key idea of a sentence
  stat     number that counts up + "label"                   "73%", "$10,000", "3x"
  step     numbered item "01  Pick a topic"                  first / second / third ...
  chapter  band across the frame: "num" + "text"             topic change
  cta      pill: "SUBSCRIBE" / "LINK IN DESCRIPTION"          the call to action

Placement:
  auto_cards(...)  rule-based, zero tokens: numbers -> stat, "first/second/..." -> step,
                   "subscribe" / "description" -> cta
  edit.json "cards": [...]  hand-picked by the agent or the user
"""
import re

DUR = {"title": 2.8, "lower": 3.5, "keyword": 1.5, "stat": 2.2, "step": 2.6, "chapter": 1.9, "cta": 3.0}
ORD = {"first": 1, "firstly": 1, "second": 2, "secondly": 2, "third": 3, "thirdly": 3,
       "fourth": 4, "fifth": 5, "sixth": 6, "finally": 0, "lastly": 0}
NUM_RE = re.compile(r"^([$€£]?)(\d[\d,]*(?:\.\d+)?)(%|x|k|m|b|K|M|B)?$")


def ass_color(h):
    h = h.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def t_ass(t):
    cs = int(round(max(0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def text_w(s, fs):
    """rough rendered width of bold sans text (Montserrat-like)."""
    w = 0
    for ch in s:
        if ch == " ":
            w += 0.30
        elif ch.isdigit():
            w += 0.66
        elif ch.isupper():
            w += 0.76
        elif ch in ".,:;'!|":
            w += 0.30
        else:
            w += 0.60
    return w * fs


def rrect(w, h, r):
    r = min(r, h / 2, w / 2)
    k = r * 0.45
    return (f"m {r:.0f} 0 l {w - r:.0f} 0 b {w - k:.0f} 0 {w:.0f} {k:.0f} {w:.0f} {r:.0f} "
            f"l {w:.0f} {h - r:.0f} b {w:.0f} {h - k:.0f} {w - k:.0f} {h:.0f} {w - r:.0f} {h:.0f} "
            f"l {r:.0f} {h:.0f} b {k:.0f} {h:.0f} 0 {h - k:.0f} 0 {h - r:.0f} "
            f"l 0 {r:.0f} b 0 {k:.0f} {k:.0f} 0 {r:.0f} 0")


def clean(s):
    return re.sub(r"[\"“”]", "", s).strip()


def norm(w):
    return re.sub(r"[^\w'%$.,]", "", w.lower())


# ------------------------------------------------------------------ auto placement
def auto_cards(words, sents, kept, fillers):
    """words: source words [{w,s,e}], sents: lists of word indices. Returns card dicts (source times)."""
    cards = []
    on = lambda w: kept((w["s"] + w["e"]) / 2)
    # whisper splits "$2,500" into "$2" + ",500" - glue them back
    merged = []
    for w in words:
        if merged and re.match(r"^,\d", w["w"]) and re.search(r"\d$", merged[-1]["w"]):
            merged[-1] = dict(merged[-1], w=merged[-1]["w"] + w["w"], e=w["e"])
        else:
            merged.append(w)

    # stat: a number worth showing
    words_all, words = words, merged
    for i, w in enumerate(words):
        raw = w["w"].strip(",.!?;:")
        m = NUM_RE.match(raw)
        if not m or not on(w):
            continue
        pre, num, suf = m.group(1), m.group(2), (m.group(3) or "")
        nxt = [x["w"].strip(",.!?;:").lower() for x in words[i + 1:i + 6]]
        j = 0
        if nxt and nxt[0] in ("percent", "%"):
            suf, j = "%", 1
        elif nxt and nxt[0] in ("dollars", "bucks") and not pre:
            pre, j = "$", 1
        elif nxt and nxt[0] in ("thousand", "million", "billion"):
            suf, j = {"thousand": "K", "million": "M", "billion": "B"}[nxt[0]], 1
            if len(nxt) > 1 and nxt[1] in ("dollars", "bucks") and not pre:
                pre, j = "$", 2
        val = float(num.replace(",", ""))
        if not pre and not suf and (val < 10 or (1900 <= val <= 2100 and "." not in num)):
            continue  # small counts and years are not stats
        label = []
        ends = re.search(r"[.!?]$", words[i + j]["w"])
        for x in ([] if ends else words[i + 1 + j:i + 1 + j + 6]):
            t = x["w"].strip(",.!?;:\"")
            if norm(t) in fillers or NUM_RE.match(t):
                break
            label.append(t)
            if len(label) == 4 or re.search(r"[.,!?]$", x["w"]):
                break
        cards.append({"type": "stat", "at": w["s"], "text": f"{pre}{num}{suf}", "label": " ".join(label)})

    words = words_all
    # steps: sentences that start with an ordinal (only if there are at least two)
    steps = []
    for s in sents:
        first = words[s[0]]["w"].strip(",.!?;:").lower()
        if first in ORD and on(words[s[0]]):
            rest = [words[i]["w"].strip(",.!?;:\"") for i in s[1:]
                    if norm(words[i]["w"]) not in fillers][:7]
            if rest:
                txt = " ".join(rest)
                steps.append((ORD[first], words[s[0]]["s"], txt[:1].upper() + txt[1:]))
    if len(steps) >= 2:
        n = 0
        for o, at, txt in steps:
            n = o if o else n + 1
            cards.append({"type": "step", "at": at, "num": n, "text": txt})

    # call to action ("subscribe" and "link in the description" close together -> one card)
    seen = set()
    for w in words:
        k = norm(w["w"]).strip(".,")
        if k.startswith("subscrib") and "sub" not in seen and on(w):
            cards.append({"type": "cta", "at": w["s"], "text": "SUBSCRIBE"})
            seen.add("sub")
        elif k == "description" and "desc" not in seen and on(w):
            sub = next((c for c in cards if c["type"] == "cta" and c["text"] == "SUBSCRIBE"
                        and 0 <= w["s"] - c["at"] < 8), None)
            if sub:
                sub["text"] = "SUBSCRIBE + LINK BELOW"
            else:
                cards.append({"type": "cta", "at": w["s"], "text": "LINK IN DESCRIPTION"})
            seen.add("desc")
    return cards


# ------------------------------------------------------------------ drawing
class Painter:
    def __init__(self, OW, OH, fps, look):
        self.OW, self.OH, self.fps = OW, OH, fps
        self.v = OH > OW
        self.u = min(OW, OH) / 1080          # 1.0 at 1080p
        self.look = look
        self.font = look["font"]
        self.fg = ass_color(look.get("fg", "#FFFFFF"))
        self.acc = ass_color(look["accent"])
        self.ink = ass_color(look.get("ink", "#111111"))
        self.box = ass_color(look.get("bg", "#111111"))
        self.style = look.get("look", "solid")   # solid | dark | minimal
        self.lines = []

    def fit(self, text, fs, max_frac, extra=0.0):
        """shrink a font size until text (+ padding in fs units) fits max_frac of the width."""
        while fs > 20 and text_w(text, fs) + extra * fs > self.OW * max_frac:
            fs -= 2
        return fs

    def inside(self, cx, cy, w, h):
        """move a box centre so the whole box stays on screen, with a margin."""
        m = 0.04 * min(self.OW, self.OH)
        cx = min(max(cx, w / 2 + m), self.OW - w / 2 - m)
        cy = min(max(cy, h / 2 + m), self.OH - h / 2 - m)
        return int(cx), int(cy)

    def ev(self, layer, a, b, txt):
        self.lines.append(f"Dialogue: {layer},{t_ass(a)},{t_ass(b)},Card,,0,0,0,,{txt}")

    def pop(self, ms_in=240):
        return (r"\fscx55\fscy55\t(0,%d,\fscx106\fscy106)\t(%d,%d,\fscx100\fscy100)"
                % (int(ms_in * 0.6), int(ms_in * 0.6), ms_in))

    def colors(self):
        """(box colour, box alpha, text colour) for the look."""
        if self.style == "solid":
            return self.acc, "00", self.ink
        if self.style == "dark":
            return self.box, "26", self.fg
        return self.box, "FF", self.fg      # minimal: no box

    def textbox(self, layer, a, b, cx, cy, text, fs, anim_box, anim_txt, pad=0.55, bc=None, tc=None):
        bcol, balpha, tcol = self.colors()
        bc, tc = bc or bcol, tc or tcol
        fs = self.fit(text, fs, 0.9, pad * 2)
        w, h = text_w(text, fs) + fs * pad * 2, fs * 1.55
        cx, cy = self.inside(cx, cy, w * 1.06, h * 1.06)  # 1.06: room for the pop overshoot
        shadow = "" if self.style == "minimal" else r"\shad0\4a&H90&\4c&H000000&\xshad0\yshad%d" % max(2, int(6 * self.u))
        if balpha != "FF":
            self.ev(layer, a, b, r"{\an5\pos(%d,%d)\bord0%s\1c%s\1a&H%s&\p1%s}%s{\p0}"
                    % (cx, cy, shadow, bc, balpha, anim_box, rrect(w, h, fs * 0.28)))
        edge = r"\bord0\shad%d\4c&H000000&\4a&H40&" % max(2, int(4 * self.u)) if balpha == "FF" else r"\bord0\shad0"
        self.ev(layer + 1, a, b, r"{\an5\pos(%d,%d)\fs%d\1c%s%s%s}%s" % (cx, cy, fs, tc, edge, anim_txt, text))
        return w, h

    # --- the seven cards ------------------------------------------------
    def keyword(self, c, a, b):
        fs = int((110 if self.v else 96) * self.u)
        cx, cy = self.at(c, (0.5, 0.24) if self.v else (0.74, 0.40))
        txt = clean(c["text"]).upper()
        anim = self.pop() + r"\fad(0,160)"
        self.textbox(10, a, b, cx, cy, txt, fs, anim, anim)

    def stat(self, c, a, b):
        fs = int((150 if self.v else 132) * self.u)
        cx, cy = self.at(c, (0.5, 0.24) if self.v else (0.74, 0.38))
        txt = clean(c["text"])
        m = NUM_RE.match(txt.replace(" ", ""))
        label = clean(c.get("label", "")).upper()
        fs = self.fit(txt, fs, 0.42 if not self.v else 0.8, 0.9)
        lw = int(fs * 0.30)
        w = max(text_w(txt, fs), text_w(label, lw)) + fs * 0.9
        h = fs * 1.35 + (lw * 1.6 if label else 0)
        cx, cy = self.inside(cx, cy, w * 1.06, h * 1.06)
        bcol, balpha, tcol = self.colors()
        if balpha != "FF":
            self.ev(10, a, b, r"{\an5\pos(%d,%d)\bord0\shad0\1c%s\1a&H%s&%s\fad(0,160)\p1}%s{\p0}"
                    % (cx, cy, bcol, balpha, self.pop(), rrect(w, h, fs * 0.2)))
        ny = cy - (lw * 0.8 if label else 0)
        count = 0.85
        if m:
            pre, num, suf = m.group(1), m.group(2), m.group(3) or ""
            val = float(num.replace(",", ""))
            dec = len(num.split(".")[1]) if "." in num else 0
            step = 1 / 30
            t = 0.0
            while t < count:
                k = 1 - (1 - t / count) ** 3
                v = val * k
                s = f"{v:,.{dec}f}" if "," in num else f"{v:.{dec}f}"
                self.ev(11, a + t, a + t + step, r"{\an5\pos(%d,%d)\fs%d\1c%s\bord0\shad0}%s"
                        % (cx, ny, fs, tcol, pre + s + suf))
                t += step
            self.ev(11, a + count, b, r"{\an5\pos(%d,%d)\fs%d\1c%s\bord0\shad0\fad(0,160)"
                    r"\t(0,120,\fscx108\fscy108)\t(120,260,\fscx100\fscy100)}%s" % (cx, ny, fs, tcol, txt))
        else:
            self.ev(11, a, b, r"{\an5\pos(%d,%d)\fs%d\1c%s\bord0\shad0%s\fad(0,160)}%s"
                    % (cx, ny, fs, tcol, self.pop(), txt))
        if label:
            lc = tcol if balpha != "FF" else self.acc
            self.ev(11, a + 0.15, b, r"{\an5\pos(%d,%d)\fs%d\1c%s\bord0\shad0\fad(200,160)}%s"
                    % (cx, cy + fs * 0.62, lw, lc, label))

    def lower(self, c, a, b):
        fs = int((64 if self.v else 58) * self.u)
        sfs = int(fs * 0.55)
        x0 = int(self.OW * (0.08 if self.v else 0.06))
        name, sub = clean(c["text"]), clean(c.get("sub", ""))
        w = max(text_w(name, fs), text_w(sub.upper(), sfs)) + fs * 1.1
        h = fs * 1.35 + (sfs * 1.5 if sub else 0)
        cap_top = self.look.get("cap_top", 0.8) * self.OH        # keep clear of the captions
        y0 = int(min(self.OH * (0.62 if self.v else 0.70), cap_top - h - 30 * self.u))
        bar = max(6, int(10 * self.u))
        # accent bar grows, panel slides out from it, text follows
        self.ev(10, a, b, r"{\an7\pos(%d,%d)\bord0\shad0\1c%s\fad(0,200)\clip(%d,%d,%d,%d)"
                r"\t(0,220,\clip(%d,%d,%d,%d))\p1}%s{\p0}"
                % (x0, y0, self.acc, x0, y0 + h / 2, x0 + bar, y0 + h / 2,
                   x0, y0, x0 + bar, y0 + h, f"m 0 0 l {bar} 0 l {bar} {h:.0f} l 0 {h:.0f}"))
        bcol, balpha, tcol = self.colors()
        if self.style == "solid":
            bcol, tcol = self.box, self.fg
            balpha = "1A"
        if balpha != "FF":
            self.ev(9, a + 0.18, b, r"{\an7\pos(%d,%d)\bord0\shad0\1c%s\1a&H%s&\fad(0,200)\clip(%d,%d,%d,%d)"
                    r"\t(0,300,0.6,\clip(%d,%d,%d,%d))\p1}%s{\p0}"
                    % (x0 + bar, y0, bcol, balpha, x0 + bar, y0, x0 + bar, y0 + h,
                       x0 + bar, y0, x0 + bar + w, y0 + h, f"m 0 0 l {w:.0f} 0 l {w:.0f} {h:.0f} l 0 {h:.0f}"))
        tx = x0 + bar + fs * 0.5
        self.ev(11, a + 0.3, b, r"{\an4\pos(%d,%d)\fs%d\1c%s\bord0\shad0\fad(180,200)}%s"
                % (tx, y0 + fs * 0.72, fs, tcol, name))
        if sub:
            self.ev(11, a + 0.42, b, r"{\an4\pos(%d,%d)\fs%d\1c%s\bord0\shad0\fad(180,200)}%s"
                    % (tx, y0 + fs * 1.35 + sfs * 0.55, sfs, self.acc, sub.upper()))

    def step(self, c, a, b):
        fs = int((60 if self.v else 54) * self.u)
        x0 = int(self.OW * (0.08 if self.v else 0.06))
        y0 = int(self.OH * (0.18 if self.v else 0.12))
        num = f"{int(c.get('num', 1)):02d}"
        txt = clean(c["text"])
        fs = self.fit(txt, fs, (0.84 if self.v else 0.80), 2.9)
        sq = fs * 1.6
        self.ev(10, a, b, r"{\an7\pos(%d,%d)\bord0\shad0\1c%s\fad(0,180)%s\p1}%s{\p0}"
                % (x0, y0, self.acc, r"\fscx40\fscy40\t(0,200,\fscx100\fscy100)", rrect(sq, sq, fs * 0.3)))
        self.ev(11, a, b, r"{\an5\pos(%d,%d)\fs%d\1c%s\bord0\shad0\fad(80,180)}%s"
                % (x0 + sq / 2, y0 + sq / 2, int(fs * 0.85), self.ink, num))
        w = text_w(txt, fs) + fs * 1.0
        bcol, balpha, tcol = self.box, "26", self.fg
        if self.style == "minimal":
            balpha = "FF"
        gx = x0 + sq + fs * 0.25
        if balpha != "FF":
            self.ev(9, a + 0.1, b, r"{\an7\pos(%d,%d)\bord0\shad0\1c%s\1a&H%s&\fad(0,180)\clip(%d,%d,%d,%d)"
                    r"\t(0,280,0.6,\clip(%d,%d,%d,%d))\p1}%s{\p0}"
                    % (gx, y0, bcol, balpha, gx, y0, gx, y0 + sq, gx, y0, gx + w, y0 + sq, rrect(w, sq, fs * 0.3)))
        edge = r"\shad%d\4a&H40&" % max(2, int(4 * self.u)) if balpha == "FF" else r"\shad0"
        self.ev(11, a + 0.22, b, r"{\an4\pos(%d,%d)\fs%d\1c%s\bord0%s\fad(160,180)}%s"
                % (gx + fs * 0.5, y0 + sq / 2, fs, tcol, edge, txt))

    def title(self, c, a, b):
        fs = int((104 if self.v else 112) * self.u)
        sfs = int(fs * 0.36)
        cx, cy = self.OW / 2, self.OH * (0.42 if self.v else 0.46)
        self.ev(8, a, b, r"{\an7\pos(0,0)\bord0\shad0\1c&H000000&\1a&HFF&\t(0,300,\1a&H70&)\fad(0,300)\p1}"
                r"m 0 0 l %d 0 l %d %d l 0 %d{\p0}" % (self.OW, self.OW, self.OH, self.OH))
        txt = clean(c["text"])
        self.ev(11, a + 0.1, b, r"{\an5\move(%d,%d,%d,%d,0,380)\fs%d\1c%s\bord0\shad0\fad(300,300)\blur6"
                r"\t(0,380,\blur0)}%s" % (cx, cy + 40 * self.u, cx, cy, fs, self.fg, txt))
        lw = min(text_w(txt, fs), self.OW * 0.8)
        self.ev(10, a + 0.3, b, r"{\an7\pos(%d,%d)\bord0\shad0\1c%s\fad(0,300)\clip(%d,0,%d,%d)"
                r"\t(0,420,0.5,\clip(%d,0,%d,%d))\p1}m 0 0 l %d 0 l %d %d l 0 %d{\p0}"
                % (cx - lw / 2, cy + fs * 0.75, self.acc, cx, cx, self.OH, cx - lw / 2, cx + lw / 2, self.OH,
                   lw, lw, max(4, int(8 * self.u)), max(4, int(8 * self.u))))
        if c.get("sub"):
            self.ev(11, a + 0.45, b, r"{\an5\pos(%d,%d)\fs%d\1c%s\bord0\shad0\fad(300,300)}%s"
                    % (cx, cy + fs * 1.25, sfs, self.fg, clean(c["sub"]).upper()))

    def chapter(self, c, a, b):
        fs = int((86 if self.v else 80) * self.u)
        h = fs * 2.0
        y0 = self.OH * 0.5 - h / 2
        self.ev(10, a, b, r"{\an7\pos(0,%d)\bord0\shad0\1c%s\clip(0,0,0,%d)\t(0,260,0.5,\clip(0,0,%d,%d))"
                r"\fad(0,200)\p1}m 0 0 l %d 0 l %d %d l 0 %d{\p0}"
                % (y0, self.box, self.OH, self.OW, self.OH, self.OW, self.OW, h, h))
        self.ev(10, a + 0.05, b, r"{\an7\pos(0,%d)\bord0\shad0\1c%s\clip(0,0,0,%d)\t(0,260,0.5,\clip(0,0,%d,%d))"
                r"\fad(0,200)\p1}m 0 0 l %d 0 l %d %d l 0 %d{\p0}"
                % (y0 + h, self.acc, self.OH, self.OW, self.OH, self.OW, self.OW, 8 * self.u, 8 * self.u))
        num = c.get("num")
        txt = (f"{int(num):02d}   " if num else "") + clean(c["text"]).upper()
        self.ev(11, a + 0.2, b, r"{\an5\move(%d,%d,%d,%d,0,300)\fs%d\1c%s\bord0\shad0\fad(200,200)}%s"
                % (self.OW / 2 + 60 * self.u, self.OH / 2, self.OW / 2, self.OH / 2, fs, self.fg, txt))

    def cta(self, c, a, b):
        fs = int((62 if self.v else 52) * self.u)
        cx, cy = self.at(c, (0.5, 0.15) if self.v else (0.5, 0.12))
        txt = clean(c["text"]).upper()
        anim = self.pop(300) + r"\fad(0,200)"
        self.textbox(10, a, b, cx, cy, txt, fs, anim, anim, pad=0.9,
                     bc=self.acc if self.style != "solid" else None, tc=self.ink)

    def at(self, c, default):
        x, y = c.get("pos", default)
        return int(self.OW * x), int(self.OH * y)

    def draw(self, cards):
        for c in cards:
            fn = getattr(self, c["type"], None)
            if fn:
                fn(c, c["o"], c["o"] + c["dur"])
        return self.lines

    def style_line(self):
        return (f"Style: Card,{self.font},60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
                f"0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1")


def build(cards, OW, OH, fps, look):
    p = Painter(OW, OH, fps, look)
    return p.style_line(), p.draw(cards)
