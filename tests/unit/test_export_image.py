from pathlib import Path

from PIL import Image

from ndirty.services.export_image import export_image


def test_export_writes_a_new_png_without_touching_source(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    image = Image.new("RGB", (8, 8), "green")
    image.save(source)
    before = source.read_bytes()
    output = tmp_path / "source_ndirty.png"

    export_image(image, output)

    assert output.is_file()
    assert source.read_bytes() == before
