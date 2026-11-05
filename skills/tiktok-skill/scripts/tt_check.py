#!/usr/bin/env python3
"""Check every TikTok post in a plan against TikTok's API limits and posting rules, and fix what can be fixed.

    python3 scripts/tt_check.py plan.json          # report only
    python3 scripts/tt_check.py plan.json --fix    # write fixed copies to fixed/ and point the plan at them

Videos: MP4/MOV/WebM, H.264 (or H.265/VP8/VP9), 8-bit, 23 to 60 fps, 360 to 4096 px, up to 4 GB,
no longer than the account's own maximum (accounts.<key>.max_video_s, from WoopSocial), 9:16.
Photo posts: JPEG or WebP, up to 1080x1920 and 20 MB each, 1 to 35 photos, title up to 90
characters, description up to 4,000. Video captions up to 2,200 characters. At most 5 hashtags.
Posting rules: privacy chosen per account from the account's own options (no default),
branded content never private, interactions only where the account allows them, at most 5
inbox drafts and about 15 posts per account per day, a real version per account.
The limits live in LIMITS below, with the date they were checked; see references/tiktok-specs.md.

Fixes never touch the originals. Anything that can't be fixed safely is an error with the
reason, and the script exits with code 1 while errors remain.
Needs Python 3.9+, Pillow and (for video) ffmpeg/ffprobe.
"""
import argparse, json, os, re, shutil, subprocess, sys

from PIL import Image, ImageFilter, ImageOps

try:  # iPhone .heic photos, when pillow-heif is installed
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

# Checked 2026-11-05 against TikTok's Content Posting API docs and Content Sharing Guidelines.
LIMITS = {
    "video_min_px": 360, "video_max_px": 4096, "video_bytes": 4 * 1024 ** 3,
    "video_max_s": 180,  # when the account's own limit wasn't read: most accounts may post 3 minutes (API ceiling 600)
    "fps_min": 23, "fps_max": 60,
    "photo_max_w": 1080, "photo_max_h": 1920, "photo_bytes": 20 * 1024 * 1024, "photos_max": 35,
    "caption_chars": 2200, "title_chars": 90, "description_chars": 4000,
    "hashtags": 5, "fold_chars": 80,
    "posts_per_day": 15, "drafts_per_day": 5,
}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
PRIVACY = {"PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"}
NINE16 = 9 / 16

issues = []  # (level, post_id, item, message)


def report(level, post, item, msg):
    issues.append((level, post, item, msg))


def rel(path, base):
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def probe_video(path):
    if not shutil.which("ffprobe"):
        sys.exit("ffprobe not found: install ffmpeg to check videos (see scripts/check_setup.py)")
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    data = json.loads(out.stdout or "{}")
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        return None
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = abs(int(float(sd["rotation"])))
    if str(v.get("tags", {}).get("rotate", "")).strip():
        rot = abs(int(v["tags"]["rotate"]))
    if rot in (90, 270):
        w, h = h, w

    def rate(r):
        try:
            n, d = r.split("/")
            return float(n) / float(d) if float(d) else 0.0
        except Exception:
            return 0.0

    fps = rate(v.get("avg_frame_rate", "0/0")) or rate(v.get("r_frame_rate", "0/0"))
    dur = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    return {
        "w": w, "h": h, "fps": fps, "duration": dur,
        "vcodec": v.get("codec_name", ""), "pix_fmt": v.get("pix_fmt", ""),
        "acodec": a.get("codec_name", "") if a else "",
        "format": data.get("format", {}).get("format_name", ""),
        "bytes": os.path.getsize(path),
        "vfr": abs(rate(v.get("r_frame_rate", "0/0")) - fps) > 0.5,
        "color_transfer": v.get("color_transfer", ""),
    }


def faststart(path):
    """True when the 'moov' atom comes before 'mdat' (the video can start before it fully loads)."""
    try:
        with open(path, "rb") as f:
            head = f.read(1 << 20)
        m, d = head.find(b"moov"), head.find(b"mdat")
        return m != -1 and (d == -1 or m < d)
    except OSError:
        return True


