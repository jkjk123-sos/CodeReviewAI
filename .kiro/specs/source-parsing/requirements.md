# Requirements Document — 源码解析与改动块切分（source-parsing）

## Introduction

本规范定义 CodeReviewAI 的入口模块：把用户给的**目录路径**或**一次 diff**，转成规则引擎可直接消费的 `DiffUnit` 列表。

上游无依赖（本模块是链路的起点），下游是 B 线规则引擎。规范采用 EARS 句式（WHEN / IF / WHILE / WHERE + the system SHALL），每条验收标准都可用给定输入观测到结果。

## Requirement 1：目录扫描与文件筛选

**User Story:** 作为开发者，我想把整个仓库或某个目录交给工具，这样首次接入时不用手工挑文件。

### Acceptance Criteria

1. WHEN 用户传入一个存在的目录，THEN the system SHALL 递归列出该目录下所有扩展名在支持表内的文件。
2. WHEN 目录内存在 `.gitignore` 且某文件被其忽略，THEN the system SHALL 排除该文件，不产出任何块。
3. WHEN 用户传入的路径是单个文件，THEN the system SHALL 只处理该文件，不展开同目录其他文件。
4. IF 用户传入的路径不存在，THEN the system SHALL 立即以退出码 2 结束并给出 `path_not_found`。
5. WHILE 遍历目录，the system SHALL 按路径字典序收集文件，保证输出顺序可复现。

## Requirement 2：语言与编码识别

**User Story:** 作为规则引擎的调用方，我想让每块代码都带正确语言标识，这样同一套规则可以按语言分派。

### Acceptance Criteria

1. WHEN 文件扩展名为 `.py`，THEN the system SHALL 将其语言标识设为 `py`，注释前缀设为 `#`。
2. WHEN 文件扩展名为 `.js` / `.ts` / `.tsx`，THEN the system SHALL 将语言标识设为 `js`，注释前缀设为 `//`。
3. IF 扩展名不在支持表内，THEN the system SHALL 跳过该文件并记录原因 `unsupported_lang`，不得抛异常中断整体。
4. WHEN 文件带 UTF-8 BOM，THEN the system SHALL 剥离 BOM 后再切块，且首行行号仍为 1。
5. IF 文件为 GBK 编码，THEN the system SHALL 以 `gbk` 回退解码成功，中文内容不得出现乱码。
6. IF 解码过程中遇到非法字节，THEN the system SHALL 用替换符降级并记录 `decode_warning`，继续产出块。

## Requirement 3：diff 解析与行号映射

**User Story:** 作为 CI 使用者，我只想审这次改动的内容，不想每次审全仓，所以我需要按 diff 增量解析。

### Acceptance Criteria

1. WHEN 输入为 unified diff 文本，THEN the system SHALL 识别所有 `diff --git` 文件段与 `@@ -a,b +c,d @@` hunk 段。
2. WHEN 解析一个 hunk，THEN the system SHALL 取 `+c,d` 作为新文件的起始行与行数。
3. WHEN 一个 hunk 内包含连续的新增行与上下文行，THEN the system SHALL 合并为一个 `DiffUnit`，`line_start` 取该段首行、`line_end` 取末行。
4. WHEN 产出 `DiffUnit`，THEN the system SHALL 使用新文件坐标（从 1 起），与 `git diff` 显示的行号一致。
5. WHEN 传入 `--diff <ref>` 且该 ref 不存在，THEN the system SHALL 以退出码 2 结束并给出 `git_ref_invalid`。
6. WHILE 处于增量模式，the system SHALL 不读取 diff 未涉及的文件。

## Requirement 4：跳过与降级

**User Story:** 作为一个真实仓库的使用者，我希望二进制、超大文件和坏文件不会让整次审查失败。

### Acceptance Criteria

1. IF 文件大小超过 2 MB 或行数超过 5000，THEN the system SHALL 跳过并记录原因 `too_large`。
2. IF 文件内容含 NUL 字节，THEN the system SHALL 判定为二进制并记录原因 `binary`。
3. IF 某文件在读取或解析中抛出异常，THEN the system SHALL 只跳过该文件、记录异常类型，其余文件照常处理。
4. WHEN 本次运行存在被跳过的文件，THEN the system SHALL 在结果中返回 skipped 列表（路径 + 原因），不得静默丢弃。
5. WHILE 跳过文件时，the system SHALL 不改变报告整体状态（仍为 `done`），跳过信息作为附注出现。

## Requirement 5：DiffUnit 交付契约

**User Story:** 作为 B 线规则引擎的开发者，我需要一个字段稳定、语义明确的结构，这样规则只关心文本与行号。

### Acceptance Criteria

1. WHEN 产出块，THEN the system SHALL 每个块包含 `file_path`、`line_start`、`line_end`、`text`、`lang`、`is_comment`、`is_blank`、`source` 八个字段，不多不少。
2. WHEN 该行以语言对应注释前缀开头，THEN the system SHALL 置 `is_comment = true`。
3. WHEN 该行去空白后为空，THEN the system SHALL 置 `is_blank = true`，且空行不单独成块。
4. WHEN 块来自 diff 解析，THEN the system SHALL 置 `source = "diff"`；来自全量扫描则置 `source = "scan"`。
5. IF 下游要求新增字段，THEN the system SHALL 走契约变更流程（提 issue + 双线确认），不得单方面加字段。

## Requirement 6：统计与可复现

**User Story:** 作为报告装配方，我需要扫描统计与被审文件的完整性保证。

### Acceptance Criteria

1. WHEN 解析结束，THEN the system SHALL 返回 `files_scanned`、`skipped_count`、`skipped_reasons`、`blocks_total`。
2. WHEN 同一输入连续运行两次，THEN the system SHALL 产出完全相同的块序列（顺序与内容均一致）。
3. WHEN 解析前后比对被审文件，THEN the system SHALL 保证 mtime 与内容 SHA256 不变。
4. WHILE 解析 200 个文件，the system SHALL 峰值内存不超过 200 MB。
