# Implementation Plan

- [x] 1. 建立报告契约与三条构造时校验
  - 在 `contract/models.py` 定义 `Report` / `Finding` / `Counts` / `Level` / `Status`
  - 用 `model_validator(mode="after")` 实现 V-01（数字自洽）、V-02（标签与明细一致）、V-03（状态交代原因）
  - 用 `Field(gt=0)` 约束行号，用 `Literal["2.0"]` 锁版本
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 2. 定义 8 个错误码与 HTTP 状态映射
  - 4xxx 表调用方问题，5xxx 表我方问题
  - `ApiError` 携带 `code` / `message` / `http_status`
  - _Requirements: 6.2_

- [x] 3. 实现规则集基类（模板方法）
  - `run()` 固定四步：归一化 → 逐块检查 → 分级 → 去重
  - `dedupe()` 按 `rule|file|line` 指纹，写在基类
  - `counts_of()` 从明细反推计数，保证与 `findings` 同源
  - 子类只实现 `check()`
  - _Requirements: 4.5_

- [x] 4. 实现解析器工厂
  - `_REGISTRY` 后缀表：`.py` / `.js` / `.ts` / `.tsx` / `.jsx`
  - 未知后缀抛 `UnsupportedLanguage`，由 CLI 转成退出码 2
  - _Requirements: 1.3, 1.4_

- [x] 5. 实现三种渲染策略
  - `TextRenderer`：按 `rule_kind` 分组，组内按文件与行号排序
  - `JsonRenderer`：完整报告对象
  - `SarifRenderer`：SARIF 2.1.0
  - 注册表 `_REGISTRY = {r.name: r}`，加格式只加类 + 一行注册
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 6. 串起 CLI 主流程与三档退出码
  - `run()` 七步：收集 → 选解析器 → 判定 → 计数 → 构造报告 → 渲染 → 定退出码
  - `--fail-on` 支持 `blocking` / `warning` / `none`
  - `--save` 只写库不打印，避免 CI 刷屏污染趋势
  - _Requirements: 1.1, 1.2, 1.5, 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 7. 实现三级配置合并
  - 优先级：命令行 > 环境变量 > 配置文件 > 默认值
  - 返回生效值与来源链，便于 `config` 子命令展示
  - _Requirements: 1.1_

- [x] 8. 实现双后端存储与游标分页
  - `db.py` 同接口支持 SQLite / PostgreSQL
  - `repo.py` 浅页用 OFFSET，深页用 `(started_at, run_id)` 行值比较
  - `page > 100` 拒绝并提示改用 cursor
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 9. 装配 13 个 REST 路由
  - `routes_reviews.py` 6 个、`routes_rules.py` 3 个、`routes_stats.py` 3 个、`/healthz` 1 个
  - `envelope.py` 统一 `{code, message, data, traceId, timestamp}`
  - 中间件生成或沿用 `X-Trace-Id`
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 10. 编写数据定义 20 条
  - 8 表 + 8 索引 + 按月分区 + 视图 + CHECK 约束
  - `finding.rule` 不加外键，`run_partial_needs_reason` 让库守 V-03
  - 在 PostgreSQL 16.4 上实跑，0 报错
  - _Requirements: 5.1_

- [x] 11. 补三类测试共 23 条
  - 契约 5 条、模式 5 条、接口 13 条
  - `pytest -q` 全绿
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 6.1_

- [x] 12. 本地化接口文档
  - `/docs` 用本地 swagger-ui 资源，不依赖 CDN
  - `/ui` 零依赖控制台，直读 `openapi.json` 渲染
  - _Requirements: 6.1_

- [ ] 13. 端到端压测
  - 200 文件 1.5 s 目前是设计值，解析器接入后补 20 次跑分
  - 依赖 A 线解析器合并
  - _Requirements: 1.5_

- [ ] 14. 监控阈值校准
  - 6 条阈值缺实测基线，单机环境压不出真实分布
  - 依赖实验五压测
  - _Requirements: 5.4_
