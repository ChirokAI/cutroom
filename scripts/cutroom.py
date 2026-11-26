#!/usr/bin/env python3
"""cutroom - one command: raw video in, edited video out.

Cuts dead air, fillers and retakes, adds punch-in zooms, word-by-word captions,
levels the audio. Everything local (ffmpeg + faster-whisper).

usage:
  python cutroom.py RAW.mp4                      -> RAW_edited.mp4
  python cutroom.py RAW.mp4 --aspect 9:16        -> RAW_9x16.mp4 (Reels / Shorts / TikTok)
  python cutroom.py RAW.mp4 --preview            -> quick 540p check first
  options: --out FILE  --lang en  --model small|medium  --accent "#FFD23F"
           --music bed.mp3  --no-captions  --no-zoom  --noise -35
           --title "Title|subtitle"  --no-cards

Running it again on the same video skips transcription and re-uses the work
folder (RAW_cutroom/), so changes in RAW_cutroom/edit.json render in seconds.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def step(name, *args):
    r = subprocess.run([sys.executable, os.path.join(HERE, name), *args])
    if r.returncode:
        sys.exit(f"cutroom: {name} failed")


def main():
    ap = argparse.ArgumentParser(description="raw video in, edited video out")
    ap.add_argument("video")
    ap.add_argument("--aspect", choices=["source", "16:9", "9:16", "1:1"], default=None)
    ap.add_argument("--preview", action="store_true", help="fast 540p render instead of the final")
    ap.add_argument("--out", default=None)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--model", default="small")
    ap.add_argument("--noise", default="-35")
    ap.add_argument("--accent", default=None)
    ap.add_argument("--music", default=None)
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--no-zoom", action="store_true")
    ap.add_argument("--title", default=None, help='title card at the start, e.g. "My Video|subtitle"')
    ap.add_argument("--no-cards", action="store_true")
    ap.add_argument("--retranscribe", action="store_true")
    a = ap.parse_args()

    style_path = os.path.join(os.path.dirname(HERE), "style.json")
    style = json.load(open(style_path, encoding="utf-8")) if os.path.exists(style_path) else None
    if style is None:
        print("note: no house style yet (style.json) - using defaults. "
              "Ask the user the setup questions in SKILL.md and run setup.py to save them.")
    if not a.lang and style and style.get("lang"):
        a.lang = style["lang"]
    video = os.path.abspath(a.video)
    if not os.path.exists(video):
        sys.exit(f"not found: {video}")
    base = os.path.splitext(video)[0]
    work = base + "_cutroom"
    src_json = os.path.join(work, "source.json")

    # 1. transcribe (once per video)
    stamp = f"{os.path.getsize(video)}:{int(os.path.getmtime(video))}"
    fresh = False
    if os.path.exists(src_json) and not a.retranscribe:
        fresh = json.load(open(src_json, encoding="utf-8")).get("stamp") == stamp
    if not fresh:
        args = [video, "--work", work, "--model", a.model, "--noise", a.noise]
        if a.lang:
            args += ["--lang", a.lang]
        step("transcribe.py", *args)
        s = json.load(open(src_json, encoding="utf-8"))
        s["stamp"] = stamp
        json.dump(s, open(src_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        print("transcript: re-using", src_json)

    # 2. options -> edit.json (anything not given on the command line stays as it is)
    edit_path = os.path.join(work, "edit.json")
    if not os.path.exists(edit_path):
        json.dump({"drop": []}, open(edit_path, "w", encoding="utf-8"), indent=2)
    edit = json.load(open(edit_path, encoding="utf-8"))
    if a.aspect:
        edit["aspect"] = a.aspect
    if a.accent:
        edit.setdefault("captions", {})["accent"] = a.accent
    if a.no_captions:
        edit.setdefault("captions", {})["on"] = False
    if a.no_zoom:
        edit.setdefault("zoom", {}).update({"auto_punch": False, "push_every": 0})
    if a.title:
        t, _, sub = a.title.partition("|")
        edit["title"] = {"text": t.strip(), **({"sub": sub.strip()} if sub.strip() else {})}
    if a.no_cards:
        edit.setdefault("cards", {})["mode"] = "off"
    if a.music:
        edit.setdefault("music", {})["file"] = os.path.abspath(a.music)
    json.dump(edit, open(edit_path, "w", encoding="utf-8"), indent=2)

    # 3. plan + render
    step("plan.py", work)
    tl = json.load(open(os.path.join(work, "timeline.json"), encoding="utf-8"))
    tag = "edited" if tl.get("has_video", True) and (tl["out_w"], tl["out_h"]) == (tl["src_w"] - tl["src_w"] % 2, tl["src_h"] - tl["src_h"] % 2)         else f"{tl['out_w']}x{tl['out_h']}"
    out = os.path.abspath(a.out) if a.out else f"{base}_{tag}{'_preview' if a.preview else ''}.mp4"
    step("render.py", work, "--out", out, *([] if a.preview else ["--final"]))
    print(f"\nDONE  {out}\n      transcript + decisions: {work}\\transcript.md, edit.json")


if __name__ == "__main__":
    main()
