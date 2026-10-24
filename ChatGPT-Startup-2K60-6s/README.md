# ChatGPT 2K60 桌面启动动画

一个可直接运行的 Windows 桌面启动器。启动后播放 6 秒逐笔线稿动画，然后唤起已安装的桌面版 ChatGPT。

## 使用

1. 下载 `ChatGPT-Startup-2K60-6s.exe`。
2. 将它放到桌面或任意文件夹中。
3. 双击运行。
4. 动画播放完成后自动进入 ChatGPT；播放期间按 `Esc` 可立即进入。

启动器为单文件程序，动画已内嵌，不需要额外下载 MP4 或资源文件。

## 画面规格

- 2560 × 1440，16:9
- 60 fps，360 帧，6.00 秒
- H.264 视频，无音轨
- 银白青蓝渐变字体、细描边和青蓝柔光
- 长发与人物主体先成形，随后补齐衣纹、道具和细节线网
- 最后过渡回彩色原画，同时保留新排版、Esc 提示与加载条
- 不显示视频播放控件、时间码或可拖拽进度条

## 仓库内容

- `ChatGPT-Startup-2K60-6s.exe`：Windows 桌面启动器
- `showcase/chatgpt-startup-2k60-6s.mp4`：完整动画成片
- `preview.png`：最终画面预览
- `render_animation.py`：逐帧动画渲染与编码
- `src/ChatGptStartupOptimized.cs`：WPF 桌面启动器
- `build.ps1`：单文件 EXE 构建脚本
- `assets/`：启动器使用的视觉素材

## 本地构建

环境和依赖：

- Windows 10/11
- .NET Framework 4.x
- Python 3.12
- Python 包：`opencv-python`、`numpy`、`Pillow`、`imageio-ffmpeg`

在项目根目录运行：

```powershell
python .\render_animation.py --render
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

预览模式不会打开 ChatGPT：

```powershell
.\ChatGPT-Startup-2K60-6s.exe --preview-test
```

## 说明

- 启动器通过 Windows 应用激活接口唤起本机已安装的 ChatGPT 桌面应用。
- Windows 首次运行未签名程序时可能显示安全提示，请确认文件来源。
- 上传或公开发布前，请确认人物插画及所有视觉素材具有相应使用与分发授权。
