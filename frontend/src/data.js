/** @author ahui
 * 唯一本地快照。桥接成功后才替换状态；浏览器预览不伪装保存成功。
 */
import { reactive } from "vue";
export const state = reactive({
  classes: [],
  settings: {},
  defaults: {},
  last_class: null,
  ready: false,
});
/**
 * 调用桌面数据桥接，失败时拒绝 Promise，调用方负责保留草稿并显示错误。
 * @param {string} action 后端白名单动作名称。
 * @param {Object} payload 对应动作参数，默认空对象；不接受 SQL 或任意文件路径。
 * @returns {Promise<*>} 后端 value；文件对话框取消可返回 null 或 false。
 * @throws {Error} 桥接未就绪或后端返回失败；底层桥接异常原样传播。
 */
export async function call(action, payload = {}) {
  if (!window.pywebview?.api) throw new Error("请在桌面程序中使用此功能");
  const result = await window.pywebview.api.data(action, payload);
  if (!result.ok) throw new Error(result.error);
  return result.value;
}
/** @param {Object|null} value 完整业务快照；无 classes 时忽略，不修改当前页面数据。 */
export function apply(value) {
  if (value?.classes) Object.assign(state, value, { ready: true });
}
/**
 * 成功后统一发布快照；有延迟揭晓需求的抽取使用 call 后自行 apply。
 * @param {string} action 写入或 load 动作名称。
 * @param {Object} [payload] 动作参数，缺省时由 call 使用空对象。
 * @returns {Promise<Object>} 已发布的完整快照。
 * @throws {Error} 沿用 call 的失败条件，失败时不替换页面状态。
 */
export async function change(action, payload) {
  const result = await call(action, payload);
  apply(result);
  return result;
}
