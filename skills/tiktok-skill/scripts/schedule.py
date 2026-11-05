#!/usr/bin/env python3
"""Give every post a time per account, and write the WoopSocial request for each one.

    python3 scripts/schedule.py plan.json --start 2026-11-16
    python3 scripts/schedule.py plan.json --bodies-only      # times already set; just (re)write requests

Posts without a time get one day each, in plan order, one per day per account by default
(--per-day), skipping --skip days. Each account posts at its own `times` in its own `timezone`
(from plan.json; --times and --tz are the defaults for accounts that don't set them).
Inbox drafts (settings.draft) land in the account's TikTok inbox at that time; the user finishes
and posts them in the app (to add a trending sound, for example).

Writes schedule.md (the table to show the user, with the first-hour notes) and
requests/<post>-<account>.json: the exact body for WoopSocial's posts_validate and posts_create.
Media IDs come from the plan's `mediaIds` / `coverId` (or the target's own, for per-account media).
Needs Python 3.9+ (zoneinfo). On Windows also: pip install tzdata.
"""
import argparse, json, os, shutil, sys
from datetime import date, datetime, timedelta

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
POST_TYPE = {"video": "VIDEO", "photo": "PHOTO"}
PLACEHOLDER = "12:00"
DRAFT_LEAD = 120  # minutes an inbox draft arrives before the time it should go live


