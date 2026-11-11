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

### 1.4 · 2026-10-30 · Greenhouse + Lever 抓取进原始层
- **做了什么：** 抓取 19 家公司的公开招聘页（14 家 Greenhouse、5 家 Lever），原样存进 Postgres，再全部过一遍安全闸门。共建了 4 张表：`raw.ingest_runs`（每次运行一行）、`raw.job_postings`（每个职位的每个内容版本一行，原始 JSON 不改）、`raw.job_sightings`（每个职位每天被看到一次就记一行）、`gate.results`（闸门结果，带版本号）。建表用编了号的 SQL 文件，只会执行一次。手动运行命令：`uv run python -m pipeline.ingest`。
- **为什么：** DECISIONS #21。
- **文件：** `config/companies.toml`、`db/migrations/001_raw.sql`、`db/migrations/002_gate.sql`、`pipeline/db.py`、`pipeline/load.py`、`pipeline/gate_step.py`、`pipeline/ingest.py`、`ingestion/http.py`、`ingestion/greenhouse.py`、`ingestion/lever.py`、`ingestion/sources.py`、`pipeline/config.py`（新增 `is_source_enabled`，默认地址改为 127.0.0.1）、`.env.example`；测试：`tests/conftest.py`、`tests/fixtures/*.json`、`tests/test_sources.py`、`tests/test_http.py`、`tests/test_ingest_db.py`
- **提交：** 见本条所在的提交（`git log -- pipeline/ingest.py`）
- **验证：**
  1. 97 个测试全部通过，用时 2 秒，ruff 也通过。新增 21 个测试：8 个测解析和内容指纹（`updated_at` 变化不算改版；内容改了才算；部门顺序不影响），5 个测网络请求（遵守 `Retry-After`；遇到 5xx 按 1/2/4 秒退避，3 次后放弃；404 不重试；连接错误会重试），8 个数据库测试，在单独的 `jobhunt_test` 库里跑（重复加载新增为 0；内容改一处只多 1 个版本；隔一天只多看到记录；一家公司失败不影响其他公司；闸门每个版本只检查一次）
  2. 真实运行第 1 次：19 家全部成功，共 2300 个职位、2300 个版本，闸门检查 2300 个、报警 14 个，用时 62 秒
  3. 马上运行第 2 次：新增版本 0，闸门检查 0。**幂等得到证明**
- **真实数据观察：** 2300 个职位里，标题像 DE 的有 58 个。14 个报警**全部是误报**：10 个是同一句 "You are an AI pragmatist"（Samsara 销售岗），3 个是 SSH 出现在 JumpCloud 的技能描述里，1 个是 "as an AI/Tech evangelist"（JumpCloud；原规则只放过 "As an AI Engineer" 这类职位名称，豁免名单里没有 evangelist）。58 个 DE 类职位都没有报警。没有发现真正的攻击。这组数据就是以后调规则的依据（#20）。
- **怎么判断是误报的（每一条都核对过）：** ① 读完整的触发句：是在描述候选人或技能，还是在命令 AI 做事；② 检查其他信号：隐藏内容、隐形字符、隐形文字、隐藏网址、混用字母，14 条全部为 0，句子都是明面上所有人可见的，而攻击通常要藏起来；③ 合不合常理：都在公司官方招聘页上，10 条是同一个招聘模板。这是有依据的人工判断，不是证明。（更正：第一次汇总时只看了每句前 110 个字符，误把 "as an AI" 那条归进了 SSH，已改正。）
- **撤回：** `git revert` 这个提交；要清空数据库里的数据，执行 `drop schema raw cascade; drop schema gate cascade; drop table public.schema_migrations;`（会删掉所有已抓到的职位）。
- **备注：** 这一步的坑：默认地址 `localhost` 每次连接要慢好几秒（Windows 先尝试 IPv6），已改为 `127.0.0.1`，见 `NOTES.md` 第 5 节。起步清单里大多是中大型公司，只用来跑通管道；小公司为主的目标清单在 M5。跨来源去重和每日运行脚本还没做。

### 1.5 · 2026-10-30 · 报警分档：把人工判断写成确定的规则（规则循环第 A 步）
- **做了什么：** 把 1.4 里判断误报的标准写成了代码。每个闸门结果自动分到四档之一：clean（干净）/ benign（放行）/ review（人工看）/ block（拦截），并附上原因。规则放在数据文件 `config/triage_rules.toml` 里，包括哪些是"弱规则"、哪些是"指挥 AI 的信号词"，以及版本号。上游的每条指令规则都起了一个固定的名字（`RULE_SIGNATURES`），规则文件按名字引用。闸门版本改成"检测版本 + 规则版本"，也就是 `d1-t1`。新增报告命令 `pipeline.alarm_report`，以及只重算、不抓取的 `pipeline.ingest --gate-only`。"代码在运行时判断、AI 只提建议、规则只能通过循环修改"这条原则写进了 `CLAUDE.md` 的硬性规定。
- **为什么：** DECISIONS #22。
- **文件：** `config/triage_rules.toml`、`pipeline/alarm_triage.py`、`pipeline/alarm_report.py`、`pipeline/safety_gate.py`、`pipeline/gate_step.py`、`pipeline/ingest.py`、`db/migrations/003_gate_triage.sql`、`tests/fixtures/gate_cases.jsonl`、`tests/test_alarm_triage.py`、`tests/test_safety_gate.py`、`tests/test_ingest_db.py`、`CLAUDE.md`、`docs/DESIGN.md`
- **提交：** 见本条所在的提交（`git log -- pipeline/alarm_triage.py`）
- **验证：**
  1. 标准答案集共 39 条：5 条真实误报必须放行；25 条攻击写法必须是"人工看"或"拦截"（其中 19 条来自上游测试，6 条是专门针对我们规则写的，比如把指令放在 200 个字符的截断之后、把已知无害的句子藏进隐藏内容）；另有干净和混用字母的例子。**全部落在预期的档位**
  2. 一共 174 个测试全部通过，ruff 也通过；另有测试保证上游每条规则都恰好有一个名字，上游一改，测试就会失败
  3. 用新规则从原始数据重算 2300 个职位：clean 2286、benign 14、review 0、block 0；再跑一次，新增 0；旧版本 `1` 的 2300 条结果仍然保留
- **撤回：** `git revert` 这个提交。数据库里 `d1-t1` 版本的结果可以留着，不影响旧版本；要删就执行 `delete from gate.results where gate_version = 'd1-t1'`。
- **备注：** 两个坑：Write 工具把规则文件里的 `'` 直接写成了撇号，导致 TOML 字符串提前结束；改用 sed 时反斜杠又被 shell 吃掉了。最后改用编辑工具解决，见 `NOTES.md` 第 5 节。残留风险：只用弱规则里的说法、又避开所有信号词的攻击句会被放行。这样的句子本身不在指挥 AI，而且 M2 的 AI 助手会有自己的"只当数据"规则作为第二道防线。下一步是循环第 B 步：标签表和评估命令。

### 1.6 · 2026-10-30 · 规则循环第 B 步：标签和评估，并完整走一遍
- **做了什么：** 新增标签表 `gate.labels`（只追加；同一个职位以最新的标签为准，旧的保留），记录标签类别、备注、谁标的、什么时候，以及当时的规则版本、档位和看到的触发句。新增打标签命令 `pipeline.labels`（add / list / export）：导出时**只导出触发的那一句话**，不导出整个职位；相同的句子合并成一条；隐藏的内容重新藏起来；隐形文字重新用隐形字符写出来。导出的结果写进 `tests/fixtures/gate_cases_labeled.jsonl`。新增评估命令 `pipeline.evaluate_rules`：用当前规则和提议规则把所有标准答案、所有历史职位各判一遍，输出硬性检查、软性指标、各档数量的前后对比，以及哪些职位的档位会变；只读，不写任何东西。报告命令现在会显示职位编号，方便打标签。新增 `config/proposals/` 文件夹，存放规则修改的提议。
- **为什么：** DECISIONS #23。
- **文件：** `db/migrations/004_gate_labels.sql`、`pipeline/labels.py`、`pipeline/evaluate_rules.py`、`pipeline/alarm_report.py`、`pipeline/alarm_triage.py`（`visible_line` 改为公开函数）、`pipeline/safety_gate.py`（`is_alarmed` 改为公开函数）、`config/proposals/README.md`、`tests/fixtures/gate_cases_labeled.jsonl`、`tests/test_labels.py`、`tests/test_evaluate_rules.py`、`tests/test_alarm_triage.py`
- **提交：** 见本条所在的提交（`git log -- pipeline/evaluate_rules.py`）
- **完整走一遍循环（真实数据）：**
  1. 报告：14 个放行的职位，每个都显示了编号
  2. 打标签：14 个都标为 `false_positive`（你在对话里确认过），备注写明原因
  3. 导出：合并成 5 条标准答案（10 个 Samsara 职位是同一个模板）
  4. 提议和评估：
     - "所有规则都改成弱规则" → **48 项硬性检查不通过**，命令报失败
     - "只把 chat_template_token 改成弱规则" → **不通过**，`<|im_start|>system` 会被放行。注意：只看 2300 个真实职位，结果是"0 个变化"，看起来完全无害，**是标准答案集拦住了它**
     - "只改注释" → 通过，0 个变化
  5. 正式规则保持第 1 版：没有真实数据要求改规则，所以不改
- **验证：** 191 个测试通过，1 个跳过（还没有已标注的真实攻击）；ruff 通过。写测试时发现了一件事：只放宽"忘记之前的指令"这条规则，并不会放过 "Forget your previous instructions."，因为句子里的 *instructions* 是信号词，两层规则各自起了作用。这一点也写成了测试。
- **撤回：** `git revert` 这个提交；标签表里的数据可以用 `drop table gate.labels` 删除，同时从 `public.schema_migrations` 里删掉 `004_gate_labels.sql` 这一行。
- **备注：** 标签时间按 UTC 记录，所以在美国晚上标的会显示成第二天的日期。

### 1.7 · 2026-10-31 · freehire、LinkedIn（默认关闭）、跨来源去重、发现新招聘页
- **做了什么：**
  - **抓取改为支持"按搜索抓"：** 除了按招聘页抓（`config/companies.toml`），现在也能按保存好的搜索条件抓（`config/searches.toml`）。新增 `FetchContext`，所有请求都经过它，便于计数和设置上限。运行记录里的 `company` 列改名为 `target`，新增 `requests_made` 和 `note` 两列（迁移 005）。每个职位的公司名改为从职位数据本身读取。
  - **freehire：** 照他们的客户端改写成 Python，开头带 MIT 声明。按"美国 + data/analytics engineer 标题"搜索，一页一页地翻；页数有上限；遵守 API 的 offset 窗口限制；内容指纹不包括浏览数、`reality` 等经常变的字段。
  - **LinkedIn：** 照他们的解析代码改写，开头带 MIT 声明，但**没有搬**伪装成浏览器的身份和请求头。默认关闭（需要设置 `LINKEDIN_PUBLIC_ENABLED=true` 才会运行）；每天的请求数有硬上限，同一天跑几次加起来也不会超；已经存过的职位不再请求详情页，只记一条"今天看到了"；原始数据存 LinkedIn 返回的 HTML。**这次没有发出任何真实的 LinkedIn 请求。**
  - **跨来源去重：** 用 SQL 视图实现（迁移 006、007），按"招聘系统/招聘页/职位 id"确定身份，优先采用直接从招聘系统抓到的那一份。
  - **发现新招聘页：** 新增 `pipeline.discover_boards`，只读，列出 freehire 里出现过、但我们还没有的 Greenhouse/Lever 招聘页。
