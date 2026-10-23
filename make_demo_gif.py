"""Render demo/demo.gif from the real logs and report in demo/ (run ledger.py first)."""
from PIL import Image, ImageDraw, ImageFont

W, H, PAD, LH = 980, 640, 22, 20
BG, FG, DIM, ACC, WARN = (24, 26, 33), (222, 226, 232), (130, 138, 150), (120, 200, 140), (240, 190, 90)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 14)


def frame(lines):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for i, (text, color, f) in enumerate(lines[-((H - 2 * PAD) // LH):]):
        d.text((PAD, PAD + i * LH), text[:118], fill=color, font=f)
    return im


run1 = [l for l in open("demo/run1.log").read().splitlines() if l.strip()]
run2 = [l for l in open("demo/run2.log").read().splitlines() if l.strip()]
report = open("demo/report.md").read().splitlines()

frames, durations, screen = [], [], []


def show(ms):
    frames.append(frame(screen))
    durations.append(ms)


cmd = "$ python ledger.py demo/statement.csv"
for i in range(2, len(cmd) + 1, 3):
    screen[:] = [(cmd[:i], FG, bold)]
    show(60)
screen.append((run1[0], DIM, font)); show(1200)
screen.append(("   … Gemma 3 4B labelling merchants on 2 CPU cores (2.5 min, sped up) …", DIM, font)); show(1200)
screen.append((run1[1], ACC, font)); show(900)
screen.append(("", FG, font))
screen.append(("$ cat report.md", FG, bold)); show(700)
import textwrap
wrapped = []
for line in report:
    wrapped += textwrap.wrap(line, 112, subsequent_indent="  ") or [""]
for line in wrapped:
    color = WARN if line.startswith("- ") else (ACC if line.startswith("#") else FG)
    screen.append((line, color, bold if line.startswith("#") else font))
    show(160)
show(4000)
screen[:] = [("# next month: only new merchants go to the model, everything else is cached", DIM, font),
             ("$ python ledger.py demo/statement.csv", FG, bold)]
show(900)
screen.append((run2[0], ACC, font)); show(3500)

frames[0].save("demo/demo.gif", save_all=True, append_images=frames[1:], duration=durations,
               loop=0, optimize=True)
print("demo/demo.gif", len(frames), "frames")
