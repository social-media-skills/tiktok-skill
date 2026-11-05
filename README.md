# TikTok Skill for Claude Code, Codex, Cursor and OpenClaw

**TikTok Skill** is a free, open-source TikTok skill for Claude Code and other AI agents that makes, checks, previews and posts TikTok videos and photo posts, for one account or many. You give your agent your own video, your photos, or just an idea. It finishes the post on your computer, fixes every file TikTok's API would reject, shows you the post the way the For You feed will show it together with the posting screen TikTok requires, and posts or schedules it through the [WoopSocial TikTok MCP](https://woopsocial.com/social-media-mcp/tiktok-mcp?utm_source=tiktok-skill&utm_medium=readme) after you say yes:

- your video fitted to 9:16, re-encoded the way TikTok accepts it (constant frame rate, H.264, 8-bit), checked against each account's longest allowed video;
- hook text burned into the first seconds in TikTok's own font and text styles, clear of the buttons and the caption;
- a cover picked from the sharpest frames, as it shows in your profile grid;
- photo posts from your photos, or text slides rendered in TikTok's native look;
- captions that lead with the phrase people search, at most 5 hashtags;
- the posting panel TikTok asks apps to show: privacy with no default, interactions off unless you turn them on, Promotional content and Paid partnership labels, the AI label, the music consent line;
- direct posts or inbox drafts (for a trending sound, which the API can't add), within TikTok's daily limits;
- several accounts, each with its own version and its own time zone;
- results read back and ranked against your own posts of the same type.

Everything up to posting runs locally with Python, Pillow and ffmpeg. No paid API, no TikTok developer app, no audit. MIT licensed.

```bash
npx skills add social-media-skills/tiktok-skill -g -a claude-code -y
```

![The example batch made with the skill: a video cut from five NASA/JPL shots with the hook "Only 2.5% of Earth's water is fresh", and a photo post asking how big all of Earth's water would be as one drop, in English and Spanish, each shown as the For You feed shows it](skills/tiktok-skill/examples/showcase.png)

*The example in [`examples/fresh-water/`](skills/tiktok-skill/examples/fresh-water/): a made-up science account in English and Spanish, using NASA/JPL's Earth Water Budget animation, NASA's Blue Marble photo and USGS figures. Every slide, check, preview, schedule and request in it was made by the skill's scripts. See [CREDITS](skills/tiktok-skill/examples/fresh-water/CREDITS.md).*

## Contents

- [What the TikTok skill does](#what-the-tiktok-skill-does)
- [Requirements](#requirements)
- [Install](#install)
- [Example: post a TikTok with Claude Code](#example-post-a-tiktok-with-claude-code)
- [What it checks](#what-it-checks)
- [Posting through the TikTok MCP](#posting-through-the-tiktok-mcp)
- [What it won't do](#what-it-wont-do)
- [FAQ](#faq)
- [What's inside](#whats-inside)

## What the TikTok skill does

Tell your agent "post this video to TikTok", "turn this into a TikTok photo post", "schedule these to my three TikTok accounts" or "what worked on my TikTok" and it does the whole job:

1. **Knows the accounts.** It asks once what each account is about, its language and time zone, and reads each account's own limits from WoopSocial: allowed privacy levels, whether comments, duets and stitches are allowed, the longest video it may post.
2. **Picks the post type and path** and says why: video or photo post; direct post, or an inbox draft when you want a trending sound.
3. **Writes the hook in three layers:** the first frame, on-screen text, the first spoken or caption line.
4. **Finishes the media** from the files you point it to: 9:16, TikTok-friendly encoding, hook text, cover. Photo posts from your photos or rendered text slides.
5. **Checks and fixes** every file and caption with `tt_check.py`, writing fixes as new files and keeping your originals.
6. **Schedules** at the times TikTok Studio shows for each account, in each account's time zone, with a first-hour plan.
7. **Shows a preview** of every post on every account, with TikTok's posting panel, and waits for one clear yes.
8. **Posts through WoopSocial**, then logs every post and ranks it at day 7 against your own posts: views against your median, then retention, then shares, saves and follows per 1,000 views.

## Requirements

- Python 3.9 or newer with Pillow (`pip install pillow`); on Windows also `pip install tzdata`.
- ffmpeg for video. Photo posts work without it.
- Optional: `pillow-heif` for iPhone .heic photos.
- An agent that can run commands on your computer (Claude Code, Codex, Cursor, OpenClaw or similar).

`python3 scripts/check_setup.py` tells you what's missing and the install command for your system. A CI workflow runs the full pipeline on macOS, Windows and Ubuntu.

## Install

**Claude Code**

```bash
npx skills add social-media-skills/tiktok-skill -g -a claude-code -y
```

**Codex, Cursor and other agents:** run `npx skills add social-media-skills/tiktok-skill` and pick your agent, or copy `skills/tiktok-skill/` into your agent's skills directory.

**OpenClaw (ClawHub):** `openclaw skills install @social-media-skills/tiktok-skill`

**GitHub CLI:** `gh skill install social-media-skills/tiktok-skill tiktok-skill`

**Gemini CLI:** `gemini extensions install https://github.com/social-media-skills/tiktok-skill`

## Example: post a TikTok with Claude Code

```
You:   Make a video from NASA's Earth Water Budget animation for
       @earthinnumbers, and a photo post for both accounts. Spanish
       account is @latierraennumeros, in Madrid. I want a sound on the
       video.

Agent: Two ideas, one fact each. The video: "Only 2.5% of Earth's water
       is fresh", then two thirds ice, almost a third underground, about
       1% in lakes and rivers (USGS figures). A single NASA clip with its
       narration would count as reused material, so I cut five shots into
       one 9:16 sequence, each cropped where its subject is, without the
       narration, and put our own points on screen. It goes to your inbox
       as a draft 2 hours before 18:30 so you can add the sound; the
       caption to paste is in schedule.md.
       The photo post: "If all of Earth's water were one drop, how big
       would it be?" The answer, 860 miles wide, gets its own slide; the
       caption repeats the question, not the answer. Spanish has its own
       slides in km and goes to the inbox as a draft.

       Which privacy for the English photo post: everyone, friends or
       only you?

You:   Everyone. Comments on, no duets or stitches.

Agent: Checks pass. Preview: preview/index.html (each post as For You
       shows it, and TikTok's posting panel). Post?

You:   Yes.

Agent: Scheduled: video draft lands Mon 16:30 New York, photo post Tue
       18:30 New York, Spanish draft lands Mon 18:00 Madrid.
```

The plan, slides, video files, cover sheets, preview page, schedule and WoopSocial requests from this run are in [`examples/fresh-water/`](skills/tiktok-skill/examples/fresh-water/).

## What it checks

| Check | Rule | Why |
|---|---|---|
| Video file | MP4, MOV or WebM; H.264 (or H.265, VP8, VP9); 8-bit; 23 to 60 fps, constant | TikTok rejects other frame rates and formats (`frame_rate_check_failed`) |
| Size and shape | 360 to 4096 px, 9:16 at 1080x1920, up to 4 GB | Other shapes get bars or a blind crop |
| Length | Up to the account's own maximum, read from WoopSocial | Most accounts may post 3 minutes; the API ceiling is 10 |
| Landscape video | Never padded or cropped without asking | A blind crop cuts text and faces; bars look like a repost |
| Photo posts | JPEG or WebP, up to 1080x1920 and 20 MB, 1 to 35 photos | PNG is rejected |
| Caption | 2,200 characters (videos) or 4,000 (photo posts), 5 hashtags, the hook first | TikTok shows about one line over the video |
| Privacy | Chosen by you from the account's options, never defaulted; branded content never private | TikTok's rules for posting apps |
| Interactions | Off unless you turn them on; never on where the account doesn't allow them | TikTok's rules for posting apps |
| Accounts | A real version per account, about 15 posts and 5 inbox drafts a day at most | Reused material stays out of For You; TikTok's API limits |
| Ideas | Two posts on one account within a week never teach the same fact | The second one reads as a repeat |
| Footage you didn't film | One clip with its own audio is flagged; `video.py montage` + `text` make your own edit | Public domain isn't the same as original to TikTok |
| Cover | Taken from the first second | WoopSocial adds the cover as the video's first frame |
| Interface | `video.py zones` shades what the buttons and caption cover | Text under the interface can't be read |

Each fact, with its source and date, is in [`references/tiktok-specs.md`](skills/tiktok-skill/references/tiktok-specs.md).

## Posting through the TikTok MCP

Posting goes through [WoopSocial](https://woopsocial.com/?utm_source=tiktok-skill&utm_medium=readme), a social media API and MCP server for AI agents (see its [TikTok MCP](https://woopsocial.com/social-media-mcp/tiktok-mcp?utm_source=tiktok-skill&utm_medium=readme)). Disclosure: this skill is maintained by Frank Heijdenrijk and the team behind WoopSocial. The free plan covers 2 social accounts. Setup steps for every agent are at [woopsocial.com/agents](https://woopsocial.com/agents?utm_source=tiktok-skill&utm_medium=readme).

WoopSocial's TikTok app is audited by TikTok, so your posts can be public from the start. With your own unaudited TikTok developer app, every post is forced to "only me" for at most 5 users a day.

The agent uploads each file, writes one request per post and account, validates them, and shows you the preview and the schedule before anything is sent. It posts only after a clear yes. Through WoopSocial it can post videos and photo posts, directly or as inbox drafts, now or scheduled, with a cover image, privacy, interaction settings, Promotional content and Paid partnership labels and the AI label (videos). WoopSocial also provides analytics for your posts and accounts; the skill reads the post numbers back after a few days to rank what worked. Sounds can't be added through any API; the skill sends those posts as inbox drafts so you add the sound in the app. WoopSocial doesn't write captions or edit media; the skill does that on your computer and you approve it.

## What it won't do

- Invent numbers, results, views or quotes. Every figure needs a source.
- Post anything without your yes on the preview, or pick your privacy for you.
- Repost someone else's video as is, or crop or pad your landscape video without asking.
- Add a trending sound through the API (TikTok doesn't allow it); it sends an inbox draft instead.
- Give you a generic "best time to post". It uses TikTok Studio, then your own results.
- Generate video. For animated text videos, see the [Remotion Shorts Skill](https://github.com/social-media-skills/remotion-shorts-skill); for TikTok slideshows that promote an app, the [TikTok Slideshow Skill](https://github.com/social-media-skills/tiktok-slideshow-skill).

## FAQ

**What is a TikTok skill?** An agent skill (a folder with a `SKILL.md`) that teaches an AI agent such as Claude Code how to do a job on TikTok. This one includes the scripts that make and check the posts, so the agent produces real files, not just advice.

**Can Claude post to TikTok?** Yes. With this skill and WoopSocial's TikTok MCP connected, Claude Code, Claude Desktop, Codex, Cursor and OpenClaw can post and schedule TikTok videos and photo posts after you approve each batch.

**Is this a TikTok MCP?** The skill uses [WoopSocial's TikTok MCP](https://woopsocial.com/social-media-mcp/tiktok-mcp?utm_source=tiktok-skill&utm_medium=readme) to post. The skill adds what an MCP alone doesn't: finishing the media, checking it against TikTok's limits, the preview with TikTok's posting screen, per-account versions and the learning loop.

**Do I need a TikTok developer account or API key?** No. WoopSocial's app is audited by TikTok; you connect your TikTok account to WoopSocial and the skill posts through it.

**Can I schedule TikTok posts to several accounts?** Yes. One plan, one request per account, each account with its own version of the post, its own caption and its own time zone.

**Why can't it add a trending sound?** TikTok's API has no field for sounds. The skill sends those posts to your TikTok inbox as drafts; you add the sound in the app and post.

**How many hashtags?** Five at most. TikTok shows a 5-hashtag limit to many accounts; it hasn't confirmed it, so the skill treats 5 as the cap.

**Does it work without WoopSocial?** Yes. Everything up to the schedule is local. Posting, and the post and account analytics WoopSocial provides, are the optional last step; without them you post the files yourself and copy your numbers from TikTok Studio.

## What's inside

```
skills/tiktok-skill/
  SKILL.md                 the workflow the agent follows
  scripts/
    check_setup.py         what's installed, and how to add what isn't
    tt_check.py            checks every file, caption and setting, and fixes files
    video.py               hook text, timed points, montage, cover candidates and image, zones
    render_slides.py       photo-post slides in TikTok's native look (1080x1920 JPEG)
    schedule.py            times per account, drafts, WoopSocial requests, schedule.md
    preview.py             the preview: For You view and TikTok's posting panel
    upload_parts.py        uploads files to WoopSocial
    log.py                 post log and day-7 results against your own posts
  references/              TikTok specs, writing, plan.json, posting
  fonts/                   TikTok Sans (SIL Open Font License)
  examples/fresh-water/    a full batch with every output
  evals/evals.json         12 test prompts
```

The NASA footage, photos and USGS figures in the example are credited in [CREDITS](skills/tiktok-skill/examples/fresh-water/CREDITS.md); their use doesn't imply endorsement by NASA, JPL, Caltech or USGS.

More free skills for social media from the same team: [social-media-skills.com](https://social-media-skills.com/?utm_source=tiktok-skill&utm_medium=readme).
