from ndirty.infra.diagnostics import report


def test_diagnostics_reports_local_runtime_without_user_image_data() -> None:
    text = report()

    assert "NDirty 0.1.1" in text
    assert "ONNX Runtime" in text
    assert "LaMa 模型" in text
    assert "网络：未使用" in text