# ---------- image checks and fixes ----------


def fit_image(src, dst, ratio, mode, max_w=1080):
    """Fit to the target ratio: 'crop' keeps the centre, 'pad' adds a blurred copy behind it."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, "white")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        icc = im.info.get("icc_profile")
        if icc:
            try:
                from PIL import ImageCms
                import io
                src_prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                im = ImageCms.profileToProfile(im, src_prof, ImageCms.createProfile("sRGB"), outputMode="RGB")
            except Exception:
                pass
        w, h = im.size
        cur = w / h
        if ratio and abs(cur - ratio) > 0.005:
            if mode == "crop":  # never upscale: the crop keeps the source's own pixels
                tw = min(max_w, w if cur <= ratio else round(h * ratio))
            else:               # padding keeps the full width and adds space around the picture
                tw = min(max_w, w)
            th = round(tw / ratio)
            if mode == "crop":
                im = ImageOps.fit(im, (tw, th), Image.LANCZOS, centering=(0.5, 0.45))
            else:
                bg = ImageOps.fit(im, (tw, th), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
                bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.25)
                fg = ImageOps.contain(im, (tw, th), Image.LANCZOS)
                bg.paste(fg, ((tw - fg.width) // 2, (th - fg.height) // 2))
                im = bg
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
        q = 92
        while True:
            im.save(dst, "JPEG", quality=q, optimize=True, progressive=True, subsampling=0 if q >= 90 else 2)
            if os.path.getsize(dst) <= LIMITS["photo_bytes"] or q <= 70:
                break
            q -= 6
    return dst


# ---------- video checks and fixes ----------


def edge_colour(src):
    """The average colour of the video's top and bottom edges, so the plate blends into it."""
    tmp = src + ".edge.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", src, "-frames:v", "1", "-vf", "scale=64:-2", tmp],
                   capture_output=True)
    try:
        with Image.open(tmp) as im:
            im = im.convert("RGB")
            px = [im.getpixel((x, y)) for x in range(im.width) for y in (0, 1, im.height - 2, im.height - 1)]
        os.remove(tmp)
        return "#%02X%02X%02X" % tuple(sum(p[i] for p in px) // len(px) for i in range(3))
    except Exception:
        return "#101010"


def frame_plate(dst_png, title, bg="#0E1726", fg="#FFFFFF", video_h=608, video_y=520):
    """A 1080x1920 background with a headline above where the video will sit (a 'framed' video).
    The headline sits below TikTok's top bar, the video above the caption area at the bottom."""
    from PIL import ImageDraw
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from render_slides import font
    img = Image.new("RGB", (1080, 1920), bg)
    d = ImageDraw.Draw(img)
    if title:
        size = 76
        while size >= 48:
            f = font("sans", size, "Bold")
            words, lines, cur = title.split(), [], ""
            for w in words:
                t = (cur + " " + w).strip()
                if d.textlength(t, font=f) <= 1080 - 2 * 96 or not cur:
                    cur = t
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
            lh = round(size * 1.15)
            if len(lines) <= 3:
                break
            size -= 4
        y = max(300, video_y - 40 - lh * len(lines))
        for ln in lines:
            d.text(((1080 - d.textlength(ln, font=f)) / 2, y), ln, fill=fg, font=f)
            y += lh
    img.save(dst_png)
    return dst_png


def fit_video(src, dst, ratio, mode, frame=None):
    """Re-encode to TikTok's sweet spot: H.264 High, 8-bit, AAC 48 kHz, moov first.
    Keeps the source frame rate when it's within 23 to 60 fps (24 and 25 fps footage stays as it is)."""
    tw = 1080
    th = round(tw / ratio)
    th -= th % 2
    if mode == "frame":
        # landscape video full width on a plate with a headline: no blur, nothing cut off
        plate = dst + ".plate.png"
        info = probe_video(src) or {"w": 1920, "h": 1080}
        vh = round(tw * info["h"] / info["w"]) // 2 * 2
        # headline from y=300 (below the top bar), video under it, all above the caption area (bottom 35%)
        title = (frame or {}).get("title", "")
        lines_guess = 0 if not title else min(3, max(1, len(title) // 22 + 1))
        vy = max(520, 300 + lines_guess * 88 + 40) if vh <= 760 else max(270, (th - vh) // 2)
        vy = min(vy, 1260 - vh) // 2 * 2
        frame_plate(plate, title, (frame or {}).get("bg") or edge_colour(src), video_h=vh, video_y=vy)
        cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", plate, "-i", src, "-filter_complex",
               f"[1:v]scale={tw}:{vh}[v];[0:v][v]overlay=0:{vy}:shortest=1,format=yuv420p",
               "-map", "1:a?", "-r", fps_arg(src), "-c:v", "libx264", "-profile:v", "high", "-preset", "medium",
               "-crf", "19", "-maxrate", "20M", "-bufsize", "40M", "-color_primaries", "bt709", "-color_trc", "bt709",
               "-colorspace", "bt709", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
               "-movflags", "+faststart", dst]
        r = subprocess.run(cmd, capture_output=True, text=True)
        os.remove(plate)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "ffmpeg failed")
        return dst
    if mode == "crop":
        vf = f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}"
    else:
        # blur at a quarter of the size, then scale up: same look, about 10x faster
        sw, sh = (tw // 4) // 2 * 2, (th // 4) // 2 * 2
        vf = (f"split[a][b];[a]scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
              f"boxblur=10:2,eq=brightness=-0.08,scale={tw}:{th}[bg];[b]scale={tw}:{th}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    vf += ",zscale=t=bt709:m=bt709:r=tv,format=yuv420p" if has_zscale() and is_hdr(src) else ",format=yuv420p"
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, "-filter_complex" if mode != "crop" else "-vf", vf,
           "-r", fps_arg(src), "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", "19",
           "-maxrate", "20M", "-bufsize", "40M", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-colorspace", "bt709", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "ffmpeg failed")
    return dst


def fps_arg(src):
    info = probe_video(src) or {}
    f = info.get("fps") or 30
    if info.get("vfr") or not LIMITS["fps_min"] - 0.5 <= f <= LIMITS["fps_max"] + 0.5:
        return "30"
    return f"{f:.3f}".rstrip("0").rstrip(".")


_zs = None


def has_zscale():
    global _zs
    if _zs is None:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        _zs = " zscale " in out
    return _zs


def is_hdr(path):
    info = probe_video(path)
    return bool(info and info["color_transfer"] in ("smpte2084", "arib-std-b67"))


# ---------- caption checks ----------

HASHTAG = re.compile(r"(?<![\w&])#(\w+)", re.UNICODE)
MENTION = re.compile(r"(?<![\w.])@([A-Za-z0-9._]{1,30})")


# ---------- checks ----------

def media_kind(path):
    return "video" if os.path.splitext(path)[1].lower() in VIDEO_EXT else "image"


def check_photo(path, pid, label):
    problems = []
    try:
        with Image.open(path) as im:
            fmt, mode = im.format, im.mode
            w, h = ImageOps.exif_transpose(im).size
    except Exception as e:
        hint = " (install pillow-heif to read iPhone .heic photos)" if path.lower().endswith((".heic", ".heif")) else ""
        report("error", pid, label, f"can't open as an image{hint} ({e})")
        return None, ["unreadable"]
    if fmt not in ("JPEG", "WEBP"):
        problems.append("format")
        report("fix", pid, label, f"{fmt} image: TikTok photo posts take JPEG or WebP only")
    if mode not in ("RGB", "L"):
        problems.append("mode")
        report("fix", pid, label, f"colour mode {mode}: needs RGB (transparency becomes white)")
    ratio = w / h
    if abs(ratio - NINE16) > 0.01:
        problems.append("ratio")
        report("fix", pid, label, f"{w}x{h}: photo posts fill the screen at 9:16; other shapes get bars. Fit to 1080x1920")
    elif w > LIMITS["photo_max_w"]:
        problems.append("big")
        report("fix", pid, label, f"{w}x{h}: larger than TikTok's 1080p photo limit; resize to 1080x1920")
    if w < 720:
        report("warn", pid, label, f"{w} px wide: TikTok shows 1080, so this will look soft")
    if os.path.getsize(path) > LIMITS["photo_bytes"]:
        problems.append("bytes")
        report("fix", pid, label, f"{os.path.getsize(path) / 1e6:.1f} MB: photo posts take at most 20 MB per photo")
    return ratio, problems


def check_video(path, pid, label, max_s, draft=False):
    info = probe_video(path)
    if not info:
        report("error", pid, label, "can't read this video (no video stream)")
        return None, ["unreadable"]
    problems = []
    ratio = info["w"] / info["h"] if info["h"] else 0
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".mp4", ".mov", ".webm"):
        problems.append("container")
        report("fix", pid, label, f"{ext} file: TikTok takes MP4, MOV or WebM")
    if info["vcodec"] not in ("h264", "hevc", "vp8", "vp9"):
        problems.append("codec")
        report("fix", pid, label, f"video codec {info['vcodec']}: TikTok takes H.264 (best), H.265, VP8 or VP9")
    if info["pix_fmt"] not in ("yuv420p", "yuvj420p"):
        problems.append("pix")
        report("fix", pid, label, f"pixel format {info['pix_fmt']} (10-bit or HDR can come out washed out): re-encode to 8-bit")
    if info["color_transfer"] in ("smpte2084", "arib-std-b67"):
        problems.append("hdr")
        report("fix", pid, label, "HDR video: convert to SDR so colours survive TikTok's processing")
    if info["acodec"] and info["acodec"] not in ("aac", "mp3", "opus", "vorbis"):
        problems.append("audio")
        report("fix", pid, label, f"audio codec {info['acodec']}: re-encode to AAC")
    if not info["acodec"] and not draft:  # a silent video sent as an inbox draft gets its sound in the app
        report("warn", pid, label, "no audio track: sounds can't be added through the API. Post it as an inbox draft "
               "(postMode MEDIA_UPLOAD) and add a sound in the app, or add your own audio first")
    if info["fps"] and not LIMITS["fps_min"] - 0.03 <= info["fps"] <= LIMITS["fps_max"] + 0.03:
        problems.append("fps")
        report("fix", pid, label, f"{info['fps']:.2f} fps: TikTok takes 23 to 60; re-encode at 30")
    if info["vfr"]:
        problems.append("vfr")
        report("fix", pid, label, "variable frame rate (phone screen recordings): TikTok can reject it "
               "(frame_rate_check_failed) or drift the audio; re-encode to constant 30 fps")
    if min(info["w"], info["h"]) < LIMITS["video_min_px"] or max(info["w"], info["h"]) > LIMITS["video_max_px"]:
        problems.append("res")
        report("fix", pid, label, f"{info['w']}x{info['h']}: TikTok takes 360 to 4096 px per side; fit to 1080x1920")
    if abs(ratio - NINE16) > 0.01:
        problems.append("ratio")
        report("fix", pid, label, f"{info['w']}x{info['h']}: TikTok fills the screen at 9:16; fit to 1080x1920")
    d = info["duration"]
    if d > max_s:
        report("error", pid, label, f"{d:.0f} s: longer than this account may post ({max_s:.0f} s); trim it")
    if d < 3:
        report("warn", pid, label, f"{d:.1f} s: very short; TikTok documents no minimum, but most players treat under 3 s as broken")
    if info["bytes"] > LIMITS["video_bytes"]:
        report("error", pid, label, f"{info['bytes'] / 1e9:.1f} GB: over TikTok's 4 GB limit")
    if not faststart(path) and not problems:
        report("warn", pid, label, "the 'moov' index is at the end of the file; a --fix re-encode moves it to the front")
    return ratio, problems


HASHTAG = re.compile(r"(?<![\w&])#(\w+)", re.UNICODE)
NUM = re.compile(r"\d[\d.,]*\s?%?")


STOP = set("""the a an and or but of to in on at for with from by is are was were be been it its this that these those
your you our we they their there here what which who how much many most more less than then just only about into over under
de la el los las y o en con por para del al es son que un una lo se su sus como más menos muy""".split())


def file_hash(path):
    import hashlib
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return path
    return h.hexdigest()


def idea_tokens(p, t, base):
    """Numbers and content words a viewer would take away: hook, on-screen beats, caption first line, slide text."""
    texts = [(t.get("caption") or p.get("caption") or "").strip().split("\n")[0], (p.get("hook") or {}).get("text", "")]
    beats = t.get("beats") or p.get("beats") or []
    if isinstance(beats, str):  # a beats.json file, as video.py text takes it
        bp = beats if os.path.isabs(beats) else os.path.join(base, beats)
        try:
            with open(bp, encoding="utf-8") as f:
                beats = json.load(f)
        except (OSError, ValueError):
            beats = []
    if isinstance(beats, dict):
        beats = beats.get("beats", [])
    texts += [b.get("text", "") for b in beats if isinstance(b, dict)]
    spec = t.get("slides") or p.get("slides")
    if spec:
        sp = spec if os.path.isabs(spec) else os.path.join(base, spec)
        try:
            with open(sp, encoding="utf-8") as f:
                texts += [s.get("text", "") + " " + s.get("subtext", "") for s in json.load(f).get("slides", [])]
        except (OSError, ValueError):
            pass
    blob = " ".join(texts).lower()
    nums = {x.strip(" .,") for x in NUM.findall(blob) if any(c.isdigit() for c in x) and len(x.strip(" .,")) > 1}
    # words only from what leads the post (hook, caption first line): a niche account repeats its topic words everywhere
    head = " ".join(texts[:2]).lower()
    words = {w for w in re.findall(r"[a-záéíóúñü]{5,}", head) if w not in STOP}
    return nums, words


def close_in_time(a, b):
    from datetime import datetime
    try:
        return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).days) <= 7
    except ValueError:
        return True  # unscheduled posts in one batch count as close