- **为什么：** DECISIONS #24。
- **文件：** `ingestion/context.py`、`ingestion/freehire.py`、`ingestion/linkedin.py`、`ingestion/http.py`（新增 `get_text`）、`ingestion/greenhouse.py`、`ingestion/lever.py`、`ingestion/sources.py`、`config/searches.toml`、`pipeline/ingest.py`、`pipeline/load.py`、`pipeline/config.py`、`pipeline/discover_boards.py`、`db/migrations/005_search_sources.sql`、`006_dedupe_views.sql`、`007_dedupe_jobs_group_once.sql`；测试 `tests/test_freehire.py`、`tests/test_linkedin.py`、`tests/test_search_sources_db.py`，以及 `tests/fixtures/` 里的 3 个样例文件（都是我手写的，不含真实职位文字）
- **提交：** 见本条所在的提交（`git log -- ingestion/freehire.py`）
- **验证：**
  1. 211 个测试通过，ruff 通过。新增的测试覆盖：freehire 翻页、参数、页数上限、API 窗口；LinkedIn 解析、隐藏内容会被闸门拦下、关闭横幅、请求预算是硬上限、已存过的职位不重复请求、**默认关闭**；数据库测试覆盖每日上限跨运行生效，以及同一个职位从 Greenhouse 和 freehire 进来只算一个
  2. 真实运行：freehire 回填 7 天，抓到 5000 个职位（达到页数上限，**回填不完整**），其中 4592 个是不重复的，用时 256 秒；再跑一遍全部来源，freehire 新增 224 个，**全是第一次被漏掉的新职位**，没有一个是旧职位改版
  3. 去重：7118 条原始记录 → 7073 个职位，有 45 个同时来自 Greenhouse 和 freehire
- **真实数据观察：**
  - freehire 按相关度排序，翻页的几分钟里排序一直在变，所以同一个职位可能出现在两页上（408 个重复，已被幂等加载吸收），也可能被漏掉。每天只抓 2 天（约 1300 个、14 页）不会碰到上限
  - freehire 自己判定 **22% 的职位是陈旧职位**（1065 个）；职位来源主要是 Greenhouse 1117、Manatal 874、Workday 755、Oracle 339
  - 闸门：review 4、block 5，**全部像是误报**。4 个 review 中，3 个是 Axon 的防诈骗提示（"please ignore the message"），1 个是没有换行的长段落里提到 SSH；5 个 block 都是复制粘贴留下的零宽空格，比如 `stor|y`、`|h|eadquarters`。这些标签和可能的规则调整，要先等你确认（规则循环）
- **一个性能问题（已修复）：** 去重视图第一版用了"每行一次子查询"，到 7000 行时 20 秒都跑不完。改成先分组、再连接（迁移 007），同样的数据只用 0.59 秒。没有修改已经执行过的迁移 006，而是新加一个迁移，保证改动有记录。
- **撤回：** `git revert` 这个提交；数据库里的视图用 `drop schema dedupe cascade` 删除；freehire 的数据可以用 `delete from gate.results where posting_version_id in (select posting_version_id from raw.job_postings where source='freehire')`，再加上对 `raw.job_sightings`、`raw.job_postings` 做同样条件的删除。
- **备注：** 运行慢查询之前应该先设 `statement_timeout`，这次是靠后台任务超时才发现的。

### 1.8 · 2026-10-31 · 规则循环第一次真正跑一圈（规则 v2），以及 HTTP 身份调整
- **做了什么：**
  - **打标签：** 你确认 freehire 带来的 9 个报警都是误报（3 个 Axon 防诈骗提示、1 个 Schneider 的 SSH、5 个零宽空格残留），全部标成 `false_positive`。导出后共有 13 条标准答案。
  - **导出改进：** 超过 300 字符的行（比如整篇描述都没有换行的 Schneider）只导出触发词附近的片段，整篇描述不会进入公开仓库；含零宽字符的单词从职位原文里复现，先去掉 HTML 标签，这样 BOM 那条也能找到。
  - **规则 v2：** 新增一个开关：单词里只有零宽字符、没有任何其他可疑信号时，按"编辑残留"放行，不再拦截。先写成 `config/proposals/triage_rules.v2.toml` 提议，评估通过后你批准，才复制成正式规则。新增手写标准答案：零宽残留 → 放行；双向控制符 → 拦截。
  - **HTTP 身份（#25）：** User-Agent 改用爬虫标准格式（和 Googlebot 一样），加上 Accept 和 Accept-Language、退避时的随机抖动，LinkedIn 详情页 404 时只跳过该职位。**没有采用** `X-Requested-With`，因为它会让请求冒充成 LinkedIn 自己的网页。
- **为什么：** DECISIONS #25、#26。
- **文件：** `config/triage_rules.toml`（v2）、`config/proposals/triage_rules.v2.toml`、`pipeline/alarm_triage.py`（开关和 `is_editing_artifact`）、`pipeline/labels.py`、`ingestion/http.py`、`ingestion/linkedin.py`、`tests/fixtures/gate_cases.jsonl`、`tests/fixtures/gate_cases_labeled.jsonl`、`tests/test_alarm_triage.py`、`tests/test_labels.py`、`tests/test_evaluate_rules.py`、`tests/test_http.py`、`tests/test_linkedin.py`、`tests/test_safety_gate.py`
- **提交：** 见本条所在的提交（`git log -- config/proposals/triage_rules.v2.toml`）
- **验证：**
  1. 打完标签后，v1 下有 6 条标准答案测试失败（v1 拦截了你确认过的误报）。这是**有意为之的信号**：现行规则和已确认的事实矛盾了
  2. 评估 v2：硬性检查全部通过；被放行的误报从 6/13 升到 12/13；只有那 5 个被标注的职位从拦截变为放行，其他不变
  3. 采用 v2 后，233 个测试全部通过；从原始数据重算 7118 个职位（`d1-t2`）：clean 7089、benign 25、review 4、block 0；再跑一次新增 0；v1 的结果仍然保留
- **撤回：** 把 `config/triage_rules.toml` 改回 version 1、去掉那个开关，然后运行 `ingest --gate-only`。v1 的结果还在数据库里，所以不会丢任何历史。
- **备注：** 找到了"转义序列变成真字符"的真正原因：我传给工具的 `​` 这类文字会在写入前被解码，用 sed 写时反斜杠又会被 shell 吃掉。现在含不可见字符的地方，一律用脚本以 `chr()` 生成，写完再扫描一遍确认没有残留的不可见字符。

### 1.9 · 2026-10-31 · 每日运行脚本
- **做了什么：** 新增 `pipeline/daily.py`，一条命令 `uv run python -m pipeline.daily` 完成每天的全部工作：
  1. 连数据库；连不上就启动一次 Docker Desktop，最多等 3 分钟
  2. 加锁（Postgres advisory lock），同一时间只允许一个 daily 在跑
  3. 抓取所有已开启的来源
  4. 过安全闸门
  5. 写报告 `output/daily/<日期>.md` 和 `latest.md`，并在 `ops.daily_runs` 记一行（迁移 008）

  搜索窗口按上次成功运行的时间自动计算（2–7 天）；"今天新增"按本次运行的 run id 判断，不看时钟。`scripts/daily.cmd` 给 Windows 任务计划程序调用。CLAUDE.md 新增一条：每次开工先汇报最近一次 daily 的结果。`.env.example` 新增 `REPORT_TIMEZONE`。`tzdata` 改为显式依赖。
- **为什么：** DECISIONS #27。
- **文件：** `pipeline/daily.py`、`db/migrations/008_daily_runs.sql`、`scripts/daily.cmd`、`tests/test_daily.py`、`tests/conftest.py`（测试库也清理 `ops` 和 `dedupe`）、`CLAUDE.md`、`.env.example`、`pyproject.toml`、`uv.lock`
- **提交：** 见本条所在的提交（`git log -- pipeline/daily.py`）
- **验证：**
  1. 244 个测试通过，覆盖：窗口计算（第一次 2 天、隔天 2 天、隔 4 天 5 天、最多 7 天、失败的运行不算）、跨来源去重后的"新增"、同一天第二次运行新增为 0、锁、报告内容确定、数据库连不上时只启动一次 Docker 然后放弃并给出提示
  2. 真实运行两次都 ok，用时约 80 秒；第二次运行进行中时启动的第三次，被锁挡住并直接退出
  3. 排查了一个疑点：Coinbase 每次运行都"新增 1 个"，查证后发现是 3 个**不同**的新职位（Coinbase 正在发布新岗位），没有任何职位出现重复版本，幂等没有问题
- **撤回：** `git revert` 这个提交；`drop schema ops cascade`；删掉 `output/daily/`。
- **备注：** 第一版用时间戳判断"今天新增"，在测试里因为模拟时间和真实时间不一致而失败，改用 run id 之后就不依赖时钟了。

### 1.10 · 2026-10-31 · 创建定时任务和桌面快捷方式（你同意后）
- **做了什么：**
  - Windows 计划任务 "de-job-hunt-agent daily"：每天本地时间 8:30（电脑本身就是太平洋时区），通过 `conhost --headless` 运行 `scripts\daily.cmd`，不会弹出窗口
  - 设置：错过后补跑、用电池也运行、不唤醒电脑、只在你登录时运行、普通权限、最长 1 小时、不同时运行两个
  - 桌面快捷方式"每日职位报告"：用记事本打开 `output\daily\latest.md`
- **验证：** 手动触发一次，结果代码 0（成功），日志里有当天的报告；下次自动运行时间显示为 11/01 08:30。
- **撤回：** 让 Claude 运行 `Unregister-ScheduledTask -TaskName "de-job-hunt-agent daily" -Confirm:$false`，然后删掉桌面上的快捷方式。
- **两个坑（已记入 NOTES）：**
  1. 创建时触发时间被存成了 `08:30-07:00`（固定的夏令时偏移），而 11/01 夏令时结束，下次运行就变成了 7:30。改成不带偏移的本地时间 `08:30` 后，全年都是 8:30。
  2. 快捷方式名和桌面路径里有中文，在 PowerShell 命令里变成了 `??`；Windows 创建快捷方式用的老组件也存不了这种路径。解决办法是先存到英文路径，再用 PowerShell 移到桌面。

### 1.11 · 2026-10-31 · 假样本档案和档案检查（M1 最后一项）
- **做了什么：**
  - `data/sample/` 放了一个虚构的候选人 Alex Sample（BI 工程师转 DE），三个文件就是以后你真文件的格式：`evidence_bank.toml`（事实库：工作经历、项目、学历、13 条经历、19 个技能及别名）、`applicant_profile.toml`（申请表资料和硬性条件）、`resume.md`（未定制的主简历）。另有 `README.md`，声明全部虚构，并列出给 M2 准备的测试场景（换个说法、只碰过一点、在学、从没碰过、模糊处理的数字、硬性条件）
  - `agents/profile.py`：读取并检查三个文件，命令是 `uv run python -m agents.profile check [文件夹]`。检查内容：字段齐全、类型正确；id 不重复；每条经历指向存在的工作或项目；技能用标准名；每个技能至少有一条证据；别名不撞车；简历的标题、日期、技能、数字都能在事实库里找到
  - `pipeline/config.py` 新增 `profile_dir()`，`.env.example` 新增 `PROFILE_DIR=data/sample`。M5 时把它改成 `private` 就切换到真档案
  - `private/README.md` 和四个 skill 文件改为指向 `<profile>/evidence_bank.toml` 这类路径；`DESIGN.md` 同步
  - 新建 `docs/INTERVIEW_NOTES.md`，写好 M1 的面试笔记（英文）
  - 顺手修了本文件 1.4 条的"撤回 / 备注"两行，它们之前跑到了文件末尾
- **为什么：** DECISIONS #16、#28。
- **文件：** `data/sample/README.md`、`data/sample/evidence_bank.toml`、`data/sample/applicant_profile.toml`、`data/sample/resume.md`、`agents/__init__.py`、`agents/profile.py`、`pipeline/config.py`、`.env.example`、`tests/test_profile.py`、`private/README.md`、`.claude/skills/{coverage-report,fit-scoring,resume-tailoring}/SKILL.md`、`docs/DESIGN.md`、`docs/INTERVIEW_NOTES.md`
- **提交：** 见本条所在的提交（`git log -- data/sample/evidence_bank.toml`）
- **验证：**
  1. `agents.profile check` 对样本输出 OK（2 份工作、2 个项目、13 条经历、19 个技能，其中 1 个在学）
  2. 新增 25 个测试：样本通过全部检查；**隐私护栏**（邮箱只能是 example.com，网址只能是 example.com，电话只能是 555-01xx，公司和学校只能是那三个虚构名字）；README 承诺的测试场景都在；每条检查都能抓到它要抓的错误（简历写了没证据的 Kafka、简历出现事实库里没有的数字、日期和工作经历对不上、标题不标准、经历指向不存在的工作、技能没用标准名、技能没有证据、别名撞车、级别或日期写错、缺字段、薪资下限高于目标）；命令行在样本上返回 0，在改坏的副本和空文件夹上返回 1
  3. 全部 269 个测试通过（1 个跳过），ruff 通过
