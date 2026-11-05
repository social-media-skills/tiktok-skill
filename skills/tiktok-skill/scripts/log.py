#!/usr/bin/env python3
"""Keep a log of what was posted, and learn from the account's own numbers.

    python3 scripts/log.py record plan.json                 # add posted targets to posts.jsonl
    python3 scripts/log.py results --metrics metrics.json   # rank posts against the account's own posts
    python3 scripts/log.py results --csv insights.csv       # add numbers only the app shows

record: every target in the plan with a WoopSocial `postId` (set it from posts_create) is appended
  once to posts.jsonl next to the plan (or --log).
results: metrics.json is one or more saved responses of WoopSocial's social_account_posts_list.
  insights.csv adds what only TikTok Studio shows, columns (any subset):
  post,account,measured,views,shares,saves,likes,comments,follows,avg_watch_s,completion
  (post = the plan id or the post URL; CSV numbers win over WoopSocial's). Writes results.md.

Rules, so it doesn't mislead:
- Rates are per 1,000 views (TikTok reports views, not reach). A post without views is listed but not ranked.
- Posts are only compared within the same format and account.
- Each post is measured once, at the collected value nearest to day 7 (within days 3 to 14),
  and that measurement is saved in posts.jsonl. So posts from different weeks are compared at
  the same age, and the comparison grows with every run. insights.csv can add a `measured`
  date column (YYYY-MM-DD) for numbers copied by hand.
- A best post is named once a format has 6 or more ranked posts; before that it says so.
- Videos: retention = average watch time / length, from TikTok Studio numbers in insights.csv.
- Posting-time advice needs 3+ ranked posts in at least 2 time slots.
Python 3.9+, standard library only.
"""
import argparse, csv, json, os, re, statistics, sys
from datetime import datetime, timezone

RATES = ["shares", "saves", "follows", "comments", "likes"]
ALIASES = {"uniqueimpressions": "reach", "reach": "reach", "impressionsunique": "reach",
           "views": "views", "plays": "views", "videoviews": "views",
           "shares": "shares", "sends": "shares", "saves": "saves", "saved": "saves",
           "likes": "likes", "comments": "comments", "follows": "follows"}
MIN_RANKED = 6


def load_log(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
    return rows


def video_length(base, m):
    import subprocess
    if not m:
        return None
    path = m if os.path.isabs(m) else os.path.join(base, m)
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True).stdout.strip()
        return round(float(out), 2)
    except Exception:
        return None


def cmd_record(a):
    base = os.path.dirname(os.path.abspath(a.plan))
    log = a.log or os.path.join(base, "posts.jsonl")
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    have = {(r.get("woop_post_id"), r.get("account")) for r in load_log(log)}
    accounts = plan.get("accounts", {})
    added = 0
    with open(log, "a", encoding="utf-8") as f:
        for p in plan.get("posts", []):
            for t in p.get("targets", []):
                if not t.get("postId") or (t["postId"], t.get("account")) in have:
                    continue
                acc = accounts.get(t.get("account"), {})
                cap = t.get("caption") or p.get("caption", "")
                f.write(json.dumps({
                    "logged": datetime.now().isoformat(timespec="seconds"),
                    "post": p.get("id"), "format": p.get("format"),
                    "items": len(t.get("media") or p.get("media", [])),
                    "account": t.get("account"), "handle": acc.get("handle"),
                    "socialAccountId": acc.get("socialAccountId"),
                    "at": t.get("at"), "timezone": acc.get("timezone") or plan.get("timezone"),
                    "first_line": cap.strip().split("\n")[0][:200],
                    "hashtags": re.findall(r"#(\w+)", cap), "trial": bool(p.get("trial")),
                    "woop_post_id": t["postId"], "url": t.get("url"),
                    "length_s": video_length(base, (t.get("media") or p.get("media", [None]))[0]) if p.get("format") == "video" else None,
                }, ensure_ascii=False) + "\n")
                added += 1
    print(f"logged {added} new post(s) to {log}")


def history(v):
    """WoopSocial stores each metric as values collected over time: return [(date or None, value)]."""
    if isinstance(v, (int, float)):
        return [(None, v)]
    out = []
    for x in (v if isinstance(v, list) else []):
        if isinstance(x, (int, float)):
            out.append((None, x))
        elif isinstance(x, dict):
            val = next((x[k] for k in ("value", "count", "total") if isinstance(x.get(k), (int, float))), None)
            if val is not None:
                out.append((x.get("collectedAt") or x.get("date") or x.get("timestamp"), val))
    return out


