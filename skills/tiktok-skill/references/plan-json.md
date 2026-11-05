# plan.json

One file holds a batch: one post or a week of them. Every script reads it; `tt_check.py --fix`,
`schedule.py` and the agent write to it. Paths are relative to the plan's folder.

```json
{
  "timezone": "America/New_York",
  "accounts": {
    "en": {"handle": "@earthinnumbers", "socialAccountId": "<from social_accounts_list>",
           "timezone": "America/New_York", "times": ["18:30"],
           "privacyOptions": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"],
           "commentAvailable": true, "duetAvailable": true, "stitchAvailable": true, "max_video_s": 600},
    "es": {"handle": "@latierraennumeros", "socialAccountId": "<id>", "timezone": "Europe/Madrid", "times": ["20:00"]}
  },
  "posts": [
    {
      "id": "fresh",
      "format": "video",
      "media": ["video/hooked.mp4"],
      "hook": {"text": "Only 2.5% of Earth's water is fresh"},
      "cover": "video/cover.jpg",
      "beats": "video/beats.json",
      "caption": "Only 2.5% of Earth's water is fresh, and two thirds of that is ice ...",
      "settings": {"allowComment": true},
      "targets": [
        {"account": "en", "settings": {"privacy": "PUBLIC_TO_EVERYONE", "privacy_from": "user"}}
      ],
      "checklist": ["Reply to comments in the first hour"]
    },
    {
      "id": "drop",
      "format": "photo",
      "media": ["slides/en/tiktok/slide-01.jpg", "slides/en/tiktok/slide-02.jpg"],
      "slides": "slides-en.json",
      "caption": "If all of Earth's water were one drop, how big would it be? ...",
      "settings": {"allowComment": true, "autoAddMusic": true},
      "targets": [
        {"account": "en", "settings": {"privacy": "PUBLIC_TO_EVERYONE", "privacy_from": "user"}},
        {"account": "es", "media": ["slides/es/tiktok/slide-01.jpg", "slides/es/tiktok/slide-02.jpg"],
         "caption": "Si toda el agua de la Tierra fuera una gota, ¿qué tamaño tendría? ...", "settings": {"draft": true}}
      ]
    }
  ]
}
```

## Fields

| Field | Meaning |
|---|---|
| `format` | `video` (one video) or `photo` (1 to 35 photos) |
| `media` | files in order. `tt_check.py --fix` replaces entries with fixed copies in `fixed/` and keeps a `plan.json.bak` |
| `caption` | video caption, or the photo post's description. A target's own `caption` replaces it |
| `hook.text` | the on-screen hook rendered with `video.py hook` |
| `beats`, `slides` | the on-screen points file (`video.py text`) and the slide spec (`render_slides.py`). With the hook and caption first line, `tt_check.py` compares them across one account's posts within 7 days so two posts don't teach the same fact |
| `source` | `"third_party"` when the footage isn't the user's own (NASA, news, another creator): `tt_check.py` warns on a single clip that keeps its own audio |
| `cover` | videos: a 1080x1920 JPEG from `video.py cover`, also the profile-grid tile |
| `settings` | per post, overridden per target: `privacy` (one of the account's options, chosen by the user, never defaulted) with `"privacy_from": "user"` to record that the user picked it, `allowComment`, `allowDuet`, `allowStitch` (off unless the user turns them on), `yourBrand` (Promotional content), `brandedContent` (Paid partnership, never private), `aiGenerated`, `autoAddMusic` (photo posts), `draft` (send to the TikTok inbox to finish in the app) |
| `accounts.<key>` | handle, `name` (the nickname TikTok shows; the preview uses it), socialAccountId, `timezone`, `times` (from TikTok Studio), and the limits from `social_accounts_get_platform_inputs`: `privacyOptions`, `commentAvailable`, `duetAvailable`, `stitchAvailable`, `max_video_s` |
| `targets[].media`, `.cover`, `.caption` | the account's own version of the post (another hook, cut, order or language). Needed for a second account: TikTok keeps reused material out of For You |
| `frame`, `own_footage` | landscape video from the user's own footage: `{"title": "..."}` makes a framed video (full width under a headline). Only with `"own_footage": true` |
| `targets[].at` | local time `YYYY-MM-DDTHH:MM` in the account's time zone; `schedule.py` fills it. `"now": true` posts right away |
| `checklist` | what the user does in the TikTok app afterwards (sound on drafts, AI label on photo posts, replies) |
| `mediaIds`, `coverId` | set after uploading (also per target); `schedule.py --bodies-only` puts them in the requests |
| `targets[].postId`, `targets[].url` | set after `posts_create` / `posts_get`; `log.py record` logs them |

## Files the scripts write next to it

`fixed/`, `check.json`, `requests/<post>-<account>.json`, `schedule.md`, `preview/index.html` and
`preview/preview.png`, `posts.jsonl` (the log), `results.md`.
