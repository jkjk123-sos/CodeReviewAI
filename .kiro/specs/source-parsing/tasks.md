# Implementation Plan — source-parsing

- [x] 1. 建立模块骨架与契约镜像
  - 建 `codereview/parse/` 包，定义 `DiffUnit` 只读数据类（8 字段，`frozen=True`）
  - 与 C 线确认字段清单，写入契约变更记录
  - _Requirements: 5.1, 5.5_

- [x] 2. 实现路径扫描与忽略规则
  - `SourceScanner.scan()` 递归遍历，按路径字典序产出
  - 一级 `.gitignore` 匹配（目录名、`*.ext`）
  - _Requirements: 1.1, 1.3, 1.5, 6.2_

- [x] 3. 实现参数校验
  - 路径不存在时立即失败，退出码 2 + `path_not_found`
  - `--diff` 的 ref 无效时 `git_ref_invalid`
  - _Requirements: 1.4, 3.5_

- [x] 4. 实现语言映射表与注释前缀
  - `LANG_BY_SUFFIX` 表；未知后缀返回 `unsupported_lang`
  - 加语言的改动面控制在"一行表项"
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 5. 实现编码识别与降级
  - 顺序 `utf-8-sig` → `gbk` → `utf-8(replace)`
  - BOM 剥离后行号仍从 1 起
  - _Requirements: 2.4, 2.5, 2.6_

- [x] 6. 实现大文件与二进制判定
  - 阈值 2 MB / 5000 行；NUL 字节判二进制
  - 跳过原因入库为 `too_large` / `binary`
  - _Requirements: 4.1, 4.2_

- [x] 7. 实现 unified diff 解析
  - 识别 `diff --git` 与 `@@ -a,b +c,d @@`，取新文件区间
  - `-` 行丢弃，`+`/` ` 行保留
  - _Requirements: 3.1, 3.2_

- [x] 8. 实现块切分
  - 连续非空行合并；空行断开不成块；行号累加不回退
  - 标记 `is_comment` / `is_blank` / `source`
  - _Requirements: 3.3, 3.4, 5.2, 5.3, 5.4_

- [x] 9. 实现 pipeline 与统计回传
  - 串起 scanner → reader → splitter / diff
  - 返回 `ScanStats`（四字段）
  - _Requirements: 6.1_

- [x] 10. 实现单文件容错
  - 每个文件独立 try/except，记录异常类型进 skipped
  - 整体状态不受影响
  - _Requirements: 4.3, 4.4, 4.5_

- [x] 11. 编写单元测试与属性测试
  - 边界：全空行文件、单行文件、跨空行切块、BOM 文件
  - 属性：行号单调、块内连续、不重叠、覆盖率、幂等
  - _Requirements: 6.2, 3.3_

- [ ] 12. 补充完整 gitignore 语法支持
  - 当前只做目录名与 `*.ext` 一级匹配，`!` 取反与嵌套规则未支持
  - 若引入 `pathspec` 依赖需评估 CI 影响
  - _Requirements: 1.2_

- [ ] 13. 200 文件性能基准
  - 生成 200 文件 / 2 万行语料，取 P95 与峰值内存
  - 当前仅有 20 文件的手测数据，NFR-A-01 尚未验证
  - _Requirements: 6.4_

- [x] 14. 与 B 线联调交付
  - 按冻结字段结构交付，B 线规则可直接消费
  - 联调发现行号偏移问题一次，已修复行号基线
  - _Requirements: 5.1, 3.4_

---

**说明**：12、13 两项挂起。12 的原因是依赖引入需全组确认；13 的原因是基准语料尚未固化（内容随仓库增长变化），列入实验四。