- **撤回：** `git revert` 这个提交。不涉及数据库。
- **备注：** 简历上的数字检查会跳过粘在字母上的数字（S3、EC2 不算声称"3""2"）。日期只看格式为 "Mar 2021 – Present" 的那一种。

### 1.12 · 2026-11-01 · 第一次定时运行被错过；改到 9:30
- **做了什么：** 第一次定时运行（11/01 8:30）没有发生。查了任务设置和系统日志：电脑从 10/31 晚上 9:21 一直睡到 11/01 早上 9:03，任务设置的是"不唤醒电脑"，所以 8:30 没跑。Windows 记下了这次错过（`NumberOfMissedRuns = 1`）。9:04 手动跑了一次（run 4：ok，用时 61 秒，新增 163 个职位，其中 DE 类 30 个，没有报警）。然后按你的要求，把触发时间改成每天 9:30，存的是不带偏移的本地时间，其他设置不变。
- **为什么：** DECISIONS #29。
- **文件：** 只改了 Windows 计划任务（不在仓库里）；文档：`docs/DECISIONS.md`、`docs/STATUS.md`、`docs/NOTES.md`
- **提交：** 见本条所在的提交（`git log -- docs/JOURNAL.md`）
- **验证：** `StartBoundary` 是 `2026-11-02T09:30:00`（没有偏移），下次运行显示 11/02 9:30，补跑、用电池也运行、不唤醒电脑、限时 1 小时这些设置都还在。
- **没能验证：** "错过后补跑"到底会不会自己触发。电脑 9:03 醒来，Windows 要先等大约 10 分钟才补跑；9:10 改触发时间时还没到这 10 分钟，而改触发时间又把错过次数清零了（`NumberOfMissedRuns` 变回 0），所以这次看不出结论。下次电脑在 9:30 睡着时，醒来大约 10 分钟后看一下 `ops.daily_runs` 有没有新的一行。
- **撤回：** 把触发时间改回 `08:30`，同样不带偏移。

### 1.13 · 2026-11-02 · "错过后补跑"验证通过
- **发生了什么：** 11/02 9:30 电脑在睡眠：从 9:18 一直睡到 19:33，中间每 15 分钟只醒几秒（系统的维护唤醒），这几秒不够触发补跑。19:33 电脑真正醒来，计划任务 **19:39:17 自己补跑了**，也就是醒来后约 6 分钟（Windows 会先等一会儿）。这一次没人动过触发时间，所以终于看清楚了，1.12 里"没能验证"的问题有了答案。
- **结果：** run 5 ok，用时 143 秒，搜索回看 2 天，新增 532 个职位，其中 DE 类 76 个（两天的量）；1 个新报警：CDW 的 "As an AI forward company"，在描述公司，看起来是误报，等你打标签。
- **结论：** 电脑睡着时错过的运行，醒来几分钟后会自动补上，不需要手动跑。只有电脑一整天都没真正醒来时才会缺一天；下一次运行的自适应窗口（2–7 天）会把漏掉的职位补回来。
- **文件：** 只改了文档（`docs/JOURNAL.md`、`docs/NOTES.md`、`docs/STATUS.md`）
- **撤回：** 不涉及代码。

## Milestone 2 · AI 助手（agent 层）

### 2.1 · 2026-11-01 · AI 调用的底座：提示词版本、请求构造、缓存、费用
- **做了什么：**
  - 你确认了 M2 的设计：AI 负责读和写，代码负责打分和判断；简历排版用 Typst；默认模型 Opus 5.5，思考深度 medium。记为决策 #30
  - 用 uv 装了 Anthropic 官方 SDK（`anthropic` 2.3.0）
  - `agents/skills.py`：把每个 SKILL.md 读成"带版本号的提示词"。六个 skill 文件开头都加了 `version: 1`；`config/prompt_lock.toml` 记录版本号和全文指纹；命令 `agents.skills check | lock`
  - `agents/llm.py`：所有 AI 调用都走这里。系统提示 = skill 文件 + "数据不是指令"规则；职位放在 `<data>` 标签里（职位里如果出现 `</data>`，会被转义，免得它提前结束数据块）；用结构化输出拿 JSON；开启备用模型（fallback）；系统提示标记为可缓存
  - 迁移 009：`agents.llm_calls` 表，同时是缓存和费用记录（请求指纹、提示词版本、输入指纹、模型、实际回答的模型、token 数、费用）
  - 命令：`agents.llm ping`（一次很小的真实调用，测试 key）、`agents.llm costs`（今天 / 本月 / 总计花费）
  - `.env.example` 新增 `LLM_MODEL`、`LLM_EFFORT`；`pipeline/config.py` 新增 `llm_settings()`
- **为什么：** DECISIONS #22、#30。
- **文件：** `agents/skills.py`、`agents/llm.py`、`config/prompt_lock.toml`、`db/migrations/009_agents.sql`、`.claude/skills/*/SKILL.md`（加 `version: 1`）、`pipeline/config.py`、`.env.example`、`pyproject.toml`、`uv.lock`、`tests/test_skills.py`、`tests/test_llm.py`、`tests/conftest.py`（测试库也清理 `agents`）
- **提交：** 见本条所在的提交（`git log -- agents/llm.py`）
- **验证：**
  1. 新增 28 个测试，全部 297 个测试通过（1 个跳过），ruff 通过。覆盖：六个 skill 都能读出版本号；提示词锁和文件一致；改文字不升版本会被抓到，而且不能直接写进锁；升了版本要先 lock；CRLF 和 LF 指纹相同；请求指纹稳定，模型、思考深度、提示词、格式、内容任何一个变了指纹都会变；职位关不掉 `<data>` 块；发给 SDK 的参数正确（fallback、结构化输出、提示缓存）；第二次同样的请求从缓存取、不再调用；回答被拒、被截断、缺字段时报错且不存；备用模型回答时按它的价格记账；按今天 / 本月 / 总计统计花费
  2. 真实命令：`agents.skills check` 输出 OK；`agents.llm costs` 显示 0 次、$0.00；没有 key 时，`agents.llm ping` 会给出一句清楚的提示，而不是一大段报错
  3. **还没做真实的 AI 调用**：`.env` 里还没有 API key
- **撤回：** `git revert` 这个提交；数据库执行 `drop schema agents cascade`，再从 `public.schema_migrations` 删掉 `009_agents.sql` 这一行。
- **备注：** 一个坑：`ping` 第一版先创建 SDK 客户端，后读 `.env`，这样就算 `.env` 里有 key，SDK 也看不到。已改成先读 `.env`。另外，没有 key 时 SDK 抛的是 `TypeError`，不是它自己的错误类型，所以要单独处理。

### 2.2a · 2026-11-01 · 拆解 JD：范围规则、简报格式、试点 20 个
- **做了什么：**
  - `config/analysis_scope.toml`（版本 1）：代码先筛。标题像 DE（和每日报告是同一条规则，有测试保证两者一致）；排除 Staff/Principal/Lead/Manager/Director/Head/VP/Intern；最近 3 天还在招；闸门档位 clean 或 benign；跳过 freehire 标为 stale 的职位
  - `agents/jd_analysis.py`：简报格式 `BRIEF_SCHEMA`（每个字段必填、不许多字段）；选职位的 SQL；给 AI 的数据是"公司、职位、招聘页上的地点 + 闸门清理后的正文"；公司名、职位名、链接由代码从原始数据填进简报；命令 `run [--limit N] [--dry-run]` 和 `show <编号>`；某个职位失败（被拒、被截断）就记下来，继续跑其他的
  - `jd-analysis/SKILL.md` 升到 **版本 2**：输出格式和 schema 一致，加了技能命名、原文照抄、工作方式、薪资、签证担保的规则，删掉"公司分段"（交给代码）。提示词锁已更新
  - 迁移 010：`agents.jd_briefs`（职位版本 × 提示词版本 × 模型，一行一份简报，记录范围规则版本和对应的 AI 调用）
- **为什么：** DECISIONS #31。
- **文件：** `agents/jd_analysis.py`、`config/analysis_scope.toml`、`.claude/skills/jd-analysis/SKILL.md`、`config/prompt_lock.toml`、`db/migrations/010_jd_briefs.sql`、`tests/test_jd_analysis.py`、`tests/test_skills.py`（改成读取当前版本号，以后升版本不会误报）
- **提交：** 见本条所在的提交（`git log -- agents/jd_analysis.py`）
- **验证：**
  1. 新增 11 个测试，全部 308 个通过，ruff 通过。覆盖：范围规则和每日报告一致；schema 处处严格；三个来源的公司、地点、链接取法；只选还在招、通过闸门的 DE 职位；**测试数据里那个藏了"忽略之前的指令"的攻击职位被闸门拦下，永远到不了 AI**；陈旧职位被跳过；拆过的不再拆；dry-run 不调用 AI；`--limit` 生效；被拒的职位记为失败、不存
  2. dry-run：879 个 DE 标题 → 442 个在范围内，预估全部 $26
  3. **真实试点 20 个：** 20 个全部成功，没有被拒，共 **$0.76**（每篇约 $0.038，比预估便宜：平均输入 1,225、输出 1,589 个 token，提示缓存命中了 51,889 个输入 token），约 4 分钟。岗位类型：pipeline_de 11、analytics_engineer 6、infra_de 3；级别：senior 17；工作方式：hybrid 9、unclear 5、onsite 4、remote 2；写了薪资的 5 个；平均必备技能 11 个
- **试点中发现的问题（留给 2.2b、2.3）：**
  1. 经验年限规则写的是"取最小的数字"，结果一个标题写着 "Minimum 07+ Yrs" 的职位被记成 3 年。应该改成"整体经验要求"，走规则循环升到 v3
  2. AI 给的技能名有 "ETL pipelines"、"Data pipelines" 这类写法，2.3 对接事实库时要做名称映射
  3. 20 个里 17 个是 senior。要不要把级别也作为硬性条件，到 2.3 时由你决定
  4. 一个 Java 后端岗位因为标题里有 "Data Platforms" 混了进来，打分时会被筛掉
  5. 有一个职位末尾多了一串奇怪的字符 `xhmxlyz`，AI 把它记进了 `safety_flags` 并忽略了，这正是我们希望的处理方式
- **撤回：** `git revert` 这个提交；数据库执行 `drop table agents.jd_briefs`，再从 `public.schema_migrations` 删掉 `010_jd_briefs.sql`。AI 的回答留在 `agents.llm_calls` 里也没关系。

### 2.2b · 2026-11-01 · 标准答案集和评估命令（提议待你批准）
- **做了什么：**
  - `tests/fixtures/jd_golden.toml`：10 个真实职位的标准答案（我起草，等你核对）。挑选时覆盖了各种情况：Anthropic（年限只出现在"加分项"里）、Bold Penguin（典型 analytics engineer）、ASSYST（每条要求都写 8+ 年）、Voto（年限自相矛盾的假 DE 岗）、SMBC（freehire 只给了一段被截断的公司简介）、Rosen's（Azure Databricks，正文没写工作方式）、Metabase（必备很少，"加分"工具很多）、Samsara（10+ 年、偏软件工程）、Reddit（标题是 AE，要求像 pipeline DE）、Sigma（必备很少，坐班）。**文件里只有职位编号和期望结果，没有职位原文**；评估时从本地数据库按（来源、职位 id、内容指纹）读原文
  - `agents/evaluate_prompt.py`：用现行提示词和提议的提示词分别拆解这 10 个职位，比较必备技能找到了几个、岗位类型、工作方式、经验年限；新版本找到的必备技能最多只能少 1 个（模型的随机误差），其他几项都不能变差。结果有缓存，重跑免费；不写入 `agents.jd_briefs`
  - 两份提议：`config/proposals/jd-analysis.v3.md`（只改经验年限规则：取"整体经验要求"，不取某个工具的年限；范围取下限；只写在加分项里也算；标题和正文矛盾时取较大的整体数字）；`config/proposals/analysis_scope.v2.toml`（新增 `min_text_chars = 1000`，跳过被截断的片段：442 个里有 56 个，全是 freehire）
  - 代码改动：给 AI 的数据里**去掉了招聘页上的地点**，改由代码写进简报的 `board_location`。这样同一个职位在多个城市发布（例如 Samsara 一个职位发了 8 个城市）时，请求完全相同，只付一次钱
