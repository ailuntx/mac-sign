# Privacy notice / 隐私说明

Effective date / 生效日期: 2026-09-10

Publisher / 发布者: 沈阳霓虹星桥科技工作室（个人独资） / ailuntz

Website: https://www.ailuntz.com

Mac Sign is a local macOS signing plugin. It reads the selected project
configuration, App bundle metadata and code, and the list of valid signing
identities exposed by the macOS security command. It invokes Apple's codesign
tool to use an existing Keychain identity. It does not read or export private
keys, request account passwords, or change Keychain access controls.

Results can contain local project and App paths, bundle identifiers, certificate
names and public fingerprints, Team IDs, code hashes, signature requirements,
and command errors. Certificate names can include an Apple account email;
local paths can include a username. Results and build output returned to your
assistant become part of that AI platform's conversation and are subject to its
data practices. Remove personal information before posting diagnostic results
publicly.

Signing uses a temporary App copy, verifies it, and replaces the selected output
only after verification. Temporary copies and extracted public certificates
are normally removed at completion. The original build output is preserved
when a different output path is selected. Reports are written only when a
report path is requested. A project may save an .ai-sign.json configuration.

The publisher operates no backend, analytics, account database, or remote
signing service for this plugin and does not receive your Apps or signing keys.
The signing script has no publisher network endpoint. Optional project build
commands can access files and networks as defined by that project. macOS,
developer tools, GitHub and the AI platform have their own data practices.

Uninstalling the plugin stops its use. Signed Apps and explicitly saved project
configurations or reports remain under your control. There is no publisher-side
user database to delete.

本插件在本机读取指定项目、App 和公开签名信息，调用系统 codesign 完成签名。
发布者不接收 App 或私钥，不提供远程签名后台。签名结果可能包含本地路径及证书
名称中的账号邮箱；这些结果进入你使用的 AI 对话，适用该平台的数据政策。
可选构建命令的文件与网络访问由项目本身决定。公开反馈前请删除个人信息。

Support: https://github.com/ailuntx/mac-sign/issues. Issues are public; never
post private keys, passwords, certificate exports containing private keys, or
private project files.
