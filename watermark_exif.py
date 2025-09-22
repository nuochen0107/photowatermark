#!/usr/bin/env python3
"""
watermark_exif.py
CLI: 从图片 EXIF 读取拍摄日期（年月日），将 YYYY-MM-DD 作为文字水印绘制到图片上并另存到 <原目录>/<原目录名>_watermark/
依赖: Pillow, piexif
"""

import os
import sys
import argparse
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageColor
import piexif

ALLOWED_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.tiff', '.bmp'}


def get_exif_date(path):
    """尝试从 EXIF 中读 DateTimeOriginal -> DateTimeDigitized -> DateTime，返回 YYYY-MM-DD 或 None"""
    try:
        exif_dict = piexif.load(path)
    except Exception:
        return None

    candidates = [
        ('Exif', piexif.ExifIFD.DateTimeOriginal),
        ('Exif', piexif.ExifIFD.DateTimeDigitized),
        ('0th', piexif.ImageIFD.DateTime),
    ]
    for ifd_name, tag in candidates:
        try:
            value = exif_dict.get(ifd_name, {}).get(tag)
            if value:
                if isinstance(value, bytes):
                    s = value.decode('utf-8', errors='ignore')
                else:
                    s = str(value)
                # EXIF 时间通常是 "YYYY:MM:DD HH:MM:SS"
                try:
                    dt = datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
                    return dt.strftime("%Y-%m-%d")
                except Exception:
                    # 尝试把前两个 ":" 替换为 "-"（保守处理）
                    try:
                        s2 = s.replace(":", "-", 2)
                        dt = datetime.strptime(s2, "%Y-%m-%d %H:%M:%S")
                        return dt.strftime("%Y-%m-%d")
                    except Exception:
                        continue
        except Exception:
            continue
    return None


def fallback_file_date(path):
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def parse_color_to_rgba(color_str):
    """返回 (r,g,b,a) 四元组。user 可传 '#RRGGBB'/'RRGGBB' 或 color name"""
    try:
        rgb = ImageColor.getrgb(color_str)
        if len(rgb) == 3:
            return (rgb[0], rgb[1], rgb[2], 255)
        elif len(rgb) == 4:
            return rgb
    except Exception:
        pass
    # 默认白色
    return (255, 255, 255, 255)


def compute_position(position_name, image_size, text_size, margin):
    W, H = image_size
    w, h = text_size
    pos = position_name.lower()
    if pos == 'top-left':
        return (margin, margin)
    if pos == 'top-right':
        return (W - w - margin, margin)
    if pos == 'bottom-left':
        return (margin, H - h - margin)
    if pos == 'bottom-right':
        return (W - w - margin, H - h - margin)
    if pos == 'center':
        return ((W - w) // 2, (H - h) // 2)
    if pos == 'top-center':
        return ((W - w) // 2, margin)
    if pos == 'bottom-center':
        return ((W - w) // 2, H - h - margin)
    # default
    return (margin, margin)


def draw_text_on_image(img, text, font, color_rgba, position, margin=10, outline=True):
    """返回处理后的 Image 对象（RGBA 或 RGB，根据原图处理）"""
    # ensure RGBA for compositing
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x, y = compute_position(position, base.size, (text_w, text_h), margin)

    # optional outline for readability
    if outline:
        outline_color = (0, 0, 0, 200)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)

    draw.text((x, y), text, font=font, fill=color_rgba)

    result = Image.alpha_composite(base, overlay)
    return result


def ensure_font(font_path, size):
    """尝试使用用户字体或系统常见字体；失败则 load_default"""
    try:
        if font_path:
            return ImageFont.truetype(font_path, size)
        # try common PIL bundled font
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        try:
            return ImageFont.load_default()
        except Exception:
            raise RuntimeError("无法加载字体，请传入 --font 字体文件。")


def process_single_file(path, out_dir, args):
    try:
        date_text = get_exif_date(path) or fallback_file_date(path)
        text = date_text
        img = Image.open(path)
        font = ensure_font(args.font, args.font_size)
        rgba = parse_color_to_rgba(args.color)
        result_img = draw_text_on_image(img, text, font, rgba, args.position, margin=args.margin, outline=args.outline)
        # convert if saving as jpeg
        ext = os.path.splitext(path)[1].lower()
        out_path = os.path.join(out_dir, os.path.basename(path))
        if result_img.mode == 'RGBA' and ext in ('.jpg', '.jpeg'):
            result_img = result_img.convert('RGB')
        result_img.save(out_path)
        print(f"[OK] {path} -> {out_path}")
    except Exception as e:
        print(f"[ERR] 处理 {path} 失败: {e}")


def main():
    p = argparse.ArgumentParser(description="将图片 EXIF 拍摄日期（YYYY-MM-DD）绘制为水印并保存到 <原目录>_watermark 子目录")
    p.add_argument("path", help="图片文件路径或目录路径")
    p.add_argument("--font-size", type=int, default=36, help="字体大小 (默认 36)")
    p.add_argument("--color", default="#FFFFFF", help="文字颜色，支持 #RRGGBB 或 color name (默认 白)")
    p.add_argument("--position", default="bottom-right", choices=['top-left', 'top-right', 'bottom-left', 'bottom-right', 'center', 'top-center', 'bottom-center'])
    p.add_argument("--font", default=None, help="可选：字体文件路径 (ttf)")
    p.add_argument("--margin", type=int, default=10, help="到边缘的边距（像素）")
    p.add_argument("--outline", action="store_true", help="是否添加黑色描边以提升可读性")
    args = p.parse_args()

    input_path = os.path.abspath(args.path)
    if not os.path.exists(input_path):
        print("路径不存在：", input_path)
        sys.exit(1)

    # 计算输出目录：作为原目录的子目录，名字为 <原目录名>_watermark
    if os.path.isdir(input_path):
        base_dir = input_path
        base_name = os.path.basename(os.path.normpath(input_path)) or "root"
        out_dir = os.path.join(base_dir, f"{base_name}_watermark")
        os.makedirs(out_dir, exist_ok=True)
        # 遍历目录文件
        items = sorted(os.listdir(base_dir))
        for name in items:
            full = os.path.join(base_dir, name)
            ext = os.path.splitext(name)[1].lower()
            if os.path.isfile(full) and ext in ALLOWED_EXTS:
                process_single_file(full, out_dir, args)
        print("全部处理完成，输出目录:", out_dir)
    else:
        # 单文件处理
        file_path = input_path
        parent = os.path.dirname(file_path) or os.getcwd()
        parent_name = os.path.basename(os.path.normpath(parent)) or "root"
        out_dir = os.path.join(parent, f"{parent_name}_watermark")
        os.makedirs(out_dir, exist_ok=True)
        process_single_file(file_path, out_dir, args)
        print("处理完成，输出目录:", out_dir)


if __name__ == "__main__":
    main()
