/**
 * 名单导入业务回归：只使用 Node 内置测试工具，不安装额外前端依赖。
 * 执行：node --test tests/roster_import.test.mjs。
 * @author ahui
 */
import test from "node:test";
import assert from "node:assert/strict";
import { previewSheet, validateImport, validateImportIssues, columnLabel } from "../frontend/src/rosterImport.js";

test("空行保留原始位置，可选学号不读取无关公式", () => {
  const rows = [["姓名", "学号"], [], ["测试甲", { issue: "公式结果未保存" }]];
  const omitted = previewSheet("名单", rows, { startRow: 2, nameCol: 1, noCol: null });
  assert.deepEqual(omitted.errors, []);
  assert.deepEqual(omitted.entries, [{ sheet: "名单", row: 3, name: "测试甲", no: "" }]);
  const mapped = previewSheet("名单", rows, { startRow: 2, nameCol: 1, noCol: 2 });
  assert.match(mapped.errors[0], /名单 · B3：公式结果未保存/);
});

test("多个表独立映射，重复学号指出两处来源，替换不与旧名单冲突", () => {
  const first = previewSheet("第一表", [["姓名", "学号"], ["甲", "001"]], { startRow: 2, nameCol: 1, noCol: 2 });
  const second = previewSheet("第二表", [["001", "乙"]], { startRow: 1, nameCol: 2, noCol: 1 });
  assert.match(validateImport([...first.entries, ...second.entries], [])[0], /第二表 · 第 1 行.*第一表 · 第 2 行/);
  assert.match(validateImport(first.entries, [{ no: "001" }])[0], /当前班级/);
  assert.deepEqual(validateImport(first.entries, []), []);
});

test("缺失姓名结果不得因空行过滤而漏导入；真实空文本仍按必填校验", () => {
  const missing = previewSheet("名单", [[{ issue: "公式结果未保存" }]], { startRow: 1, nameCol: 1, noCol: null });
  assert.equal(missing.entries.length, 1);
  assert.match(missing.errors[0], /A1/);
  assert.match(validateImport(missing.entries, [])[0], /姓名缺失/);
  const emptyName = previewSheet("名单", [["", "001"]], { startRow: 1, nameCol: 1, noCol: 2 });
  assert.match(validateImport(emptyName.entries, [])[0], /姓名缺失/);
});

test("边界：空表、越界配置、数值零与整批人数上限", () => {
  assert.ok(previewSheet("空表", [], { startRow: 1, nameCol: 1, noCol: null }).errors.length);
  assert.ok(previewSheet("名单", [["甲"]], { startRow: 0, nameCol: 1, noCol: null }).errors.length);
  assert.ok(previewSheet("名单", [["甲"]], { startRow: 1, nameCol: 2, noCol: null }).errors.length);
  const zero = previewSheet("名单", [["甲", 0]], { startRow: 1, nameCol: 1, noCol: 2 });
  assert.equal(zero.entries[0].no, "0");
  const entries = Array.from({ length: 10000 }, (_, i) => ({ sheet: "名单", row: i + 1, name: "甲", no: "" }));
  assert.deepEqual(validateImport(entries, []), []);
  assert.match(validateImport([...entries, entries[0]], [])[0], /10000/);
  assert.equal(columnLabel(50), "AX");
});

test("完整预览不截断；跨页问题保留结构化原行号，不依赖表名或提示文本解析", () => {
  const sheet = "名单 · 第 50 行：特殊名称";
  const rows = [["姓名", "学号"], ...Array.from({ length: 121 }, (_, index) =>
    [index === 110 ? "" : `测试${index + 1}`, String(index + 1)])];
  const result = previewSheet(sheet, rows, { startRow: 2, nameCol: 1, noCol: 2 });
  assert.equal(result.entries.length, 121);
  assert.equal(result.entries.at(-1).row, 122);
  const issues = validateImportIssues(result.entries, []);
  assert.equal(issues.length, 1);
  assert.equal(issues[0].sheet, sheet);
  assert.equal(issues[0].row, 112);
  rows[111][0] = { issue: "公式结果未保存" };
  const missing = previewSheet(sheet, rows, { startRow: 2, nameCol: 1, noCol: 2 });
  assert.equal(missing.issues[0].row, 112);
  assert.equal(missing.issues[0].sheet, sheet);
  assert.equal(missing.issues[0].message, missing.errors[0]);
});

test("预览修正覆盖公式问题，切列保留；移除保留原行号且源文件数据不变", () => {
  const rows = [["姓名", "学号"], [{ issue: "缓存缺失" }, "001"], ["乙", "002"]];
  const original = JSON.stringify(rows);
  const config = { startRow: 2, nameCol: 1, noCol: 2,
    edits: { 2: { name: "修正甲", no: "003" } }, removedRows: [3] };
  const result = previewSheet("名单", rows, config);
  assert.equal(result.entries.length, 1);
  assert.deepEqual(result.issues, []);
  assert.deepEqual(result.entries[0], { sheet: "名单", row: 2, name: "修正甲", no: "003" });
  assert.match(validateImport(result.entries, [{ no: "003" }])[0], /重复/);
  assert.deepEqual(previewSheet("名单", rows, { ...config, noCol: null }).entries, result.entries);
  assert.equal(previewSheet("名单", rows, { ...config, removedRows: [] }).entries[1].row, 3);
  assert.equal(JSON.stringify(rows), original);
  assert.ok(previewSheet("名单", rows, { ...config, removedRows: [2, 3] }).issues.length);
});

test("字段修正独立：切学号列不重置姓名，未编辑字段读取新列，显式空学号保留", () => {
  const rows = [["姓名", "学号", "备用"], ["原名", "001", "002"]];
  const config = { startRow: 2, nameCol: 1, noCol: 2, edits: { 2: { name: "修改姓名" } } };
  assert.equal(previewSheet("名单", rows, { ...config, noCol: 3 }).entries[0].name, "修改姓名");
  assert.equal(previewSheet("名单", rows, { ...config, noCol: 3 }).entries[0].no, "002");
  config.edits[2].no = "";
  assert.equal(previewSheet("名单", rows, { ...config, nameCol: 3 }).entries[0].no, "");
  rows[1][2] = { issue: "公式结果未保存" };
  delete config.edits[2].no;
  assert.equal(previewSheet("名单", rows, { ...config, noCol: 3 }).issues.length, 1);
});