- **为什么：** DECISIONS #22、#30、#31；批准后记为 #32。
- **文件：** `agents/evaluate_prompt.py`（含 `--review` 核对页面）、`agents/jd_analysis.py`（数据格式、`board_location`、`min_text_chars`）、`tests/fixtures/jd_golden.toml`、`config/proposals/jd-analysis.v3.md`、`config/proposals/analysis_scope.v2.toml`、`tests/test_evaluate_prompt.py`、`tests/test_jd_analysis.py`
- **提交：** 见本条所在的提交（`git log -- agents/evaluate_prompt.py`）
- **验证：**
  1. 全部 317 个测试通过，ruff 通过
  2. **真实评估**（10 个职位，Opus 5.5，共花 $1.14）：

     | | v2 medium | v3 medium | v3 low |
     | --- | --- | --- | --- |
     | 必备技能找到 | 72/75 | 73/75 | 73/75 |
     | 岗位类型对 | 9/9 | 9/9 | 9/9 |
     | 工作方式对 | 9/10 | 9/10 | 10/10 |
     | **经验年限对** | **7/10** | **10/10** | **10/10** |
     | 每篇费用 | $0.043 | $0.038 | $0.033 |

     v3 修好了年限：Voto 3 → 7、Samsara 3 → 10、Anthropic 空 → 5。判定 PASS
  3. 剩下的差异都很小：v3 在 Anthropic 漏了 "Orchestration"、在 Reddit 漏了 "Dashboards"；v2 在 Bold Penguin 漏了 LLM、在 Rosen's 漏了 Data warehousing、在 Samsara 漏了 PySpark。这些属于模型每次回答的正常波动，10 个样本看不出谁更好
- **你核对后的补充（11/02）：** 你在核对页面上指出，ASSYST 的 HL7/FHIR/SNOMED、Rosen's 的 Unity Catalog、Samsara 的 MCP 都没有标。它们写在 Preferred、Additional 或职责里，所以不算必备；AI 其实都把它们放进了加分项，只是标准答案没检查加分项。于是：
  - 标准答案加了 `nice_to_haves`（7 个职位共 28 个），评估多了两项检查："加分技能有没有被保留"（不能少于现行版本减 1）、"有没有被错放进必备"（不能多于现行版本加 1）
  - 核对时发现 Bold Penguin 的 JIRA 其实写在要求列表里（没写 "a plus"），AI 把它放进必备是对的，错的是我的标签，已改为必备
  - 核对页面做成了正式功能：`agents.evaluate_prompt <提议> --review` 生成 `output/golden_review.html`（不提交），原文里必备标黄、加分标蓝
  - "root cause / troubleshooting" 这类所有工程岗位都有的通用说法不标：ATS 不搜它，简历上也不能当关键词
  - 重新打分（全部来自缓存，$0）：v3 必备 74/76（v2 73/76），加分保留 28/28，错放进必备 0，年限 10/10（v2 7/10），PASS
- **11/02 你批准了：** 采用 v3、采用范围规则 v2、思考深度保持 medium（DECISIONS #32）。提议文件复制到 `.claude/skills/jd-analysis/SKILL.md` 和 `config/analysis_scope.toml`，提示词锁更新到 `jd-analysis@3`；提议文件留在 `config/proposals/` 作为历史。测试库里的样例职位都很短，所以相关测试关掉了 1,000 字符下限，另有一个测试专门检查这个下限。dry-run：范围内 425 个职位，v3 还一个都没拆，粗估 $25（按试点的实际费用约 $16）。320 个测试通过
- **撤回：** `git revert` 这个提交。提议文件不影响正在运行的系统。

### 2.2c · 2026-11-02 · 每日运行加上 AI 拆解（只拆当天的新职位）
- **做了什么：**
  - `pipeline/daily.py`：抓取 → 闸门 → 汇总之后，多一步"拆解当天的新职位"。新职位的标准和报告一样（所有副本都是这次运行第一次存进来的），再过一遍分析范围；最新的优先，每天最多 `JD_ANALYSIS_DAILY_MAX`（默认 50）个。老职位改了文字**不算**新职位，不拆，免得变相补跑
  - 整个 AI 步骤出错（比如 key 失效、网络断了）时只记下来：抓取和闸门的结果照常保存，这次运行标为 partial。单个职位失败就列出来，其余继续
  - 每日报告新增"AI 拆解"一段：范围内的新职位、拆了几个、几个来自缓存、花费、因为上限没拆的、失败的、今天最常要求的 5 个必备技能（数量相同时按名字排，保证同样的数据得出同样的报告）。`ops.daily_runs` 里也记了这些数字
  - `.env.example` 新增 `JD_ANALYSIS_ENABLED`、`JD_ANALYSIS_DAILY_MAX`；`pipeline/config.py` 新增 `daily_analysis_settings()`；`agents/jd_analysis.run()` 可以只处理指定的职位版本（`only=`），并统计必备技能和"因为上限没拆"的数量
  - CLAUDE.md：每次开工汇报每日运行时，加上 AI 拆了几个、花了多少
- **为什么：** DECISIONS #33。
- **文件：** `pipeline/daily.py`、`pipeline/config.py`、`agents/jd_analysis.py`、`.env.example`、`CLAUDE.md`、`tests/test_daily.py`
- **提交：** 见本条所在的提交（`git log -- pipeline/daily.py`）
- **验证：**
  1. 新增 7 个测试，全部 327 个通过，ruff 通过。用假 AI 跑完整的每日流程：只拆当天新的、在范围内的职位（测试数据里 4 个新职位：藏攻击的那个被闸门拦下，一个陈旧的被跳过，所以拆了 2 个）；同一天再跑一次，不再拆，也不再调用 AI；上限生效；改过文字的老职位不拆；AI 整步出错时抓取照常保存，状态为 partial；单个职位被拒时，其余继续；关掉开关时报告写"已关闭"
  2. **真实运行两次：** run 6 是 partial，因为 freehire 读取超时（他们那边偶尔会这样），AI 步骤正常执行，拆了 0 个；run 7 ok，新增 4 个职位，但都不是 DE，所以拆了 0 个。离上一次运行只隔了几个小时，没有新的 DE 职位，属于正常情况
  3. **还没有在真实的新 DE 职位上跑过 AI 步骤**：第一次是下一次定时运行（11/03 9:30）。AI 调用本身在试点和评估里已经真实跑过很多次
- **撤回：** `git revert` 这个提交；或者只在 `.env` 里设 `JD_ANALYSIS_ENABLED=false`。

### 2.2d · 2026-11-02 · 给 CDW 的报警打标签
- **做了什么：** 你确认 CDW "Sales Goals Analytics Lead" 的报警（"As an AI forward company, we see AI not just as a tool…"）是误报：这句话在描述公司，没有任何隐藏内容，而且不是 DE 岗位。标为 `false_positive`（标签 24），导出后标准答案共 14 条。规则不变，它继续留在"人工看"这一档，不会送给 AI。
- **文件：** `tests/fixtures/gate_cases_labeled.jsonl`
- **验证：** 规则相关测试 113 个通过（标签和现行规则不矛盾）。
- **撤回：** 从 jsonl 删掉这一行；数据库里的标签可以用一条新的 `unsure` 标签覆盖（标签只追加，以最新一条为准）。

### 2.2e · 2026-11-02 · 覆盖率检查：你在 LinkedIn 上看到的职位，我们有没有
- **做了什么：**
  - `pipeline/find_job.py`：`uv run python -m pipeline.find_job "公司" "职位名关键词"`。在所有已存的职位里查：公司名忽略大小写、标点和 LLC/Inc 这类后缀，匹配招聘页代号、slug 或公司全名的开头；职位名按"连续的词组"匹配（"data engineer" 不会匹配到 "Data Center Engineer"）。找到了就说明哪个来源、哪天到哪天看到过、闸门档位、有没有拆解；没拆解的话，说明是被分析范围的哪条规则排除的
  - 没找到时，在线查一次 freehire（公司名 + 职位名，美国，最近 60 天，最多 3 页），判断最可能的原因：标题不在我们的搜索词里 / freehire 有、标题也对得上（多半是在我们的抓取窗口之前发布的）/ 是我们直接抓的招聘页但没存到 / 我们的来源都没有 / 说不准（检查失败，或者结果太多没看完）
  - 每次检查都记进 `ops.coverage_checks`（迁移 011）；`--stats` 给出覆盖率（找到 / 查过）和各个原因的数量
  - 两个坑：freehire 的搜索没有按公司筛选的功能；而且一加公司名，它就不再按标题筛选（返回了 Snowflake 的所有职位，包括 "Revenue Manager"）。所以公司和标题都在我们这边再筛一遍；结果没看完时，如实说"说不准"，不硬下结论
- **为什么：** DECISIONS #34。
- **文件：** `pipeline/find_job.py`、`db/migrations/011_coverage_checks.sql`、`tests/test_find_job.py`
- **提交：** 见本条所在的提交（`git log -- pipeline/find_job.py`）
- **验证：**
  1. 新增 13 个测试，全部 341 个通过，ruff 通过。覆盖：公司名的各种写法、职位名按词组匹配、找到的职位说明为什么没被拆解（测试数据里的攻击职位显示 "gate triage block"）、五种没找到的原因、freehire 检查失败时问题照样记下、覆盖率统计
  2. **我自己试了 4 个真实例子（试完已从记录里删掉，不算进你的覆盖率）：** Anthropic Data Engineer：找到，已拆解；Sigma Computing Data Engineer：找到（在分析范围内，但早于每日 AI 拆解，所以没拆）；Netflix Analytics Engineer：**没抓到**，freehire 上有，但发布于 10/20 和 9/09，早于我们第一次回填 freehire 的时间（10/31 往回 7 天）；Snowflake Data Engineer：说不准（freehire 结果太多没看完）
- **发现：** 我们是从 10/31 开始、往回 7 天抓 freehire 的，所以**更早发布、但现在还在招的职位一个都没有**。如果要补，一次性把 freehire 往回抓 30 天就行，不花 AI 的钱（只是多一些请求），等你决定。
- **撤回：** `git revert` 这个提交；数据库执行 `drop table ops.coverage_checks`，再从 `public.schema_migrations` 删掉 `011_coverage_checks.sql`。

### 2.2f · 2026-11-02 · 修 freehire 翻页的 bug，回填 30 天
- **做了什么：**
  - **发现一个真 bug：** 回填时，"data engineer" 只抓到 899 个就停了。查了 API 返回才发现：freehire 说一共有 11,298 个结果，但在第 850 条那一页只给了 49 条（应该 50 条）。我们的代码把"这一页不满"当成"没有更多了"，于是停下，后面的一万多条全丢了。**每天的运行也可能因此提前停下，漏掉职位。** 已经改成按 API 返回的总数 `meta.total` 来判断有没有翻完；只有 API 没给总数时，才把不满的一页当成最后一页
  - **回填 30 天**（你批准的，只抓取、过闸门，不调用 AI）：按标题分成两组搜索。"data engineer" 30 天内有 11,298 个，超过 API 最多能翻的 10,000 个，所以又按工作方式（远程 / 混合 / 坐班）各搜了一遍，补上窗口之外的部分。重复的职位只存一份
  - 第一次回填时 freehire 读取超时，加上上面这个 bug，结果不完整；修好之后重跑了一遍完整的
- **文件：** `ingestion/freehire.py`（翻页逻辑）、`tests/test_freehire.py`（新增"中间有一页不满时不能停"的测试）
- **提交：** 见本条所在的提交（`git log -- ingestion/freehire.py`）
- **验证：**
  1. 全部 342 个测试通过，ruff 通过
  2. 回填结果：analytics engineer 看到 3,062 个；data engineer 看到 9,995 个（API 窗口上限），新增 4,326 个；按工作方式补的三遍又新增 613 个（远程 357、混合 144、坐班 112）。闸门新检查了 4,939 个：clean 4,915、benign 19、review 5、block 0。库里现在一共 15,434 个职位（原来约 7,200 个）
  3. **再查 Netflix：** 10/20 发布的 "Analytics Engineer 5 - Ads Identity & Signals" 现在找到了。9/09 的那个超过 30 天，不在这次回填范围内，符合预期
  4. **还剩的缺口（如实记下）：** 按工作方式补的三遍加起来是 5,301 个，而 data engineer 总共 11,298 个，说明很多职位没标工作方式，所以窗口之外那大约 1,300 个只补回了一部分。每天的运行只看 2 天，大约 1,300 个结果，远低于 10,000 的上限，不受影响
