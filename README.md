# cutroom - a free video editing skill for AI agents

Hand your agent a raw video (or just a voice recording) and get back a posted-ready one: dead air and "um"s cut, retakes found and removed, punch-in zooms on jump cuts, focus zooms on what you're talking about, word-by-word captions, animated motion-graphics cards (title, lower third, keyword, counting stats, numbered steps, chapter, subscribe), pictures and B-roll where you ask for them, loudness at -14 LUFS, optional ducked music, and 9:16 for Reels/Shorts/TikTok.

Everything runs on your own computer: **ffmpeg + faster-whisper + Python**. No API keys, no subscriptions, no uploads.

## Install

**Easiest: let your agent do it.** Open your project in Antigravity or Claude Code and say:

> Install the cutroom skill from https://github.com/ChirokAI/cutroom into this project.

The agent clones this repository into the right skills folder and checks that ffmpeg, Python and faster-whisper are there.

**By hand (no commands):**

1. On this page, click the green **Code** button, then **Download ZIP**.
2. Unzip it. You get a folder called `cutroom-main`. **Rename it to `cutroom`.**
3. Move that `cutroom` folder into your agent's skills folder, so that `SKILL.md` ends up at `.../skills/cutroom/SKILL.md`:

| Agent | This project only | All projects |
|---|---|---|
| Google Antigravity | `<project>/.agents/skills/cutroom/` | `~/.gemini/config/skills/cutroom/` (older versions: `~/.gemini/antigravity/skills/cutroom/`) |
| Claude Code | `<project>/.claude/skills/cutroom/` | `~/.claude/skills/cutroom/` |

Folders starting with a dot are hidden on Mac and sometimes on Windows. If you can't see `.agents` or `.claude` in your project, create it (Windows: in File Explorer, View → Show → Hidden items; Mac: Cmd + Shift + .).

Prefer git? `git clone https://github.com/ChirokAI/cutroom .agents/skills/cutroom` (Antigravity) or `git clone https://github.com/ChirokAI/cutroom .claude/skills/cutroom` (Claude Code).

Requirements: [ffmpeg](https://ffmpeg.org/download.html), Python 3.9+ and `pip install faster-whisper`. Restart the agent afterwards (in Antigravity, cutroom should be listed under Customizations in the agent panel).

## Use

Put your video in the project and ask:

> Edit `raw.mp4` with cutroom. Cut the silences and retakes, add captions, make a 9:16 version for Reels.

The first time, the agent asks you 9 quick questions (platform, captions, font, caption look, cuts and zoom, pace, language, cards, pictures and B-roll) that you answer with short codes like "1c 2a 5b" and saves your answers as your house style in `cutroom/style.json`. You can also just send a screenshot of captions or cards you like, and it copies the look. After that it never asks again: every video gets your style with one command, which keeps each edit fast and cheap on tokens. Say "from now on…" to change the style.

The agent runs one command and hands you the finished file. Or run it yourself:

```
python cutroom/scripts/cutroom.py raw.mp4 --aspect 9:16
```

Want changes? Ask the agent ("keep the retake", "zoom on the button at 0:36", "smaller captions"). It edits `raw_cutroom/edit.json` and re-renders in seconds without transcribing again.

## Files

```
cutroom/
  SKILL.md              instructions for the agent
  scripts/cutroom.py    the one command (runs the three below)
  scripts/transcribe.py video -> words, silences, video facts
  scripts/plan.py       edit decisions -> transcript, timeline, captions (instant)
  scripts/cards.py      animated cards (drawn with libass, same ffmpeg pass)
  scripts/setup.py      saves your house style (style.json)
  scripts/render.py     one ffmpeg pass -> preview.mp4 / final.mp4
  fonts/                caption font (Montserrat, SIL Open Font License)
```

## License

Scripts: MIT. Montserrat font: SIL Open Font License 1.1 (see fonts/OFL.txt).
