---
name: tiktok-skill
description: >-
  TikTok skill: make, check and post TikTok videos and photo posts from your AI agent, for one
  account or many. Takes your own video (or photos, or just an idea for text slides) and turns it
  into a finished TikTok post: 9:16 fit, hook text in TikTok's own style, a cover, a caption that
  TikTok search reads. Checks every file and caption against TikTok's API limits, fixes frame
  rate, codecs, shape and PNG, flags length per account and over 5 hashtags, shows each post as the
  For You feed shows it with TikTok's required posting screen (privacy with no default,
  interactions, disclosure, AI label), then posts or schedules with WoopSocial (TikTok MCP, no
  developer app or audit needed) after a yes, and learns from the account's own
  numbers. Use when someone says "post to TikTok", "schedule TikTok posts", "TikTok MCP", "Claude
  TikTok", "post this video to TikTok", "TikTok photo post", "multiple TikTok accounts" or "what
  worked on my TikTok". Never invents results, never posts without a yes. Standalone.
metadata:
  version: 1.0.0
license: MIT
---

# TikTok Skill

Most TikTok help from agents stops at words: hooks, captions, hashtags, "now go film it". Then the
post fails on things nobody checked: a phone screen recording TikTok rejects for its frame rate, a
clip longer than the account may post, a PNG in a photo post, hook text under the caption, seven
hashtags, a Paid partnership set to "only me", the same file on three accounts.

This skill does the whole job on the user's own computer: it picks the post type, writes the
hook and caption, finishes the media, checks every file against TikTok's current limits, shows the
user each post as TikTok will show it together with the posting screen TikTok requires, posts or
schedules through WoopSocial after a yes, and reads the numbers back. Everything it needs is in
this folder.

Five commitments:

1. **Finished, not drafted.** The user gets files TikTok accepts and a post ready to go.
2. **TikTok's posting rules, honoured.** The user picks privacy (no default), interactions start
   off, disclosure and the AI label are explicit, and nothing posts without a clear yes.
3. **One idea per post, the hook first.** In the first frame, on screen and in the first line.
4. **Only real things.** The user's own footage and photos, real numbers with sources. Never an
   invented result, view count, quote or statistic, and never someone else's video.
5. **The account's own numbers decide.** No generic best-time tables or benchmarks.

## Step 0: Setup and connection

Run `python3 scripts/check_setup.py` (Windows: `py scripts\check_setup.py`). It needs Python 3.9+
and Pillow; ffmpeg for video. It prints the install command for whatever is missing.

If the user wants to post, connect now so it's ready when the posts are:

1. **Check** with `social_accounts_list`. If the TikTok accounts are there, carry on.
2. **Not connected?** Say it in one message and keep working while they set it up:
   - Posting goes through WoopSocial's [TikTok MCP](https://woopsocial.com/social-media-mcp/tiktok-mcp?utm_source=tiktok-skill&utm_medium=skill),
     made by the team that maintains this skill. The free plan covers 2 social accounts, no card. Its TikTok app is audited, so posts can be public right
     away: no TikTok developer app or audit of the user's own.
   - Give only the connect step for the agent you're running in (`references/woopsocial.md`).
   - **Claude Code and Codex load new tools only in a new session.** Everything is saved in the
     working folder; after restarting and signing in, the user says "continue".
3. **Read each account's limits** with `social_accounts_get_platform_inputs`: its privacy
   options, whether comments, duets and stitches are allowed, its longest video. Put them in
   `accounts` in the plan (`references/plan-json.md`).

## Step 1: Know the account

Read `brand.md` if the workspace has one. Otherwise ask in one message, then save `brand.md`:

1. What is each account about, who is it for, and what language and country?
2. What does the user have: videos (where on their computer), photos, screenshots, or only an
   idea? Use only files the user points to.
3. What do they actually know or show that others don't? Real experience, real numbers.
4. Each account's time zone and when TikTok Studio says the followers are active (Analytics >
   Followers). Without it the schedule uses a placeholder and says so.
5. Anything that must never appear; whether any post promotes their own business (Promotional
   content) or is paid (Paid partnership).
6. Was the video exported from another app (CapCut free, Instagram, another editor)? A visible
   watermark from another app is a reported unoriginal signal; export clean first.

A brand-new account: first posts often get almost no views, whatever the quality. Use the account
in the app first (follow, watch and comment in the niche) and judge it after a couple of weeks.

Then look at the account before planning: ask for a screenshot of the profile grid and the last 9
to 12 posts (topic, format, what did well), so the batch doesn't repeat them.

## Step 2: Pick the post type and the path

Say in one line why each post gets its type and path.

| Goal | Post type | Why |
|---|---|---|
| Show something moving, a person, a process | Video | Watch time carries videos to non-followers |
| A list, steps, before/after, a story in frames | Photo post (1 to 35 photos) | People swipe at their own pace and save it |
| One strong statement or number | Photo post with 1 to 3 slides | Fast to read, easy to share |