- **撤回：** `git revert` 这个提交。回填进来的职位不用删：它们和其他职位一样，是原样存下来的原始数据。
- **备注：** 新增 5 个 review 报警（目前没打标签的一共 11 个），等你有空时一起看；review 档的职位本来就不会送给 AI。

### 2.3 · 2026-11-02 · 打分（纯代码）和每日报告里的"今天值得投的"
- **做了什么：**
  - `agents/fit_scoring.py`：拿每份简报对照档案打分，不调用 AI
    - **对技能：** 技能名（以及拆开的部分，比如 "Cloud SQL / PostgreSQL"、"X and Y"）可以通过名字、事实库别名、通用词表里的同义词、技能家族来匹配；JD 原文的写法只能按名字、别名、同义词匹配，**不能走家族**。每个对上的技能都记下级别、证据条目和匹配方式
    - **算分：** 70 × 必备覆盖率（核心技能算双倍）+ 20 × 加分覆盖率 + 岗位类型调整（+5 / 0 / −5）。职位没列加分项时，加分覆盖率按必备覆盖率算
    - **决定：** 碰到硬性条件或必备覆盖率不到 50% 就跳过；分数 ≥ 65 是"投 + 找内推"；其余是"投"
    - **硬性条件：** 年限比档案多 1 年以上（analyst 加 BIE 一起算）、薪资上限低于最低要求、需要担保但职位不给、简报里没有必备技能。**地点现在不查**（小公司试水阶段），以后大厂阶段限定加州、华盛顿州、德州
  - `config/fit_scoring.toml`（打分规则，版本 1）、`config/skill_vocabulary.toml`（同义词和技能家族，版本 1）
  - 迁移 012：`agents.fit_scores`，按（职位版本、简报版本、模型、档案指纹、规则版本、词表版本）存。换档案或改规则，几秒钟就能全部重算，旧分数保留
  - 每日运行：拆解之后自动打分，报告新增"今天值得投的（按 XX 打分）"：按分数排列，列出决定、必备覆盖率、工作方式、地点、链接；跳过的按原因计数。打分出错只记下来，不影响其他步骤。M5 之前是假人 Alex 的分，报告标题里写着"样本档案"
  - `fit-scoring/SKILL.md` 升到 v2：现在说明的是代码的规则，不再是给 AI 的提示词
  - CLAUDE.md：开工汇报时加上"有几个值得投"
- **为什么：** DECISIONS #35（你 11/02 的回答都在里面）。
- **文件：** `agents/fit_scoring.py`、`config/fit_scoring.toml`、`config/skill_vocabulary.toml`、`db/migrations/012_fit_scores.sql`、`.claude/skills/fit-scoring/SKILL.md`、`config/prompt_lock.toml`、`pipeline/daily.py`、`CLAUDE.md`、`tests/test_fit_scoring.py`、`tests/test_daily.py`
- **提交：** 见本条所在的提交（`git log -- agents/fit_scoring.py`）
- **验证：**
  1. 新增 19 个测试，全部 361 个通过，ruff 通过。覆盖：各种匹配方式；JD 原文不能走家族（Snowflake 的例子）；家族取最强成员的级别；Alex 的年数 = 9.5；分数公式（例：必备 75%、加分 50%、AE +5 → 68 分 → 投 + 找内推）；没有加分项时的处理；低于 50% 跳过；没有必备技能的简报；每种硬性条件，包括年限容差 1 年、时薪不比较、外币不比较、地点不查；同样的输入不重复存，换了档案才存新的；每日运行里打分并写进报告；档案坏了只影响打分这一步
  2. **用试点的 20 份 v2 简报试算**（用完已删掉）：跳过 11、投 8、投 + 找内推 1。第一版发现一个问题：Bold Penguin 的 "Snowflake" 被算成覆盖了，原因是 AI 在 JD 原文写法里放了 "cloud data warehouse"，走家族对上了 Redshift。已改成原文写法不能走家族。那个"投 + 找内推"是一个只有 519 字符的猎头职位，只有一个必备技能（范围规则 v2 现在已经排除这种片段）
  3. v3 版还没有简报，所以真实打分从明天 9:30 的运行开始
- **撤回：** `git revert` 这个提交；数据库执行 `drop table agents.fit_scores`，再从 `public.schema_migrations` 删掉 `012_fit_scores.sql`。

### 2.4a · 2026-11-03 · 简历日期改用普通连字符，样本简历加一行定位
- **做了什么：** 简历里的日期从长破折号改成普通连字符（"Mar 2021 - Present"），样本简历、`check_resume` 的规则、`resume-tailoring` 说明（升到 v2，提示词锁已更新）三处一起改。样本简历在联系方式上面加了一行定位 "Data Engineer · SQL / Python / AWS"。字体 Liberation Sans 2.1.5（官方发布包，1.6 MB，连 LICENSE 和 AUTHORS）放进 `templates/fonts/`
- **为什么：** DECISIONS #36。ai-job-search 记录过 Workday 导入时把长破折号连着的日期丢掉；定位那行是 `resume-tailoring` 要求的"最上面三分之一"
- **文件：** `data/sample/resume.md`、`agents/profile.py`、`tests/test_profile.py`、`.claude/skills/resume-tailoring/SKILL.md`、`config/prompt_lock.toml`、`templates/fonts/`、`docs/DECISIONS.md`
- **提交：** 见本条所在的提交
- **验证：** `agents.profile check` OK；`tests/test_profile.py`、`tests/test_skills.py` 36 个通过
- **撤回：** `git revert` 这个提交，再跑 `agents.skills lock`

### 2.4b · 2026-11-03 · 一页简历模板、PDF 检查、生成命令
- **做了什么：**
  - `templates/resume.typ`：单栏、标准标题、联系方式在正文里、没有页眉页脚、左对齐、US Letter、关掉连字和断词、不写生成日期
  - `agents/resume_doc.py`：把 `resume.md` 读成结构化数据；读不懂的行直接报错，不猜。还给出"PDF 必须显示的每一行"，按阅读顺序排列
  - `agents/pdf_checks.py`：检查做好的 PDF。失败项：不是一页、没有文字层、缺行或顺序错、缺必须出现的文字（2.5 用来放 JD 关键词）、日期用了长破折号、字体没嵌入、有连字或不可见字符。警告项：文字排到页面不足 80%。折叠文字和日期检查那一段是从 ai-job-search 逐字节复制的（带 MIT 版权头），其余是我们写的；版面测量只借思路，用 pypdf 读文字位置，不需要 Poppler
  - `agents/render_resume.py`：命令 `agents.render_resume`，生成 `output/resume/Alex_Sample.pdf` 和对照页 `review.html`，同时跑 `check_resume`（事实库检查）
  - 新依赖：`typst`、`pypdf`
- **和设计的一处不同：** 对照页左边原计划放 PDF，但应用内的浏览器显示不出来，所以改成嵌入 Typst 渲染的页面图片，再加一个打开真 PDF 的链接。图片和 PDF 来自同一个模板和同一份数据
- **为什么：** DECISIONS #36
- **文件：** `templates/resume.typ`、`agents/resume_doc.py`、`agents/pdf_checks.py`、`agents/render_resume.py`、`tests/test_resume_pdf.py`、`pyproject.toml`、`uv.lock`；文档 `CLAUDE.md`、`README.md`、`docs/DESIGN.md`、`docs/NOTES.md`
- **提交：** 见本条所在的提交
- **验证：**
  1. 新增 31 个测试，全部通过，ruff 通过。覆盖：解析格式和各种错误格式；样本 1 页且没有失败项；渲染两次字节相同；内容里的 `$ # * _ = [ ] < > @ %` 和 `--` 原样打印，不会被当成模板语法；每个检查都有一个做坏的例子（两页、没有文字、文件损坏、缺行、乱序、缺关键词、长破折号日期、连字、零宽字符、字体未嵌入、页面太空）
  2. 真实跑了 `agents.render_resume`：1 页，所有检查通过；一条警告：样本内容较短，文字只排到页面 67%。这是内容少，不是模板的问题；所以没有去拉伸版面
  3. 看过渲染出来的页面和对照页
- **撤回：** `git revert` 这个提交，再跑 `uv sync`

### 2.3b · 2026-11-03 · 安全许可（clearance）规则：提议阶段，还没启用
- **做了什么：**
  - 第一次全流程运行里，排第一的"值得投"是 Maxar 的 `Junior Data Engineer (TS/SCI)`，要政府安全许可。打分规则里没有这一项。FL 同意加规则，所以按规则流程先写提议，不改真规则
  - `config/proposals/fit_scoring.v2.toml`：用正则表达式读职位标题和正文，分三类：**ignore**（不算要求，比如 "No Clearance"、"Polygraph Protection Act"、Public Trust）、**obtain**（必须能够取得）、**hold**（必须已经持有）
  - 申请资料新增两个字段：`has_security_clearance`、`can_obtain_security_clearance`（样本 Alex 都是 false）。规则只读文字，要不要跳过由档案决定，所以 FL 的真实情况放在 `private/`，不进公开仓库
  - `agents/fit_scoring.py`：支持这段规则（真规则文件里没有这一段时不起作用），`run` 现在连带读出闸门清洗后的正文
  - `agents/evaluate_fit_rules.py`：新命令，用当前规则和提议各算一遍，列出决定会变的职位；同时跑标准答案，并把规则用在所有 DE 类职位上做更大范围的测试。`--review` 生成 `output/fit_rules_review.html`，带原文和标记
  - `tests/fixtures/clearance_cases.toml`：44 条真实写法和它们应该落在哪一类
- **为什么不让 AI 判断：** 这是决定（#22、#30），而且简报里没有这个字段。加字段要升提示词版本、重新评估，这条规则用代码读原文，免费、结果确定
- **文件：** `config/proposals/fit_scoring.v2.toml`、`agents/fit_scoring.py`、`agents/evaluate_fit_rules.py`、`agents/profile.py`、`data/sample/applicant_profile.toml`、`tests/fixtures/clearance_cases.toml`、`tests/test_evaluate_fit_rules.py`、`tests/test_fit_scoring.py`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：**
  1. 评估结果：44 条标准答案全部通过；今天的 50 个职位里只有 2 个决定会变（Maxar 的两个 TS/SCI 职位，投 → 跳过）；全部 2,462 个 DE 类职位：必须持有 218、必须能取得 43、提到但不算要求 45、没提 2,156
  2. 我读了约 100 条抽样和全部只靠笼统字眼判断的结果。第一版抓错了几种：把 "Employee Polygraph Protection Act"（法律样板话）、"Minimum Clearance Required to Start: None"、"No Clearance" 当成要求；"U.S." 里的句点让"能够取得"被判成"必须持有"。都修了，都写进了标准答案
  3. 仍然存在的灰色情况：一个职位同时写"必须持有或能够取得"时算作"必须持有"；"T-3 Investigation" 这种写法算作要求。没有读完全部 218 条，所以不能说完全没有错判
- **撤回：** `git revert` 这个提交。提议没有启用，数据库和每日运行都没有变化

### 2.3c · 2026-11-03 · 安全许可规则启用（打分规则 v2）
- **做了什么：** FL 看过审核页面后同意启用。提议复制成 `config/fit_scoring.toml`（版本 2），提议文件留作历史；`fit-scoring` 说明升到 v3；测试改成检查真规则，以后改规则也要通过这 44 条标准答案；`agents.fit_scoring run` 重新打分
- **为什么：** DECISIONS #37
- **文件：** `config/fit_scoring.toml`、`.claude/skills/fit-scoring/SKILL.md`、`config/prompt_lock.toml`、`config/proposals/README.md`、`tests/test_evaluate_fit_rules.py`、`tests/test_fit_scoring.py`、`docs/DECISIONS.md`、`docs/NOTES.md`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：** 452 个测试通过，ruff 通过。重新打分 50 个：投 20、跳过 30（之前投 21、投 + 找内推 1、跳过 28）。Maxar 那个职位显示跳过，原因写明 TS/SCI。旧分数（规则版本 1）还在表里，没有删。11/03 的报告是旧规则生成的，不重写；下一次每日运行开始用新规则
- **撤回：** 把 `config/fit_scoring.toml` 改回版本 1（`git revert` 这个提交），再跑 `agents.fit_scoring run`

