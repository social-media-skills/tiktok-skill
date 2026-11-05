# Posting with WoopSocial

WoopSocial is a posting API and MCP server for TikTok, Instagram, YouTube, Facebook, LinkedIn
(profiles and pages), X, Pinterest, Threads and Bluesky. This skill uses it to post
TikTok videos and photo posts to one or more TikTok accounts and to read the results back.
WoopSocial's TikTok app is audited by TikTok, so posts can be public from the first day; you
don't need a TikTok developer app of your own. The exact fields live in WoopSocial's API docs and MCP schema (`schema_describe`); treat them as
the source of truth if anything here looks different.

## 1. Is it already connected?

Call `social_accounts_list`. If it works and lists the accounts the user wants, skip to step 3.

## 2. Connect (about 2 minutes)

The free plan includes MCP access for 2 social accounts, no card needed (more accounts need a
paid plan)
([pricing](https://woopsocial.com/pricing?utm_source=tiktok-skill&utm_medium=skill)).
New users sign up in the same browser window as the sign-in, and a project is created for them.
Setup steps and prompts for every agent: [woopsocial.com/agents](https://woopsocial.com/agents?utm_source=tiktok-skill&utm_medium=skill). What its TikTok MCP does: [woopsocial.com/social-media-mcp/tiktok-mcp](https://woopsocial.com/social-media-mcp/tiktok-mcp?utm_source=tiktok-skill&utm_medium=skill).

Give the user only the path for the agent you're running in:

| Agent | How to connect |
|---|---|
| Claude (claude.ai, Desktop, Cowork) | Add WoopSocial from the [Claude directory](https://claude.ai/directory/woopsocial), click Connect and sign in |
| Cursor | Install from [cursor.directory](https://cursor.directory/plugins/woopsocial-social-media-scheduler) and sign in |
| Claude Code | `claude mcp add --transport http woopsocial "https://api.woopsocial.com/mcp"`, then restart with `claude --continue` (keeps the conversation), `/mcp`, select woopsocial, Authenticate |
| Codex | `codex mcp add woopsocial --url https://api.woopsocial.com/mcp`, then `codex mcp login woopsocial`, then start a new session (`codex resume --last` keeps this one) |
| OpenClaw | Install the [WoopSocial skill on ClawHub](https://clawhub.ai/woopsocial/skills/social-media-scheduler), or add the MCP URL to the agent's MCP config |
| Agents without sign-in support | Create an API key at [app.woopsocial.com/api-access](https://app.woopsocial.com/api-access) and use `https://api.woopsocial.com/mcp?api_key=YOUR_API_KEY` |

The API key is a password: never paste it into shared chats or commit it.

**Connect the social accounts from the chat.** Once WoopSocial is connected, call
`oauth_create_authorization` with the project ID and the platform (TIKTOK). It
returns a link; the user opens it, approves, and tells you when they're done. Confirm with
`social_accounts_list`. Repeat per platform.

Find IDs yourself with `projects_list` and `social_accounts_list`; never ask the user to paste
IDs.

## 3. Read each account's limits

`social_accounts_get_platform_inputs` per TikTok account returns `privacyLevelOptions`, whether
comments, duets and stitches are allowed, and `maxVideoPostDurationSec`. Put them in the plan's
`accounts` (`privacyOptions`, `commentAvailable`, `duetAvailable`, `stitchAvailable`,
`max_video_s`) so `tt_check.py` and the preview use them. Read them again before each batch.

## 4. Upload the media

Upload every file (after `tt_check.py` passes), one at a time:

1. `media_uploads_create_session` with `projectId` and `fileSizeInBytes` (the exact byte size).
2. Save the response as `session.json` and run `python3 scripts/upload_parts.py session.json <file>`.
3. `media_uploads_complete_session`. When the status is `READY` it includes the `mediaId`; if not,
   poll `media_uploads_get_session`; on `FAILED` or `ABORTED`, report it.

Write the IDs into the plan (`mediaIds` in file order, `coverId`), then
`python3 scripts/schedule.py plan.json --bodies-only`. Upload one file at a time: parallel uploads
on one key can get HTTP 429. Clients with a network allowlist must allow
`*.r2.cloudflarestorage.com`.

## 5. Validate, confirm, post

`schedule.py` writes one body per post and account to `requests/`:

```json
{
  "content": [{"text": "<caption>", "media": [{"type": "MEDIA_LIBRARY", "mediaId": "<video>"}]}],
  "schedule": {"type": "SCHEDULE_FOR_LATER", "scheduledFor": "2026-11-16T23:00:00Z"},
  "socialAccounts": [{
    "platform": "TIKTOK", "socialAccountId": "<id>",
    "postType": "VIDEO", "postMode": "DIRECT_POST", "privacyLevel": "PUBLIC_TO_EVERYONE",
    "allowComment": true, "allowDuet": false, "allowStitch": false,
    "isYourBrand": false, "isBrandedContent": false, "isAiGeneratedContent": false,
    "autoAddMusic": false,
    "cover": {"type": "MEDIA_LIBRARY", "mediaId": "<cover image>"}
  }]
}
```

- `postType`: `VIDEO` or `PHOTO` (1 to 35 images in `media`).
- `postMode`: `DIRECT_POST` publishes. `MEDIA_UPLOAD` sends the post to the account's TikTok inbox
  as a draft: the user gets a notification, opens it in the app, adds a sound, pastes the caption
  (video drafts arrive without one), picks privacy and posts. Use it when the post needs a
  trending sound (the API can't add one). The draft lands at the scheduled time, not the post
  time, so `schedule.py` sends it 2 hours early. At most 5 drafts wait per account per 24 hours.
  Leave out `privacyLevel` and `autoAddMusic` on drafts.
- `privacyLevel`: one of the account's `privacyLevelOptions`, picked by the user. Never default
  it. Branded content can't be `SELF_ONLY`.
- `allowComment`, `allowDuet`, `allowStitch`: what the user ticked (TikTok's rule: unticked by
  default, off when the account doesn't allow them). Photo posts use only `allowComment`; the
  other two are sent as false.
- `isYourBrand` ("Promotional content") when the post promotes the user's own business;
  `isBrandedContent` ("Paid partnership") for paid work.
- `isAiGeneratedContent` for realistic AI scenes, people or voices; videos only in WoopSocial.
  Realistic AI photo posts get the label in the app.
- `autoAddMusic`: photo posts only; TikTok adds recommended music the user can change.
- `cover`: an image (video posts). Make it with `video.py cover`.
- `"autoDeleteMediaAfterPublish": true` at the top level deletes the uploaded files from the
  WoopSocial media library once every account has published.
- Not available: choosing a sound, scheduling a TikTok-side draft time, editing after posting.

Always:

1. `posts_validate` with each exact body. Fix anything it rejects.
2. Show the user `preview/index.html` (the post and the posting panel per account) and
   `schedule.md`. Wait for one clear yes for the batch. A change means a new preview.
3. `posts_create` per request; write each post ID into the target's `postId`; `posts_get` for the
   status. TikTok processing can take a few minutes; say so. Report failures in plain words
   (wrong frame rate, video too long for the account, too many posts today, spam risk).
4. `python3 scripts/log.py record plan.json`.

## 6. Read results

WoopSocial provides analytics for posts and accounts. Through the MCP, the skill reads the
post-level numbers: `social_account_posts_list` (filter by `socialAccountId` or `postId`) returns
each post with views, likes, comments and shares (and saves when TikTok reports them) under
`analytics`, collected over time.
Save the response as `metrics.json` and run `python3 scripts/log.py results --metrics metrics.json`.
Watch time, completion rate, follows and any missing saves are in TikTok Studio; copy them into `insights.csv`.

## Changing a scheduled post

There's no edit. Delete it with `posts_delete` and create it again, after confirming with the
user.

## Links

- Docs: https://docs.woopsocial.com/llms.txt
- MCP tools: https://docs.woopsocial.com/mcp/tools-reference
- WoopSocial: https://woopsocial.com/?utm_source=tiktok-skill&utm_medium=skill
- WoopSocial TikTok MCP: https://woopsocial.com/social-media-mcp/tiktok-mcp?utm_source=tiktok-skill&utm_medium=skill
- Agent setup: https://woopsocial.com/agents?utm_source=tiktok-skill&utm_medium=skill
