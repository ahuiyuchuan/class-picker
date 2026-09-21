"""抽取人数变化的真实 WebView2 回归，使用全新隔离数据库。

@author ahui
从设置页修改人数和效果，验证请求等待、动画、成功及失败四个阶段。
测试桥接仅在本进程加入短延迟/单次失败，确保旧布局闪现可稳定复现。
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
ARTIFACTS = Path(tempfile.mkdtemp(prefix='draw-counts-', dir=ROOT.parent))
os.environ['CLASS_PICKER_DATA_DIR'] = str(ARTIFACTS / 'data')

import main
import verify_window
from storage import Store, DEFAULTS

original_data = main.WindowApi.data


def delayed_data(self, action, payload=None):
    """测试专用延迟：等待期间也必须按新人数布局；单次失败不写入数据。"""
    if action == 'draw':
        time.sleep(0.4)
        if getattr(self, '_fail_next_draw', False):
            self._fail_next_draw = False
            return {'ok': False, 'error': '测试抽取失败'}
    return original_data(self, action, payload)


def run(api):
    """验证 5→2→1→5、不同效果、连续点击、失败恢复及后续重试。"""
    window = api._window
    checks = []
    report = {'passed': False, 'checks': checks}

    def wait(code, label):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if window.evaluate_js(code):
                checks.append(label)
                return
            time.sleep(0.04)
        raise AssertionError(label)

    def press(text):
        assert window.evaluate_js(f"""(() => {{
            const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==={json.dumps(text)});
            if (!button || button.disabled) return false;
            button.click(); return true;
        }})()"""), text

    def visible_names():
        return window.evaluate_js("[...document.querySelectorAll('.multi-results b,.result-card .name')].map(e=>e.textContent.trim())")

    def configure(count, effect):
        window.evaluate_js("document.querySelector('.gear-button').click()")
        wait("!!document.querySelector('.settings-popover')", '设置菜单')
        press('应用设置')
        wait("!!document.querySelector('.settings-page')", '设置页面')
        window.evaluate_js(f"""(() => {{
            const input=document.querySelector('[aria-label=每次抽取人数]');
            input.value={json.dumps(str(count))};input.dispatchEvent(new Event('input',{{bubbles:true}}));
        }})()""")
        press(effect)
        press('保存设置')
        wait("document.querySelector('.save-status').textContent.includes('所有设置已保存')", '配置保存完成')
        press('返回课堂')
        wait("!!document.querySelector('.draw-btn')", '回到课堂')

    try:
        wait("document.querySelectorAll('.multi-results b').length===5", '初始五人结果')
        for count, effect in [(2, '姓名滚动'), (1, '姓名滚动'), (5, '姓名滚动'), (2, '简短揭晓'), (1, '直接显示')]:
            old_names = visible_names()
            configure(count, effect)
            assert visible_names() == old_names, '改配置不应改写上次真实结果'
            recent = window.evaluate_js("document.querySelector('.recent').textContent")
            before = len(api._store.snapshot()['classes'][0]['history'])
            window.evaluate_js("document.querySelector('.draw-btn').click();document.querySelector('.draw-btn').click()")
            wait("document.querySelector('.draw-btn').disabled", '请求中锁定抽取')
            wait(f"document.querySelectorAll('.multi-results b,.result-card .name').length==={count}", f'等待响应即显示{count}个槽位')
            assert window.evaluate_js("document.querySelector('.recent').textContent") == recent
            assert window.evaluate_js("!document.querySelector('.multi-results span') && !(document.querySelector('.number')?.textContent.trim())")
            if effect != '直接显示':
                time.sleep(0.6)
                names = visible_names()
                assert len(names) == count, '动画数量必须与本次设置一致'
                assert window.evaluate_js("document.querySelector('.draw-btn').disabled")
                assert window.evaluate_js("document.querySelector('.recent').textContent") == recent
                if effect == '姓名滚动':
                    assert len(set(names)) == count and all(name.startswith('测试学生') for name in names), names
                else:
                    assert names == ['抽取中…'] * count, names
            wait("!document.querySelector('.draw-btn').disabled", '抽取结束')
            latest = api._store.snapshot()['classes'][0]
            assert visible_names() == [student['name'] for student in latest['latest']]
            assert len(latest['latest']) == count and len(latest['history']) == before + 1
            checks.append(f'{count}人/{effect}布局、记录时序及重复提交通过')

        configure(5, '姓名滚动')
        previous = visible_names()
        before = api._store.snapshot()
        api._fail_next_draw = True
        window.evaluate_js("document.querySelector('.draw-btn').click()")
        wait("document.querySelectorAll('.multi-results b').length===5", '失败请求仍使用本次数量')
        wait("!document.querySelector('.draw-btn').disabled && document.querySelector('.notice')?.textContent.includes('测试抽取失败')", '失败提示并解锁')
        assert visible_names() == previous and api._store.snapshot() == before
        window.evaluate_js("document.querySelector('.draw-btn').click()")
        wait("document.querySelector('.draw-btn').disabled", '失败后可重试')
        wait("!document.querySelector('.draw-btn').disabled && document.querySelectorAll('.multi-results b').length===5", '重试成功')
        assert len(api._store.snapshot()['classes'][0]['history']) == len(before['classes'][0]['history']) + 1
        report['passed'] = True
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        (ARTIFACTS / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        window.destroy()


if __name__ == '__main__':
    store = Store(ARTIFACTS / 'data')
    cid = store.mutate('save_class', {'name': '人数变化测试班'})['classes'][0]['id']
    store.mutate('import', {'class_id': cid, 'rows': [{'name': f'测试学生{i}', 'no': str(i)} for i in range(12)]})
    store.mutate('settings', {'values': {**DEFAULTS, 'mode': 'random', 'count': 5, 'duration': 1}})
    store.draw(cid, 'seed-five-results')
    main.WindowApi.data = delayed_data
    verify_window.run = run
    sys.argv.append('--verify-window')
    main.main()
    result = json.loads((ARTIFACTS / 'report.json').read_text(encoding='utf-8'))
    print(json.dumps({'passed': result['passed'], 'error': result.get('error'), 'report': str(ARTIFACTS)}, ensure_ascii=False))
    sys.exit(0 if result['passed'] else 1)
