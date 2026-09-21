/**
 * 名单导入预览与整批校验；不执行公式、不写数据库。
 * 保留工作表和原始行号，供多表重复学号及缺失缓存定位。
 * @author ahui
 */

/**
 * @param {number} column 从 1 开始的列号。
 * @returns {string} Excel 列字母，用于字段选择和错误位置。
 */
export function columnLabel(column) {
  let label = "";
  for (let value = column; value > 0; value = Math.floor((value - 1) / 26))
    label = String.fromCharCode(65 + ((value - 1) % 26)) + label;
  return label;
}

/**
 * @param {string|number|{issue: string}|null} cell 后端文本或不可用结果标记。
 * @returns {string} 去除首尾空白的值；问题标记由校验处理，不能转成姓名。
 */
export function cellText(cell) {
  return cell && typeof cell === "object" ? "" : String(cell ?? "").trim();
}

/**
 * 按单张表配置生成预览；先按原行号截取，再忽略空行，不压缩错误行号。
 * @param {string} sheet 工作表名。
 * @param {Array<Array>} rows 原始二维单元格数组，问题标记也视为非空。
 * @param {{startRow: number, nameCol: number, noCol: number|null, removedRows?: number[], edits?: Object}} config 独立映射；null 不读取源学号。手工修正按原始行号和字段保存，切列仍优先使用，仅存在本次预览。
 * @returns {{entries: Array, errors: string[], issues: Array}} 完整预览及带原始位置的问题；errors 保留文本调用兼容。
 */
export function previewSheet(sheet, rows, config) {
  const errors = [], entries = [], issues = [];
  const width = rows.reduce((max, row) => Math.max(max, row.length), 0);
  if (!Number.isInteger(config.startRow) || config.startRow < 1 ||
      config.startRow > rows.length)
    errors.push(`${sheet}：数据起始行请输入工作表范围内的正整数`);
  if (!Number.isInteger(config.nameCol) || config.nameCol < 1 || config.nameCol > width)
    errors.push(`${sheet}：请选择有效的姓名列`);
  if (config.noCol !== null && (!Number.isInteger(config.noCol) ||
      config.noCol < 1 || config.noCol > width))
    errors.push(`${sheet}：请选择有效的学号列，或留空`);
  if (errors.length) return { entries, errors, issues: errors.map((message) => ({ sheet, row: null, message })) };
  rows.forEach((row, index) => {
    if (index + 1 < config.startRow || config.removedRows?.includes(index + 1) || !row.some((cell) => cell?.issue || cellText(cell))) return;
    // 手动字段优先于源列；空学号也是显式修正，不能用 truthy 判断丢掉。
    const edit = config.edits?.[index + 1] || {};
    for (const [field, column] of [["name", config.nameCol], ["no", config.noCol]]) {
      if (column !== null && !Object.hasOwn(edit, field) && row[column - 1]?.issue) {
        const message = `${sheet} · ${columnLabel(column)}${index + 1}：${row[column - 1].issue}`;
        errors.push(message);
        issues.push({ sheet, row: index + 1, message });
      }
    }
    entries.push({
      sheet, row: index + 1,
      name: Object.hasOwn(edit, "name") ? edit.name : cellText(row[config.nameCol - 1]),
      no: Object.hasOwn(edit, "no") ? edit.no : config.noCol === null ? "" : cellText(row[config.noCol - 1]),
    });
  });
  if (!entries.length) {
    const message = `${sheet}：没有可导入的数据`;
    errors.push(message);
    issues.push({ sheet, row: null, message });
  }
  return { entries, errors, issues };
}

/**
 * @param {Array<{sheet: string, row: number, name: string, no: string}>} entries 按文件工作表顺序合并的行。
 * @param {Array} existing 当前班级学生；替换模式传空数组。
 * @returns {string[]} 整批人数、字段、跨表及已有学号冲突；后端仍作最终事务校验。
 */
export function validateImport(entries, existing) {
  return validateImportIssues(entries, existing).map((issue) => issue.message);
}

/**
 * 校验整个待导入批次，而非当前预览页；使用结构化位置定位，避免解析中文错误文本。
 * @param {Array} entries 完整待导入行，保留 sheet 和原始 row。
 * @param {Array} existing 当前班级学生；替换时传空数组。
 * @returns {Array<{sheet: string|null, row: number|null, message: string}>} 全部问题；全局限制无行位置。
 */
export function validateImportIssues(entries, existing) {
  const issues = [];
  const seen = new Map(existing.filter((student) => student.no).map((student) => [student.no, "当前班级"]));
  if (entries.length > 10000) issues.push({ sheet: null, row: null, message: "每次合计最多导入 10000 人，请减少所选工作表或拆分文件" });
  entries.forEach((entry) => {
    const location = `${entry.sheet} · 第 ${entry.row} 行`;
    const addIssue = (message) => issues.push({ sheet: entry.sheet, row: entry.row, message: `${location}：${message}` });
    if (!entry.name) addIssue("姓名缺失（姓名为空）");
    if (entry.name.length > 60) addIssue("姓名超过 60 字");
    if (entry.no.length > 60) addIssue("学号超过 60 字");
    if (entry.no && seen.has(entry.no))
      addIssue(`学号 ${entry.no} 与${seen.get(entry.no)}重复`);
    if (entry.no && !seen.has(entry.no)) seen.set(entry.no, location);
  });
  return issues;
}
