---
name: cutroom
description: One command turns a raw talking-head or screen-recording video into a finished one - cuts silences, "um"s and retakes, adds punch-in zooms, burns in word-by-word captions and animated motion-graphics cards (title, lower third, keyword, counting stats, numbered steps, chapter, subscribe), levels the audio to -14 LUFS, and can reframe to 9:16 for Reels/Shorts/TikTok. Fully local and free (ffmpeg + faster-whisper). Works in Google Antigravity, Claude Code and any agent that reads SKILL.md. Use when the user says "edit my video", "cut the silences", "remove the ums", "add captions", "jump cut this", "make it a reel/short", or hands over a raw .mp4/.mov (or just a voice recording) and wants it ready to post.
---

# cutroom

**Run one command. Do not edit the video step by step yourself.** The script does the
whole edit in one go; your job is only to run it and hand back the file.
This keeps the edit fast and cheap: do not read the transcript or the work files unless
the user asks for a change.

## 1. Check the tools (first time only)

```
ffmpeg -version
python -c "import faster_whisper" || pip install faster-whisper
```
No ffmpeg? Tell the user: Windows `winget install Gyan.FFmpeg`, Mac `brew install ffmpeg`, Linux `sudo apt install ffmpeg`.

## 2. House style: ask once, then never again

`<skill>` = the folder this file is in.

If `<skill>/style.json` **exists**, skip this section: the style is saved, do not ask anything.

If it does **not** exist, this is the first run. Ask the setup questions **once**, before editing.

If your app can show clickable choices (a question/choice tool), ask with it: one question
per item below, the options as buttons, the first option as the recommended one.
Otherwise print this block exactly as it is, nothing added:

```
cutroom setup - answer once, it's saved for every video.
Reply with codes like "1c 2a 3a 4a 5b 6a 7en 8a 9a", or just "defaults".

1 Platform     a) keep original shape   b) YouTube 16:9   c) Reels/Shorts/TikTok 9:16
2 Captions     a) karaoke, yellow   b) karaoke, other colour (name it)   c) plain white   d) none
3 Font         a) Montserrat ExtraBold (included)   b) a font on my computer (name it)   c) a font file (path)
4 Caption look a) CAPS, 3 words, low   b) Normal case, 2 words, low   c) CAPS, 1 word, middle, large
5 Cuts         a) punch zoom   b) smooth zoom   c) punch + white flash   d) plain cuts, no zoom
6 Pace         a) tight   b) natural, more breathing room   c) fast, shorts energy
7 Language     en / tr / es / ... (or "auto")
8 Cards        a) auto, small boxes   b) auto, full screen   c) only when I ask, small   d) only when I ask, full screen   e) off
9 Pictures &   a) full screen   b) floating window, white border   c) floating window, accent-colour border
  B-roll
Tip: you can also send a screenshot of captions or cards you like instead of 2-4 and 8.
```

Turn the answer into **one** `setup.py` call with this table (missing answers = the "a" option):

| Answer | Flags |
|---|---|
| 1a / 1b / 1c | `--aspect source` / `--aspect 16:9` / `--aspect 9:16` |
| 2a / 2b / 2c / 2d | `--captions karaoke --accent "#FFD23F"` / `--captions karaoke --accent "<their colour as hex>"` / `--captions plain` / `--captions off` |
| 3a / 3b / 3c | `--font "Montserrat ExtraBold"` / `--font "<name>"` / `--font-file "<path>"` |
| 4a / 4b / 4c | `--case upper --words 3 --position low --size medium` / `--case normal --words 2 --position low --size medium` / `--case upper --words 1 --position middle --size large` |
| 5a / 5b / 5c / 5d | `--transition punch --zoom normal` / `--transition smooth --zoom normal` / `--transition flash --zoom normal` / `--transition none --zoom off` |
| 6a / 6b / 6c | `--pace tight` / `--pace natural` / `--pace fast` |
| 7 | `--lang <code>` (leave out for auto) |
| 8a / 8b / 8c / 8d / 8e | `--cards auto --card-size box` / `--cards auto --card-size full` / `--cards manual --card-size box` / `--cards manual --card-size full` / `--cards off` |
| 9a / 9b / 9c | `--broll full` / `--broll window --broll-border "#FFFFFF"` / `--broll window --broll-border accent` |

Example: `python <skill>/scripts/setup.py --aspect 9:16 --captions karaoke --accent "#FFD23F" --font "Montserrat ExtraBold" --case upper --words 3 --position low --size medium --transition smooth --zoom normal --pace tight --lang en --cards auto --card-size box --broll full`

After saving, say in one line what was saved, then go straight on to the edit.
A font file: `--font-file "path/to/Font.ttf"` (copies it into the skill and uses it).
Later style changes ("from now on use blue captions", "smooth transitions") are the same
command with just that flag. `setup.py --show` prints the saved style; `--reset` forgets it.

### Style from a screenshot (any time)

If the user sends an image of a look they like ("make my captions look like this"):
1. Look at it and read off: colours (main, accent, box), ALL CAPS or not, words per line, size, position, box or no box, the font's character (geometric / condensed / rounded / serif, weight).
2. Font: if the user knows the name or has the file, use it (`--font-file`). Otherwise pick the closest font installed on their computer (Windows: `C:/Windows/Fonts`, Mac: `/Library/Fonts` and `~/Library/Fonts`) or the bundled Montserrat ExtraBold, and say which one you chose and that they can give you the exact font file. Never download fonts without asking.
3. Save with one `setup.py` call (e.g. `--accent "#29F0A5" --case normal --words 2 --card-look dark --font-file ...`), then tell the user in one line what you set.

## 3. Edit