def norm(key):
    return ALIASES.get(re.sub(r"[^a-z]", "", key.lower()))


def read_metrics(path):
    """{(postId, socialAccountId): {metric: [(date, value), ...]}}"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for page in (data if isinstance(data, list) else [data]):
        for it in (page.get("socialAccountPosts", []) if isinstance(page, dict) else []):
            vals = out.setdefault((str(it.get("postId")), str(it.get("socialAccountId"))), {})
            for k, v in (it.get("analytics") or {}).items():
                n = norm(k)
                if n:
                    vals.setdefault(n, []).extend(history(v))
    return out


def pick_day7(hist, posted, now):
    """The value collected nearest to day 7 after posting, within days 3 to 14. Returns (value, age) or None."""
    best = None
    for d, v in hist:
        when = parse_dt(d) or now
        age = (when - posted).total_seconds() / 86400 if posted else None
        if age is None or not 3 <= age <= 14:
            continue
        if best is None or abs(age - 7) < abs(best[1] - 7):
            best = (v, age)
    return best


def num(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def parse_dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def cmd_results(a):
    rows = load_log(a.log)
    if not rows:
        sys.exit(f"no posts in {a.log}; run 'log.py record plan.json' after posting")
    woop = read_metrics(a.metrics) if a.metrics else {}
    csv_rows = []
    if a.csv:
        with open(a.csv, encoding="utf-8-sig") as f:
            csv_rows = list(csv.DictReader(f))
    now = datetime.now(timezone.utc)
    for r in rows:
        posted = parse_dt(r.get("at"))
        meas = dict(r.get("measured") or {})
        for k, hist in woop.get((str(r.get("woop_post_id")), str(r.get("socialAccountId"))), {}).items():
            got = pick_day7(hist, posted, now)
            old = meas.get(k)
            if got and (not old or abs(got[1] - 7) < abs(old["age"] - 7)):
                meas[k] = {"value": got[0], "age": round(got[1], 1)}
        for c in csv_rows:
            key = (c.get("post") or "").strip()
            if key and key in (r.get("post"), r.get("url")) and (not c.get("account") or c["account"].strip() in (r.get("account"), r.get("handle"))):
                mdate = parse_dt(c.get("measured")) or now
                age = round((mdate - posted).total_seconds() / 86400, 1) if posted else 7
                for k in ("reach", "views", "shares", "saves", "likes", "comments", "follows", "avg_watch_s", "completion"):
                    v = num(c.get(k, ""))
                    if v is not None:
                        meas[k] = {"value": v, "age": age}
        r["measured"] = meas
        r["m"] = {k: x["value"] for k, x in meas.items()}
        r.setdefault("length_s", None)
        ages = [x["age"] for k, x in meas.items() if k in ("views", "shares", "saves")]
        r["age"] = round(sum(ages) / len(ages)) if ages else ((now - posted).days if posted else None)
    # keep the day-7 numbers, so later runs can compare posts from any week
    with open(a.log, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: v for k, v in r.items() if k not in ("m", "age", "r", "score")}, ensure_ascii=False) + "\n")

    lines = ["# Results", "",
             "Rates per 1,000 views; in brackets, x times the median of the same format on the same account.", ""]
    by_acc = {}
    for r in rows:
        by_acc.setdefault(r.get("handle") or r.get("account"), []).append(r)
    if not any(r["m"] for r in rows):
        lines.append("No numbers yet. WoopSocial collects them over the first days after posting; "
                     "or copy them from TikTok Studio into insights.csv.")
    for acc, items in by_acc.items():
        lines += [f"## {acc}", ""]
        for fmt in ("video", "photo"):
            group = [i for i in items if i.get("format") == fmt]
            if not group:
                continue
            ranked, notes = [], []
            for i in group:
                reach = i["m"].get("views")  # TikTok reports views, not reach
                if not i["m"]:
                    notes.append(f"{i['post']}: no numbers yet")
                elif not reach:
                    notes.append(f"{i['post']}: no views reported, not ranked")
                elif i["age"] is not None and i["age"] < 0:
                    notes.append(f"{i['post']}: not published yet")
                elif i["age"] is not None and i["age"] < 3:
                    notes.append(f"{i['post']}: {i['age']} day(s) old, too new to compare; run this again after day 3")
                elif i["age"] is not None and i["age"] > 14:
                    notes.append(f"{i['post']}: no numbers from days 3 to 14 were collected, so it isn't compared")
                else:
                    i["r"] = {k: i["m"][k] / reach * 1000 for k in RATES if k in i["m"]}
                    ranked.append(i)
            lines.append(f"### {fmt.title()}s ({len(ranked)} ranked of {len(group)})")
            lines.append("")
            if ranked:
                keys = [k for k in RATES if any(k in i["r"] for i in ranked)]
                med = {k: statistics.median([i["r"][k] for i in ranked if k in i["r"]]) for k in keys}
                mviews = statistics.median([i["m"]["views"] for i in ranked])
                for i in ranked:
                    if fmt == "video" and i["m"].get("avg_watch_s") and i.get("length_s"):
                        i["retention"] = min(1.0, i["m"]["avg_watch_s"] / i["length_s"])
                rets = [i["retention"] for i in ranked if "retention" in i]
                mret = statistics.median(rets) if rets else None
                for i in ranked:
                    # On TikTok, views are the outcome (how far TikTok pushed the post); then retention for videos,
                    # then shares, saves and follows per view. Each part is x times this account's median.
                    parts = [i["m"]["views"] / mviews if mviews else 1]
                    if "retention" in i and mret:
                        parts.append(i["retention"] / mret)
                    parts += [i["r"][k] / med[k] for k in ("shares", "saves", "follows") if k in i["r"] and med.get(k)]
                    i["score"] = sum(parts) / len(parts)
                ranked.sort(key=lambda i: i["score"], reverse=True)
                extra = ["Avg watch", "Retention", "Watched full"] if fmt == "video" else []
                lines.append("| Post | Views (x median) | " + " | ".join(k.title() + " /1k" for k in keys) + "".join(f" | {e}" for e in extra) + " |")
                lines.append("|---|---|" + "---|" * (len(keys) + len(extra)))
                for i in ranked:
                    cells = [f"{i['r'][k]:.1f} ({i['r'][k] / med[k]:.1f}x)" if k in i["r"] and med[k] else "" for k in keys]
                    if fmt == "video":
                        cells += [f"{i['m']['avg_watch_s']:.1f} s" if "avg_watch_s" in i["m"] else "",
                                  f"{i['retention']:.0%}" if "retention" in i else "",
                                  f"{i['m']['completion']:.0f}%" if "completion" in i["m"] else ""]
                    v = int(i["m"]["views"])
                    lines.append(f"| {i['post']}: {i['first_line'][:48]} | {v} ({v / mviews:.1f}x) | " + " | ".join(cells) + " |")
                lines.append("")
                if len(ranked) >= MIN_RANKED:
                    lines.append(f"Best {fmt} (views, retention, shares, saves, follows against your own median): **{ranked[0]['post']}**. "
                                 "Make the next one closer to it and change one thing at a time.")
                else:
                    lines.append(f"Too few {fmt}s to call a winner ({len(ranked)} of the {MIN_RANKED} needed). Keep posting and compare again.")
                if fmt == "video" and not rets:
                    lines.append("TikTok judges videos mostly on watch time: copy average watch time (avg_watch_s) and "
                                 "'watched full video' (completion) from TikTok Studio into insights.csv.")
                missing = [k for k in ("saves", "follows") if k not in keys]
                if missing:
                    lines.append(f"Not reported through the API: {', '.join(missing)}. Copy them from TikTok Studio into insights.csv to rank on them.")
            for n in notes:
                lines.append(f"- {n}")
            lines.append("")
        slots = {}
        for i in items:
            if "score" not in i:
                continue
            d = datetime.fromisoformat(i["at"])
            band = "morning" if d.hour < 12 else "afternoon" if d.hour < 17 else "evening"
            slots.setdefault(f"{'weekday' if d.weekday() < 5 else 'weekend'} {band}", []).append(i["score"])
        good = {k: v for k, v in slots.items() if len(v) >= 3}
        if len(good) >= 2:
            best = max(good, key=lambda k: statistics.median(good[k]))
            lines.append("Posting time (median score, 1.0 = typical): " + ", ".join(
                f"{k} {statistics.median(v):.2f} ({len(v)})" for k, v in sorted(good.items())) + f". Best so far: **{best}**.")
        else:
            lines.append("Posting time: not enough data yet (3+ ranked posts in at least 2 time slots). "
                         "Until then, use the hours TikTok Studio shows your followers are most active.")
        lines.append("")
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("plan")
    r.add_argument("--log")
    s = sub.add_parser("results")
    s.add_argument("--log", default="posts.jsonl")
    s.add_argument("--metrics")
    s.add_argument("--csv")
    s.add_argument("--out", default="results.md")
    a = ap.parse_args()
    (cmd_record if a.cmd == "record" else cmd_results)(a)


if __name__ == "__main__":
    main()