def check_text(p, t, pid, who):
    fmt = p["format"]
    cap = t.get("caption") or p.get("caption") or ""
    if not cap.strip():
        report("warn", pid, "caption" + who, "empty caption: TikTok search reads the caption; put the main phrase first")
    limit = LIMITS["caption_chars"] if fmt == "video" else LIMITS["description_chars"]
    if len(cap) > limit:
        report("error", pid, "caption" + who, f"{len(cap)} characters: the limit is {limit}")
    tags = HASHTAG.findall(cap)
    if len(tags) > LIMITS["hashtags"]:
        report("error", pid, "caption" + who, f"{len(tags)} hashtags: keep 5 or fewer (TikTok shows a 5-hashtag limit to many accounts)")
    if any(x.lower() in ("fyp", "foryou", "foryoupage", "viral", "xyzbca") for x in tags):
        report("warn", pid, "caption" + who, "#fyp, #viral and the like say nothing about the video; use tags that name the topic")
    first = cap.strip().split("\n")[0]
    if len(first) > LIMITS["fold_chars"]:
        report("warn", pid, "caption" + who, f"first line is {len(first)} characters: TikTok shows about one line over the video; put the hook first")
    if re.search(r"https?://\S+", cap):
        report("warn", pid, "caption" + who, "links in captions aren't clickable on TikTok; say 'link in bio'")
    if "—" in cap or "–" in cap:
        report("warn", pid, "caption" + who, "long dash in the caption: many readers now see it as an AI tell")
    if fmt == "photo":
        title = t.get("title") or p.get("title") or ""
        if title and len(title) > LIMITS["title_chars"]:
            report("error", pid, "title" + who, f"title is {len(title)} characters: the limit is 90")


