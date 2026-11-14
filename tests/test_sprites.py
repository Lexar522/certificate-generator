from PIL import Image

from renderers.pillow_renderer import LayerSprite, _apply_opacity, _apply_rotation, composite_at


def test_rotation_keeps_sprite_center():
    sprite = LayerSprite(Image.new("RGBA", (100, 20), (255, 0, 0, 255)), 50, 40)
    rotated = _apply_rotation(sprite, 90)

    assert rotated.image.size == (20, 100)
    assert (rotated.x + rotated.image.width / 2, rotated.y + rotated.image.height / 2) == (100, 50)


def test_opacity_scales_alpha_without_mutating_source():
    source = Image.new("RGBA", (4, 4), (0, 0, 0, 200))
    faded = _apply_opacity(LayerSprite(source, 0, 0), 0.5)

    assert faded.image.getpixel((0, 0))[3] == 100
    assert source.getpixel((0, 0))[3] == 200


def test_composite_clips_sprite_outside_canvas():
    canvas = Image.new("RGBA", (10, 10), (255, 255, 255, 255))
    sprite = LayerSprite(Image.new("RGBA", (6, 6), (0, 0, 255, 255)), -3, 7)

    result = composite_at(canvas, sprite)

    assert result.getpixel((0, 9)) == (0, 0, 255, 255)
    assert result.getpixel((3, 9)) == (255, 255, 255, 255)
    assert canvas.getpixel((0, 9)) == (255, 255, 255, 255)


def test_composite_ignores_fully_offscreen_sprite():
    canvas = Image.new("RGBA", (10, 10))
    sprite = LayerSprite(Image.new("RGBA", (5, 5), (255, 0, 0, 255)), 50, 50)
    assert composite_at(canvas, sprite) is canvas
