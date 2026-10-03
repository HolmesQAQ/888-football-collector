# 版本管理与发布

GitHub：https://github.com/HolmesQAQ/888-football-collector

`main` 保存最新开发成果；用户优先下载 Releases 中的固定版本。`VERSION` 是唯一版本号来源。

每次对外交付：

1. 按修复、新增功能或不兼容变更选择版本号，更新 `VERSION`。
2. 在 `CHANGELOG.md` 顶部说明改动、验证、已知限制、数据兼容性；新增 `releases/v版本号.md`。
3. 运行 `python -B -m unittest discover -s tests -v`，确认不提交 data、凭据和运行日志。
4. 提交并同步到 main，保留可追踪的提交信息，不强制推送覆盖历史。
5. GitHub Actions 先执行 Windows Python 3.10/3.12 测试，再为新版本创建 `v版本号` 标签和 Release，附固定 ZIP 及 SHA-256 校验文件。
6. 核验 Release 附件可下载，才向用户宣告该版本正式发布。

已存在的版本禁止替换附件或移动标签。代码修复必须升版本；仅文档调整可不发布，已有 Release 保持不变。发布中断需核验已创建的标签与附件，不能靠删除重建版本绕过问题。

升级前备份 data。涉及数据结构变更时提供迁移或兼容说明；回退使用原版本和升级前备份。