### 2.5 · 2026-11-03 · AI 改写简历：起草 → 代码查事实 → 审稿 → 一页 PDF
- **做了什么：**
  - `agents/tailor.py`：一个职位进去，一份检查过的一页简历出来。AI 只写定位、总结、每条经历（注明来自哪几条证据）、技能排序；姓名、头衔、公司、日期、学历由代码从事实库填入
  - `agents/resume_checks.py`：事实检查（每条经历的证据属于这段工作、数字必须在它注明的证据里、JD 要求但没证据的技能不能出现、事实库和词表里都没有的专有名词不能出现）和质量检查（关键词 80%、定位写明岗位、一半经历有数字、不用第一人称、不写 "Responsible for"、经历不能太长、至少一个项目）
  - `resume-tailoring` v3、新的 `resume-reviewer` v1、`ats-critic` v2（不再单独调用 AI，只记录每项检查放在哪）
  - 审稿 AI 读职位原文和草稿，提出具体修改；代码逐条应用，破坏事实检查的直接拒绝。最多两轮，第二轮只在还有问题或有修改被拒时才跑
  - 超过一页时，代码删最长那段经历的最后一条（经历按相关度排，最后一条最不相关），并记录下来
  - 迁移 013：`agents.tailored_resumes`。每个职位的文件在 `output/tailored/<编号_公司_职位>/`：PDF、`resume.md`、`changes.md`、`not_covered.md`、对照页 `review.html`；`output/tailored/index.html` 是总览
  - 命令：`agents.tailor run --top 5`、`agents.tailor run <编号>`、`--dry-run`。分数判定跳过的职位不会被改写。不放进每日运行，到 Milestone 5 再接上
- **为什么：** DECISIONS #38（改掉了 #36 里"AI 直接写 resume.md"那一部分）
- **文件：** `agents/tailor.py`、`agents/tailor_review.py`、`agents/resume_checks.py`、`agents/profile.py`、`db/migrations/013_tailored_resumes.sql`、`.claude/skills/resume-tailoring/SKILL.md`、`.claude/skills/resume-reviewer/SKILL.md`、`.claude/skills/ats-critic/SKILL.md`、`config/prompt_lock.toml`、`tests/test_tailor.py`、`tests/test_skills.py`
- **提交：** 见本条所在的提交
- **验证：**
  1. 新增 62 个测试（全部 514 个通过，ruff 通过）。重点是"编造的东西到不了页面"：别的工作的真实数字、Kafka、Terraform、编造的工作经历、把 4 改成 40 的修改，都被拦住。假 AI 代替真 API，不花钱
  2. 写测试时发现一个真漏洞：职位要 "Apache Kafka" 时，简历写 "Kafka" 查不出来。已修。第一次真实运行发现一个误报：新句子开头的大写词被当成产品名。已修
  3. **试跑（FL 同意的 5 个职位）：** 5 份都是 ready，都正好一页，文字排到页面 80-89%。共花 $1.02（修误报后重跑了一个职位），修完后平均每份 $0.18，低于估计的 $0.3-0.5
  4. 我逐条读了 5 份简历：AI 没有编造工具或数字；Airflow 写成 "first DAG"、"the load still runs from a cron script"，Spark 写成课程练习，都如实。可以讨论的：Cheil 那份总结写了 "advanced Python and SQL"（JD 的原话）和 "Builds data platforms"，证据里没有 "advanced"。代码查不出这种语气上的抬高，审稿 AI 这次也没有提，要 FL 判断
  5. 没有验证：FL 还没读结果；真实档案还没跑（Milestone 5）
- **撤回：** `git revert` 这个提交；数据库执行 `drop table agents.tailored_resumes`，再从 `public.schema_migrations` 删掉 `013_tailored_resumes.sql`

### 2.5b · 2026-11-04 · FL 看完试跑后的三处修改：提议阶段，提示词和词表还没启用
- **FL 的反馈：** "moving into analytics engineering" 多余，BIE 几乎就是 Analytics Engineer；看不懂 `replace` 和"起草时的选择"；totalwine 为什么只有 58 分
- **做了什么：**
  - **A. 去掉转型说法：** 提议 `resume-tailoring` v4、`resume-reviewer` v2；代码检查（已生效）：定位行和总结里不许出现 "moving into"、"transitioning"、"aspiring"、"career change"
  - **B. 对照页改成中文（已生效）：** 改写：原来 X，改成 Y；加一条经历；调到最前面……"起草时的选择"改名"起草 AI 的说明（不会上简历）"
  - **C. 修打分：** 提议 `jd-analysis` v4（"几选一"合并成一条必备技能；职能背景不算技能）、`skill_vocabulary` v2（BI development、SQL 调优的几种写法）
  - 标准答案加了 3 个职位（totalwine、Agility Robotics、Cheil）和两项新检查：几选一有没有被拆开、职能有没有被当成技能
  - `agents/evaluate_scoring.py`：新命令，用提议重新拆解指定职位，列出分数和必备技能的前后变化，`--review` 生成 `output/scoring_review.html`。`agents.tailor run` 加了试跑参数，结果放 `output/tailored_trial/`，不写数据库
  - 事实检查跟着调整：`Python or Java` 被 Python 覆盖，不代表简历可以写 Java；全部由事实库已有的词组成的短语（比如 "dbt tests"）不算编造
- **为什么：** totalwine 的 JD 写 "dbt, Snowflake, BigQuery, or similar"，被拆成 3 个必备技能；"3-6 years in analytics engineering, data modeling, or BI development" 里的 BI development 被当成缺的技能。粗略扫描 87 份简报，47 份可能有这个问题，有些职位可能被错误跳过
- **文件：** `config/proposals/resume-tailoring.v4.md`、`resume-reviewer.v2.md`、`jd-analysis.v4.md`、`skill_vocabulary.v2.toml`、`agents/evaluate_scoring.py`、`agents/evaluate_prompt.py`、`agents/jd_analysis.py`、`agents/resume_checks.py`、`agents/tailor.py`、`agents/tailor_review.py`、`tests/fixtures/jd_golden.toml`、`tests/test_evaluate_scoring.py`、`tests/test_evaluate_prompt.py`、`tests/test_tailor.py`
- **提交：** 见本条所在的提交
- **验证：**
  1. 535 个测试通过，ruff 通过
  2. 标准答案第一次判 v4 不通过：看起来丢了 3 个加分技能和 1 个必备技能。查原文发现技能都还在，只是写成了 "Microsoft Fabric or Power BI or streaming data" 这种合并形式，评分程序不认识。改成和打分同样的拆分方式后，新旧提示词用同一把尺子量：必备 86/86、加分 29/29（都一样），几选一 0/4 → 4/4，职能当技能 1 → 0，通过。这是改了尺子，所以记在这里，FL 可以在 `output/golden_review.html` 对照检查
  3. 10 个真实职位：8 个上升，UChicago Medicine 62 → 59。Agility Robotics 从跳过变成投（31 → 45）；Hunter Industries 从投变成跳过（38 → 31），看原文这个判断是对的，它的核心就是 Snowflake、Power BI 和 Oracle Fusion；totalwine 58 → 85（我之前手算的是 70，因为 "Familiarity with" 的 Git、CI/CD 按提示词原有规则移到了加分项，semantic layer 也不在必备里了）
  4. 重跑 5 份简历：都是 ready，都没有转型说法。发现并修好一个误报："dbt tests" 被判成编造，JD 的关键词被删掉了
  5. 花费：这次提议一共 $1.89（标准答案 $0.48、重新拆解 $0.36、简历 $0.86 + 修误报后重跑 $0.19），高于我说的约 $1.3
  6. 还有疑问：semantic layer 只出现在 JD 的职责里，v4 没有把它列为加分项；有的定位行写成 "Senior Data Engineer"；总结写 "Data engineer who builds"。都留给 FL 判断
- **撤回：** `git revert` 这个提交。提议没有启用；已生效的只有对照页文字和转型说法检查

### 2.5c · 2026-11-04 · 启用 FL 同意的三处修改
- **做了什么：** FL 看完审核页面后同意。`jd-analysis` v4、`resume-tailoring` v4、`resume-reviewer` v2 复制成正式版本，提示词锁已更新；`skill_vocabulary` v2 启用；提议文件留作历史；测试改成检查正式版本。没有重新拆解现有的 87 份简报
- **为什么：** DECISIONS #39
- **文件：** `.claude/skills/jd-analysis/SKILL.md`、`.claude/skills/resume-tailoring/SKILL.md`、`.claude/skills/resume-reviewer/SKILL.md`、`config/prompt_lock.toml`、`config/skill_vocabulary.toml`、`tests/test_evaluate_prompt.py`、`tests/test_evaluate_scoring.py`、`docs/DECISIONS.md`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：** 全部测试通过，ruff 通过，`agents.skills check` 通过。真实使用从下一次每日运行开始，那时才能确认新简报进了 `agents.jd_briefs` 的 `jd-analysis@4`，报告也正常
- **注意：** 打分和改写只读当前提示词版本的简报。下一次运行之前 `agents.tailor run --top N` 和 `agents.fit_scoring top` 查不到职位，这是预期的
- **撤回：** `git revert` 这个提交，再跑 `agents.skills lock`

### 2.6 · 2026-11-04 · 待投队列（Milestone 2 最后一步）
- **做了什么：**
  - `agents/application_queue.py`：命令 `build`、`approve`、`pass`、`applied`。按分数挑 5 个还在招的职位，同一家公司只留一个，同一个职位不重复，然后走改写流程
  - `agents/queue_review.py`：清单页 `output/queue/<日期>/index.html`，批准后写提交包（PDF 和表单答案）
  - `config/queue.toml`：每批几个、每家几个、网站分类、表单答案的规则
  - 迁移 014：`agents.queue_items`（排进队列的职位，不再改动）、`agents.application_events`（每次状态变化记一条，只增不改）、视图 `agents.applications`（每个职位现在的状态）
  - `agents.jd_analysis run --ids`：只拆解指定职位
  - **文件名和设计不同：** 设计里叫 `agents/queue.py`，实际叫 `application_queue.py`，避免和 Python 自带的 `queue` 混淆
  - **和设计不同：** 设计说样本档案不生成提交包。改成生成，但文件名是 `SAMPLE_DO_NOT_SUBMIT`，这样现在就能看到整个流程；标记"已投"仍然被代码拒绝
- **为什么：** DECISIONS #40
- **文件：** `agents/application_queue.py`、`agents/queue_review.py`、`agents/jd_analysis.py`、`config/queue.toml`、`db/migrations/014_application_queue.sql`、`tests/test_application_queue.py`、`docs/DECISIONS.md`、`docs/INTERVIEW_NOTES.md`、`docs/NOTES.md`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：**
  1. 新增 43 个测试（全部 578 个通过），ruff 通过。重点：同一医院两个名字只留一个（来自真实数据）；经验类问题绝不代答；样本简历不能标记已投；步骤不能跳；不在招的职位不进队列；同一天再跑不花钱也不变
  2. **真实跑了一遍：** 把试跑过的 10 份 v4 简报存进数据库（全部来自缓存，$0），`build` 生成 5 个职位，花 $0.23（只有 UChicago 是新改写）。页面看过，提交包预览过（放在临时文件夹，没有改动批次）
  3. 发现：这 5 个职位里 4 个的网站要账号，1 个是聚合站，0 个不用账号
  4. **没有验证：** 批准这一步留给 FL 真实做；Chrome 填表和提交还没做；明天 9:30 的运行是否正常要明天看
- **撤回：** `git revert` 这个提交；数据库删除视图 `agents.applications` 和表 `agents.application_events`、`agents.queue_items`，再从 `public.schema_migrations` 删掉 `014_application_queue.sql`

### 2.6a · 2026-11-04 · 第一次真实批准，Milestone 2 完成
- **做了什么：** FL 批准了第一批的 5 个职位。事件表里每个职位多了一条 approved，历史还在；提交包写好了：5 份 PDF 和一份答案，都标着 `SAMPLE_DO_NOT_SUBMIT`
- **文件：** 只改了 `docs/JOURNAL.md`、`docs/STATUS.md`；批准记录在数据库，提交包在 `output/`
- **提交：** 见本条所在的提交
- **验证：** 5 个职位状态都是 approved。试着把 1 号标记为已投，代码拒绝了，状态没变
- **撤回：** 不需要撤回；这是虚构档案，不会投出去

