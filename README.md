# NDirty

项目创建者：**南京大学智能化软件专业241880428沈逸文**  
版本：0.1.1

NDirty 是 Windows 离线图像遮挡补全软件。用户导入图片并绘制蒙版，软件使用本地修补模型生成与周边一致的内容；不会上传图片，也不承诺恢复被遮挡区域的真实原始像素。

默认使用流程：**导入图片 → 标记遮挡区域 → 补全图像 → 导出结果**。项目保存、蒙版导入/导出和智能候选区均为辅助功能，不是完成一次补全的必经步骤。

## 直接下载运行（推荐）

Windows x64 用户可从 [v0.1.1 发布页](https://github.com/mingtu149411/NDirty/releases/tag/v0.1.1) 下载 `NDirty-0.1.1-windows-x64.zip`。解压后直接运行 `NDirty\\NDirty.exe`；该离线包已经包含模型和运行时，不需要安装 Python，也不需要联网下载模型。

## 从源码运行

仓库包含运行必需的 LaMa 与 OCR ONNX 模型，但不包含 Python 虚拟环境、构建缓存或 Windows `dist` 输出。请在 Windows x64 上安装 Python 3.11–3.13，并在项目根目录执行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,build]"
python -m pytest -q
python -m ndirty
```

启动后：点击“导入图片”，用画笔、矩形或套索标记红色补全区域，点击左侧“补全图像”，检查结果后点击“导出结果”。结果导出到新文件，程序会拒绝覆盖输入原图。

## 构建 Windows 便携版

```powershell
.\scripts\build_release.ps1
.\scripts\check_size.ps1 -ProjectRoot .\dist\NDirty
```

构建结果为 `dist/NDirty/NDirty.exe`。该便携版包含模型与运行时，最终用户不需要安装 Python、pip 或联网下载模型。

## 文档

- [用户指南](docs/用户指南.md)
- [P5 离线验收矩阵](docs/P5离线验收矩阵.md)
- [P6 发布验收](docs/P6发布验收.md)
- [第三方组件与模型清单](第三方清单.md)
- [创建者与版权声明](AUTHORS.md)

## 合规与隐私

请只处理您拥有权利或已获得授权的图像。软件设计为本地离线运行，原图默认只读，导出结果必须另存。

公开发布前请阅读 `THIRD_PARTY_NOTICES.md`：PP-OCR 权重版权归 Baidu，需由发布者确认其预期分发场景的上游授权条款。项目源码的创建者和版权声明见 `AUTHORS.md`。
