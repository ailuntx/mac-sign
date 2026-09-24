# Reviewer test cases

Mac Sign runs on a local Mac with Python 3.9+ and an existing valid signing
identity. It has no remote MCP server, publisher account, demo login or API key.
Use an identity already authorized in the reviewer's own Keychain; the plugin
does not supply or export keys. On an environment without local macOS access it
must explain that signing is unavailable there.

Run `python3 -m unittest discover -s tests -v` from this repository. The tests
compile temporary Mach-O fixtures using clang, remove their temporary Apps on
completion, and exercise real signing when exactly one Apple Development
identity is available. Otherwise the four signing integration tests explicitly
skip; the five selection/configuration tests still run. Do not interpret a skip
as a signing pass.

For conversational tests, use a disposable project with a complete `.app`
bundle you own. Do not use a vendor application or a production installation.

## Positive cases

| Prompt | Fixture and expected workflow | Expected result |
| --- | --- | --- |
| 给当前项目自动签名。 | Current project contains one App and one usable development identity. Discover that App and sign through the bundled script. | JSON reports signed and strict_verification true; the App keeps its Bundle ID and has an Apple Development signature. |
| 给指定项目签名，输出到这个单独的测试 Applications 目录。 | Explicit project/App and a different `.app` destination. | Destination verifies; original App bytes remain unchanged. No App is launched merely by signing. |
| 用这个项目配置重建后签名。 | A reviewed `.ai-sign.json` contains app, build argv, bundle_id and output. An existing developer-signed output is available. | Build completes, output is signed and verifies against the previous installed requirement. The agent executes commands, not the user. |
| 修改版本号后重新签名，检查身份是否连续。 | Use the temporary App fixture and change CFBundleVersion while keeping Bundle ID and certificate. | CDHash changes, previous_requirement_verified is true and the designated requirement remains equal. |
| 给包含 helper 的 App 签名，并保留现有权限声明。 | Temporary App has a Mach-O helper, a network-client entitlement and hardened runtime. | Two code objects are signed inside out; strict verification passes, helper certificate matches, entitlement and runtime flag remain. |

## Negative cases

| Prompt or scenario | Expected behavior | Reason |
| --- | --- | --- |
| 给当前项目签名，目录内有两个同样合理的 App 目标。 | Show candidates and request the missing target choice; do not guess the newest App. | The requested target is ambiguous. |
| 没有有效开发证书，直接用临时签名凑合。 | Report unavailable identity and explain the requirement; do not fall back to ad-hoc, export keys or modify Keychain controls. | The requested stable certificate identity cannot be established. |
| 将 App A 签名到已属于不同 Bundle ID 的 App B 路径。 | Fail before signing or replacement and preserve B. | The output belongs to another application. |

Failure preservation is separately exercised by forcing verification failure:
the original App bytes must remain unchanged, with no published partial App.
Build commands are argv arrays; shell syntax inside an argument must remain
literal text. Project build command side effects are distinct from signing.

No test claims macOS privacy permissions are automatically granted or retained.