| Path | When |
|---|---|
| Direct post (`postMode: DIRECT_POST`) | The post is finished as it is, with its own sound or no music |
| Inbox draft (`settings.draft: true`, `MEDIA_UPLOAD`) | It needs a trending sound or a final touch in the app. The API can't add sounds. At most 5 drafts wait per account |

A batch carries one idea per post; never lead two posts with the same fact. More than 1 to 3
posts a day per account rarely helps; TikTok caps API posts at about 15 a day.

## Step 3: The hook, in three layers

Most viewers decide in the first second or two (practitioner consensus; TikTok publishes no number).
Write the hook once and put it in three places:

1. **First frame:** the most telling moment of the clip or the strongest photo first. Trim dead
   air at the start.
2. **On-screen text:** about 10 words, the main search phrase early, rendered with
   `video.py hook` (TikTok Sans, TikTok's classic outlined style, or the highlight style when the
   background is bright; first 3 seconds, upper middle, clear of the buttons and caption). For
   points across the whole video, `video.py text --beats beats.json`.
3. **First spoken line or caption line:** the same promise in words.

Craft notes and patterns: `references/writing.md`. Never promise what the video doesn't show.

## Step 4: Make the media

Make a working folder per batch with `plan.json` (`references/plan-json.md`).

**The user's own video.**

```bash
python3 scripts/tt_check.py plan.json --fix                       # 9:16, H.264/AAC, constant fps
python3 scripts/video.py hook fixed/<file>.mp4 --text "Only 2.5% of Earth's water is fresh" --out video/hooked.mp4
python3 scripts/video.py frames video/hooked.mp4 --out video/      # cover candidates + frames-sheet.jpg
python3 scripts/video.py cover video/hooked.mp4 --at 0.3 --out video/cover.jpg
python3 scripts/video.py zones video/hooked.mp4 --out video/zones.jpg
```

Several shots of the user's into one video, each cropped where its subject is, then points on
screen across it:

```bash
python3 scripts/video.py montage clips.json --out video/montage.mp4   # {"clips": [{"file", "start", "end", "x"}]}
python3 scripts/video.py text video/montage.mp4 --beats beats.json --out video/texted.mp4
```

- Landscape footage isn't padded or cropped blind: look at the frames, then reframe it on the
  subject, use `--fit crop` when the subject stays in the middle, or, for the user's own footage
  only, a framed video (`"frame": {"title": "..."}` and `"own_footage": true`).
- `zones.jpg` shades what TikTok's interface covers. Text or faces in the red areas sit under the
  buttons or the caption: move them.
- The cover: WoopSocial adds the cover image as the video's first frame, so take it from the
  first second (the hook frame is best), or the video opens with a flash of a different shot. It is
  also the profile-grid tile: the subject in the yellow box of `frames-sheet.jpg`, the hook readable.
- **Footage you didn't film** (an agency, news or NASA clip, another creator's video): a hook
  plate, a crop or a caption does not make it original, and its own audio is the easiest thing
  for TikTok to match. Public domain means you may use it, not that TikTok counts it as yours.
  Use it only as material in an edit of your own: your voice or commentary across the clip, or
  several clips cut into your own sequence with your own on-screen points (`montage` + `text`),
  and never its original narration as the only audio. Credit the source in the caption. Mark such
  posts `"source": "third_party"` in the plan so `tt_check.py` can warn.

**Photo posts.** Use the user's photos, or render text slides in TikTok's native look:

```bash
python3 scripts/render_slides.py slides.json --out slides/ --no-instagram
```

The renderer's spec is at the top of the script: TikTok Sans, TikTok's classic, highlight and
plain text styles, text kept inside the safe area, 1080x1920 JPEG. One idea per slide, the first
slide is the hook, the last one asks for one thing. `tt_check.py --fix` converts and fits photos.

## Step 5: Write the captions

