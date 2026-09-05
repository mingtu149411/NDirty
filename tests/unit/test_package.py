import ndirty


def test_package_exposes_version() -> None:
    assert ndirty.__version__ == "0.1.0"
