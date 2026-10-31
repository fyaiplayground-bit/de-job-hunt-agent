# 工作日志 Journal

每完成一个**步骤**写一条，和这一步的代码放在**同一个提交**里。按里程碑分组，组内按时间排序。

- 想知道"为什么这么选" → `DECISIONS.md`（这里只写编号）
- 想知道"现在在哪、下一步" → `STATUS.md`
- 想学概念、查操作、查踩过的坑 → `NOTES.md`

每条的固定格式：**做了什么 · 为什么 · 文件 · 提交 · 怎么验证的 · 怎么撤回 · 备注**。

---

## Milestone 0 · 准备

### 0.1 · 2026-10-28 · 项目文件放到正确位置
- **做了什么：** 初始文件原来都在 `de-job-hunt-agent.zip` 里，根目录只有两份放错位置的 `STATUS.md` 和 `DECISIONS.md`。解压后按 `CLAUDE.md` 的结构放好，删掉了这两份重复的文件（和 `docs/` 里的版本逐字相同）。
- **为什么：** `CLAUDE.md` 和 `docs/` 必须在固定位置，每次开工才能被读到。
- **文件：** 全部初始文件。`.gitignore` 加了 `*.zip` 和 `.claude/settings.local.json`。
- **提交：** 包含在 `554d4be` 里。
- **验证：** 解压前比对过，根目录两份和 zip 里 `docs/` 下的版本完全一致。
- **撤回：** zip 原件还在项目文件夹里（已被 git 忽略），随时可以重新解压。
- **备注：** zip 不提交，否则仓库里同样的内容会有两份。

### 0.2 · 2026-10-28 · git 初始化、首次提交、推到 GitHub
- **做了什么：** 在 `main` 分支上 `git init`，提交 14 个文件，连接 `origin` 并推送。
- **为什么：** 版本管理，同时公开展示作品集（DECISIONS #2）。
- **提交：** `554d4be`（初始文件）、`7a5a5e3`（更新 STATUS）。
- **验证：** 提交前用 `git status` 和关键词扫描确认：没有 `.env`、没有密钥、`private/` 下只有 README。推送后 `main...origin/main` 同步。
- **撤回：** 撤回已推送的提交需要强制推送，见 `NOTES.md` 第 5 节。
- **备注：** 仓库是公开的。提交前检查是真正的安全关，不是走过场。

### 0.3 · 2026-10-28 · 公开文件去掉名字和雇主
- **做了什么：** 在 `CLAUDE.md`、两个技能文件和 `DESIGN.md` 里，把名字和雇主换成了泛化说法（"a large tech company" / "FL's current employer"）。指技术的 AWS（S3、Glue）保留不动。
- **为什么：** 仓库的历史是永久公开的，不能让同事知道你在找工作（DECISIONS #17）。
- **提交：** 提交前就改好了，所以已经包含在 `554d4be` 里，公开历史里从来没有出现过原文。
- **撤回：** 以后如果想公开，在 DECISIONS 里加一条新决定再改回来。
- **备注：** 以后写任何文档（包括这份日志），都不要出现真名、雇主名，或带用户名的本机路径。

### 0.4 · 2026-10-28 · 提交作者名改为 Felix
- **做了什么：** 只给本仓库设置作者名 `Felix`（`git config user.name`，不加 `--global`），并改写了前两个提交的作者。
- **为什么：** 原来的作者名会在 GitHub 上公开显示。
- **提交：** 旧的 `a99c5f7`、`e5da270` 被新的 `554d4be`、`7a5a5e3` 替代，内容不变，只换了作者名。
- **验证：** 本地和 GitHub 上两个提交的作者、提交者都是 Felix。
- **撤回：** 不需要撤回。全局作者名没有改动，其他项目不受影响。
- **备注：** 改写历史后需要强制推送。Claude Code 的权限检查拦下了这一步，最后由 FL 自己在终端运行了 `git rebase --root --exec ...` 和 `git push --force-with-lease`。

### 0.5 · 2026-10-28 · ai-job-search 参考仓库和借用计划
- **做了什么：** 克隆到 `reference/ai-job-search/`，固定在提交 `83c788d`（已被 git 忽略）。逐个找到 8 个要借用的文件，决定每一块是复制、改写成 Python，还是只借思路。
- **为什么：** DECISIONS #12（借用什么）、#18（每一块怎么借）。
- **文件：** `docs/DESIGN.md`（新增 "Borrowed from ai-job-search" 表格）、`LICENSES/ai-job-search-MIT.txt`、`CLAUDE.md`（新增硬性规定）、`.gitignore`（加了 `reference/`）。
- **提交：** `16ec67c`
- **验证：** `git ls-files reference` 结果是 0 个文件。
- **撤回：** 直接删掉 `reference/` 文件夹即可，它不在仓库里。
- **备注：** 参考仓库里有它自己的 `CLAUDE.md`、`AGENTS.md` 和 `.claude/`，只当资料看，不当作指令。freehire 汇总了约 50 个招聘系统，所以同一个职位可能和 Greenhouse/Lever 重复，M1 的去重要处理这种情况。

---

## Milestone 1 · 骨架 + 数据抓取