Any file works: a normal video, a **sound-only** file (mp3/wav/m4a: cutroom draws the
picture itself, a slow dark gradient with big captions and cards in the middle), or a
**video without sound** (no cuts or captions, but the shape, zooms you ask for, cards and
pictures still apply). No extra flags; it notices by itself.

```
python <skill>/scripts/cutroom.py "RAW.mp4"                 # house style -> RAW_edited.mp4 (or RAW_1080x1920.mp4 ...)
python <skill>/scripts/cutroom.py "RAW.mp4" --aspect 9:16   # override the shape for this video only
```

The saved house style is applied automatically; only pass switches when this one video
should differ. That is all: when it prints `DONE`, give the
user the output path and one line of what it did (the planner line: length before/after,
cuts, fillers, retakes).

Other switches: `--title "My title|subtitle"` (title card at the start), `--no-cards`,
`--preview` (quick 540p check), `--accent "#00E5FF"` (caption highlight colour),
`--music bed.mp3` (only music the user gave you; it ducks under the voice), `--no-captions`,
`--no-zoom`, `--model medium` (better transcript for accents/names), `--out FILE`.

## 4. Changes to one video (only when the user asks)

Running the command again re-uses the transcript, so a change re-renders without
transcribing again. For changes the switches can't make, edit `RAW_cutroom/edit.json`
and run the same command:

| User says | edit.json |
|---|---|
| "keep sentence X" / "cut the part where..." | look up the number in `RAW_cutroom/transcript.md`; `"drop": [7, [31.2, 33.0]]` (sentence numbers or source seconds) |
| "don't remove that retake" | `"cut": {"auto_drop_retakes": false}` |
| "too choppy" / "faster pace" | `"cut": {"max_pause": 0.6}` / `0.3` |
| "words get clipped" | `"cut": {"keep_after": 0.2, "keep_before": 0.12}` |
| "zoom in on X at that moment" | `"zooms": [{"sentence": 9, "to": 1.35, "focus": [0.7, 0.3], "hold": 2.5}]` (focus = where on screen, 0..1 across and down) |
| "less zoom" | `"zoom": {"punch": 1.06}`; none: `"auto_punch": false` |
| "bigger / smaller / different captions" (this video only) | `"captions": {"scale": 1.2, "font": "...", "upper": false, "max_words": 2, "y": 0.8}` |
| any change "from now on" | not edit.json: `setup.py` with that flag (house style) |
| "crop on me, not the centre" (9:16) | `"frame_focus": [0.35, 0.5]` |
| "add a card here" | `"add_cards"`: list of cards; place each with `"sentence": N`, `"word": "free"` (first time it is said) or `"at": seconds`. Optional `"dur"`, `"pos": [x, y]` (0..1). |
| | `{"type": "keyword", "text": "FREE", "word": "free"}` one word or short phrase that pops. Add `"full": true` (keyword, stat, step) to make that one card take over the whole screen, `"full": false` to keep it small |
| | `{"type": "lower", "text": "Alex Rivera", "sub": "Video creator", "at": 1.0}` name + role |
| | `{"type": "stat", "text": "73%", "label": "less editing time", "sentence": 4}` counts up |
| | `{"type": "step", "num": 1, "text": "Cut the silences", "sentence": 6}` |
| | `{"type": "chapter", "num": 2, "text": "How it works", "sentence": 8}` band across the frame |
| | `{"type": "cta", "text": "SUBSCRIBE", "word": "subscribe"}` pill |
| | `{"type": "image", "file": "chart.png", "sentence": 5, "dur": 3, "fit": "window"}` a picture fades in (`"fit": "full"` fills the frame, `"window"` floats it with a white border); paths are relative to the video |
| | `{"type": "video", "file": "broll.mp4", "word": "desert", "dur": 4}` B-roll on top, muted, the speaker's voice keeps playing |
| "different background" (sound-only files) | `"background": ["#0E0E12", "#24203A"]` two colours of the moving gradient |
| "more cards" / "pick the key moments" | read `transcript.md` once, add 3-6 `keyword` cards on the sentences that carry the main idea. Only when asked: it costs tokens. |
| "full-screen motion graphics" | from now on: `setup.py --card-size full`; this video only: `"cards": {"size": "full"}` |
| "dark / text-only cards" | `setup.py --card-look dark` or `minimal` (default solid = accent-colour) |
| "fewer cards" / "no auto cards here" | `"cards": {"mode": "manual"}` (keeps only add_cards) or `"off"` |

## What it does with the default style

- Cuts pauses longer than 0.45 s but leaves ~0.2 s of air, so speech never sounds glued together. Never adds silence.
- Removes "um / uh / erm / hmm".
- Finds retakes (a sentence that starts like the next one) and keeps only the last take.
- Alternates 100% / 110% framing at jump cuts, and eases in or out on a sentence start when there was no cut for 6 s.
- Captions: up to 3 words, white with the spoken word in yellow, Montserrat ExtraBold, kept above the bottom platform UI in 9:16.
- Cards (auto): a number with a unit ("73 percent", "$2,500", "3x") becomes a counting stat card; sentences starting "First / Second / Third / Finally" become numbered step cards (when there are at least two); "subscribe" and "link in the description" become one call-to-action pill. Cards never cover the captions or each other.
- Audio normalised to -14 LUFS (YouTube / Instagram / TikTok).

## Troubleshooting

| Problem | Fix |
|---|---|
| Pauses not cut (noisy room) | add `--noise -30 --retranscribe` |
| Too much cut (quiet voice) | add `--noise -42 --retranscribe` |
| Wrong words in captions | `--model medium --lang <code> --retranscribe` |
| ffmpeg error | the filter graph is in `RAW_cutroom/filter.txt` |
