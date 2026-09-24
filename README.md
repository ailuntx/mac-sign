# Mac Sign

给本机 macOS 项目自动签名的 Codex 插件。支持当前项目、指定项目、指定 `.app` 和输出位置，复用系统钥匙串里的开发证书。无需 Python 第三方依赖。

Mac Sign 0.2.0 已完成本机验证，并上传到[原插件目录条目](https://chatgpt.com/plugins/plugins_6aa2994c60f08191ad89867e0ea1546a)作为新版本草稿；公开版须通过平台扫描、审核和发布。平台要求同一条目的内部标识保持 `ai-mac-sign`，因此目录包使用该兼容标识；本地插件源码和安装标识为 `mac-sign`。两种包的技能与签名脚本相同。

[隐私说明](docs/privacy.md) · [使用条款](docs/terms.md) · [支持与反馈](https://github.com/ailuntx/mac-sign/issues)

安装后直接说：

- “给当前项目自动签名。”
- “重建并签名 cap，放到我的 Applications。”
- “把这个 App 签名到指定位置，检查是否仍满足旧版本签名身份。”

代理负责识别产物、选择已有证书、调用脚本并验证结果。常用项目以 `.ai-sign.json` 保存产物路径和构建命令；不必再让用户复制各项目的构建命令。首次缺少证书或钥匙串需要授权时仍需用户完成系统要求。

源码位于 `plugins/mac-sign`，技能入口是 [mac-sign](plugins/mac-sign/skills/mac-sign/SKILL.md)。支持 Python 3.9+ 和 macOS 14+。自动选择 Apple Development；也可明确指定其他有效代码签名证书。适用于能访问本地 Mac 终端的 Codex，不是网页 ChatGPT 中直接运行的远程签名服务。

已在 cap 和 minibridge 完成发现产物、首次签名、配置驱动重建、安装版签名身份连续性验证，详见 [实测记录](docs/validation.md)。个人市场安装后，新开对话即可加载技能。

执行流程：检查身份 → 可选构建 → 复制 App → 从内到外签名 → 校验身份与整包完整性 → 替换输出。输出 JSON 可通过 `--report` 留存。签名不改变 Bundle ID，也不会自动启动 App、修改钥匙串访问控制、导出私钥或修改系统隐私数据库。

只有目标路径的签名替换具有失败保留原文件的保证；项目构建命令自身的副作用由项目负责。签名保留旧的权限声明，并不为新 App 自动授予权限，也不承诺公证或公开分发。[Apple 签名说明](https://developer.apple.com/library/archive/technotes/tn2206/)

```sh
python3 -m unittest discover -s tests -v
python3 scripts/package.py
```
