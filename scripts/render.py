#!/usr/bin/env python3
"""cutroom step 3: render what plan.py decided. One ffmpeg pass.

usage: python render.py WORK_DIR            -> WORK_DIR/preview.mp4 (540p, fast - for review)
       python render.py WORK_DIR --final    -> WORK_DIR/final.mp4   (full quality)
       python render.py WORK_DIR --final --out my_video.mp4
"""
import argparse, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "fonts")


def piecewise(events, idx, start, T="t"):
    """ffmpeg expression for value idx of zoom events [t, z, fx, fy, ease]."""
    expr, prev = f"{start}", start
    for ev in events:
        t, val, d = ev[0], ev[idx], ev[4]
        dv = round(val - prev, 4)
        prev = val
        if abs(dv) < 1e-4:
            continue
        if d <= 0:
            expr += f"+({dv})*gte({T},{t:.3f})"
        else:
            c = f"clip(({T}-{t:.3f})/{d:.3f},0,1)"
            expr += f"+({dv})*{c}*{c}*(3-2*{c})"
    return expr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    tl = json.load(open(os.path.join(work, "timeline.json"), encoding="utf-8"))
    F, OW, OH, W, H = tl["fps"], tl["out_w"], tl["out_h"], tl["src_w"], tl["src_h"]

    keep = "+".join(f"between(t,{s['s']:.3f},{s['e']:.3f})" for s in tl["segments"])
    v = [f"fps={F}", f"select='{keep}'", f"setpts=N/({F}*TB)"]

    # reframe to the output aspect
    if (OW, OH) != (W - W % 2, H - H % 2):
        if W / H > OW / OH:
            cw, ch = int(H * OW / OH) // 2 * 2, H - H % 2
        else:
            cw, ch = W - W % 2, int(W * OH / OW) // 2 * 2
        fx, fy = tl["frame_focus"]
        v.append(f"crop={cw}:{ch}:{int((W - cw) * fx)}:{int((H - ch) * fy)}")
        v.append(f"scale={OW}:{OH}:flags=lanczos")
    else:
        v.append(f"scale={OW}:{OH}") if (W, H) != (OW, OH) else None

    # eased zooms and punch-ins. perspective keeps the frame size constant (a per-frame
    # scale+crop changes the size every frame, which crashes some ffmpeg builds) and
    # samples sub-pixel, so slow pushes don't wobble. "in" = output frame number.
    ev = tl["zoom"]
    if ev:
        T = f"(in/{F})"
        z = f"({piecewise(ev, 1, 1.0, T)})"
        x0 = f"(({piecewise(ev, 2, 0.5, T)})*(W-W/{z}))"
        y0 = f"(({piecewise(ev, 3, 0.5, T)})*(H-H/{z}))"
        x1, y1 = f"({x0}+W/{z})", f"({y0}+H/{z})"
        v.append(f"perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':x2='{x0}':y2='{y1}'"
                 f":x3='{x1}':y3='{y1}':interpolation=cubic:eval=frame")

    # pictures and B-roll asked for at certain moments, under the captions and cards
    extra_inputs, ov_chain = [], []
    for c in tl.get("overlays", []):
        o, d = c["o"], c["dur"]
        if c["type"] == "image":
            extra_inputs += ["-loop 1", c["file"]]
            src = f"[{{i}}:v]fps={F},trim=0:{tl['duration'] + 1:.3f},setpts=PTS-STARTPTS"
        else:
            extra_inputs += ["-stream_loop -1", c["file"]]
            src = f"[{{i}}:v]fps={F},trim=0:{d:.3f},setpts=PTS-STARTPTS+{o:.3f}/TB"
        if c.get("fit") == "window":
            fit = (f"scale={int(OW * 0.72)}:{int(OH * 0.72)}:force_original_aspect_ratio=decrease,"
                   f"pad=iw+{max(4, OW // 160)}*2:ih+{max(4, OW // 160)}*2:{max(4, OW // 160)}:{max(4, OW // 160)}:0x{c.get('border', '#FFFFFF').lstrip('#')}")
        else:
            fit = f"scale={OW}:{OH}:force_original_aspect_ratio=increase,crop={OW}:{OH}"
        fade = f"format=rgba,fade=t=in:st={o:.3f}:d=0.25:alpha=1,fade=t=out:st={o + d - 0.25:.3f}:d=0.25:alpha=1"
        ov_chain.append((src, fit, fade, o, d))

    if tl.get("flashes"):
        on = "+".join(f"between(t,{t:.3f},{t + 2.5 / F:.3f})" for t in tl["flashes"])
        v.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.55:t=fill:enable='{on}'")

    if tl["captions"]:
        fdir = os.path.join(work, "fonts")
        os.makedirs(fdir, exist_ok=True)
        if os.path.isdir(FONTS):
            for f in os.listdir(FONTS):
                if f.lower().endswith((".ttf", ".otf")):
                    shutil.copy2(os.path.join(FONTS, f), fdir)
        v.append("subtitles=captions.ass:fontsdir=fonts")
    if not a.final:
        v.append("scale=-2:540")
    v.append("format=yuv420p")

    # inputs: the file itself, plus a drawn background when there is no picture
    # and silence when there is no sound
    has_v, has_a = tl.get("has_video", True), tl.get("has_audio", True)
    sd = tl.get("src_duration", tl["duration"])
    if has_v and has_a:
        inputs, vin, ain = ["-i", tl["video"]], "[0:v]", "[0:a]"
    elif has_a:
        c0, c1 = [x.lstrip("#") for x in tl.get("background", ["#0E0E12", "#24203A"])]
        inputs = ["-f", "lavfi", "-t", f"{sd:.3f}", "-i",
                  f"gradients=s={OW // 8}x{OH // 8}:r={F}:c0=0x{c0}:c1=0x{c1}:speed=0.006:n=2,"
                  f"scale={OW}:{OH}:flags=bicubic,gblur=sigma=6",
                  "-i", tl["video"]]
        vin, ain = "[0:v]", "[1:a]"
    else:
        inputs = ["-i", tl["video"], "-f", "lavfi", "-t", f"{sd:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        vin, ain = "[0:v]", "[1:a]"
    first_extra = inputs.count("-i")
    for k in range(0, len(extra_inputs), 2):
        inputs += [*extra_inputs[k].split(), "-i", extra_inputs[k + 1]]

    au = [f"aselect='{keep}'", "asetpts=N/SR/TB"]
    pre = [x for x in v if x and not x.startswith(("drawbox", "subtitles", "scale=-2", "format=yuv"))]
    post = [x for x in v if x and x.startswith(("drawbox", "subtitles", "scale=-2", "format=yuv"))]
    graph = f"{vin}{','.join(pre)}[b0];"
    last = "b0"
    for n, (src, fit, fade, o, d) in enumerate(ov_chain):
        i = first_extra + n
        graph += f"{src.format(i=i)},{fit},{fade}[o{n}];"
        graph += f"[{last}][o{n}]overlay=(W-w)/2:(H-h)/2:enable='between(t,{o:.3f},{o + d:.3f})':eof_action=pass[b{n + 1}];"
        last = f"b{n + 1}"
    graph += f"[{last}]{','.join(post)}[v];{ain}{','.join(au)}"
    mus = tl.get("music") or {}
    if mus.get("file") and os.path.exists(mus["file"]):
        mi = len([x for x in inputs if x == "-i"])
        inputs = inputs + ["-stream_loop", "-1", "-i", os.path.abspath(mus["file"])]
        graph += f",asplit=2[vo][sc];[{mi}:a]atrim=0:{tl['duration']:.3f},volume={mus.get('db', -24)}dB[m0];"
        if mus.get("duck", True):
            graph += "[m0][sc]sidechaincompress=threshold=0.02:ratio=8:attack=30:release=400[m1];"
        else:
            graph += "[sc]anullsink;[m0]anull[m1];"
        graph += "[vo][m1]amix=inputs=2:duration=first:normalize=0,"
    else:
        graph += ","
    graph += "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"

    script = os.path.join(work, "filter.txt")
    open(script, "w", encoding="utf-8").write(graph)
    out = os.path.abspath(a.out) if a.out else os.path.join(work, "final.mp4" if a.final else "preview.mp4")
    enc = (["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-b:a", "192k"] if a.final
           else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-b:a", "128k"])
    tail = ["-map", "[v]", "-map", "[a]", *enc, "-c:a", "aac", "-r", str(F),
            "-movflags", "+faststart", "-y", out]

    print(f"rendering {'final' if a.final else 'preview'} {tl['duration']:.1f}s -> {out}")
    for flag in (["-/filter_complex", "filter.txt"], ["-filter_complex_script", "filter.txt"]):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-stats", *inputs, *flag, *tail], cwd=work)
        if r.returncode == 0:
            print("done:", out)
            return
    sys.exit("ffmpeg failed - see the error above (filter graph is in filter.txt)")


if __name__ == "__main__":
    main()
