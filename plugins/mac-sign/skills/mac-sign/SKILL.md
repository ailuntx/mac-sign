---
name: mac-sign
description: Automatically sign local macOS apps with an existing Apple development identity, using the current project or a specified project/App/output path. Use for automatic signing, replacing ad-hoc signatures, or rebuilding a user's own app configured with .ai-sign.json. Requires a local Mac terminal.
---

# macOS 自动签名

直接运行本技能目录下的 `scripts/mac_sign.py`；由代理完成命令调用，不让用户复制项目构建脚本。项目默认是当前任务目录，不是插件目录。插件不自带证书或个人路径。

## 使用

先执行 `python3 <skill-dir>/scripts/mac_sign.py inspect --project <project>`，读取候选 App、现有身份和项目配置。已有用户授权的签名/重建请求直接执行；不要重复索要确认。

```sh
# 指定项目；不传 --project 则使用命令当前目录
python3 <skill-dir>/scripts/mac_sign.py sign --project /path/to/project
# 指定产物及签名后的安装位置
python3 <skill-dir>/scripts/mac_sign.py sign --project /path/to/project \
  --app dist/Example.app --output ~/Applications/Example.app
# 重建并签名，使用已检查过的项目配置
python3 <skill-dir>/scripts/mac_sign.py sign --project /path/to/project --build
```

路径以项目为基准，`--report` 以命令当前目录为基准。多个候选不按修改时间猜测：结合项目说明确定目标；仍无法确定时简短询问。没有产物时，读取项目构建说明和脚本，先构建完整 App。需要运行、安装或重建时，按用户任务完成；仅签名请求不默认启动 App。使用 `--output` 可保留原构建产物，将签名后的 App 放到指定位置。

常用项目可写 `.ai-sign.json`，仅保存需要的字段，不创建全局项目注册表：

```json
{
  "app": "dist/Example.app",
  "bundle_id": "com.example.Example",
  "build": ["./script/build_and_run.sh", "--build"],
  "output": "~/Applications/Example.app"
}
```

配置是项目代码：首次执行 `build` 前读取命令和其调用脚本；选择只构建、不提前结束运行中 App 的入口。`build` 是 argv 数组，不解析 shell 字符串。脚本不猜测并执行项目命令。`--build` 只在需要重建时使用，默认仅签已有产物。日后同一任务修改源码并重建该 App 后，重新执行签名，避免最终又留下临时签名产物。

默认优先复用 App 原证书；否则选择唯一有效的 `Apple Development` 身份。多个证书时用 `identities` 列出名称和指纹，结合已有项目配置选择；不能确定再询问。`--identity` 或配置 `identity` 接受完整名称/指纹，不接受 ad-hoc `-`。私钥始终留在系统钥匙串，由 `codesign` 使用。

## 结果与边界

- 临时副本从内到外签名，保留原有 entitlements、运行标志和约束，整包严格校验成功后才替换目标；失败不会发布半签名 App。原地签名运行中的 App 后，旧进程不会自动更新；如任务包含运行测试，使用已知路径重启该 App 并检查进程/UI。
- 检查 JSON 的 `strict_verification`、`identity`、`signature` 和 `previous_requirement_verified`。后者只有确实使用同证书且旧身份要求校验成功时才为 true；首次从 ad-hoc 转换为 false 是正常结果。
- 每个软件保留自身唯一的 Bundle ID，不为了省弹窗共用其他 App 的 ID。配置中的 `bundle_id` 用于校验，脚本不改 Info.plist。
- 签名失败时报告具体错误。若钥匙串要求用户交互，提示用户处理系统提示；不要改私钥 ACL、导出私钥或自动操作受保护授权窗口。现有钥匙串授权可用时直接完成，无需用户去终端执行。
- 这是本机开发签名，不代替公证或分发证书，也不代替首次隐私授权。跨重建身份验证与 TCC 授权保留分开报告，不能把前者当作后者实测。

[Apple 代码签名说明](https://developer.apple.com/library/archive/technotes/tn2206/)；嵌套代码显式从内到外签名，`--deep` 仅用于验证。
