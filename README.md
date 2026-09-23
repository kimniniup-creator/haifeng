# 海风

把今天的一小片，带回来。

海风是一个本机运行的照片回顾应用：放一张照片、写一句话，Reachy 围绕照片回应，再把这个片段留下来。第一版输入为文字；图片可上传，也可通过电脑附近的 Luma 兼容眼镜主动拍摄。

**当前状态：软件首版可运行，完整硬件验收尚未完成。** 真实视觉模型已验证；音频已送达 Reachy USB 输出设备，现场可闻性待确认。当前机器人电机未检测到，眼镜未被本机扫描发现。详见 [验收记录](docs/ACCEPTANCE.md)。

## 在这台电脑打开

双击 `D:\海风\start.cmd`，或运行：

```powershell
Set-Location D:\海风
.\start.ps1
```

浏览器访问 http://127.0.0.1:8088 。页面设置里可更换实际模型服务。页面中的“新的片段”新建记录，照片和对话自动保存在本机；可命名、回看、删除。停止会取消当前任务。

## 从 GitHub 恢复

需要 Windows、Python 3.12（推荐 uv）、Git。克隆本仓库到新的空目录，运行 `start.ps1` 会创建桥接环境并安装固定的直接依赖。Python BLE 路径不要求 Rust 或初始化上游子模块。

```powershell
git clone https://github.com/kimniniup-creator/haifeng.git
Set-Location haifeng
.\start.ps1
```

首次在页面设置里填写支持图像的 OpenAI-compatible 模型地址、模型名和密钥。本机首次启动自动生成随机连接令牌，仅回环地址页面可领取；模型密钥不会返回浏览器。

运行 `start_robot.ps1` 安装/启动独立的 Reachy SDK 1.11.0 环境。机器人须连接独立电源和 USB；不要同时启动另一份桌面程序的 Daemon。脚本不会自动唤醒头部，应用只请求小幅触角动作。

## 配置与隐私

可参考 `.env.example` 建立本机 `.env`。`LUMA_MODE=python` 使用 Bleak，`LUMA_DEVICE` 可填设备广播名称或地址；不填写时仅在唯一候选设备存在时连接。`TTS_ENABLED=true` 使用 Windows 本地中文语音合成，输出明确绑定 Reachy 音频设备；失败不会静默改用电脑扬声器。

页面设置更改的模型配置保存在 `data/settings.json`，优先于旧环境配置。图片和对话保留在 `data/`，直到主动删除片段。发送文字/图片时内容会交给配置的模型服务；本地存储不代表离线推理。不要提交 `.env`、`data/` 或运行日志。

默认只监听本机。手机响应式布局已测试；手机实体局域网访问尚未验收。不要把 Reachy 8000 控制端口暴露公网。本版不是多用户云服务。

## 开发与验证

```powershell
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m bridge.luma_ble scan
```

19 项自动测试包含 20 轮模拟队列测试；模拟不代表硬件联调成功。运行日志在 `.runtime/`。用户界面在 `bridge/static/`，桥接服务为 FastAPI/SQLite。

## 项目依据

继承 [timesbye/Robot_glasses](https://github.com/timesbye/Robot_glasses) V2（E06兼容修复），保留上游 Git 历史和 Rust 可选构建路径。上游记录的 E06/S3 拍照成功属于另一环境，本机不沿用其验收结论。Python协议后备实现依据固定的 [luma-core](https://github.com/metastable-lab/luma-core) MIT 源码；Reachy接口按本机1.11.0 OpenAPI检查。

- [产品方向与取舍](docs/PRODUCT.md)
- [验收与真实限制](docs/ACCEPTANCE.md)
- [工作日志](WORKLOG.md)
- [接手说明](HANDOFF.md)