def zone(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        sys.exit(f"time zone '{name}' not found. On Windows run: pip install tzdata. "
                 "Use names like Europe/Madrid or America/New_York.")


def to_utc(local_iso, tz):
    d = datetime.fromisoformat(local_iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=zone(tz))
    return d.astimezone(zone("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def refs(files, ids):
    out = []
    for i, m in enumerate(files):
        mid = ids[i] if i < len(ids) and ids[i] else f"<mediaId for {os.path.basename(m)}>"
        out.append({"type": "MEDIA_LIBRARY", "mediaId": mid})
    return out


def settings_of(post, target):
    return dict(post.get("settings") or {}, **(target.get("settings") or {}))


def body_for(post, target, accounts, tz):
    """One WoopSocial request for one TikTok account. Privacy is never defaulted: a missing choice
    stays a placeholder, so posts_validate refuses it until the user has picked."""
    acc = accounts.get(target.get("account"), {})
    s = settings_of(post, target)
    text = target.get("caption") or post.get("caption", "")
    files = target.get("media") or post.get("media", [])
    ids = target.get("mediaIds") or ([] if target.get("media") else post.get("mediaIds", []))
    video = post["format"] == "video"
    sa = {"platform": "TIKTOK",
          "socialAccountId": acc.get("socialAccountId") or f"<socialAccountId for {target.get('account')}>",
          "postType": "VIDEO" if video else "PHOTO",
          "postMode": "MEDIA_UPLOAD" if s.get("draft") else "DIRECT_POST",
          "privacyLevel": s.get("privacy") or "<ask the user: " + "/".join(acc.get("privacyOptions") or ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]) + ">",
          "allowComment": bool(s.get("allowComment")),
          "allowDuet": bool(s.get("allowDuet")) if video else False,
          "allowStitch": bool(s.get("allowStitch")) if video else False,
          "isYourBrand": bool(s.get("yourBrand")),
          "isBrandedContent": bool(s.get("brandedContent")),
          "autoAddMusic": bool(s.get("autoAddMusic")) if (not video and not s.get("draft")) else False}
    if s.get("draft"):
        sa.pop("autoAddMusic")  # TikTok applies it to direct photo posts only; the sound is added in the app
        if not s.get("privacy"):
            sa.pop("privacyLevel")  # inbox drafts: the user picks privacy in the app when finishing the post
    if video:
        sa["isAiGeneratedContent"] = bool(s.get("aiGenerated"))
        cover = target.get("cover") or post.get("cover")
        if cover:
            cid = target.get("coverId") or (None if target.get("cover") else post.get("coverId"))
            sa["cover"] = {"type": "MEDIA_LIBRARY", "mediaId": cid or "<mediaId for the cover>"}
    body = {"content": [{"text": text, "media": refs(files, ids)}], "socialAccounts": [sa]}
    if target.get("now"):
        body["schedule"] = {"type": "PUBLISH_NOW"}
    elif target.get("at"):
        at = target["at"]
        if s.get("draft"):  # the draft lands in the inbox ahead of the slot, so the user can finish it on time
            at = (datetime.fromisoformat(at) - timedelta(minutes=DRAFT_LEAD)).isoformat(timespec="minutes")
        body["schedule"] = {"type": "SCHEDULE_FOR_LATER", "scheduledFor": to_utc(at, tz)}
    else:
        body["schedule"] = {"type": "DRAFT"}
    return body


def parse_times(s):
    out = []
    for t in (s if isinstance(s, list) else str(s).split(",")):
        hh, mm = str(t).strip().split(":")
        out.append((int(hh), int(mm)))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("plan")
    ap.add_argument("--start", help="first day, YYYY-MM-DD (default: tomorrow)")
    ap.add_argument("--times", help="default posting times, local, e.g. 12:30,19:00 (from TikTok Studio follower activity)")
    ap.add_argument("--per-day", type=int, default=1, help="feed posts per account per day")
    ap.add_argument("--skip", default="", help="days to skip, e.g. sat,sun")
    ap.add_argument("--stagger", type=int, default=0, help="optional minutes between accounts that share a time zone")
    ap.add_argument("--tz", help="default IANA time zone (default: the plan's timezone)")
    ap.add_argument("--bodies-only", action="store_true")
    a = ap.parse_args()

    base = os.path.dirname(os.path.abspath(a.plan))
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    default_tz = a.tz or plan.get("timezone")
    accounts = plan.get("accounts", {})
    for k, acc in accounts.items():
        if not (acc.get("timezone") or default_tz):
            sys.exit(f"no time zone for account '{k}': set accounts.{k}.timezone or \"timezone\" in plan.json")
        zone(acc.get("timezone") or default_tz)
    tz_of = lambda k: accounts.get(k, {}).get("timezone") or default_tz
    placeholder = False
    posts = plan.get("posts", [])
    by_id = {p.get("id"): p for p in posts}

    if not a.bodies_only:
        def times_of(k):
            nonlocal placeholder
            t = accounts.get(k, {}).get("times") or a.times
            if not t:
                placeholder = True
                t = PLACEHOLDER
            return parse_times(t)

        skip = {s.strip().lower()[:3] for s in a.skip.split(",") if s.strip()}
        start = date.fromisoformat(a.start) if a.start else date.today() + timedelta(days=1)
        cursor = {}  # account -> (day, index within the day)
        for p in posts:
            for k, t in enumerate(p.get("targets", [])):
                if t.get("at") or t.get("now"):
                    continue
                acct = t.get("account")
                times = times_of(acct)
                if a.per_day > len(times):
                    sys.exit(f"--per-day {a.per_day} needs at least that many times for account '{acct}'")
                day, idx = cursor.get(acct, (start, 0))
                now = datetime.now(zone(tz_of(acct))).replace(tzinfo=None)
                while True:
                    if DAYS[day.weekday()] in skip or idx >= a.per_day:
                        day, idx = day + timedelta(days=1), 0
                        continue
                    h, m = times[idx]
                    slot = datetime(day.year, day.month, day.day, h, m)
                    if slot > now + timedelta(minutes=20):
                        break
                    idx += 1
                cursor[acct] = (day, idx + 1)
                shared = [x for x in p.get("targets", [])[:k] if tz_of(x.get("account")) == tz_of(acct)]
                slot += timedelta(minutes=a.stagger * len(shared))
                t["at"] = slot.isoformat(timespec="minutes")
        shutil.copyfile(a.plan, a.plan + ".bak")
        with open(a.plan, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1, ensure_ascii=False)

    rdir = os.path.join(base, "requests")
    os.makedirs(rdir, exist_ok=True)
    rows, missing, drafts = [], set(), []
    for p in posts:
        if p.get("format") not in POST_TYPE:
            sys.exit(f"post {p.get('id')}: unknown format {p.get('format')}")
        for t in p.get("targets", []):
            tz = tz_of(t.get("account"))
            body = body_for(p, t, accounts, tz)
            name = f"{p['id']}-{t.get('account', 'account')}.json"
            with open(os.path.join(rdir, name), "w", encoding="utf-8") as f:
                json.dump(body, f, indent=1, ensure_ascii=False)
            if "<" in json.dumps(body):
                missing.add(p["id"])
            full = (t.get("caption") or p.get("caption", "")).strip()
            cap = full.split("\n")[0]
            if settings_of(p, t).get("draft"):
                lands = ""
                if t.get("at"):
                    lands = (datetime.fromisoformat(t["at"]) - timedelta(minutes=DRAFT_LEAD)).strftime("%H:%M")
                cap = f"(inbox draft: lands {lands}, finish and post at the time shown) " + cap
                drafts.append((t.get("at") or "", accounts.get(t.get("account"), {}).get("handle", t.get("account")), p["id"], p["format"], full))
            utc = body["schedule"].get("scheduledFor", "")
            rows.append((utc or "~", t.get("at") or ("now" if t.get("now") else "draft"), tz, p["id"], p["format"],
                         accounts.get(t.get("account"), {}).get("handle", t.get("account")), cap))
    rows.sort()
    lines = ["# Schedule", ""]
    if placeholder:
        lines += ["**The times are a placeholder (12:00 local).** Replace them with the hours TikTok Studio shows "
                  "(Analytics > Followers > Follower activity) and run this again.", ""]
    lines += ["| Goes live (account's local time) | Post | Format | Account | First line |", "|---|---|---|---|---|"]
    for _, at, tz, pid, fmt, acc, cap in rows:
        when = at
        try:
            when = datetime.fromisoformat(at).strftime("%a %d %b %H:%M") + f" ({tz.split('/')[-1].replace('_', ' ')})"
        except ValueError:
            pass
        lines.append(f"| {when} | {pid} | {fmt} | {acc} | {cap.replace('|', '/')[:90]} |")
    if drafts:
        lines += ["", "## Inbox drafts to finish in TikTok", ""]
        for at, acc, pid, fmt, full in sorted(drafts):
            lines.append(f"- **{pid}** on {acc}, post at {at.replace('T', ' ') or 'your chosen time'}: open the TikTok inbox, "
                         "add the sound, pick privacy and disclosure"
                         + (", and paste this caption (video drafts arrive without one):" if fmt == "video" else ", check the caption:"))
            lines.append("")
            lines.append("  ```")
            lines += ["  " + ln for ln in full.split("\n")]
            lines.append("  ```")
    lines += ["", "## The first hour after each feed post", "",
              "- Be online: reply to comments in the first hour, with a video reply to the best question if you can.",
              "- Inbox drafts: they arrive 2 hours before the time shown; at most 5 may wait per account.",
              "- Pin the comment that answers the most likely question, if there is one.",
              "- Add what's on each post's checklist (sound, AI label for photo posts, collaborators)."]
    with open(os.path.join(base, "schedule.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[: lines.index("## The first hour after each feed post")]))
    print(f"wrote {len(rows)} request bodies to {rdir} and schedule.md")
    if missing:
        print("Still placeholders (upload the media, put the IDs in mediaIds/coverId, set socialAccountId, "
              "then run again with --bodies-only): " + ", ".join(sorted(missing)))


if __name__ == "__main__":
    main()
