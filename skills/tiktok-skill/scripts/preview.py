#!/usr/bin/env python3
"""Show every TikTok post the way TikTok will, with the posting screen TikTok requires, before anything is posted.

    python3 scripts/preview.py plan.json --out preview/

Writes preview/index.html (open it in a browser) and preview/preview.png (the same, as one image
the agent can look at). For each post and account: the post full screen as the For You feed shows
it, with TikTok's interface drawn on top (buttons, caption, sound line), every photo of a photo
post, and the posting panel TikTok asks posting apps to show: the account, privacy (no default),
comments/duets/stitches, the commercial-content labels, the AI label and the music consent line.
Privacy shows as chosen only when the plan records it as the user's choice ("privacy_from": "user").
On top: each account's profile grid after the batch (newest first, 3:4 tiles).
Needs Python 3.9+ and Pillow; ffmpeg for video thumbnails.
"""
import argparse, html, json, os, shutil, subprocess, sys
from datetime import datetime

from PIL import Image, ImageDraw, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
PRIV_LABEL = {"PUBLIC_TO_EVERYONE": "Everyone", "MUTUAL_FOLLOW_FRIENDS": "Friends",
              "FOLLOWER_OF_CREATOR": "Followers", "SELF_ONLY": "Only you"}


def font(size, weight="Regular"):
    from render_slides import font as rfont
    return rfont("sans", size, weight)


def is_video(p):
    return os.path.splitext(p)[1].lower() in VIDEO_EXT


def thumb(src, dst, at=1.0):
    """A 540x960 JPEG of an image or of a video frame."""
    if is_video(src):
        img = Image.new("RGB", (540, 960), "#222")
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", src, "-frames:v", "1",
                            "-vf", "scale=540:960:force_original_aspect_ratio=increase,crop=540:960", dst], capture_output=True)
            if os.path.exists(dst):
                img = Image.open(dst).convert("RGB")
    else:
        with Image.open(src) as im:
            img = ImageOps.fit(ImageOps.exif_transpose(im).convert("RGB"), (540, 960), Image.LANCZOS)
    img.save(dst, "JPEG", quality=85)
    return img


def when(at, tz):
    if not at:
        return "not scheduled"
    try:
        return datetime.fromisoformat(at).strftime("%a %d %b, %H:%M") + (f" ({tz.split('/')[-1].replace('_', ' ')})" if tz else "")
    except ValueError:
        return at


def grid_tile(img, size=200):
    w, h = img.size
    th = min(h, round(w * 4 / 3))
    y = (h - th) // 2
    return img.crop((0, y, w, y + th)).resize((size, round(size * 4 / 3)), Image.LANCZOS)


def settings_of(p, t):
    return dict(p.get("settings") or {}, **(t.get("settings") or {}))