def check_settings(p, t, pid, acc, who):
    """TikTok's posting-app rules: privacy chosen, from the account's options; disclosure consistent."""
    s = dict(p.get("settings") or {}, **(t.get("settings") or {}))
    priv = s.get("privacy")
    options = acc.get("privacyOptions")
    if not priv and s.get("draft"):
        pass  # inbox drafts: privacy is chosen in the app
    elif priv and s.get("privacy_from") != "user":
        report("error", pid, "privacy" + who, "privacy is filled in but not marked as the user's choice. TikTok requires the user to "
               "pick it: ask them, then set \"privacy_from\": \"user\" next to it")
    elif not priv:
        report("error", pid, "privacy" + who, "no privacy chosen. TikTok requires the user to pick it, with no default: "
               f"ask them ({', '.join(options) if options else 'everyone, friends or only me'})")
    elif priv not in PRIVACY:
        report("error", pid, "privacy" + who, f"privacy '{priv}' is not a TikTok privacy level")
    elif options and priv not in options:
        report("error", pid, "privacy" + who, f"this account can't use {priv}; its options are {', '.join(options)}")
    if s.get("brandedContent") and priv == "SELF_ONLY":
        report("error", pid, "privacy" + who, "branded content (Paid partnership) can't be private on TikTok; pick a public option")
    for k, avail in (("allowComment", "commentAvailable"), ("allowDuet", "duetAvailable"), ("allowStitch", "stitchAvailable")):
        if s.get(k) and acc.get(avail) is False:
            report("error", pid, k + who, f"this account doesn't allow {k[5:].lower()}s; leave it off")
        if p["format"] == "photo" and k != "allowComment" and s.get(k):
            report("warn", pid, k + who, "photo posts only have Allow Comment; duet and stitch are ignored")
    if s.get("aiGenerated") and p["format"] == "photo":
        report("warn", pid, "ai" + who, "WoopSocial sets the AI label on videos only: add 'AI-generated' in the TikTok app for this photo post")
    if s.get("draft"):
        if s.get("autoAddMusic"):
            report("warn", pid, "music" + who, "autoAddMusic is ignored on inbox drafts: the user picks the sound in the app")
        report("warn", pid, "draft" + who, "inbox draft: it lands in the TikTok inbox; the user adds the sound, "
               + ("pastes the caption (video drafts arrive without it), " if p["format"] == "video" else "checks the caption, ")
               + "picks privacy and disclosure, then posts")