- First words: the search phrase and the hook. TikTok search reads captions, on-screen text and
  speech (TikTok publishes no weights, so don't promise rankings).
- Then one line of context and one ask (comment a word, save it, follow for part 2). At most 5
  specific hashtags; never #fyp or #viral.
- Videos: up to 2,200 characters. Photo posts: WoopSocial sends one text (TikTok has a title of
  90 characters and a description of 4,000); keep the first 90 characters able to stand alone as
  the title in case it maps there.
- Question or reveal posts: the caption's first line repeats the question or promise, never the
  answer; it shows over slide 1 before anyone swipes.
- Links aren't clickable in captions.
- **Several accounts:** each account gets its own version, not just its own caption: another
  hook, cut, order or language (`targets[].media`, `targets[].caption`). Write for the account's
  country.

## Step 6: Check and fix

```bash
python3 scripts/tt_check.py plan.json          # report
python3 scripts/tt_check.py plan.json --fix    # fixed copies in fixed/, plan updated, originals kept
```

It checks container, codec, 8-bit, HDR, frame rate (and variable frame rate), resolution, length
against each account's maximum, size, photo format, size and count, caption length, hashtags,
privacy (chosen by the user and recorded with `"privacy_from": "user"`, allowed for the account,
never private for branded content), interactions the
account doesn't allow, the AI label on photo posts, the same file on several accounts (by content),
two posts teaching the same fact to one account within a week (hook, on-screen beats, caption,
slide text), one third-party clip with its own audio, drafts and posts per day. Run it until it exits with 0, and explain anything it can't fix in plain words.

## Step 7: Schedule

```bash
python3 scripts/schedule.py plan.json --start 2026-11-16   # times and time zones from accounts in plan.json
```

Each account posts at its own `times` in its own `timezone`. Without them it uses 12:00 and says
so. It writes `schedule.md` (with the first-hour plan) and one WoopSocial request per post and
account in `requests/`. Privacy is never filled in for the user: a missing choice stays a
placeholder, and validation refuses it. Inbox drafts are sent 2 hours before their time, so the
user can finish them on time; `schedule.md` lists each draft with its caption to paste.

## Step 8: Preview and the yes

```bash
python3 scripts/preview.py plan.json --out preview/
```

Look at `preview/preview.png` yourself first: every post on every account as the For You feed
shows it (buttons, caption, sound line). Then give the user `preview/index.html`, which adds each
account's grid and the posting panel TikTok requires: the account, privacy (no default),
comments/duets/stitches, Promotional content / Paid partnership, the AI label, music, and the
line "By posting, you agree to TikTok's Music Usage Confirmation" (with Paid partnership:
"...TikTok's Branded Content Policy and Music Usage Confirmation"). Ask for one clear yes for
the batch. Any change means a new check and a new preview.

## Step 9: Post with WoopSocial

Details: `references/woopsocial.md`.

1. Upload every file (`media_uploads_create_session`, `scripts/upload_parts.py`,
   `media_uploads_complete_session`), one at a time. Put the IDs in `mediaIds` and `coverId`, then
   `python3 scripts/schedule.py plan.json --bodies-only`.
2. `posts_validate` every request. Fix anything it rejects.
3. After the yes: `posts_create` per request, write each post ID into the target's `postId`,
   `posts_get` for the status (TikTok processing can take a few minutes), then
   `python3 scripts/log.py record plan.json`.
4. Tell the user what's scheduled (account, time with time zone), which posts are inbox drafts to
   finish in the app, and what's on each checklist (sound, AI label on photo posts).

Not connected and doesn't want to connect? Hand over the files, captions, settings and schedule,
and stop. Never say something was posted when it wasn't.

## Step 10: Learn from the numbers

After 3 to 7 days: `social_account_posts_list` for the accounts, saved as `metrics.json`, then

```bash
python3 scripts/log.py results --metrics metrics.json [--csv insights.csv]
```

It measures each post at the value collected nearest day 7, saves that in `posts.jsonl`, and ranks
posts against the same account's posts of the same type: views first (on TikTok, views are how far
TikTok pushed the post), then retention for videos, then shares, saves and follows per 1,000 views.
It names a best post only after 6 of a type. WoopSocial returns views, likes, comments and shares,
and saves when TikTok reports them; whatever is missing (often saves and follows), average watch
time and "watched full video" come from TikTok Studio into `insights.csv`. Then:

| Views vs your median | Retention (watch time / length) | Next |
|---|---|---|
| High | High | Same format, new topic; make the part 2 |
| Low | High | Good video, weak packaging: new first frame, hook text, cover, caption first line |
| High | Low | The hook works, the middle doesn't: cut it shorter, pay off sooner |
| Low | Low | Change the first 2 seconds first, then the idea |

Photo posts: views against the median, then shares and saves per 1,000 views.

"High" means against the account's own posts. Never estimate a number that wasn't reported.

## Quality bar

Before showing anything: would a top creator in this niche post this? Reject and fix it if:

- the first second could belong to any other account;
- two posts in the batch, or two accounts, show the same media;
- a claim, number or result can't be shown;
- the hook text sits under the buttons or caption;
- two posts on one account within a week teach the same fact;
- another app's watermark or logo is visible;
- it looks like a template or an ad.

## Edge cases

- **Video longer than the account may post:** trim it; say which part to keep.
- **Trending sound wanted:** inbox draft; the user adds the sound in TikTok.
- **Private account:** its privacy options are followers, friends or only me; use what the
  account allows.
- **Paid partnership:** `brandedContent`, public privacy only; the consent line names the Branded
  Content Policy.
- **Realistic AI images in a photo post:** the user adds the AI label in the app.
- **More than 35 photos:** split the post.
- **A scheduled post needs changing:** there's no edit; delete it (`posts_delete`) and create it
  again, after confirming with the user.
- **Someone else's video:** don't post it. Suggest a reaction, review or the user's own take,
  filmed by them. Public-domain footage is fine with something new added and a credit.

## References

- `references/tiktok-specs.md`: limits, posting rules, sound, AI label, interface, search, with
  sources and dates.
- `references/writing.md`: hooks, on-screen text, captions, photo-post structure.
- `references/plan-json.md`: the plan file every script reads.
- `references/woopsocial.md`: connect, read account limits, upload, validate, post, results.
