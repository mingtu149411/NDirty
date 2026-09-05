from pathlib import Path

from PIL import Image

from ndirty.domain.project import load_project, save_project


def test_project_round_trip_does_not_embed_source_image(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (12, 10), "blue").save(source)
    mask = Image.new("L", (12, 10), 0)
    mask.putpixel((2, 3), 255)
    project_path = tmp_path / "work.ndirty"

    save_project(project_path, source_path=source, mask=mask)
    project = load_project(project_path)

    assert project.source_path == source.resolve()
    assert project.mask.tobytes() == mask.tobytes()
    assert project_path.stat().st_size < source.stat().st_size + 10_000
