"""真实 WinForms 窗口几何回归，不仅检查最大化布尔状态。

@author ahui
在隔离目录运行；验证工作区、全屏显示器边界和还原尺寸，结果写入 work。
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
ARTIFACTS = Path(tempfile.mkdtemp(prefix='window-transitions-', dir=ROOT.parent))
os.environ['CLASS_PICKER_DATA_DIR'] = str(ARTIFACTS / 'data')

import main
import verify_window


def run(api):
    """通过实际按钮完成状态循环，记录物理像素矩形并检查是否遮挡任务栏。"""
    from System import Func, Object
    from System.Drawing import Rectangle
    from System.Windows.Forms import Screen
    window = api._window
    report = {'passed': False, 'checks': [], 'violations': []}

    def wait(code):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if window.evaluate_js(code):
                return
            time.sleep(0.05)
        raise AssertionError(code)

    def geometry(label):
        result = {'label': label}

        def read():
            form = window.native
            screen = Screen.FromControl(form)
            for key, rect in [('bounds', form.Bounds), ('restore', form.RestoreBounds),
                              ('work', screen.WorkingArea), ('screen', screen.Bounds)]:
                result[key] = [rect.X, rect.Y, rect.Width, rect.Height]
            result['state'] = str(form.WindowState)
            result['fullscreen'] = bool(form.is_fullscreen)
            return None

        window.native.Invoke(Func[Object](read))
        report['checks'].append(result)
        return result

    def click(selector):
        wait(f"!!document.querySelector({json.dumps(selector)}) && !document.querySelector({json.dumps(selector)}).disabled")
        window.evaluate_js(f"document.querySelector({json.dumps(selector)}).click()")
        # 等待 bridge 回写和桌面窗口动画，几何判定不能只依赖一次 resize 事件。
        wait("!document.querySelector('.full-btn').disabled")
        time.sleep(0.25)

    def expect(condition, message):
        if not condition:
            report['violations'].append(message)

    def matches(left, right):
        return all(abs(a - b) <= 2 for a, b in zip(left, right))

    try:
        wait("!!document.querySelector('.draw-btn') && !document.querySelector('.full-btn').disabled")
        normal = geometry('initial normal')
        # 绕过自定义按钮，确认启动时已为系统最大化安装工作区约束。
        window.maximize()
        wait("!!document.querySelector('button[aria-label=还原]:not(:disabled)')")
        system_max = geometry('system maximize')
        expect(matches(system_max['bounds'], system_max['work']), '系统最大化也必须保留任务栏')
        click('.window-actions button:nth-child(2)')
        for cycle in range(3):
            click('.window-actions button:nth-child(2)')
            maximized = geometry(f'{cycle}: maximized')
            expect(maximized['state'] == 'Maximized', '最大化原生状态错误')
            expect(matches(maximized['bounds'], maximized['work']), '最大化必须使用工作区，不能覆盖任务栏')
            click('.full-btn')
            full = geometry(f'{cycle}: fullscreen')
            expect(full['fullscreen'] and matches(full['bounds'], full['screen']), '全屏必须占满所在显示器')
            click('.full-btn')
            back = geometry(f'{cycle}: exit fullscreen to maximized')
            expect(back['state'] == 'Maximized' and not back['fullscreen'], '退出全屏应恢复最大化')
            expect(matches(back['bounds'], back['work']), '退出全屏后最大化必须保留任务栏空间')
            click('.window-actions button:nth-child(2)')
            restored = geometry(f'{cycle}: restore normal')
            expect(restored['state'] == 'Normal' and matches(restored['bounds'], normal['bounds']),
                   '最大化→全屏→退出→还原必须回到原普通窗口尺寸与位置')

        # 普通窗口直接全屏也应还原为原尺寸；F11/Esc 走同一套状态切换。
        window.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown',{key:'F11'}))")
        wait("document.querySelector('.app-shell').classList.contains('is-fullscreen')")
        wait("!document.querySelector('.full-btn').disabled")
        window.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
        wait("!document.querySelector('.app-shell').classList.contains('is-fullscreen') && !document.querySelector('.full-btn').disabled")
        restored = geometry('normal fullscreen Escape restore')
        expect(matches(restored['bounds'], normal['bounds']), '普通窗口退出全屏必须恢复普通尺寸')

        # 用户手动调整过尺寸和位置时，不能每次还原为启动默认大小。
        window.resize(1000, 700)
        window.move(80, 90)
        time.sleep(0.25)
        resized = geometry('custom normal')
        click('.window-actions button:nth-child(2)')
        click('.full-btn')
        click('.full-btn')
        click('.window-actions button:first-child')
        expect(api.state()['minimized'], '退出全屏后的最大化窗口仍应能够最小化')
        window.restore()
        wait("!!document.querySelector('button[aria-label=最大化]:not(:disabled)')")
        restored = geometry('custom normal after minimize and restore')
        expect(matches(restored['bounds'], resized['bounds']), '调整过的普通尺寸和位置必须保留')

        # 模拟原显示器已断开：不改用户系统设置，只替换本进程的还原矩形。
        click('.full-btn')
        api._normal_before_fullscreen = Rectangle(-30000, -30000, 1000, 700)
        click('.full-btn')
        visible = geometry('unavailable monitor fallback')
        expect(visible['bounds'][0] >= visible['work'][0]
               and visible['bounds'][1] >= visible['work'][1], '原显示器不可用时还原窗口必须可见')
        report['passed'] = not report['violations']
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        (ARTIFACTS / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        window.destroy()


if __name__ == '__main__':
    verify_window.run = run
    sys.argv.append('--verify-window')
    main.main()
    result = json.loads((ARTIFACTS / 'report.json').read_text(encoding='utf-8'))
    print(json.dumps({'passed': result['passed'], 'violations': result['violations'],
                      'error': result.get('error'), 'report': str(ARTIFACTS)}, ensure_ascii=False))
    sys.exit(0 if result['passed'] else 1)
