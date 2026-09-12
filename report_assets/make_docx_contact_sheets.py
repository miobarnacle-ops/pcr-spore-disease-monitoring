from pathlib import Path
import sys
from PIL import Image, ImageDraw


qa_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent / 'docx_qa'
pages = sorted(qa_dir.glob('page-*.png'), key=lambda p: int(p.stem.split('-')[-1]))

for group_start in range(0, len(pages), 6):
    group = pages[group_start:group_start + 6]
    thumb_w = 340
    thumb_h = 440
    sheet = Image.new('RGB', (thumb_w * 3, (thumb_h + 32) * 2), 'white')
    draw = ImageDraw.Draw(sheet)
    for index, page in enumerate(group):
        image = Image.open(page).convert('RGB')
        image.thumbnail((thumb_w - 12, thumb_h - 12))
        x = (index % 3) * thumb_w + (thumb_w - image.width) // 2
        y = (index // 3) * (thumb_h + 32) + 28
        sheet.paste(image, (x, y))
        draw.text(((index % 3) * thumb_w + 10, (index // 3) * (thumb_h + 32) + 6), f'第 {group_start + index + 1} 页', fill='black')
    sheet.save(qa_dir / f'contact-{group_start // 6 + 1}.png')