def foryou(first, caption, handle, fmt, count, width=405, sound="original sound"):
    """The post as the For You feed shows it: full screen, buttons on the right, caption at the bottom."""
    h = round(width * 16 / 9)
    card = ImageOps.fit(first.convert("RGB"), (width, h), Image.LANCZOS).convert("RGBA")
    shade = Image.new("RGBA", card.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for i in range(round(h * 0.34)):
        sd.line([(0, h - i), (width, h - i)], fill=(0, 0, 0, round(150 * (1 - i / (h * 0.34)))))
    card = Image.alpha_composite(card, shade)
    d = ImageDraw.Draw(card)
    s = width / 405
    f, fb, fs = font(round(15 * s)), font(round(16 * s), "Bold"), font(round(13 * s))
    # top tabs
    d.text((width / 2 - 70 * s, 16 * s), "Following", fill=(255, 255, 255, 170), font=fs)
    d.text((width / 2 + 12 * s, 16 * s), "For You", fill="white", font=font(round(13 * s), "Bold"))
    # right column: avatar, like, comment, save, share
    x = width - 46 * s
    y = h * 0.50
    d.ellipse([x, y, x + 36 * s, y + 36 * s], fill="#DDDDDD", outline="white", width=2)
    for _ in range(4):  # like, comment, save, share
        y += 62 * s
        d.ellipse([x + 4 * s, y, x + 32 * s, y + 28 * s], fill=(255, 255, 255, 210))
    # caption block
    words = caption.replace("\n", " ").split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width - 90 * s:
            cur = t
        else:
            lines.append(cur)
            cur = w
            if len(lines) == 2:
                break
    if cur and len(lines) < 2:
        lines.append(cur)
    more = len(" ".join(lines)) < len(caption.replace("\n", " ").strip())
    y = h - (36 + 22 * len(lines) + 28) * s
    if fmt == "photo" and count > 1:  # the photo counter dots sit just above the caption block
        dots = min(count, 12)
        sx = width / 2 - dots * 5
        for i in range(dots):
            d.ellipse([sx + i * 10, y - 16 * s, sx + i * 10 + 5, y - 16 * s + 5], fill="white" if i == 0 else (255, 255, 255, 110))
    d.text((12 * s, y), handle, fill="white", font=fb)
    y += 26 * s
    for i, ln in enumerate(lines):
        d.text((12 * s, y), ln + (" ... more" if more and i == len(lines) - 1 else ""), fill="white", font=f)
        y += 22 * s
    d.text((12 * s, h - 28 * s), sound, fill="white", font=fs)
    return card.convert("RGB")


def panel_html(acc, s, fmt):
    """TikTok's required posting screen, filled in from the plan."""
    opts = acc.get("privacyOptions") or ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]
    priv = s.get("privacy") if s.get("privacy_from") == "user" else None
    draft = s.get("draft")
    rows = []
    if draft:
        rows.append('<p class="draft">Inbox draft: it arrives in your TikTok inbox 2 hours before the time above. You pick the '
                    'sound, privacy and disclosure in TikTok' + (', and paste the caption (video drafts arrive without one)' if fmt == "video" else '')
                    + ', then post.</p>')
        return "".join(rows)
    else:
        choice = "".join(
            f'<span class="opt{" on" if o == priv else ""}{" off" if (o == "SELF_ONLY" and s.get("brandedContent")) else ""}">{PRIV_LABEL.get(o, o)}</span>'
            for o in opts)
        rows.append(f'<div class="row"><b>Who can view</b><span>{choice}</span></div>')
        if not priv:
            rows.append('<p class="err">Who can view: not chosen yet. TikTok asks you to pick it; there is no default.</p>')
    inter = [("allowComment", "Comments", "commentAvailable")] + ([] if fmt == "photo" else [("allowDuet", "Duet", "duetAvailable"), ("allowStitch", "Stitch", "stitchAvailable")])
    boxes = "".join(f'<span class="box{" on" if s.get(k) else ""}{" off" if acc.get(av) is False else ""}">{lab}</span>' for k, lab, av in inter)
    rows.append(f'<div class="row"><b>Allow</b><span>{boxes}</span></div>')
    disc = []
    if s.get("yourBrand"):
        disc.append("Promotional content")
    if s.get("brandedContent"):
        disc.append("Paid partnership")
    rows.append(f'<div class="row"><b>Disclose content</b><span>{" + ".join(disc) or "Off"}</span></div>')
    rows.append(f'<div class="row"><b>AI-generated</b><span>{"On" if s.get("aiGenerated") else "Off"}'
                f'{" (add it in the app for photo posts)" if (s.get("aiGenerated") and fmt == "photo") else ""}</span></div>')
    if fmt == "photo":
        rows.append(f'<div class="row"><b>Music</b><span>{"TikTok adds recommended music" if s.get("autoAddMusic") else "None; add a sound in the app if you want one"}</span></div>')
    consent = ("By posting, you agree to TikTok's Branded Content Policy and Music Usage Confirmation." if s.get("brandedContent")
               else "By posting, you agree to TikTok's Music Usage Confirmation.")
    rows.append(f'<p class="consent">{consent}</p>')
    return "".join(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("plan")
    ap.add_argument("--out", default="preview")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.plan))
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    out = a.out if os.path.isabs(a.out) else os.path.join(base, a.out)
    tdir = os.path.join(out, "media")
    os.makedirs(tdir, exist_ok=True)
    accounts = plan.get("accounts", {})
    checks = None
    if os.path.exists(os.path.join(base, "check.json")):
        checks = json.load(open(os.path.join(base, "check.json"), encoding="utf-8"))

    def P(x):
        return x if os.path.isabs(x) else os.path.join(base, x)

    cards, tiles, sections = [], {}, []
    for p in plan.get("posts", []):
        pid, fmt = p.get("id", "post"), p.get("format", "video")
        phones, strips = "", ""
        for t in p.get("targets", []):
            key = t.get("account") or "_"
            acc = accounts.get(key, {})
            handle = acc.get("handle") or "@yourhandle"
            files = t.get("media") or p.get("media", [])
            if not files or not os.path.exists(P(files[0])):
                continue
            imgs = [thumb(P(m), os.path.join(tdir, f"{pid}-{key}-{i + 1:02d}.jpg")) for i, m in enumerate(files) if os.path.exists(P(m))]
            cover = t.get("cover") or p.get("cover")
            first = Image.open(P(cover)).convert("RGB") if (cover and os.path.exists(P(cover))) else imgs[0]
            cap = t.get("caption") or p.get("caption", "")
            s = settings_of(p, t)
            if s.get("draft"):
                sound = "you add the sound in the app"
            elif fmt == "photo":
                sound = "TikTok adds music" if s.get("autoAddMusic") else "no music"
            else:
                sound = "original sound"
            card = foryou(imgs[0] if fmt == "photo" else thumb(P(files[0]), os.path.join(tdir, f"{pid}-{key}-play.jpg"), at=0.4),
                          cap, handle, fmt, len(imgs), sound=sound)
            cname = f"{pid}-{key}-foryou.jpg"
            card.save(os.path.join(tdir, cname), "JPEG", quality=88)
            cards.append((f"{pid} {handle}", card))
            tiles.setdefault(key, []).append((t.get("at") or "", grid_tile(first)))
            phones += (f'<div class="acct"><div class="phone"><img src="media/{cname}"></div>'
                       f'<div class="panel"><div class="who"><span class="av"></span><b>{html.escape(acc.get("name") or handle)}</b><span class="note">{html.escape(handle) if acc.get("name") else ""}</span>'
                       f'<span class="when">{html.escape(when(t.get("at"), acc.get("timezone") or plan.get("timezone", "")))}</span></div>'
                       f'<pre>{html.escape(cap)}</pre>{panel_html(acc, s, fmt)}</div></div>')
            if fmt == "photo":
                figs = "".join(f'<figure><img src="media/{pid}-{key}-{i + 1:02d}.jpg"><figcaption>{i + 1}</figcaption></figure>' for i in range(len(imgs)))
                strips += f'<p class="note">{html.escape(handle)}: all {len(imgs)} photos</p><div class="strip">{figs}</div>'
        issues = [c for c in (checks or []) if c.get("post") == pid and c.get("level") in ("error", "fix", "warn")]
        issue_html = "".join(f'<li class="{c["level"]}"><b>{c["level"]}</b> {html.escape(c["item"])}: {html.escape(c["message"])}</li>' for c in issues) \
            or ('<li class="ok">All checks pass.</li>' if checks is not None else '<li class="warn"><b>not checked</b> run scripts/tt_check.py plan.json first</li>')
        todo = "".join(f"<li>{html.escape(x)}</li>" for x in p.get("checklist", [])) or "<li>Nothing to add in the app.</li>"
        sections.append(f'<section class="post"><h2>{html.escape(pid)} <span class="fmt">{fmt}</span></h2>{phones}{strips}'
                        f'<h3>Checks</h3><ul class="checks">{issue_html}</ul><h3>After posting, in the TikTok app</h3><ul>{todo}</ul></section>')

    grid_html = ""
    for key, items in tiles.items():
        imgs = [g for _, g in sorted(items, key=lambda x: x[0], reverse=True)]
        for i, g in enumerate(imgs):
            g.save(os.path.join(tdir, f"grid-{key}-{i + 1:02d}.jpg"), "JPEG", quality=88)
        grid_html += (f'<div class="gridwrap"><p class="note">{html.escape(accounts.get(key, {}).get("handle", key))}</p><div class="grid">'
                      + "".join(f'<img src="media/grid-{key}-{i + 1:02d}.jpg">' for i in range(len(imgs))) + "</div></div>")

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TikTok preview</title><style>
:root{{--fg:#161823;--muted:#8A8B91;--line:#E3E3E4;--bg:#F8F8F8;--card:#fff;--red:#FE2C55}}
body{{margin:0;font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--fg)}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 80px}} h1{{font-size:22px;margin:0 0 4px}} .lede{{color:var(--muted);margin:0 0 24px}}
.grids{{display:flex;gap:28px;flex-wrap:wrap}} .gridwrap{{flex:1;min-width:220px;max-width:360px}} .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:2px}} .grid img{{width:100%;display:block}}
.post{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:28px 0}} .post h2{{margin:0 0 14px;font-size:18px}}
.fmt{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);border:1px solid var(--line);border-radius:99px;padding:2px 8px;margin-left:6px}}
.acct{{display:flex;gap:24px;flex-wrap:wrap;margin:0 0 22px}} .phone{{width:270px;max-width:100%}} .phone img{{width:100%;border-radius:14px;display:block}}
.panel{{flex:1;min-width:260px}} .who{{display:flex;align-items:center;gap:10px;margin-bottom:8px}} .av{{width:28px;height:28px;border-radius:50%;background:#ddd;display:inline-block}} .when{{margin-left:auto;color:var(--muted);font-size:13px}}
pre{{white-space:pre-wrap;font:inherit;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;margin:0 0 10px}}
.row{{display:flex;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding:8px 0}} .row span{{text-align:right}}
.opt,.box{{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;margin-left:6px;font-size:13px;color:var(--muted)}}
.opt.on,.box.on{{border-color:var(--fg);color:var(--fg);font-weight:600}} .opt.off,.box.off{{text-decoration:line-through;opacity:.45}}
.err{{color:var(--red);font-weight:600;margin:4px 0}} .draft{{background:#FFF7E6;border-radius:8px;padding:8px 10px}} .consent{{color:var(--muted);font-size:13px;margin-top:10px}}
.checks{{padding-left:18px}} .checks .error b{{color:var(--red)}} .checks .fix b{{color:#E5A00D}} .checks .warn b{{color:var(--muted)}} .checks .ok{{color:#2E7D32}}
.strip{{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px}} .strip figure{{margin:0;flex:0 0 auto}} .strip img{{height:220px;border-radius:6px;display:block}} .strip figcaption{{font-size:12px;color:var(--muted);text-align:center}}
.note{{color:var(--muted);font-size:13px}}
@media (prefers-color-scheme:dark){{:root{{--fg:#F1F1F2;--muted:#A2A3A8;--line:#2F2F35;--bg:#121212;--card:#1A1A1E}} .draft{{background:#3A2E12}}}}
</style></head><body><main>
<h1>TikTok preview</h1><p class="lede">{len(sections)} post(s). Nothing has been posted. Check each post, the grid and every posting panel, then say yes, change something, or cancel.</p>
<h3>Profile grid after this batch (newest first)</h3><div class="grids">{grid_html}</div>
{''.join(sections)}
</main></body></html>"""
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)

    pad, w = 24, 405
    hmax = max([c.height for _, c in cards] + [1])
    sheet = Image.new("RGB", (pad + len(cards) * (w + pad), hmax + 2 * pad + 36), "#EFEFEF")
    d = ImageDraw.Draw(sheet)
    x = pad
    for label, c in cards:
        d.text((x, pad - 4), label, fill="#333", font=font(20, "SemiBold"))
        sheet.paste(c, (x, pad + 30))
        x += w + pad
    if sheet.width > 4000:
        sheet = sheet.resize((4000, round(sheet.height * 4000 / sheet.width)), Image.LANCZOS)
    sheet.save(os.path.join(out, "preview.png"))
    print(f"wrote {os.path.join(out, 'index.html')} and preview.png ({len(cards)} post views)")


if __name__ == "__main__":
    main()
