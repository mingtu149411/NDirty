from PIL import Image, ImageDraw

from ndirty.services.smart_selection import grabcut_candidate


def test_grabcut_returns_foreground_mask_for_boxed_object() -> None:
    image = Image.new("RGB", (120, 100), "#1d3557")
    ImageDraw.Draw(image).rectangle((42, 28, 78, 72), fill="#f1faee")

    mask = grabcut_candidate(image, (25, 12, 98, 88))

    assert mask.mode == "L"
    assert mask.size == image.size
    assert mask.getbbox() is not None
    assert mask.getpixel((60, 50)) == 255
