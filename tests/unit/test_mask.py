from PIL import Image

from ndirty.domain.mask import MaskEditor


def test_brush_undo_and_redo_only_change_the_masked_area() -> None:
    editor = MaskEditor((32, 32))
    editor.begin_action()
    editor.draw_brush((8, 8), (16, 8), radius=2, value=255)
    assert editor.commit_action()
    edited = editor.mask.copy()
    assert editor.can_undo
    assert editor.undo()
    assert editor.mask.getbbox() is None
    assert editor.redo()
    assert editor.mask.tobytes() == edited.tobytes()


def test_rectangle_polygon_and_clear_are_undoable() -> None:
    editor = MaskEditor((20, 20))
    editor.begin_action()
    editor.fill_rectangle((2, 2), (5, 5), 255)
    assert editor.commit_action()
    editor.begin_action()
    editor.fill_polygon([(10, 10), (16, 10), (13, 16)], 255)
    assert editor.commit_action()
    assert editor.clear()
    assert editor.mask.getbbox() is None
    assert editor.undo()
    assert editor.mask.getbbox() is not None


def test_imported_mask_can_be_undone() -> None:
    editor = MaskEditor((8, 8))
    imported = Image.new("L", (8, 8), 255)
    assert editor.replace_mask(imported)
    assert editor.mask.getpixel((0, 0)) == 255
    assert editor.undo()
    assert editor.mask.getbbox() is None
