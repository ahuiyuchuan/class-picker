"""显式 --verify-window 时运行的真实 WebView2 回归；不在普通启动执行。

@author ahui
结果保存到调用者指定路径；只允许使用调用者显式指定的隔离数据目录，测试数据不会写入正式目录。
"""
import json
import os
import time
from pathlib import Path


def run(api):
    """通过真实 DOM 按钮调用桥接，验证原生状态及可见布局，而非仅检查进程。"""
    assert os.environ.get("CLASS_PICKER_DATA_DIR"), "测试必须指定隔离数据目录"
    window = api._window
    results = []
    report = Path(os.environ.get('CLASS_PICKER_TEST_REPORT', 'window-check.json'))

    def wait_for(check, description):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if check():
                    results.append(description)
                    return
            except Exception:
                pass
            time.sleep(.1)
        raise AssertionError(description)

    def click(label):
        window.evaluate_js(f"document.querySelector('button[aria-label={label}]').click()")

    try:
        wait_for(lambda: window.evaluate_js("!!window.pywebview?.api && !!document.querySelector('.name')"), 'WebView2 mounted')
        click('最大化')
        wait_for(lambda: api.state()['maximized'], 'maximize button')
        wait_for(lambda: window.evaluate_js("!!document.querySelector('button[aria-label=还原]:not(:disabled)')"), 'restore icon synchronized')
        click('最小化')
        wait_for(lambda: api.state()['minimized'], 'minimize after maximize')
        window.restore()
        wait_for(lambda: not api.state()['minimized'], 'restore from minimized')
        wait_for(lambda: window.evaluate_js("!!document.querySelector('button[aria-label=最大化]:not(:disabled)')"), 'state synchronized after system restore')
        click('最大化')
        wait_for(lambda: api.state()['maximized'], 'maximize again')
        wait_for(lambda: window.evaluate_js("!!document.querySelector('button[aria-label=还原]:not(:disabled)')"), 'restore ready')
        click('还原')
        wait_for(lambda: not api.state()['maximized'], 'restore button')
        wait_for(lambda: window.evaluate_js("!document.querySelector('.full-btn').disabled"), 'fullscreen ready')
        window.evaluate_js("document.querySelector('.full-btn').click()")
        wait_for(lambda: api.state()['fullscreen'], 'native fullscreen')
        wait_for(lambda: window.evaluate_js("document.querySelector('.app-shell').classList.contains('is-fullscreen') && !document.querySelector('.full-btn').disabled"), 'fullscreen layout')
        window.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
        wait_for(lambda: not api.state()['fullscreen'], 'Escape exits fullscreen')
        wait_for(lambda: window.evaluate_js("!document.querySelector('.full-btn').disabled"), 'title double click ready')
        # Maximize/fullscreen must return to maximized, including a double-click title action.
        window.evaluate_js("document.querySelector('.brand').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))")
        wait_for(lambda: api.state()['maximized'], 'title double click maximizes')
        wait_for(lambda: window.evaluate_js("!document.querySelector('.full-btn').disabled"), 'fullscreen from maximized ready')
        window.evaluate_js("document.querySelector('.full-btn').click()")
        wait_for(lambda: api.state()['fullscreen'], 'fullscreen from maximized')
        wait_for(lambda: window.evaluate_js("!document.querySelector('.full-btn').disabled"), 'fullscreen exit ready')
        window.evaluate_js("document.querySelector('.full-btn').click()")
        wait_for(lambda: api.state()['maximized'] and not api.state()['fullscreen'], 'fullscreen restores maximized')
        window.restore()
        for width, height in [(1280,820), (1000,700), (900,600), (800,560), (1600,900)]:
            window.resize(width, height)
            time.sleep(.35)
            metrics = window.evaluate_js("""(() => {
                const box = s => { const r=document.querySelector(s).getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}; };
                const selectors=['.topbar','.contextbar','.result-card','.name','.number','.draw-btn','.shortcut','.stats','.bottom-row','.recent','.tools'];
                return {width:innerWidth,height:innerHeight,boxes:Object.fromEntries(selectors.map(s=>[s,box(s)])),scroll:document.documentElement.scrollHeight>innerHeight};
            })()""")
            assert not metrics['scroll'], metrics
            for name, rect in metrics['boxes'].items():
                assert rect['bottom'] <= metrics['height'] + 1 and rect['right'] <= metrics['width'] + 1, (name, metrics)
            assert metrics['boxes']['.result-card']['bottom'] <= metrics['boxes']['.draw-btn']['top'], metrics
            assert metrics['boxes']['.shortcut']['bottom'] <= metrics['boxes']['.stats']['top'], metrics
            assert abs(metrics['boxes']['.stats']['left'] - metrics['boxes']['.tools']['left']) < 1, metrics
            assert abs(metrics['boxes']['.stats']['right'] - metrics['boxes']['.recent']['right']) < 1, metrics
            assert metrics['height'] - metrics['boxes']['.recent']['bottom'] <= 24, metrics
            results.append({'layout': metrics})
        # WebView zoom exercises CSS-pixel contraction without changing user's OS settings.
        from System import Func, Object
        window.resize(1280, 820)
        for factor in [1.25, 1.5, 1.0]:
            def zoom():
                window.native.browser.webview.ZoomFactor = factor
                return None
            window.native.Invoke(Func[Object](zoom))
            time.sleep(.35)
            zoomed = window.evaluate_js("""(() => {
                const els=[...document.querySelectorAll('.topbar,.stats,.recent,.tools,.name,.number,.draw-btn,.shortcut')];
                return {width:innerWidth,height:innerHeight,visible:els.every(el=>{const r=el.getBoundingClientRect();return r.top>=0&&r.left>=0&&r.bottom<=innerHeight+1&&r.right<=innerWidth+1})};
            })()""")
            assert zoomed['visible'], zoomed
            results.append({'zoom': factor, 'layout': zoomed})
        def press(text, scope="document"):
            """按可见中文按钮文案执行，缺失或禁用立即失败。"""
            code = f"[...{scope}.querySelectorAll('button')].find(b=>b.textContent.trim()==={json.dumps(text)})"
            assert window.evaluate_js(f"!!({code}) && !({code}).disabled"), text
            window.evaluate_js(f"({code}).click()")

        def fill(selector, value):
            window.evaluate_js(f"(()=>{{const e=document.querySelector({json.dumps(selector)});e.value={json.dumps(value)};e.dispatchEvent(new Event('input',{{bubbles:true}}))}})()")

        def ready(selector, label):
            wait_for(lambda: window.evaluate_js(f"!!document.querySelector({json.dumps(selector)})"), label)

        def modal_done():
            wait_for(lambda: window.evaluate_js("!document.querySelector('dialog[open]')"), 'dialog saved')

        assert api._store.snapshot()['classes'] == []
        window.evaluate_js("window.confirm=()=>{throw new Error('native confirmation forbidden')};document.querySelector('.gear-button').click()")
        ready('.settings-popover', 'gear menu opens')
        press('班级名单')
        ready('.roster-page', 'roster navigation')
        press('新建班级')
        ready('dialog[open] input', 'new class form')
        fill('dialog input', '回归一班')
        press('保存', "document.querySelector('dialog')")
        modal_done()
        press('批量粘贴导入')
        ready('dialog textarea', 'paste form')
        fill('dialog textarea', '\n'.join(f'测试学生{i}' for i in range(1,31)))
        wait_for(lambda: window.evaluate_js("!document.querySelector('dialog button[type=submit]').disabled"), 'paste preview valid')
        press('确认导入')
        modal_done()
        wait_for(lambda: window.evaluate_js("document.querySelectorAll('.roster-panel tbody tr').length===30"), '30 students persisted and rendered')
        window.evaluate_js("document.querySelector('[aria-label=编辑学生]').click()")
        ready('[aria-label=编辑学号]', 'student inline edit')
        fill('[aria-label=编辑学号]', '001')
        window.evaluate_js("document.querySelector('.roster-panel .inline-check input').click()")
        press('保存', "document.querySelector('.roster-panel')")
        wait_for(lambda: window.evaluate_js("!document.querySelector('[aria-label=编辑学号]')"), 'inline edit saved')
        assert api._store.snapshot()['classes'][0]['students'][0]['enabled'] == 0
        results.append('student leading-zero number and disabled state saved')
        for width,height in [(1280,820),(800,560)]:
            window.resize(width,height)
            time.sleep(.3)
            assert window.evaluate_js("document.documentElement.scrollWidth<=innerWidth && document.documentElement.scrollHeight<=innerHeight"), 'roster overflow'
            assert window.evaluate_js("document.querySelector('.table-scroll').clientHeight>80"), 'usable roster table'
        press('返回课堂')
        ready('.draw-btn', 'return to classroom')
        window.evaluate_js("document.querySelector('.draw-btn').click()")
        wait_for(lambda: window.evaluate_js("!document.querySelector('.draw-btn').disabled && document.querySelector('.name').textContent.includes('测试学生')"), 'draw result committed and displayed')
        assert len(api._store.snapshot()['classes'][0]['history']) == 1
        window.evaluate_js("document.querySelector('.tools button:last-child').click()")
        ready('dialog[open]', 'custom reset opens')
        before=api._store.snapshot()
        window.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown',{code:'Space',key:' '}))")
        time.sleep(.2)
        assert api._store.snapshot()==before
        press('取消', "document.querySelector('dialog')")
        modal_done()
        window.evaluate_js("document.querySelector('.gear-button').click()")
        ready('.settings-popover', 'settings menu')
        press('应用设置')
        ready('.settings-page', 'settings navigation')
        fill('input[aria-label=每次抽取人数]', '2')
        wait_for(lambda: window.evaluate_js("document.querySelector('.save-status').textContent.includes('有未保存')"), 'unsaved indicator')
        press('返回课堂')
        ready('dialog[open]', 'unsaved changes guarded')
        press('取消', "document.querySelector('dialog')")
        modal_done()
        press('保存设置')
        wait_for(lambda: api._store.snapshot()['settings']['count']==2, 'global count persisted')
        for width,height in [(1280,820),(800,560)]:
            window.resize(width,height)
            time.sleep(.3)
            assert window.evaluate_js("document.documentElement.scrollWidth<=innerWidth && document.documentElement.scrollHeight<=innerHeight"), 'settings overflow'
            assert window.evaluate_js("document.querySelector('.settings-footer').getBoundingClientRect().bottom<=innerHeight+1"), 'save footer visible'
        press('返回课堂')
        ready('.draw-btn', 'settings back')
        window.evaluate_js("document.querySelector('.draw-btn').click()")
        wait_for(lambda: window.evaluate_js("document.querySelectorAll('.multi-results>div').length===2 && !document.querySelector('.draw-btn').disabled"), 'two-person draw')
        from storage import Store
        assert Store(api._store.folder).snapshot()==api._store.snapshot()
        results.append('fresh connection restores settings, roster, progress and latest result')
        assert window.evaluate_js("document.querySelectorAll('select').length===0")
        assert window.evaluate_js("getComputedStyle(document.querySelector('.draw-btn')).backgroundImage==='none'")
        results.append('custom dropdowns and stable draw background')
        report.write_text(json.dumps({'passed': True, 'checks': results}, ensure_ascii=False, indent=2), encoding='utf-8')
        click('关闭')
    except Exception as exc:
        report.write_text(json.dumps({'passed': False, 'error': str(exc), 'checks': results}, ensure_ascii=False, indent=2), encoding='utf-8')
        window.destroy()
