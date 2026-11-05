#!/usr/bin/env python3
"""Finish a TikTok video: cut, text, cover, and a check against what TikTok's interface covers.

    python3 scripts/video.py montage clips.json --out video/montage.mp4  # cut clips into one 9:16 sequence
    python3 scripts/video.py hook video.mp4 --text "Only 2.5% of Earth's water is fresh" --out video/hooked.mp4 [--seconds 3]
    python3 scripts/video.py text video.mp4 --beats beats.json --out video/texted.mp4  # timed on-screen points
    python3 scripts/video.py frames video.mp4 --out video/            # 8 cover candidates + a sheet
    python3 scripts/video.py cover video.mp4 --at 0.3 --out video/cover.jpg [--title "3 rules"]
    python3 scripts/video.py zones video.mp4 --out video/zones.jpg     # frames with TikTok's interface drawn on

montage: cuts clips (file, start, end, x) into one 1080x1920 video without sound, each clip
  cropped where its subject is (x 0 = left edge, 0.5 = middle, 1 = right edge). For your own
  edit of several shots; check every clip with frames first.
hook / text: burn on-screen text into a 9:16 video, in TikTok's own font (TikTok Sans) and text
  styles: "classic" white with a thin outline, or "highlight" on white strips. "auto" (default)
  picks highlight when the background behind the text is bright. The text sits in the upper middle,
  clear of the top bar, the buttons and the caption. Refuses video that isn't 9:16 yet.

frames: sharp, well-lit candidates spread over the video, with the 3:4 profile-grid crop and the
  area clear of TikTok's interface drawn on a contact sheet (frames-sheet.jpg).
cover: a 1080x1920 JPEG from one frame (default 0.3 s), with an optional title inside the part the
  profile grid shows (the middle 3:4). Also writes cover-grid.jpg. WoopSocial adds the cover as the
  video's first frame, so take it from the first second.
zones: 6 frames with the areas TikTok's interface covers (top bar, buttons, caption) shaded, so you
  can see whether any text in the video sits under them.
Needs Python 3.8+, Pillow and ffmpeg.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

W, H = 1080, 1920
# Areas TikTok's interface covers on a 1080x1920 frame. TikTok publishes no organic numbers; these
# follow its in-feed ads template (top 240, bottom 660, sides 120), which covers a bit more than
# the organic interface. See references/tiktok-specs.md.
TOP, BOTTOM, SIDE = 240, 660, 120
GRID_H = round(W * 4 / 3)              # the 3:4 window the profile grid shows
GRID_Y = (H - GRID_H) // 2


def need_ffmpeg():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        sys.exit("ffmpeg not found: run scripts/check_setup.py for the install command")


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                         capture_output=True, text=True).stdout
    try:
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        sys.exit(f"can't read {path} as a video")


def grab(path, t, out):
    """One frame at time t, scaled and cropped to fill 1080x1920 the way a 9:16 TikTok shows."""
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                        "-vf", vf, "-q:v", "2", out], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        return None
    return out


def score(img):
    """Sharpness (edge energy) and exposure, so blurry or black frames sink."""
    g = img.convert("L").resize((270, 480))
    edges = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]
    mean = ImageStat.Stat(g).mean[0]
    exposure = 1 - abs(mean - 120) / 120
    return edges * max(exposure, 0.05)


def font(size, bold=True):
    try:
        from render_slides import font as rfont
        return rfont("sans", size, "Bold" if bold else "Regular")
    except Exception:
        return ImageFont.load_default()


def text_plate(text, style, y=470, size=82):
    """A transparent 1080x1920 PNG with text in TikTok's style, starting at y (upper middle by default)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    max_w = W - 2 * (SIDE + 40)
    while size >= 48:
        f = font(size)
        lines = wrap(d, text, f, max_w)
        lh = round(size * 1.22)
        if len(lines) <= 3:
            break
        size -= 6
    if style == "highlight":
        # all strips first, then all text, so no strip covers the descenders of the line above
        ascent, descent = f.getmetrics()
        pad = round(size * 0.22)
        yy = y
        for ln in lines:
            tw = d.textlength(ln, font=f)
            x = (W - tw) / 2
            d.rounded_rectangle([x - pad, yy - pad * 0.5, x + tw + pad, yy + ascent + descent + pad * 0.3],
                                radius=round(size * 0.18), fill=(255, 255, 255, 255))
            yy += lh
    for ln in lines:
        tw = d.textlength(ln, font=f)
        x = (W - tw) / 2
        if style == "highlight":
            d.text((x, y), ln, font=f, fill=(0, 0, 0, 255))
        else:
            d.text((x, y), ln, font=f, fill=(255, 255, 255, 255), stroke_width=max(3, size // 18), stroke_fill=(0, 0, 0, 230))
        y += lh
    return img, y


def is_nine16(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip().split(",")
    try:
        w, h = int(out[0]), int(out[1])
        return abs(w / h - 9 / 16) < 0.01, (w, h)
    except Exception:
        return False, (0, 0)


def bright_behind(video, t, y0, y1):
    """Mean brightness of the band where the text will sit, so white text never lands on white."""
    tmp = os.path.join(tempfile.mkdtemp(), "f.jpg")
    if not grab(video, t, tmp):
        return 0
    with Image.open(tmp) as im:
        band = im.convert("L").crop((SIDE, max(0, y0), W - SIDE, min(H, y1)))
        return ImageStat.Stat(band).mean[0]


def burn_text(video, beats, out):
    """Burn one or more timed text beats into a 9:16 video. Each beat: start, end, text, style (auto)."""
    need_ffmpeg()
    ok, size = is_nine16(video)
    if not ok:
        sys.exit(f"{video} is {size[0]}x{size[1]}, not 9:16. Fit it first with tt_check.py --fix "
                 "(or video.py montage), so nothing is cropped without you seeing it")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    d = duration(video)
    tmpdir = tempfile.mkdtemp()
    inputs, chain, last = [], [], "[0:v]"
    notes = []
    for i, b in enumerate(beats):
        start, end = float(b.get("start", 0)), min(float(b.get("end", 3)), d)
        if end <= start:
            continue
        y = int(b.get("y", 470))
        style = b.get("style", "auto")
        plate, bottom = text_plate(b["text"], "classic", y)
        if bottom > H - BOTTOM:
            sys.exit(f"beat {i + 1} is too long to stay clear of the caption area; shorten it to about 10 words")
        if style == "auto":
            lum = bright_behind(video, start + 0.2, y - 20, bottom + 20)
            style = "highlight" if lum > 170 else "classic"
            if style == "highlight":
                notes.append(f"beat {i + 1}: bright background, used the highlight style")
        plate, _ = text_plate(b["text"], style, y)
        p = os.path.join(tmpdir, f"beat{i}.png")
        plate.save(p)
        inputs += ["-loop", "1", "-t", f"{d:.2f}", "-i", p]
        n = len(inputs) // 6
        chain.append(f"{last}[{n}:v]overlay=0:0:enable='gte(t,{start:.3f})*lt(t,{end:.3f})'[v{n}]")
        last = f"[v{n}]"
    if not chain:
        sys.exit("no beats to burn in")
    vf = ";".join(chain) + f";{last}format=yuv420p[out]"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, *inputs, "-filter_complex", vf, "-map", "[out]",
                        "-map", "0:a?", "-t", f"{d:.2f}", "-c:v", "libx264", "-profile:v", "high", "-crf", "19", "-preset", "medium",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], capture_output=True, text=True)
    shutil.rmtree(tmpdir, ignore_errors=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    for n in notes:
        print(n)
    print(f"wrote {out} with {len(chain)} text beat(s). Check it with: video.py zones {out}")


def cmd_hook(a):
    burn_text(a.video, [{"start": 0, "end": a.seconds, "text": a.text, "style": a.style}], a.out)


def cmd_text(a):
    with open(a.beats, encoding="utf-8") as f:
        beats = json.load(f)
    burn_text(a.video, beats.get("beats", beats) if isinstance(beats, dict) else beats, a.out)


def cmd_montage(a):
    """Cut clips into one 9:16 sequence, each cropped where its subject is (x: 0 left, 0.5 middle, 1 right)."""
    need_ffmpeg()
    base = os.path.dirname(os.path.abspath(a.spec))
    with open(a.spec, encoding="utf-8") as f:
        spec = json.load(f)
    clips = spec.get("clips", [])
    if not clips:
        sys.exit("no clips in the spec")
    tmpdir = tempfile.mkdtemp()
    parts = []
    for i, c in enumerate(clips):
        src = c["file"] if os.path.isabs(c["file"]) else os.path.join(base, c["file"])
        start, end = float(c["start"]), float(c["end"])
        x = min(1.0, max(0.0, float(c.get("x", 0.5))))
        vf = (f"crop='min(iw,ih*9/16)':'ih':'(iw-min(iw,ih*9/16))*{x}':0,scale={W}:{H},setsar=1,fps=30,format=yuv420p")
        part = os.path.join(tmpdir, f"p{i:02d}.mp4")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", src, "-t", f"{end - start:.3f}",
                            "-vf", vf, "-an", "-c:v", "libx264", "-crf", "18", "-preset", "medium", part], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"clip {i + 1} failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
        parts.append(part)
    lst = os.path.join(tmpdir, "list.txt")
    with open(lst, "w") as f:
        f.write("".join(f"file '{p}'\n" for p in parts))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-crf", "19",
                        "-preset", "medium", "-movflags", "+faststart", a.out], capture_output=True, text=True)
    shutil.rmtree(tmpdir, ignore_errors=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    total = sum(float(c["end"]) - float(c["start"]) for c in clips)
    print(f"wrote {a.out}: {len(clips)} clips, {total:.1f} s, 1080x1920, no sound (add one in the TikTok app: post it as an inbox draft)")


def outline_zones(img):
    """Outlines only, for the cover candidates sheet, so the frames keep their real colours."""
    d = ImageDraw.Draw(img)
    red = (255, 59, 48)
    d.rectangle([SIDE, TOP, W - SIDE, H - BOTTOM], outline=red, width=5)
    d.rectangle([0, GRID_Y, W - 1, GRID_Y + GRID_H], outline=(255, 214, 10), width=6)
    return img


def shade_zones(img, alpha=110):
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    red = (255, 59, 48, alpha)
    d.rectangle([0, 0, W, TOP], fill=red)
    d.rectangle([0, H - BOTTOM, W, H], fill=red)
    d.rectangle([0, TOP, SIDE, H - BOTTOM], fill=red)
    d.rectangle([W - SIDE, TOP, W, H - BOTTOM], fill=red)
    # the right-hand button column (like, comment, save, share, sound) reaches up to mid-screen
    d.rectangle([W - 170, round(H * 0.42), W, H - BOTTOM], fill=red)
    d.rectangle([0, GRID_Y, W - 1, GRID_Y + GRID_H], outline=(255, 214, 10, 255), width=6)
    out = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
    return out


def sheet(images, labels, out, cols=4, thumb=270):
    th = round(thumb * H / W)
    rows = (len(images) + cols - 1) // cols
    pad, lab = 16, 44
    canvas = Image.new("RGB", (cols * thumb + (cols + 1) * pad, rows * (th + lab) + (rows + 1) * pad), "#111111")
    d = ImageDraw.Draw(canvas)
    f = font(26, False)
    for i, (im, text) in enumerate(zip(images, labels)):
        x = pad + (i % cols) * (thumb + pad)
        y = pad + (i // cols) * (th + lab + pad)
        canvas.paste(im.resize((thumb, th)), (x, y))
        d.text((x, y + th + 8), text, fill="#EEEEEE", font=f)
    canvas.save(out, "JPEG", quality=88)
    return out


def cmd_frames(a):
    need_ffmpeg()
    os.makedirs(a.out, exist_ok=True)
    d = duration(a.video)
    start = min(0.5, d / 10)
    n_try = max(a.n * 3, 12)
    cands = []
    tmp = tempfile.mkdtemp()
    for i in range(n_try):
        t = start + (d - start - 0.2) * (i + 0.5) / n_try
        p = grab(a.video, t, os.path.join(tmp, f"{i:03d}.jpg"))
        if p:
            with Image.open(p) as im:
                cands.append((score(im), t, p))
    if not cands:
        sys.exit("no frames could be read")
    # best first, skipping frames that look like one already picked or sit too close in time
    def small(p):
        with Image.open(p) as im:
            return im.convert("L").resize((36, 64))
    thumbs = {c[2]: small(c[2]) for c in cands}

    def alike(p, q):
        from PIL import ImageChops
        return ImageStat.Stat(ImageChops.difference(thumbs[p], thumbs[q])).mean[0] < 2.5

    gap = (d - start) / (a.n * 2)
    picks = []
    for c in sorted(cands, reverse=True):
        if len(picks) >= a.n:
            break
        if any(abs(c[1] - p[1]) < gap or alike(c[2], p[2]) for p in picks):
            continue
        picks.append(c)
    picks.sort(key=lambda c: c[1])
    imgs, labels, meta = [], [], []
    for k, (s, t, p) in enumerate(picks):
        dst = os.path.join(a.out, f"frame-{k + 1:02d}-{t:.1f}s.jpg")
        shutil.copyfile(p, dst)
        with Image.open(dst) as im:
            imgs.append(outline_zones(im.convert("RGB").copy()))
        labels.append(f"{k + 1}: {t:.1f}s")
        meta.append({"file": os.path.basename(dst), "time": round(t, 2), "score": round(s, 1)})
    shutil.rmtree(tmp, ignore_errors=True)
    sheet(imgs, labels, os.path.join(a.out, "frames-sheet.jpg"))
    with open(os.path.join(a.out, "frames.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(f"wrote {len(picks)} candidates and frames-sheet.jpg to {a.out}")
    print("Yellow box = what the profile grid shows. Red box = the area clear of TikTok's top bar, buttons and caption.")


def wrap(draw, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=f) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def cmd_cover(a):
    need_ffmpeg()
    if a.video and not a.image and a.at > 1.0:
        print(f"note: WoopSocial adds the cover image as the video's first frame, so a cover from {a.at}s makes the video "
              "open with a one-frame flash of a different shot. Prefer a frame from the first second.")
    out = a.out if a.out.lower().endswith((".jpg", ".jpeg")) else os.path.join(a.out, "cover.jpg")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if a.image:
        with Image.open(a.image) as im:
            from PIL import ImageOps
            img = ImageOps.fit(ImageOps.exif_transpose(im).convert("RGB"), (W, H), Image.LANCZOS)
    else:
        tmp = os.path.join(tempfile.mkdtemp(), "f.jpg")
        if not grab(a.video, a.at, tmp):
            sys.exit(f"no frame at {a.at}s")
        img = Image.open(tmp).convert("RGB")
    if a.title:
        dark = a.theme != "light"
        # a soft scrim behind the title so it reads on any frame
        scrim = Image.new("L", (W, H), 0)
        sd = ImageDraw.Draw(scrim)
        cy = GRID_Y + GRID_H // 2
        sd.rectangle([0, cy - 300, W, cy + 300], fill=205 if dark else 190)
        scrim = scrim.filter(ImageFilter.GaussianBlur(70))
        base = Image.new("RGB", (W, H), (0, 0, 0) if dark else (255, 255, 255))
        img = Image.composite(base, img, scrim)
        d = ImageDraw.Draw(img)
        max_w = W - 2 * 120
        size = 128
        while size >= 64:
            f = font(size)
            lines = wrap(d, a.title, f, max_w)
            lh = round(size * 1.08)
            if len(lines) <= 4 and lh * len(lines) <= 600:
                break
            size -= 6
        y = cy - lh * len(lines) // 2
        fg = "#FFFFFF" if dark else "#111111"
        for ln in lines:
            d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, fill=fg, font=f)
            y += lh
        if a.kicker:
            fk = font(44, False)
            d.text(((W - d.textlength(a.kicker, font=fk)) / 2, y + 24), a.kicker,
                   fill="#DDDDDD" if dark else "#444444", font=fk)
    img.save(out, "JPEG", quality=92, optimize=True)
    grid = img.crop((0, GRID_Y, W, GRID_Y + GRID_H)).resize((360, 480), Image.LANCZOS)
    gpath = os.path.join(os.path.dirname(os.path.abspath(out)), "cover-grid.jpg")
    grid.save(gpath, "JPEG", quality=90)
    print(f"wrote {out} (1080x1920) and {gpath} (how the profile grid shows it)")


def cmd_zones(a):
    need_ffmpeg()
    d = duration(a.video)
    tmp = tempfile.mkdtemp()
    imgs, labels = [], []
    for i in range(6):
        t = min(d - 0.1, 0.3 + (d - 0.4) * i / 5)
        p = grab(a.video, t, os.path.join(tmp, f"{i}.jpg"))
        if p:
            with Image.open(p) as im:
                imgs.append(shade_zones(im.copy()))
            labels.append(f"{t:.1f}s")
    out = a.out if a.out.lower().endswith((".jpg", ".jpeg")) else os.path.join(a.out, "zones.jpg")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet(imgs, labels, out, cols=3, thumb=300)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {out}: any text inside a red area sits under TikTok's top bar, buttons or caption")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("frames")
    f.add_argument("video")
    f.add_argument("--out", default="video")
    f.add_argument("--n", type=int, default=8)
    c = sub.add_parser("cover")
    c.add_argument("video", nargs="?")
    c.add_argument("--at", type=float, default=0.3, help="time of the frame in seconds (keep it in the first second: WoopSocial adds the cover as the video's first frame)")
    c.add_argument("--image", help="use this image instead of a frame (a photo or a rendered slide)")
    c.add_argument("--title", help="short cover title, 2 to 6 words")
    c.add_argument("--kicker", help="optional small line under the title")
    c.add_argument("--theme", choices=["dark", "light"], default="dark")
    c.add_argument("--out", default="video/cover.jpg")
    tx = sub.add_parser("text")
    tx.add_argument("video")
    tx.add_argument("--beats", required=True, help="JSON list of {start, end, text, style (auto|classic|highlight), y}")
    tx.add_argument("--out", default="video/texted.mp4")
    mo = sub.add_parser("montage")
    mo.add_argument("spec", help="JSON {clips: [{file, start, end, x}]}")
    mo.add_argument("--out", default="video/montage.mp4")
    hk = sub.add_parser("hook")
    hk.add_argument("video")
    hk.add_argument("--text", required=True, help="the on-screen hook, about 10 words; lead with the search phrase")
    hk.add_argument("--style", choices=["auto", "classic", "highlight"], default="auto")
    hk.add_argument("--seconds", type=float, default=3.0)
    hk.add_argument("--out", default="video/hooked.mp4")
    z = sub.add_parser("zones")
    z.add_argument("video")
    z.add_argument("--out", default="video/zones.jpg")
    a = ap.parse_args()
    if a.cmd == "cover" and not (a.video or a.image):
        sys.exit("give a video (and --at) or --image")
    {"frames": cmd_frames, "cover": cmd_cover, "zones": cmd_zones, "hook": cmd_hook, "text": cmd_text,
     "montage": cmd_montage}[a.cmd](a)


if __name__ == "__main__":
    main()
