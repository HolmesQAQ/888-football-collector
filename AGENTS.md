# 项目维护约定

- 远程仓库：https://github.com/HolmesQAQ/888-football-collector。发布流程遵循 RELEASING.md。
- 每次功能或修复交付同步更新 VERSION、CHANGELOG.md 和 releases/v版本号.md，测试通过后发布新版本；不覆盖旧标签或附件。仅文档修改可不升版。

- 本目录为完整最新版。原地维护，不创建重复的旧版程序目录。
- 用户已授权后续项目更新同步到此 GitHub 仓库。完成修改与相关测试后提交、推送，报告提交结果；推送失败时明确说明。
- 不提交 data/、运行日志、数据库、会话令牌、凭据或个人采集归档。
- 保持 Python 3.10+ 标准库可运行，保留 start.bat 入口与中文运行说明。
- 修改解析器后运行 python -m unittest discover -s tests -v。
- 比分来源与赔率来源保留证据。不能将 500 结果冒充澳客结果；未取得的数据留空，90 分钟比分不得混入加时或点球。
