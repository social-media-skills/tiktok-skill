# TikTok in late 2026: what's true

TikTok changes these details often. Every line says where it comes from. `scripts/tt_check.py`
uses the same numbers (`LIMITS` at its top); change both together. Last checked: 2026-11-05,
against TikTok's developer docs (Content Posting API: direct post, photo post, upload, media
transfer, creator info, post status) and Content Sharing Guidelines, unless a line says otherwise.

## Access

- **Your own TikTok developer app, unaudited:** every post is forced to "only me" (SELF_ONLY), at
  most 5 users per 24 hours, and the account must be private. An audit by TikTok lifts this.
- **Through WoopSocial:** its app is audited, so posts can be public from the start. You don't
  need a TikTok developer app of your own.
- **Daily cap:** "typically around 15 posts per day" per account through the API (varies; error
  `spam_risk_too_many_posts`).
- **Inbox drafts** (`postMode: MEDIA_UPLOAD`): at most 5 waiting in an account's inbox per 24
  hours (`spam_risk_too_many_pending_share`). The user opens TikTok, finishes and posts them.
- **Processing:** a post usually goes live within about a minute after moderation; it can take
  hours.

## The account's own limits (read them every time)

WoopSocial's `social_accounts_get_platform_inputs` returns, per account: the privacy levels it
may use (`privacyLevelOptions`), whether comments, duets and stitches are allowed, and the
longest video it may post (`maxVideoPostDurationSec`). Public accounts get everyone / friends /
only me; private accounts get followers / friends / only me. Anything else is rejected.

## What TikTok requires of a posting app (Content Sharing Guidelines)

- Show which account receives the post (nickname) and a preview of the content.
- Privacy is chosen by the user, with **no default**.
- Comment, Duet and Stitch start **unchecked**; greyed out when the account doesn't allow them.
  Photo posts only have Allow Comment.
- Commercial content: off by default. "Your brand" shows the label **Promotional content**;
  "Branded content" shows **Paid partnership**. **Branded content can't be private.**
- Before the post button: "By posting, you agree to TikTok's Music Usage Confirmation" (with
  branded content: "...TikTok's Branded Content Policy and Music Usage Confirmation").
- Send nothing until the user clearly agrees, and tell them it can take a few minutes.
- The app adds no brand name, logo or watermark of its own to the creator's content.

## Media through the API

| What | Limit |
|---|---|
| Video formats | MP4 (recommended), MOV, WebM |
| Video codecs | H.264 (recommended), H.265, VP8, VP9 |
| Frame rate | 23 to 60 fps |
| Resolution | 360 to 4096 px on each side; 1080x1920 (9:16) is the standard |
| Size | up to 4 GB |
| Length | up to the account's own maximum (often 3 minutes; some 5 or 10); 10 minutes is the API ceiling. No minimum is documented |
| Video caption | up to 2,200 characters; hashtags and @mentions inside it work |
| Photo posts | JPEG or WebP (no PNG), at most 1080p and 20 MB each, up to 35 photos |
| Photo title / description | title up to 90 characters, description up to 4,000 |
| Cover | TikTok picks a frame by timestamp; WoopSocial takes a cover image and adds it as the video's first frame, so take it from the first second |

## Sound, AI label, disclosure

- **Sounds can't be added through the API.** No field takes a sound or music ID. For photo posts,
  `autoAddMusic` lets TikTok add recommended music the user can change later. A post that needs
  a trending sound goes to the inbox as a draft and the user adds the sound in the app.
  `autoAddMusic` works on direct photo posts only, not on drafts.
- **AI label:** TikTok requires a label on AI-generated or significantly edited content showing
  realistic scenes or people (Integrity and Authenticity policy). The API has the flag for videos
  and photo posts; WoopSocial sets it on videos (`isAiGeneratedContent`). For a realistic AI photo
  post, the user adds the label in the app.
- **Brand toggles:** `isYourBrand` (Promotional content) and `isBrandedContent` (Paid
  partnership) on video and photo posts.

## Platform behaviour (not API rules)

- **Originality:** "Content is also ineligible for the FYF if it includes unoriginal or reused
  material without anything new" (TikTok, Integrity and Authenticity). Reposts without creative
  edits and another app's watermark are reported as unoriginal signals (secondhand, Creator
  Academy summaries). For several accounts of your own, make a real version per account.
- **Hashtags:** a 5-hashtag limit has been shown to some users since August 2025 (Social Media
  Today); TikTok hasn't confirmed it. The skill treats 5 as the cap.
- **Interface over the video:** TikTok publishes no numbers for organic posts. Its in-feed ads
  template, scaled to 1080x1920, works out to roughly the top 240, the bottom 660 and 120 px on
  each side; the organic interface covers a bit less. Keep text in the middle band. `video.py
  zones` draws this area.
- **Photo mode:** 9:16 at 1080x1920 fills the screen; other shapes get bars. No official spec.
- **Search:** TikTok publishes nothing about weights. Captions, on-screen text and spoken words
  are widely reported to be read, so the main phrase goes early in the caption, on screen, and
  in the first spoken line. Don't promise rankings.

## What the numbers mean

- WoopSocial reads per post: views, likes, comments and shares, and saves when TikTok reports
  them, collected over the first days. A missing number is "not reported", not zero.
- Watch time, completion rate and traffic sources are only in TikTok Studio. Ask the user to copy
  them into `insights.csv` when they matter (they do for videos).
- Compare a post with the same account's own posts of the same format, never with other accounts.
