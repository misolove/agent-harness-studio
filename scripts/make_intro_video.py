from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "video_frames"
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1280, 720
FPS = 30
DURATION = 12
TOTAL = FPS * DURATION

try:
    title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 64)
    sub_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
    small_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)
    mono_font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22)
except Exception:
    title_font = sub_font = small_font = mono_font = ImageFont.load_default()

components = [
    ("Memory", (110, 450), "#4CFF88"),
    ("Skills", (305, 450), "#58A6FF"),
    ("Hooks", (500, 450), "#D29922"),
    ("MCP", (695, 450), "#FF7B72"),
    ("Context", (890, 450), "#A371F7"),
]

def ease(x):
    return 1 - (1 - x) ** 3

def draw_center(draw, pos, text, font, fill):
    bbox = draw.textbbox((0,0), text, font=font)
    draw.text((pos[0] - (bbox[2]-bbox[0])/2, pos[1] - (bbox[3]-bbox[1])/2), text, font=font, fill=fill)

def rounded(draw, xy, r, fill, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)

for i in range(TOTAL):
    t = i / FPS
    img = Image.new("RGB", (W, H), "#0A0A1A")
    draw = ImageDraw.Draw(img)

    # grid
    for x in range(0, W, 40):
        draw.line((x, 0, x, H), fill="#111128")
    for y in range(0, H, 40):
        draw.line((0, y, W, y), fill="#111128")

    # animated glow
    pulse = int(60 + 40 * math.sin(t * 2))
    draw.ellipse((420-pulse, 120-pulse, 860+pulse, 560+pulse), fill="#101035")

    # title
    fade = min(1, t / 1.5)
    draw_center(draw, (W/2, 90), "Agent Harness Studio", title_font, "#E0E0F0")
    draw_center(draw, (W/2, 145), "Harness over Model", sub_font, "#7B5CFF")

    # central box
    yoff = int((1 - ease(min(1, max(0, t - 1) / 1.2))) * 60)
    rounded(draw, (440, 210 + yoff, 840, 360 + yoff), 18, "#12122A", "#7B5CFF", 3)
    draw_center(draw, (640, 260 + yoff), "Control Tower", sub_font, "#FFFFFF")
    draw_center(draw, (640, 310 + yoff), "Scan • Mold • Validate • Apply", small_font, "#8888BB")

    # components appear
    for idx, (name, (x, y), color) in enumerate(components):
        start = 2.3 + idx * 0.35
        prog = ease(min(1, max(0, (t - start) / 0.8)))
        yy = y + int((1 - prog) * 50)
        alpha_color = color if prog > 0.1 else "#222244"
        rounded(draw, (x, yy, x+170, yy+80), 14, "#12122A", alpha_color, 2)
        draw_center(draw, (x+85, yy+32), name, small_font, "#E0E0F0")
        draw_center(draw, (x+85, yy+58), "detected", mono_font, "#8888BB")
        if prog > 0.5:
            draw.line((x+85, yy, 640, 360+yoff), fill=color, width=2)

    # Chat Molder panel later
    if t > 6:
        prog = ease(min(1, (t-6)/1.2))
        x0 = int(W - 480 * prog)
        rounded(draw, (x0, 90, x0+430, 260), 16, "#0E0E24", "#2A2A5A", 2)
        draw.text((x0+30, 120), "Chat Molder", font=sub_font, fill="#58A6FF")
        draw.text((x0+30, 170), "> create a weather-check skill", font=mono_font, fill="#C8D3F5")
        draw.text((x0+30, 210), "diff ready • sandbox safe", font=small_font, fill="#4CFF88")

    # closing URL
    if t > 9:
        prog = min(1, (t-9)/1.0)
        draw_center(draw, (W/2, 650), "github.com/misolove/agent-harness-studio", mono_font, "#58A6FF")

    img.save(OUT / f"frame_{i:04d}.png")

print(OUT)