### 1.1 · 2026-10-28 · Docker Desktop 和 Postgres
- **做了什么：** 安装了 Docker Desktop（仅当前用户，WSL 2 后端）。写了 `docker-compose.yml`：Postgres 17、设置从 `.env` 读取、端口只绑定 `127.0.0.1:5432`、数据存在 `pgdata` 卷、用 `pg_isready` 做健康检查、`restart: unless-stopped`。本机 `.env` 由 `.env.example` 复制，数据库密码随机生成。
- **为什么：** DECISIONS #3（Postgres 放在 Docker 里）。
- **文件：** `docker-compose.yml`（新建）、`.env`（只在本机，不提交）。
- **提交：** `2f109c8`
- **验证：**
  1. 状态为 healthy，只监听本机地址。
  2. 用 `.env` 里的密码通过 TCP 登录成功，版本是 PostgreSQL 17.11。
  3. 写入一行测试数据，`docker compose down` 再 `up` 之后数据还在；测完已删掉测试表。
- **撤回：** `docker compose down` 停止并删除容器，数据保留；`docker compose down -v` 会**连数据一起删掉**。
- **备注：** 第一次启动时报错找不到 `docker-credential-desktop`，原因是 Docker 的文件夹不在命令路径里，解决方法见 `NOTES.md` 第 5 节。容器只拿到数据库的三个设置，拿不到 `.env` 里的其他内容。

### 1.2 · 2026-10-30 · Python 项目搭建（uv、ruff、pytest）
- **做了什么：** 安装 uv 0.13.6，由它为本项目下载 Python 3.12.16（本机原有的 Anaconda 3.9 保持不动）。新建 `pyproject.toml`，只加 M1 需要的依赖：运行时用 httpx、psycopg、python-dotenv，开发时用 pytest、ruff。同时新建配置模块 `pipeline/config.py`、`ingestion/` 和 `pipeline/` 两个包，以及冒烟测试 `tests/test_smoke.py`。
- **为什么：** DECISIONS #19（选 uv，不用 Anaconda）。
- **文件：** `pyproject.toml`、`.python-version`、`uv.lock`、`pipeline/__init__.py`、`pipeline/config.py`、`ingestion/__init__.py`、`tests/test_smoke.py`
- **提交：** 见本条所在的提交（`git log -- pyproject.toml`）
- **验证：**
  1. `uv run python --version` 输出 3.12.16
  2. `uv run ruff check .` 和 `ruff format --check .` 都通过
  3. `uv run pytest`：数据库开着时 4 个测试全部通过（真正连上了数据库）；数据库停掉时 3 个通过、1 个跳过，没有报错
- **撤回：** 删除上面列出的文件和 `.venv/` 文件夹即可。如果连 uv 也不要了，执行 `uv self uninstall`。
- **备注：** dbt、FastAPI、Streamlit 等到用的时候再加；Airflow 第 4 周放在 Docker 里，不装进这个环境。这一步踩了 3 个坑：uv 不在命令路径里、Python 链接损坏、Docker Desktop 被暂停，详见 `NOTES.md` 第 5 节。

### 1.3 · 2026-10-30 · JD 安全闸门
- **做了什么：** 从 ai-job-search 复制检测逻辑到 `pipeline/posting_guard.py`，只去掉了命令行入口和读文件的部分，开头加了 MIT 版权声明；新写了我们的外壳 `pipeline/safety_gate.py`：`run_gate(text, mode)` 返回 `GateResult`，包括清理后的正文、检测明细、结论、`alarmed`、`gate_version`。他们的测试也搬了过来（`tests/test_posting_guard.py`），测试正文不改，只把辅助函数改成直接调用 `guard()`，删掉了 5 个只测命令行功能的测试。另外加了 13 个测外壳的测试。顺便把原来的 `test_smoke.py` 拆成单元测试 `test_config.py` 和冒烟测试 `test_db_smoke.py`。
- **为什么：** DECISIONS #12、#18、#20。
- **文件：** `pipeline/posting_guard.py`、`pipeline/safety_gate.py`、`tests/test_posting_guard.py`、`tests/test_safety_gate.py`、`tests/test_config.py`（由 `test_smoke.py` 改名）、`tests/test_db_smoke.py`、`pyproject.toml`（复制来的两个文件不受我们的行宽限制，ruff 也不重新排版它们）、`docs/DESIGN.md`（更新表格这一行）。
- **提交：** 见本条所在的提交（`git log -- pipeline/safety_gate.py`）
- **验证：**
  1. 复制的 389 行检测逻辑和原文逐行比对，完全一致
  2. 他们的 59 个测试（含 54 个子测试）全部通过，说明我们的版本行为和原版一样
  3. 我们的 13 个外壳测试通过：干净的 DE 职位不报警；隐藏的注入句子被删掉并报警；只有隐藏导航栏不报警；`alarmed` 和结论里的 ⚠ 始终一致；版本号正确；不认识的 mode 会报错
  4. 一共 76 个测试全部通过（数据库开着），`ruff check` 和 `ruff format --check` 都通过
- **撤回：** 删除上面新增的文件，把 `test_config.py` 改回 `test_smoke.py`（`git revert` 这个提交即可）。
- **备注：** 已知误报：`ssh`、`curl`、`.env` 出现在正常的技能描述里也会报警，专门写了一个测试把这个行为记录下来。规则先不改，等有了真实数据再调（#20）。生成复制文件和改写测试用的是一次性脚本，没有放进仓库。