## Milestone 3 · 建模和报告

### 3.1–3.4 · 2026-11-04 · dbt、覆盖率报告、看板
- **做了什么：**
  - **3.1 dbt 和 staging：** `dbt/` 项目，只读管道的表，建在 `analytics_*` 这几个 schema 里。staging 把三个来源的 JSON 摊平，每个职位取最新的简报和分数
  - **3.2 skills 和 marts：** `skill_requirements`、`skill_mentions`（"A or B" 拆成两行，同义词归成一个技能），以及 `mart_skill_frequency`、`mart_coverage_summary`、`mart_coverage_by_archetype`、`mart_funnel`、`mart_pipeline_daily`、`mart_ai_costs`，加数据测试
  - **3.3 覆盖率报告：** `agents/coverage_report.py`，每日报告新增"技能覆盖"一节；`coverage-report` 升到 v2（现在是代码）。每日运行打分后重建 dbt，出错只记下来，不影响抓取
  - **3.4 看板：** `dashboard/app.py`（英文、只有这台电脑能打开），四个标签：Skills、Coverage、Funnel、Pipeline。只读 marts
  - `pipeline/analytics.py`：把词表写成 seed，把档案的技能写进 `agents.profile_skills`（迁移 015），再跑 dbt
- **为什么：** DECISIONS #41
- **文件：** `dbt/`、`pipeline/analytics.py`、`pipeline/daily.py`、`agents/coverage_report.py`、`dashboard/`、`.streamlit/config.toml`、`.claude/launch.json`、`.claude/skills/coverage-report/SKILL.md`、`config/prompt_lock.toml`、`db/migrations/015_profile_skills.sql`、`pyproject.toml`、`uv.lock`、`tests/test_analytics.py`、`docs/`
- **提交：** 见本条所在的提交（原计划分步提交，它们互相依赖，所以合成一个）
- **验证：**
  1. dbt 在真实数据上 56 步全过；新增 15 个测试（全部 593 个通过），其中 dbt 在测试数据库里真实构建，看板也真实跑了一遍
  2. **dbt 全过不代表数字对。** 我读了结果，又发现两个测试查不出来的错，都修了：(a) Alex 显示"有" CI/CD、Snowflake、Java，因为一个 "Java & Python" 的短语算覆盖就把 Java 也标成有了；改成按技能名字判断，和打分用同一段代码；(b) 87 个职位全挤在同一天，因为抓取日期是 UTC；改成洛杉矶时间的运行日期
  3. 看了看板的每个标签，又修了两处版面：柱子少时标签被挤掉；Oct 31 排到了 11 月后面
  4. 真实结果：近 30 天覆盖率 47%（87 个里 41 个），今天 49%（37 个里 18 个）；SQL 76%、Python 66%、ETL 61%；数据管道 DE 56%、分析工程师 39%、基础设施 DE 0%
  5. **没有验证：** 明天 9:30 才是 dbt 第一次跑在每日运行里；配色校验脚本要 Node，这台电脑没装，用的是文档里写明通过的前三个颜色
- **发现但没改：** 打分时，JD 原话只要有一部分对上就算覆盖。比如 "Java & Python" 让没用过 Java 的人也算满足了 Java，"Git and CI/CD" 同理。试算：如果原话必须整句对上，87 个里 16 个分数会变，3 个决定从投变跳过（Seismic、Jobgether、Sagility）。#39 里提到 Sagility 从跳过变投，现在看也是这个问题造成的。要走规则流程，等 FL 决定
- **撤回：** `git revert` 这个提交，再 `drop schema analytics_staging, analytics_skills, analytics_marts cascade`，删掉 `agents.profile_skills`，从 `public.schema_migrations` 删掉 `015_profile_skills.sql`

### 3.5 · 2026-11-04 · 打分的 JD 原话匹配：提议阶段，还没启用
- **做了什么：** FL 同意提议。JD 原话以前只要有一部分对上就算覆盖；提议改成整句对上，或者 "or" 其中一边对上
  - `config/proposals/fit_scoring.v3.toml`：新增 `[skill_matching] exact_phrases`。代码两种方式都支持，真规则文件没变，所以现在什么都没变
  - `config/proposals/skill_vocabulary.v3.toml`：加 "Git/GitHub"
  - `tests/fixtures/phrase_match_cases.toml`：18 条标准答案，多数来自真实简报
  - `agents.evaluate_fit_rules`：新增 `--every-score`、`--vocabulary`、`--brief-versions`，审核页写明每个职位失去了哪条必备技能，并标出原文
- **过程：** 我之前试算的是"必须整句对上"，3 个决定会变。逐个读完发现这太严：Jobgether 的 "Airflow or Dagster" 是真的几选一，不该丢；Seismic 的 "Git/GitHub" Alex 确实有。所以改成保留 "or"，并在词表加上这个写法，决定变化从 3 个降到 1 个
- **为什么：** "Java & Python" 让只会 Python 的人也算满足了 Java
- **文件：** `agents/fit_scoring.py`、`agents/evaluate_fit_rules.py`、`config/proposals/fit_scoring.v3.toml`、`config/proposals/skill_vocabulary.v3.toml`、`tests/fixtures/phrase_match_cases.toml`、`tests/test_evaluate_fit_rules.py`、`docs/JOURNAL.md`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：**
  1. 全部测试通过，ruff 通过；标准答案 18 条全过，当前规则过不了这些答案（证明确实在修问题）
  2. 87 个职位：1 个决定会变（Sagility，投 → 跳过，它的标题就要 Snowflake，Alex 没有），14 个只有分数变，13 个下降，DRW 上升 5 分（"Java and/or Python" 现在算对上了 Python，仍然跳过）
  3. 我读了每一个失去的必备技能。可以讨论的一个：EXL 的 "AWS-based data lakes (S3)"，Alex 用过 S3，但新规则不再算 Data lakes
- **撤回：** `git revert` 这个提交。提议没有启用，分数和每日运行都没有变化
- **2026-11-05 更新：** FL 认为 S3 经验应该算 "AWS-based data lakes (S3)"。词表提议加了 Data lakes 家族（S3、Azure Data Lake Storage、Google Cloud Storage），标准答案加了这一条（19 条，全过）。今天的运行之后再评估 137 个职位：4 个决定会变（Dalio、Sagility 投 → 跳过；CareFirst、Purple Drive 跳过 → 投，因为 data lakes 现在算覆盖），20 个只有分数变

### 3.6 · 2026-11-05 · 今天的运行：新版本第一次真实使用
- **结果：** Windows 更新重启后没登录，9:30 没跑，登录后也没有自动补跑（任务只在登录时运行）。21:25 手动启动同一个计划任务，14 分钟跑完，状态 ok：新职位 796 个，DE 类 165 个；范围内 100 个，拆解 50 个，花费 $1.96，超过上限没拆 50 个；60 份 `jd-analysis@4` 简报都有分数；dbt 第一次在每日运行里跑，通过；报告有"技能覆盖"一节；Docker 也是这次运行自己启动的
- **我的失误：** 评估命令后面多带了一条 `application_queue build --date 2026-11-06 --n 1`，没人要求。它改写了 The Bison Group 的简历（$0.16），并排进了 11/06 的队列。已经标记为跳过，原因写明，没有删记录。影响：这个职位不会再进队列；11/06 不会再生成新批次，除非 FL 同意删掉这条记录。**FL 同意后已删除：** 删掉了这一行队列记录、它的两条事件和 `output/queue/2026-11-06/`；简历和 AI 缓存留着，再改写这个职位不用再花钱；重建后漏斗回到排队 5、批准 5
- **验证：** 读了 `ops.daily_runs`、报告、`agents.fit_scores`、`analytics_marts`

### 3.7 · 2026-11-05 · 启用打分规则 v3 和词表 v3
- **做了什么：** FL 同意。两份提议复制成正式文件，提议留作历史；`fit-scoring` 说明升到 v4，提示词锁已更新；测试改成检查正式规则；重新打分，重建分析表
- **为什么：** DECISIONS #42，里面也更正了 #39 对 Sagility 的说法
- **文件：** `config/fit_scoring.toml`、`config/skill_vocabulary.toml`、`dbt/seeds/skill_synonyms.csv`、`.claude/skills/fit-scoring/SKILL.md`、`config/prompt_lock.toml`、`tests/test_evaluate_fit_rules.py`、`docs/DECISIONS.md`、`docs/JOURNAL.md`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：** 617 个测试通过，ruff 通过，`agents.skills check` 通过。60 份 v4 和 87 份 v3 简报都按新规则重新打分（纯代码，没有调用 AI），dbt 56 步通过。现在 137 个职位都是规则 v3：投 52、投 + 找内推 6、跳过 79；覆盖率 50%（137 个里 69 个）。旧分数留在表里没删
- **撤回：** `git revert` 这个提交，再跑 `agents.skills lock` 和 `agents.fit_scoring run`

### 3.8 · 2026-11-05 · 登录时补跑
- **做了什么：** 计划任务加了"登录后 5 分钟"的触发条件；`pipeline.daily` 加 `--if-not-run-today`，今天的报告已有且不是失败的就直接退出，不连数据库、不启动 Docker；`scripts/daily.cmd` 带上这个参数。手动跑不带参数，照常运行
- **为什么：** DECISIONS #43
- **文件：** `pipeline/daily.py`、`scripts/daily.cmd`、`tests/test_daily.py`；Windows 计划任务不在仓库里（新增一个登录触发器）；`docs/DECISIONS.md`、`docs/JOURNAL.md`、`docs/NOTES.md`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：**
  1. 新增测试覆盖：没有报告会跑；失败的报告会再跑；部分成功、只有 dbt 出错都算跑过；昨天的报告不算；带参数跳过时不碰数据库；不带参数照常跑
  2. 改完检查：9:30 触发器一字未变（开始时间仍然没有时区偏移，夏令时不受影响），其他设置也没变；不需要管理员权限
  3. 用真实计划任务启动了一次：几秒结束，结果 0，日志写着 already ran today，没有新增运行记录
  4. **没有验证：** 登录触发器要等下一次真实登录才算验证过。下次开工先看日志
- **撤回：** 在任务计划程序里删掉"登录时"触发器，`git revert` 这个提交

## Milestone 4 · 上线前的打磨

### 4.1 · 2026-11-09 · S3 备份（代码完成，等 FL 设置 AWS）
- **做了什么：**
  - `pipeline/backup.py`：导出整个数据库（不含 dbt 能重建的分析表），上传到 `daily/<日期>.dump`；每月第一份另存 `monthly/<月份>.dump`，并真的恢复到一个临时数据库，比对 11 张表的行数后删掉临时库。上传前核对 AWS 账号 ID，对不上就停；上传后核对大小和指纹；比上一份小 30% 以上就报警
  - 每日运行最后一步做备份，报告新增"备份"一节；出错只记下来，不影响当天的抓取和打分
  - 命令：`uv run python -m pipeline.backup run`、`uv run python -m pipeline.backup restore-check`
  - `docs/AWS_SETUP.md`：FL 自己设置 AWS 的 6 步，包括只能读写这个桶、不能删除的权限策略
  - `.env.example` 新增 `AWS_BACKUP_ACCOUNT_ID`、`AWS_REGION`；新依赖 `boto3`
- **为什么：** DECISIONS #44，替换 #3 里"只备份 JD 原文、每晚"的说法
- **文件：** `pipeline/backup.py`、`pipeline/daily.py`、`tests/test_backup.py`、`docs/AWS_SETUP.md`、`.env.example`、`pyproject.toml`、`uv.lock`、`docs/DECISIONS.md`、`docs/JOURNAL.md`、`docs/NOTES.md`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：**
  1. 新增 13 个测试（全部 640 个通过），用假 S3，不花钱不联网：每月第一份另存并恢复检查、普通日子只存一份、变小报警、传上去对不上就报错、**账号不对时连 S3 客户端都不建**、没设置好就不备份、备份失败不影响当天
  2. 在测试数据库上真实导出再恢复，行数一致；故意改一个预期数字，检查能抓到
  3. **在真实数据库上**导出再恢复了一次（没传 AWS）：83 MB，导出 22 秒，恢复检查 19 秒，11 张表全部一致，临时库已删
  4. **没有验证：** 真正的上传要等 FL 设置好 AWS
