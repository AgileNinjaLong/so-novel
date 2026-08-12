import os
from PIL import Image, ImageDraw, ImageFont

def generate_stealth_icon():
    resources_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")
    os.makedirs(resources_dir, exist_ok=True)
    
    size = (256, 256)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # 绘制外层柔和圆角矩形背景 (深色科技风/摸鱼伪装)
    draw.rounded_rectangle([12, 12, 244, 244], radius=48, fill="#1E1E2E", outline="#313244", width=4)
    
    # 绘制一个书本 / 偷窥鱼的组合造型
    # 1. 摸鱼主体 - 蓝紫渐变色感多边形或椭圆鱼形
    draw.ellipse([50, 70, 206, 176], fill="#89B4FA", outline="#B4BEFE", width=3)
    
    # 2. 鱼尾部分
    draw.polygon([(185, 123), (225, 95), (225, 151)], fill="#89B4FA")
    
    # 3. 摸鱼墨镜 (隐身伪装)
    draw.rounded_rectangle([75, 100, 125, 135], radius=8, fill="#11111B")
    draw.rounded_rectangle([131, 100, 181, 135], radius=8, fill="#11111B")
    draw.line([(125, 115), (131, 115)], fill="#11111B", width=4)
    
    # 墨镜高光反光
    draw.line([(82, 105), (95, 105)], fill="#A6E3A1", width=3)
    draw.line([(138, 105), (151, 105)], fill="#A6E3A1", width=3)
    
    # 4. 底部书本 (摸鱼阅读器元素)
    draw.polygon([(40, 185), (128, 175), (216, 185), (128, 220)], fill="#A6E3A1")
    draw.line([(128, 175), (128, 220)], fill="#94E2D5", width=3)

    png_path = os.path.join(resources_dir, "icon.png")
    ico_path = os.path.join(resources_dir, "icon.ico")
    
    image.save(png_path, format="PNG")
    
    # 保存为 ICO
    image.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"Icon generated successfully:\n- {png_path}\n- {ico_path}")

if __name__ == "__main__":
    generate_stealth_icon()