def check_media(media, p, pid, who, base, a, max_s):
    fmt = p["format"]
    changed = False
    if not media:
        report("error", pid, "media" + who, "no media files")
        return media, False
    if fmt == "video" and (len(media) != 1 or media_kind(media[0]) != "video"):
        report("error", pid, "media" + who, "a video post takes exactly one video file")
    if fmt == "photo":
        if not 1 <= len(media) <= LIMITS["photos_max"]:
            report("error", pid, "media" + who, f"{len(media)} photos: a photo post takes 1 to 35")
        if any(media_kind(m) == "video" for m in media):
            report("error", pid, "media" + who, "photo posts can't contain video")
    fixed_dir = os.path.join(base, "fixed")
    new_media = []
    all_drafts = bool(p.get("targets")) and all(dict(p.get("settings") or {}, **(t.get("settings") or {})).get("draft")
                                                for t in p["targets"])
    for i, m in enumerate(media):
        path = m if os.path.isabs(m) else os.path.join(base, m)
        label = f"{os.path.basename(m)} #{i + 1}{who}"
        if not os.path.exists(path):
            report("error", pid, label, "file not found")
            new_media.append(m)
            continue
        kind = media_kind(path)
        ratio, probs = (check_video(path, pid, label, max_s, all_drafts) if kind == "video" else check_photo(path, pid, label))
        if a.fix and probs and "unreadable" not in probs:
            loss = 1 - min(ratio, NINE16) / max(ratio, NINE16) if ratio else 0
            mode = a.fit
            if mode == "auto":
                if kind == "video" and loss >= 0.12:
                    if p.get("frame") and p.get("own_footage"):
                        mode = "frame"
                    else:
                        report("error", pid, label, f"this video would lose {loss:.0%} of its width to fill 9:16. Check video.py frames, then: "
                               "reframe it on the subject in an editor; or --fit crop when the subject stays in the middle; or, for your "
                               "own footage, give the post \"frame\": {\"title\": \"...\"} and \"own_footage\": true")
                        new_media.append(m)
                        continue
                else:
                    mode = "crop" if loss < 0.12 else "pad"
            os.makedirs(fixed_dir, exist_ok=True)
            stem = f"{pid}{'-' + who.strip(' ()') if who else ''}-{i + 1:02d}"
            try:
                if kind == "video":
                    out = fit_video(path, os.path.join(fixed_dir, stem + ".mp4"), NINE16, mode, p.get("frame"))
                else:
                    out = fit_image(path, os.path.join(fixed_dir, stem + ".jpg"), NINE16, mode)
                new_media.append(rel(out, base))
                changed = True
                report("fixed", pid, label, f"wrote {rel(out, base)} ({mode})")
                continue
            except Exception as e:
                report("error", pid, label, f"fix failed: {e}")
        new_media.append(m)
    return new_media, changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("plan")
    ap.add_argument("--fix", action="store_true", help="write fixed copies and update the plan")
    ap.add_argument("--fit", choices=["auto", "crop", "pad", "frame"], default="auto",
                    help="how to change the shape: crop the edges, pad with a blurred copy (photos), frame (your own "
                         "landscape video under a headline), or auto")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.plan))
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    posts = plan.get("posts", [])
    if not posts:
        sys.exit("plan.json has no posts")
    accounts = plan.get("accounts", {})
    changed = False
    per_day, drafts, ideas = {}, {}, {}

    for p in posts:
        pid, fmt = p.get("id", "?"), p.get("format")
        if fmt not in ("video", "photo"):
            report("error", pid, "format", f"format '{fmt}': use video or photo")
            continue
        targets = p.get("targets", [])
        if not targets:
            report("warn", pid, "targets", "no accounts yet")
        for t in targets:
            if fmt == "video" and not accounts.get(t.get("account"), {}).get("max_video_s"):
                report("warn", pid, "limits", f"limits for {t.get('account')} not read: assuming 3 minutes. Read them with "
                       "social_accounts_get_platform_inputs and set accounts.<key>.max_video_s")
        max_all = min([accounts.get(t.get("account"), {}).get("max_video_s") or LIMITS["video_max_s"] for t in targets] or [LIMITS["video_max_s"]])
        new, ch = check_media(p.get("media", []), p, pid, "", base, a, max_all)
        if a.fix and ch:
            p["media"], changed = new, True
        for t in targets:
            who = f" ({t.get('account')})"
            acc = accounts.get(t.get("account"), {})
            if t.get("media"):
                new, ch = check_media(t["media"], p, pid, who, base, a, acc.get("max_video_s") or LIMITS["video_max_s"])
                if a.fix and ch:
                    t["media"], changed = new, True
            check_text(p, t, pid, who if len(targets) > 1 else "")
            check_settings(p, t, pid, acc, who if len(targets) > 1 else "")
            day = (t.get("at") or "")[:10]
            if day:
                per_day[(t.get("account"), day)] = per_day.get((t.get("account"), day), 0) + 1
                s = dict(p.get("settings") or {}, **(t.get("settings") or {}))
                if s.get("draft"):
                    drafts[(t.get("account"), day)] = drafts.get((t.get("account"), day), 0) + 1
            ideas.setdefault(t.get("account"), []).append((pid, t.get("at") or "", idea_tokens(p, t, base)))
        if len(targets) > 1:
            sets = [tuple(file_hash(os.path.join(base, m) if not os.path.isabs(m) else m) for m in (t.get("media") or p.get("media", [])))
                    for t in targets]
            if len(set(sets)) < len(sets):
                report("warn", pid, "media", "the same file on several accounts: TikTok keeps unoriginal or reused material out of "
                       "For You. Give each account its own version (targets[].media: another hook, cut, order or language)")
        if fmt == "video" and p.get("source") == "third_party" and not p.get("own_footage") and len(p.get("media", [])) == 1:
            mp = p["media"][0] if os.path.isabs(p["media"][0]) else os.path.join(base, p["media"][0])
            info = probe_video(mp) if os.path.exists(mp) and media_kind(mp) == "video" else None
            if info and info.get("acodec"):
                report("warn", pid, "reuse", "this is one clip you didn't film, with its own audio: TikTok treats that as reused "
                       "material. Add your own voice, or cut several clips into your own sequence with your own text "
                       "(video.py montage + text), and replace the audio")
        if p.get("frame") and not p.get("own_footage"):
            report("warn", pid, "frame", "framing someone else's clip under a headline still reads as reused content. Only for your own "
                   "footage: set \"own_footage\": true")
        if fmt == "video" and not p.get("cover"):
            report("warn", pid, "cover", "no cover: TikTok uses the first frame, which also shows in your profile grid. Pick one with video.py frames/cover")

    for acct, items in ideas.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (p1, a1, (n1, w1)), (p2, a2, (n2, w2)) = items[i], items[j]
                if p1 == p2 or not close_in_time(a1, a2):
                    continue
                shared_n, shared_w = n1 & n2, w1 & w2
                if shared_n or len(shared_w) >= 3:
                    what = ", ".join(sorted(shared_n) + sorted(shared_w)[:4])
                    report("warn", p2, "idea", f"{p1} and {p2} teach the same thing to {acct} within a week ({what}): give each post its own idea")
    for (acct, day), n in per_day.items():
        if n > LIMITS["posts_per_day"]:
            report("error", "schedule", acct, f"{n} posts on {day}: TikTok allows about 15 a day per account through the API")
        elif n > 4:
            report("warn", "schedule", acct, f"{n} posts on {day}: more than a few a day rarely helps and can read as spam")
    for (acct, day), n in drafts.items():
        if n > LIMITS["drafts_per_day"]:
            report("error", "schedule", acct, f"{n} inbox drafts on {day}: TikTok allows 5 waiting drafts per 24 hours")

    if a.fix and changed:
        shutil.copyfile(a.plan, a.plan + ".bak")
        with open(a.plan, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1, ensure_ascii=False)

    order = {"error": 0, "fix": 1, "warn": 2, "fixed": 3}
    issues.sort(key=lambda x: (str(x[1]), order[x[0]]))
    if not issues:
        print("All posts pass.")
    for level, post, item, msg in issues:
        print(f"[{level}] {post} / {item}: {msg}")
    errors = sum(1 for x in issues if x[0] == "error")
    fixes = sum(1 for x in issues if x[0] == "fix") - sum(1 for x in issues if x[0] == "fixed")
    with open(os.path.join(base, "check.json"), "w", encoding="utf-8") as f:
        json.dump([dict(zip(("level", "post", "item", "message"), x)) for x in issues], f, indent=1, ensure_ascii=False)
    if fixes > 0 and not a.fix:
        print(f"\n{fixes} item(s) can be fixed: run again with --fix (originals stay untouched).")
    if errors:
        print(f"\n{errors} error(s) left. Fix them before posting.")
    sys.exit(1 if errors or (fixes > 0 and not a.fix) else 0)


if __name__ == "__main__":
    main()