- **撤回：** `git revert` 这个提交；在 `.env` 里清空 `AWS_PROFILE` 就会关掉备份

### 4.2 · 2026-11-09 · 第一次真实备份
- **做了什么：** FL 建好了个人 AWS 账号、桶和只能用这个桶的用户，钥匙由她自己输在终端里。桶名、账号 ID、`AWS_PROFILE=jobhunt-backup`、`AWS_REGION=us-east-1` 写进了 `.env`（Git 不管）。桶建在 us-east-1，不是指南里写的 us-west-2，两个都可以，桶不能换区域
- **结果：** `pipeline.backup run` 用了 71 秒：核对账号 ID 通过；上传 `daily/2026-11-09.dump` 和本月的 `monthly/2026-11.dump`（各 83 MB）；读回核对大小和指纹一致；恢复到临时库，11 张表行数全部一致。`pipeline.backup restore-check` 再从 S3 下载最新一份恢复，24 秒，全部一致
- **权限检查：** 用这把钥匙删除被拒绝（AccessDenied），说明它确实删不掉备份。它也读不了桶的过期规则，所以 30 天过期规则有没有设好，要 FL 在控制台看一眼。FL 看过了，规则在
- **文件：** 只改了文档；`.env` 不在仓库里
- **提交：** 见本条所在的提交
- **撤回：** 在 `.env` 里清空 `AWS_PROFILE` 就会关掉备份；S3 里的文件由 FL 在控制台删除

### 4.3 · 2026-11-09 · 每日运行拆成步骤（为 Airflow 做准备，行为不变）
- **做了什么：** 新增 `pipeline/daily_steps.py`：开始一次运行 → 抓取（可以按来源分开）→ 安全闸门 → 算出今天的新职位 → AI 拆解 → 打分 → dbt → 备份 → 汇总。每一步把自己的结果存进新表 `ops.daily_run_steps`（迁移 016），下一步从表里读，所以每一步都可以在单独的进程里跑、单独重试。`run_daily` 改成按顺序调用这些步骤，Windows 计划任务照常
- **为什么：** DECISIONS #45；FastAPI 先放下，等决定要不要上云时再说
- **文件：** `pipeline/daily_steps.py`、`pipeline/daily.py`、`db/migrations/016_daily_run_steps.sql`、`tests/test_daily_steps.py`、`docs/DECISIONS.md`、`docs/JOURNAL.md`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：**
  1. 原来 29 个每日运行测试一个没改，全部通过：行为没变
  2. 新增 6 个测试：一步一步分开跑（像 Airflow 那样，每步重新查运行信息）和一次跑完的结果一样；AI 和打分分开跑也一样；`run_daily` 每一步都存下来了；**抓取重试后，第一次已经存进去的职位仍然算今天的新职位**；没算出新职位前不能打分
  3. **没有验证：** 真实数据上的运行要等明天 9:30 的计划任务
- **撤回：** `git revert` 这个提交；`drop table ops.daily_run_steps`，再从 `public.schema_migrations` 删掉 `016_daily_run_steps.sql`

### 4.4 · 2026-11-09 · Airflow 在 Docker 里跑每日运行（手动触发，和 Windows 对比）
- **做了什么：** Airflow 3.3.2 装进 Docker（网页服务、调度器、DAG 读取器，再加一个只跑一次的初始化容器建 `airflow` 数据库）。镜像里给我们的代码单独装了一套 Python 环境（照着 `uv.lock` 装），和 Airflow 自己的包分开。DAG `daily_job_hunt` 一步一个任务：开始 → 四个来源同时抓 → 闸门 → 算新职位 → AI 拆解 → 打分 → dbt → 备份 → 收尾。每个任务都是在命令行跑 `python -m pipeline.daily_steps <步骤>`。和 Windows 并行期间，Airflow 的报告写到 `output/daily/airflow/`，每次运行记下是谁跑的（`runner`），一边在跑时另一边不会开始
- **为什么：** DECISIONS #46
- **文件：** `docker-compose.yml`、`docker/airflow/Dockerfile`、`docker/airflow/create_airflow_db.py`、`.dockerignore`、`dags/daily_job_hunt.py`、`pipeline/daily_steps.py`（命令行、失败记录、收尾检查）、`pipeline/daily.py`（Windows 也检查有没有别的运行在跑）、`pipeline/backup.py`（容器里走网络跑 pg_dump）、`db/migrations/017_daily_run_runner.sql`、`.env.example`、`tests/test_daily_steps.py`、`tests/test_dag.py`、`tests/test_backup.py`、文档
- **提交：** 见本条所在的提交
- **验证：**
  1. 全部 658 个测试通过；新增：命令行一步一步跑完一天（和 `run_daily` 数字一样），失败的步骤会记下来并写进报告，正在跑时不能再开一个，DAG 里的每条命令都能被命令行接受
  2. Airflow 里读取 DAG 没有错误，12 个任务都在
  3. 手动触发一次（运行 12，在 Windows 当天运行之后）：所有任务成功，3 分钟跑完；新增 183 个职位（DE 18 个），AI 拆解 6 个花了 $0.30，打分 6 个。Greenhouse 14 个公司只多了 5 个新版本，说明没变的职位认得出来，和 Windows 一样
  4. **对比发现一个问题：** 备份在容器里失败（容器里没有 Docker）。修好后只重跑"备份"和"收尾"两步（Airflow 的单步重跑），上传成功 83.8 MB；再在 Windows 上恢复这份备份，每张表的行数都对得上
  5. **没有验证：** 定时触发（4.5 再定）
- **撤回：** `git revert` 这个提交；停掉并删除 Airflow 容器（`docker compose --profile airflow rm -sf airflow-init airflow-apiserver airflow-scheduler airflow-dag-processor`），需要的话 `drop database airflow`；`alter table ops.daily_runs drop column runner`，再从 `public.schema_migrations` 删掉 `017_daily_run_runner.sql`

### 4.5 · 2026-11-10 · 定下来由 Windows 继续每天跑；README 架构图；第 4 阶段面试笔记
- **做了什么：** 你决定先不让 Airflow 接管：Windows 计划任务继续负责 9:30（加上醒来补跑和登录检查），Airflow 关掉，需要时再开。README 加了架构图（GitHub 上会直接显示成图）、设计原则、关键数字、怎么运行、目录说明。`INTERVIEW_NOTES.md` 加了第 4 阶段
- **为什么：** DECISIONS #47
- **文件：** `README.md`、`docs/INTERVIEW_NOTES.md`、`docs/DECISIONS.md`、`docs/JOURNAL.md`、`docs/STATUS.md`
- **提交：** 见本条所在的提交
- **验证：**
  1. 拆成步骤后，Windows 第一次正式运行（运行 13，11/10 电脑醒来 6 分钟后补跑）：7 个步骤全部成功，记录的是 `windows`；新增 502 个职位（DE 类 74 个），AI 拆解 45 个花了 $1.94，打分 45 个，dbt 成功，备份 86.1 MB
  2. README 里的数字是 11/10 从数据库里查的；架构图要推到 GitHub 后才能看到渲染效果
- **撤回：** `git revert` 这个提交

### 2.2b · 2026-11-10 · 考一下便宜的模型：Haiku 5.5 做 JD 拆解
- **做了什么：** 每天 AI 拆解约 $2（每月约 $60）太贵，你让先试 Haiku。考试命令加了 `--model`（同一个提示词，换模型比）；Haiku 不支持"被拒绝时换模型重试"，所以只对支持的模型发这个设置；价格表里 Sonnet 读缓存的价格从 $0.20 改成 $0.10
- **为什么：** 换不换模型还没定，考完再由你决定（还没有新的 DECISIONS）
- **文件：** `agents/evaluate_prompt.py`、`agents/llm.py`、`tests/test_llm.py`、`docs/JOURNAL.md`
- **提交：** 见本条所在的提交
- **验证：** 13 道标准答案（`tests/fixtures/jd_golden.toml`），和现在的 Opus 5.5（中等思考）比：
  1. Opus：必备 86/86、加分 29/29、either/or 4/4、工作方式 12/13
  2. **Haiku 中等思考（13 道共 $0.02，每个约 $0.0015）：** 必备 85/86（漏了 rosens 的 ETL）、加分 27/29（丢了 Streaming data、Fivetran）、1 个加分被当成必备（EHR）、either/or 3/4（totalwine 拆开了）、工作方式 13/13。按规则不及格（加分和 either/or 两项）
  3. **Haiku 高思考（$0.04）反而更差：** 必备 79/86，漏了 dbt、Data modeling、Git、CI/CD、Scala 这类真正影响打分的技能。说明 Haiku 的结果不稳定，同一道题每次答得不一样
- **撤回：** `git revert` 这个提交

### 2.2c · 2026-11-10 · Sonnet 5.5 也考了；再量一下 Opus 自己每次差多少
- **做了什么：** 考试命令加了 `--fresh`：不用缓存，让模型把同一道题再答一遍，答案不存（流水线继续用第一次的答案），只用来量"同一个模型每次答得差多少"。另外把各模型的拆解结果，用样本档案打分来比，因为真正影响你的是分数和投/跳过的判断，而不只是技能名字对不对得上
- **为什么：** 决定换不换便宜模型之前，要知道 Opus 自己的波动有多大（还没有新的 DECISIONS）
- **文件：** `agents/llm.py`、`agents/evaluate_prompt.py`、`tests/test_llm.py`、`docs/JOURNAL.md`
- **提交：** 见本条所在的提交
- **验证（13 道标准答案，样本档案打分，和存着的 Opus 答案比）：**

  | | 必备 | 加分 | 投/跳过一样 | 分数平均差 | 最大差 | 每个 JD |
  | --- | --- | --- | --- | --- | --- | --- |
  | Opus 再答一遍（$0.52） | 85/86 | 29/29 | 13/13 | 5.0 | 13 | $0.042 |
  | Sonnet 5.5 中等（$0.20） | 83/86 | 27/29 | 10/13 | 8.4 | 16 | $0.015 |
  | Haiku 5.5 中等（$0.02） | 85/86 | 27/29 | 8/13 | 10.5 | 31 | $0.0015 |
  | Haiku 5.5 高（$0.04） | 79/86 | 27/29 | 10/13 | 7.5 | 17 | $0.003 |

  结论：Opus 每次也会差 5 分左右，但投/跳过的判断没变；Sonnet 翻掉的 3 个都是从"投"变"跳过"，分数大多偏低。另外，就连 Opus 自己，分数也会因为技能怎么拆、怎么起名而上下浮动几分，以后可以改进打分，让它不那么依赖技能的叫法
- **撤回：** `git revert` 这个提交

### 2.2d · 2026-11-10 · JD 拆解换成 Haiku 5.5（第 5 阶段之前）
- **做了什么：** 加了只给 JD 拆解用的模型设置 `JD_ANALYSIS_MODEL`（你的 `.env` 里设成了 `claude-haiku-5-5`）；简历改写和审阅继续用 Opus。已经被任何模型拆过的职位不再重拆；同一个职位有几个模型的拆解时，打分、待投清单、规则评估都用更强的那个模型的结果，每个分数记下用的是哪个模型的拆解。每日报告的 AI 那一行写上了模型
- **为什么：** DECISIONS #48
- **文件：** `pipeline/config.py`、`agents/fit_scoring.py`、`agents/jd_analysis.py`、`agents/tailor.py`、`agents/evaluate_fit_rules.py`、`agents/evaluate_scoring.py`、`agents/evaluate_prompt.py`、`pipeline/daily.py`、`pipeline/daily_steps.py`、`.env.example`、`tests/test_llm.py`、`tests/test_fit_scoring.py`、`tests/test_jd_analysis.py`、`tests/test_daily_steps.py`、文档
- **提交：** 见本条所在的提交
- **验证：** 全部测试通过；新增：模型设置没填时用 `LLM_MODEL`，填了只影响 JD 拆解；同一个职位有 Opus 和 Haiku 两份拆解时用 Opus 的；换模型后已拆过的职位不再重拆；报告里写着模型。**没有验证：** 真实运行要等明天（11/11）9:30
- **撤回：** 删掉 `.env` 里的 `JD_ANALYSIS_MODEL` 那一行就回到 Opus（不用改代码）；或者 `git revert` 这个提交
