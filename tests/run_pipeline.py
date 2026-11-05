#!/usr/bin/env python3
"""End-to-end test of the TikTok skill's scripts on synthetic files (used by CI on Mac, Windows, Linux).

    python3 tests/run_pipeline.py [workdir]
"""
import json, os, shutil, subprocess, sys, tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(ROOT, "skills", "tiktok-skill")
S = os.path.join(SK, "scripts")
PY = sys.executable


def run(*args, ok=(0,)):
    print("$", " ".join(os.path.basename(a) if os.sep in a else a for a in args), flush=True)
    r = subprocess.run([PY, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-3000:], r.stderr[-2000:], sep="")
    if r.returncode not in ok:
        sys.exit(f"FAILED ({r.returncode}): {args[0]}")
    return r


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def main():
    work = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
    os.makedirs(work, exist_ok=True)
    os.chdir(work)
    from PIL import Image
    os.makedirs("in", exist_ok=True)
    Image.new("RGBA", (1200, 1600), (30, 120, 200, 255)).save("in/tall.png")
    ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-f", "lavfi", "-i", "sine=frequency=440",
       "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "in/land.mp4")
    ff("-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=50", "-f", "lavfi", "-i", "sine=frequency=330",
       "-t", "5", "-c:v", "libx264", "-pix_fmt", "yuv444p", "-c:a", "libopus", "in/vert.mkv")

    run(os.path.join(S, "check_setup.py"))
    shutil.copy(os.path.join(SK, "examples", "fresh-water", "slides-en.json"), "slides.json")
    os.makedirs("media", exist_ok=True)
    for m in ("earth.jpg", "nasa-earth.jpg", "nasa-pull.jpg", "nasa-drop.jpg", "nasa-glass.jpg"):
        shutil.copy(os.path.join(SK, "examples", "fresh-water", "media", m), f"media/{m}")
    run(os.path.join(S, "render_slides.py"), "slides.json", "--out", "slides", "--no-instagram")
    slides = sorted(f"slides/tiktok/{f}" for f in os.listdir("slides/tiktok") if f.endswith(".jpg"))
    assert len(slides) == 6, slides
    with Image.open(slides[0]) as im:
        assert im.size == (1080, 1920), im.size

    acc = {"privacyOptions": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"], "max_video_s": 600}
    plan = {
        "timezone": "Europe/Amsterdam",
        "accounts": {"a": dict(acc, handle="@a", socialAccountId="1", timezone="America/New_York", times=["18:30"]),
                     "b": dict(acc, handle="@b", socialAccountId="2", timezone="Europe/Madrid", times=["20:00"], duetAvailable=False)},
        "posts": [
            {"id": "v1", "format": "video", "media": ["in/vert.mkv"], "caption": "Hook #a #b #c #d #e #f #fyp",
             "targets": [{"account": "a", "settings": {"privacy": "PUBLIC_TO_EVERYONE"}}, {"account": "b", "settings": {"allowDuet": True}}]},
            {"id": "v2", "format": "video", "media": ["in/land.mp4"], "caption": "Only 2.5% of water is fresh: a landscape clip",
             "targets": [{"account": "a", "settings": {"privacy": "SELF_ONLY", "privacy_from": "user"}}]},
            {"id": "v3", "format": "video", "media": ["in/vert.mkv"], "caption": "Only 2.5% of water is fresh", "source": "third_party",
             "hook": {"text": "Only 2.5% of water is fresh"},
             "targets": [{"account": "a", "settings": {"privacy": "PUBLIC_TO_EVERYONE"}}]},
            {"id": "p1", "format": "photo", "media": slides[:2] + ["in/tall.png"], "caption": "A photo post",
             "settings": {"privacy": "SELF_ONLY", "brandedContent": True},
             "targets": [{"account": "a"}]},
        ],
    }
    json.dump(plan, open("plan.json", "w"))
    r = run(os.path.join(S, "tt_check.py"), "plan.json", ok=(1,))
    for must in ("7 hashtags", "#fyp", "no privacy chosen", "doesn't allow duets", "MP4, MOV or WebM", "JPEG or WebP",
                 "can't be private", "same file on several accounts", "8-bit", "not marked as the user's choice",
                 "its own audio", "teach the same thing"):
        assert must in r.stdout, f"missing check: {must}"
    r = run(os.path.join(S, "tt_check.py"), "plan.json", "--fix", ok=(1,))
    assert "would lose" in r.stdout, "landscape video must not be cropped or padded automatically"
    p = json.load(open("plan.json"))
    del p["posts"][2]
    p["posts"][0]["caption"] = "Hook line\n#a #b"
    p["posts"][0]["targets"][0]["settings"]["privacy_from"] = "user"
    p["posts"][1]["targets"][0]["settings"]["privacy_from"] = "user"
    p["posts"][0]["targets"][1] = {"account": "b", "media": [p["posts"][0]["media"][0]], "caption": "Otra versión", "settings": {"draft": True}}
    p["posts"][2]["settings"] = {"privacy": "PUBLIC_TO_EVERYONE", "privacy_from": "user", "brandedContent": True, "autoAddMusic": True}
    json.dump(p, open("plan.json", "w"))
    run(os.path.join(S, "tt_check.py"), "plan.json", "--fix", "--fit", "crop", ok=(0,))
    p = json.load(open("plan.json"))
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,pix_fmt",
                          "-of", "csv=p=0", p["posts"][0]["media"][0]], capture_output=True, text=True).stdout
    assert "h264,1080,1920,yuv420p" in out and "aac" in out, out
    with Image.open(p["posts"][2]["media"][2]) as im:
        assert im.format == "JPEG" and im.size == (1080, 1920), im.size

    run(os.path.join(S, "video.py"), "hook", p["posts"][0]["media"][0], "--text", "A hook in TikTok style", "--out", "video/hooked.mp4")
    json.dump({"clips": [{"file": "in/land.mp4", "start": 0, "end": 2, "x": 0.2}, {"file": "in/land.mp4", "start": 3, "end": 5, "x": 0.8}]},
              open("clips.json", "w"))
    run(os.path.join(S, "video.py"), "montage", "clips.json", "--out", "video/montage.mp4")
    json.dump({"beats": [{"start": 0, "end": 2, "text": "First point"}, {"start": 2, "end": 4, "text": "Second point"}]}, open("beats.json", "w"))
    run(os.path.join(S, "video.py"), "text", "video/montage.mp4", "--beats", "beats.json", "--out", "video/texted.mp4")
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration", "-of", "csv=p=0",
                          "video/texted.mp4"], capture_output=True, text=True).stdout
    assert "1080,1920" in out and abs(float(out.split()[-1]) - 4.0) < 0.2, out
    r = run(os.path.join(S, "video.py"), "text", "in/land.mp4", "--beats", "beats.json", "--out", "video/bad.mp4", ok=(1,))
    assert "not 9:16" in r.stdout + r.stderr
    run(os.path.join(S, "video.py"), "frames", "video/hooked.mp4", "--out", "video", "--n", "4")
    run(os.path.join(S, "video.py"), "cover", "video/hooked.mp4", "--at", "1.0", "--out", "video/cover.jpg")
    run(os.path.join(S, "video.py"), "zones", "video/hooked.mp4", "--out", "video/zones.jpg")
    for f in ("video/hooked.mp4", "video/frames-sheet.jpg", "video/cover.jpg", "video/cover-grid.jpg", "video/zones.jpg"):
        assert os.path.getsize(f) > 1000, f
    p["posts"][0]["media"] = ["video/hooked.mp4"]
    p["posts"][0]["cover"] = "video/cover.jpg"
    json.dump(p, open("plan.json", "w"))

    start = (date.today() + timedelta(days=3)).isoformat()
    run(os.path.join(S, "schedule.py"), "plan.json", "--start", start)
    p = json.load(open("plan.json"))
    t = p["posts"][0]["targets"]
    assert t[0]["at"].endswith("18:30") and t[1]["at"].endswith("20:00"), t
    a = json.load(open("requests/v1-a.json"))["socialAccounts"][0]
    assert a["platform"] == "TIKTOK" and a["postType"] == "VIDEO" and a["postMode"] == "DIRECT_POST" and a["privacyLevel"] == "PUBLIC_TO_EVERYONE"
    assert a["allowDuet"] is False and "cover" in a
    b = json.load(open("requests/v1-b.json"))["socialAccounts"][0]
    assert b["postMode"] == "MEDIA_UPLOAD" and "privacyLevel" not in b and "autoAddMusic" not in b, b
    bt = json.load(open("requests/v1-b.json"))["schedule"]["scheduledFor"]
    at = json.load(open("requests/v1-a.json"))["schedule"]["scheduledFor"]
    assert bt and at, (bt, at)
    assert "Inbox drafts to finish" in open("schedule.md", encoding="utf-8").read()
    ph = json.load(open("requests/p1-a.json"))["socialAccounts"][0]
    assert ph["postType"] == "PHOTO" and ph["isBrandedContent"] is True and ph["autoAddMusic"] is True and "isAiGeneratedContent" not in ph

    run(os.path.join(S, "preview.py"), "plan.json", "--out", "preview")
    html = open("preview/index.html", encoding="utf-8").read()
    assert "Music Usage Confirmation" in html and "Branded Content Policy" in html and "Inbox draft" in html
    assert os.path.getsize("preview/preview.png") > 10000

    # results: 6 photo posts posted 9 to 19 days ago, numbers collected over time
    now = datetime.now(timezone.utc)
    hist = []
    for n in range(6):
        at = (now - timedelta(days=9 + 2 * n)).replace(tzinfo=None).isoformat(timespec="minutes")
        hist.append({"id": f"h{n}", "format": "photo", "media": slides[:1], "caption": f"Post {n}",
                     "targets": [{"account": "a", "at": at, "postId": f"w{n}"}]})
    p["posts"] = hist
    json.dump(p, open("plan.json", "w"))
    run(os.path.join(S, "log.py"), "record", "plan.json")
    items = []
    for n, post in enumerate(hist):
        posted = datetime.fromisoformat(post["targets"][0]["at"]).replace(tzinfo=timezone.utc)
        ser = lambda base: [{"value": base // 3, "collectedAt": (posted + timedelta(days=1)).isoformat()},
                            {"value": base, "collectedAt": (posted + timedelta(days=7)).isoformat()}]
        items.append({"postId": f"w{n}", "socialAccountId": "1",
                      "analytics": {"views": ser(2000 + 100 * n), "shares": ser(10 + 4 * n), "saves": ser(30 - n)}})
    json.dump({"socialAccountPosts": items}, open("metrics.json", "w"))
    r = run(os.path.join(S, "log.py"), "results", "--metrics", "metrics.json")
    assert "6 ranked of 6" in r.stdout and "Best photo" in r.stdout and "| Views (x median) |" in r.stdout, r.stdout
    print("\nALL PIPELINE CHECKS PASSED")


if __name__ == "__main__":
    main()
