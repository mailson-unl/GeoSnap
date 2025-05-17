from PIL import Image, ImageDraw, ImageFont

# Simple script to generate a drone icon in multi-resolution ICO format
# Run: python generate_icon.py

def generate_icon():
    # Define icon sizes
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    # Create base image (largest size)
    base_size = sizes[-1]
    img = Image.new('RGBA', base_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw a circular drone body
    cx, cy = base_size[0] // 2, base_size[1] // 2
    body_radius = base_size[0] * 0.25
    draw.ellipse([cx - body_radius, cy - body_radius, cx + body_radius, cy + body_radius], fill=(0, 122, 255, 255))

    # Draw four propeller circles
    prop_radius = base_size[0] * 0.08
    offsets = [(-body_radius * 1.2, -body_radius * 1.2), (body_radius * 1.2, -body_radius * 1.2),
               (body_radius * 1.2, body_radius * 1.2), (-body_radius * 1.2, body_radius * 1.2)]
    for dx, dy in offsets:
        x, y = cx + dx, cy + dy
        draw.ellipse([x - prop_radius, y - prop_radius, x + prop_radius, y + prop_radius], fill=(255, 255, 255, 255))

    # Draw center hub
    hub_radius = base_size[0] * 0.15
    draw.ellipse([cx - hub_radius, cy - hub_radius, cx + hub_radius, cy + hub_radius], fill=(255, 255, 255, 255))

    # Draw a "D" in the center (optional)
    try:
        font = ImageFont.truetype("arial.ttf", int(base_size[0] * 0.3))
    except IOError:
        font = ImageFont.load_default()
    text = "D"
    text_w, text_h = draw.textsize(text, font=font)
    draw.text((cx - text_w / 2, cy - text_h / 2), text, font=font, fill=(0, 0, 0, 255))

    # Save as multi-resolution ICO
    img.save('drone_icon.ico', format='ICO', sizes=sizes)
    print("Icon generated: drone_icon.ico")

if __name__ == '__main__':
    generate_icon()
