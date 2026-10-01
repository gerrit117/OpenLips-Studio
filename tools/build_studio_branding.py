"""Convert the approved raster artwork into platform icons and compact UI assets."""
from pathlib import Path

from PIL import Image


def build(root=Path(__file__).resolve().parents[1]):
    source = root / 'assets' / 'branding' / 'concept-01'
    output = root / 'studio' / 'assets'
    output.mkdir(parents=True, exist_ok=True)
    with Image.open(source / 'icon-dark.png') as image:
        icon = image.convert('RGBA').resize((1024, 1024), Image.Resampling.LANCZOS)
        icon.resize((256, 256), Image.Resampling.LANCZOS).save(output / 'app-icon.png')
        icon.save(output / 'app-icon.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        icon.save(output / 'app-icon.icns')
    for theme in ('dark', 'light'):
        with Image.open(source / f'logo-{theme}.png') as image:
            image.thumbnail((624, 208), Image.Resampling.LANCZOS)
            image.save(output / f'studio-logo-{theme}.png')
    return output


if __name__ == '__main__':
    print(build())
