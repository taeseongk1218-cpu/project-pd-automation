"""
인스타그램에 올릴 '제목 텍스트 카드' 이미지를 만드는 공용 모듈.
쓰레드는 텍스트만으로 게시할 수 있지만 인스타그램은 반드시 이미지가 있어야 하므로,
글 제목을 넣은 심플한 카드 이미지를 자동으로 만든다. 별도 이미지 소재가 필요 없다.
"""
import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

# Ubuntu(GitHub Actions) 기준 설치 경로. 워크플로우에서 `apt-get install -y fonts-noto-cjk`로 설치한다.
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]

BG_COLOR = (255, 247, 235)
ACCENT_COLOR = (255, 138, 101)
TEXT_COLOR = (51, 51, 51)
SIZE = (1080, 1080)
BRAND_TEXT = "500md87.com"


def _find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def make_title_card(title: str, out_path: str) -> None:
    img = Image.new("RGB", SIZE, BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, SIZE[0], 28], fill=ACCENT_COLOR)
    draw.rectangle([0, SIZE[1] - 28, SIZE[0], SIZE[1]], fill=ACCENT_COLOR)

    font_path = _find_font()
    title_font = ImageFont.truetype(font_path, 64, index=0) if font_path else ImageFont.load_default()
    brand_font = ImageFont.truetype(font_path, 34, index=0) if font_path else ImageFont.load_default()

    wrapped = textwrap.fill(title, width=13)
    lines = wrapped.split("\n")
    line_height = 84
    total_h = line_height * len(lines)
    y = (SIZE[1] - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        w = bbox[2] - bbox[0]
        x = (SIZE[0] - w) // 2
        draw.text((x, y), line, font=title_font, fill=TEXT_COLOR)
        y += line_height

    bbox = draw.textbbox((0, 0), BRAND_TEXT, font=brand_font)
    w = bbox[2] - bbox[0]
    draw.text(((SIZE[0] - w) // 2, SIZE[1] - 100), BRAND_TEXT, font=brand_font, fill=ACCENT_COLOR)

    img.save(out_path, "PNG")
