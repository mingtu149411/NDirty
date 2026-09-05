import pytest

from ndirty.domain.viewport import Point, image_to_screen, screen_to_image


def test_viewport_coordinate_round_trip() -> None:
    image_point = Point(120.5, 42.25)
    pan = Point(-15, 32)
    screen_point = image_to_screen(image_point, scale=1.75, pan=pan)
    assert screen_to_image(screen_point, scale=1.75, pan=pan) == image_point


def test_viewport_rejects_non_positive_scale() -> None:
    with pytest.raises(ValueError, match="positive"):
        screen_to_image(Point(1, 1), scale=0, pan=Point(0, 0))
