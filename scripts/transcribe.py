#!/usr/bin/env python3
"""cutroom step 1: read the raw video, write work/source.json.

Collects everything the later steps need, once:
  - video facts (size, fps, duration)
  - word-level transcript (faster-whisper, local, free)
  - real silences (ffmpeg silencedetect), so cuts only ever land in silence

usage: python transcribe.py RAW.mp4 [--work DIR] [--model small] [--lang en] [--noise -35]
"""
import argparse, json, os, re, subprocess, sys

# Whisper tends to "clean up" speech and drop fillers. A disfluent prompt
# makes it write them down, so the planner can cut them.
FILLER_PROMPT = "Umm, so, uh... let me think, like, hmm. Okay, uh, here's the thing, um."


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height,avg_frame_rate,r_frame_rate",
             "-of", "json", path])
    if r.returncode:
        sys.exit("ffprobe failed: " + r.stderr)
    info = json.loads(r.stdout)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if not v and not a:
        sys.exit("no picture and no sound in this file")

    def rate(s):
        n, d = (s or "0/1").split("/")
        return float(n) / float(d) if float(d) else 0

    if v:
        fps = rate(v.get("avg_frame_rate")) or rate(v.get("r_frame_rate")) or 30
        fps = min((24, 25, 30, 50, 60), key=lambda f: abs(f - fps)) if abs(fps - round(fps)) > 0.02 else round(fps)
        if fps > 120:  # still images report silly rates
            fps = 30
    else:
        fps = 30
    # sound only: the picture is drawn by cutroom (background + captions + cards)
    return {"width": v["width"] if v else 1920, "height": v["height"] if v else 1080, "fps": fps,
            "duration": float(info["format"]["duration"]), "has_video": bool(v), "has_audio": bool(a)}


def silences(path, noise, min_len=0.18):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
             "-af", f"silencedetect=n={noise}dB:d={min_len}", "-f", "null", "-"])
    out, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            out.append([round(start, 3), round(float(m.group(1)), 3)])
            start = None
    if start is not None:
        out.append([round(start, 3), None])  # runs to the end; filled in below
    return out


def transcribe(wav, model_name, lang):
    from faster_whisper import WhisperModel
    try:
        model = WhisperModel(model_name, device="cuda", compute_type="float16")
        segs, info = model.transcribe(wav, language=lang, word_timestamps=True,
                                      initial_prompt=FILLER_PROMPT, vad_filter=False)
        segs = list(segs)
    except Exception:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segs, info = model.transcribe(wav, language=lang, word_timestamps=True,
                                      initial_prompt=FILLER_PROMPT, vad_filter=False)
        segs = list(segs)
    words = []
    for s in segs:
        for w in s.words or []:
            t = w.word.strip()
            if t:
                words.append({"w": t, "s": round(w.start, 3), "e": round(w.end, 3),
                              "p": round(w.probability, 2)})
    return words, info.language


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--work", default=None, help="work folder (default: <video name>_cutroom next to the video)")
    ap.add_argument("--model", default="small", help="tiny | base | small | medium | large-v3")
    ap.add_argument("--lang", default=None, help="language code, e.g. en (auto when left out)")
    ap.add_argument("--noise", type=float, default=-35, help="silence threshold in dB")
    a = ap.parse_args()

    video = os.path.abspath(a.video)
    work = os.path.abspath(a.work or os.path.splitext(video)[0] + "_cutroom")
    os.makedirs(work, exist_ok=True)

    meta = probe(video)
    print(f"video: {meta['width']}x{meta['height']} {meta['fps']}fps {meta['duration']:.1f}s")

    if not meta["has_audio"]:
        print("no sound: nothing to transcribe or cut by silence")
        sil, words, lang = [], [], a.lang
    else:
        if not meta["has_video"]:
            print("sound only: cutroom will draw the picture (background, captions, cards)")
        wav = os.path.join(work, "voice16k.wav")
        r = run(["ffmpeg", "-y", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000", wav])
        if r.returncode:
            sys.exit("audio extract failed: " + r.stderr)

        sil = silences(video, a.noise)
        for s in sil:
            if s[1] is None:
                s[1] = round(meta["duration"], 3)
        print(f"silences: {len(sil)}")

        print(f"transcribing with whisper '{a.model}' (first run downloads the model)...")
        words, lang = transcribe(wav, a.model, a.lang)
        print(f"words: {len(words)}  language: {lang}")

    out = {"video": video, **meta, "language": lang, "noise_db": a.noise,
           "silences": sil, "words": words}
    with open(os.path.join(work, "source.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", os.path.join(work, "source.json"))


if __name__ == "__main__":
    main()
