# Requirements Document

## Introduction

CodeReviewAI 是一个本地优先的代码审查工具。开发者在终端跑一次审查得到报告，也能通过服务查看历史与趋势，还能在 CI 里用它挡住有阻断问题的提交。

本 spec 覆盖其中 **C 线**的部分：把上游（A 线解析结果、B 线规则命中）装配成一份可存储、可翻页、可被 CI 判定的报告，并对外提供命令行与 REST 两套入口。

本 spec 不含源码解析、规则判定逻辑、表结构物理设计——它们由 A/B/D 线负责，本 spec 只消费它们的产物。

## Requirements

### Requirement 1

**User Story:** 作为一个开发者，我想用一条命令跑完一次审查，这样我不用记一堆参数也不用手动拼工具链。

#### Acceptance Criteria

1. WHEN 用户执行 `codereview run <path>` THEN the system SHALL 在该路径下递归收集 `.py`/`.js`/`.ts`/`.tsx` 文件并输出一份报告。
2. WHEN 用户执行 `codereview run <path> --diff <ref>` THEN the system SHALL 只审查该 ref 相对工作区的改动行。
3. WHEN 指定的路径不存在 THEN the system SHALL 以退出码 2 结束，并在 stderr 说明原因。
4. WHEN 路径下存在不支持的文件后缀 THEN the system SHALL 跳过该文件并在报告摘要中记录跳过数量，不中断整体审查。
5. WHEN 被审目录包含 3 个文件 THEN the system SHALL 在 10 秒内输出报告。

### Requirement 2

**User Story:** 作为一个开发者，我想选择报告的呈现格式，这样同一次审查的结果能分别给人看、给程序读、给 CI 平台解析。

#### Acceptance Criteria

1. WHEN 用户指定 `--format text` THEN the system SHALL 按 `rule_kind` 分组输出，每组内按文件路径与行号升序排列，每条带 `文件:行号` 与规则号。
2. WHEN 用户指定 `--format json` THEN the system SHALL 输出符合 `schema_version=2.0` 的完整报告对象。
3. WHEN 用户指定 `--format sarif` THEN the system SHALL 输出 SARIF 2.1.0 结构，供代码扫描平台消费。
4. WHEN 同一份审查结果分别以三种格式输出 THEN the system SHALL 保证三者的命中条数完全一致。
5. IF 用户指定的格式不在 `text`/`json`/`sarif` 之内 THEN the system SHALL 以退出码 2 结束并列出可选值。

### Requirement 3

**User Story:** 作为一个 CI 机器人，我想只读一个退出码就知道该放行还是拦下，这样流水线不需要解析任何输出。

#### Acceptance Criteria

1. WHEN 报告中没有 blocking 级别命中 THEN the system SHALL 以退出码 0 结束。
2. WHEN 报告中存在至少一条 blocking 级别命中 THEN the system SHALL 以退出码 1 结束。
3. IF 审查过程本身失败（解析器异常、数据库不可用） THEN the system SHALL 以退出码 2 结束，且不得与"有阻断"混淆。
4. WHEN 用户通过 `--fail-on warning` 提高门槛 THEN the system SHALL 在存在 warning 时也以退出码 1 结束。
5. WHEN 用户通过 `--fail-on none` 关闭门禁 THEN the system SHALL 始终以退出码 0 结束（工具故障除外）。

### Requirement 4

**User Story:** 作为一个出报告的人，我想让不合格的报告在构造那一刻就被拒绝，这样下游永远不会拿到自相矛盾的数据。

#### Acceptance Criteria

1. WHEN 构造一份报告且 `blocking+warning+info != total` THEN the system SHALL 拒绝构造并抛出 V-01 错误。
2. WHEN 构造一份报告且 `len(findings) != total` THEN the system SHALL 拒绝构造并抛出 V-01 错误。
3. WHEN 构造一份报告且 `kinds` 集合与 `findings` 中 `rule_kind` 的去重集合不相等 THEN the system SHALL 拒绝构造并抛出 V-02 错误。
4. WHEN 报告 `status` 为 `partial` 或 `failed` 且未填写 `status_reason` THEN the system SHALL 拒绝构造并抛出 V-03 错误。
5. WHEN 同一位置被同一条规则重复命中 THEN the system SHALL 按 `rule|file|line` 指纹去重，只保留一条。

### Requirement 5

**User Story:** 作为一个想回看历史的开发者，我想翻很多页也不卡，这样查几个月前的记录不用等。

#### Acceptance Criteria

1. WHEN 客户端以 `page` 参数请求列表且 `page <= 100` THEN the system SHALL 使用 OFFSET 分页返回。
2. WHEN 客户端请求 `page > 100` THEN the system SHALL 拒绝并提示改用 `cursor` 参数。
3. WHEN 客户端以 `cursor` 参数请求 THEN the system SHALL 使用 `(started_at, run_id)` 行值比较定位，不得扫描前序行。
4. WHEN 存在 20 万条记录且客户端翻至末页 THEN the system SHALL 在 50 ms 内返回。
5. IF `cursor` 无法解析 THEN the system SHALL 返回 400 与错误码 `CR-4000`。

### Requirement 6

**User Story:** 作为一个服务使用者，我想所有接口的错误形状一致，这样前端只需要写一处错误处理。

#### Acceptance Criteria

1. WHEN 任意接口成功返回 THEN the system SHALL 使用 `{code, message, data, traceId, timestamp}` 结构。
2. WHEN 任意接口失败返回 THEN the system SHALL 使用同一结构，`data` 为 null，并携带 8 个预定义错误码之一。
3. WHEN 请求进入服务 THEN the system SHALL 生成或沿用 `X-Trace-Id` 并回写到响应头。
4. IF 发生未预期异常 THEN the system SHALL 返回 500 与 `CR-5000`，且响应体不得泄露堆栈。
5. WHEN 收到 `GET /healthz` THEN the system SHALL 实际执行一次数据库探活并返回各依赖状态。

### Requirement 7

**User Story:** 作为一个审查者，我想在 PR 里一条评论看完全部结论，这样不用点开十个页面。

#### Acceptance Criteria

1. WHEN 审查由 CI 触发且存在命中 THEN the system SHALL 输出一条汇总评论，含三个级别计数与 blocking 清单。
2. WHEN blocking 条数超过 10 THEN the system SHALL 只列前 10 条并给出剩余数量与详情链接。
3. WHEN 没有命中 THEN the system SHALL 输出一条"未发现问题"的简短评论，不生成空表格。
4. WHEN 门禁判定失败 THEN the system SHALL 以 GitHub Actions 注解格式输出，使 PR 文件页出现行内标注。
