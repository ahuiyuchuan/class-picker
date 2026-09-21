"""真实 WebView2 交互回归：筛选全选、输入法、忙碌锁及键盘菜单。

@author ahui
自动创建隔离数据目录，真实点击 DOM 并核对数据库；延迟仅在测试进程生效。
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
ARTIFACTS = Path(tempfile.mkdtemp(prefix="audit-ui-", dir=ROOT.parent))
os.environ["CLASS_PICKER_DATA_DIR"] = str(ARTIFACTS / "data")
import main
import verify_window
from storage import Store


def run(api):
    """记录通过项；失败保存步骤和异常，并关闭测试窗口。"""
    window = api._window
    report = {"passed": False, "checks": []}

    def wait(code):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if window.evaluate_js(code):
                return
            time.sleep(0.05)
        raise AssertionError(code)

    def click(selector):
        wait(f"!!document.querySelector({json.dumps(selector)})")
        window.evaluate_js(f"document.querySelector({json.dumps(selector)}).click()")

    def fill(selector, value):
        window.evaluate_js(f"""(() => {{const el=document.querySelector({json.dumps(selector)});
            el.value={json.dumps(value)};el.dispatchEvent(new Event('input',{{bubbles:true}}));}})()""")

    try:
        wait("!!document.querySelector('.class-trigger')")
        window.evaluate_js(
            "document.querySelector('.gear-button').focus();document.querySelector('.gear-button').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true}))"
        )
        wait("document.activeElement.textContent.trim()==='关于'")
        report["checks"].append("齿轮向上键从最后一项开始")
        click(".settings-popover button:first-child")
        wait("document.querySelectorAll('tbody tr').length===3")
        click("tbody tr:first-child input[type=checkbox]")
        fill(".search-field input", "乙")
        wait("document.querySelectorAll('tbody tr').length===1")
        assert window.evaluate_js("!document.querySelector('thead input').checked"), (
            "隐藏选择不得冒充全选"
        )
        click("thead input")
        fill(".search-field input", "")
        wait("document.querySelectorAll('tbody tr').length===3")
        assert window.evaluate_js(
            "document.querySelector('thead input').indeterminate"
        ), "部分选择应为半选"
        assert window.evaluate_js(
            "document.querySelectorAll('tbody input[type=checkbox]:checked').length===2"
        )
        click("thead input")
        fill(".search-field input", "乙")
        wait("document.querySelectorAll('tbody tr').length===1")
        click("thead input")
        fill(".search-field input", "")
        wait("document.querySelectorAll('tbody tr').length===3")
        assert window.evaluate_js(
            "JSON.stringify([...document.querySelectorAll('tbody tr input[type=checkbox]')].map(x=>x.checked))==='[true,false,true]'"
        ), "取消筛选全选不得取消隐藏行"
        report["checks"].append("筛选全选、半选与隐藏选择保留")

        click("tbody tr:first-child button[aria-label=编辑学生]")
        fill("input[aria-label=编辑姓名]", "甲修改")
        window.evaluate_js(
            "document.querySelector('input[aria-label=编辑姓名]').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true}));document.querySelector('input[aria-label=编辑姓名]').dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',isComposing:true,bubbles:true}))"
        )
        time.sleep(0.15)
        assert api._store.snapshot()["classes"][0]["students"][0]["name"] == "甲"
        assert window.evaluate_js(
            "!!document.querySelector('input[aria-label=编辑姓名]')"
        )
        report["checks"].append("输入法确认候选不提前保存")

        original = api._store.mutate
        writes = []

        def delayed(action, payload):
            if action == "save_student":
                writes.append(action)
                time.sleep(0.4)
            return original(action, payload)

        api._store.mutate = delayed
        window.evaluate_js(
            "for(let i=0;i<2;i++)document.querySelector('input[aria-label=编辑姓名]').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))"
        )
        wait("document.querySelector('thead input').disabled")
        assert window.evaluate_js(
            "[...document.querySelectorAll('tbody input[type=checkbox]')].every(el=>el.disabled)"
        )
        wait("!document.querySelector('input[aria-label=编辑姓名]')")
        assert len(writes) == 1, writes
        assert api._store.snapshot()["classes"][0]["students"][0]["name"] == "甲修改"
        report["checks"].append("真正回车保存一次，忙碌时冻结名单选择")
        # 合法的 60 字姓名/学号也必须可读且不能覆盖抽取按钮。
        cid = api._store.snapshot()["classes"][0]["id"]
        api._store.mutate(
            "import",
            {
                "class_id": cid,
                "replace": True,
                "rows": [{"name": "长姓名" * 20, "no": "学号" * 30}],
            },
        )
        api._store.mutate(
            "settings", {"values": {"font_size": "huge", "effect": "direct"}}
        )
        api._store.draw(cid, "audit-long-result")
        window.resize(800, 560)
        click(".page-heading button")
        click(".gear-button")
        click(".settings-popover button:nth-child(2)")
        wait("!!document.querySelector('.settings-page')")
        window.evaluate_js(
            "[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='超大').click()"
        )
        window.evaluate_js(
            "[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='直接显示').click()"
        )
        click(".settings-footer .primary-btn")
        wait(
            "document.querySelector('.settings-footer .primary-btn').disabled && !document.querySelector('.page-heading button').disabled"
        )
        click(".page-heading button")
        wait("document.querySelector('.name')?.textContent.trim().length===60")
        fits = window.evaluate_js("""(() => {
            const card=document.querySelector('.result-card').getBoundingClientRect();
            const element=document.querySelector('.result-card');
            return ['.name','.number'].every(selector=>{
                const r=document.querySelector(selector).getBoundingClientRect();
                return r.top>=card.top && r.left>=card.left && r.right<=card.right;
            }) && element.scrollWidth<=element.clientWidth+1
              && (element.scrollHeight<=element.clientHeight+1 || getComputedStyle(element).overflowY==='auto')
              && card.bottom<=document.querySelector('.draw-btn').getBoundingClientRect().top;
        })()""")
        assert fits, "60 字姓名/学号超出结果卡片"
        report["checks"].append("最小窗口与超大字号下长姓名/学号边界")
        # 只截取测试应用内容，用于确认边界修复没有掩盖或覆盖主要操作。
        from System import Func, Object
        from System.IO import FileStream, FileMode
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat

        stream = FileStream(str(ARTIFACTS / "long-result.png"), FileMode.Create)
        try:
            task = window.native.Invoke(
                Func[Object](
                    lambda: (
                        window.native.browser.webview.CoreWebView2.CapturePreviewAsync(
                            CoreWebView2CapturePreviewImageFormat.Png, stream
                        )
                    )
                )
            )
            task.Wait()
        finally:
            stream.Close()
        report["passed"] = True
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        (ARTIFACTS / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        window.destroy()


if __name__ == "__main__":
    store = Store(ARTIFACTS / "data")
    cid = store.mutate("save_class", {"name": "审查班"})["classes"][0]["id"]
    store.mutate(
        "add_students",
        {"class_id": cid, "rows": [{"name": name} for name in ["甲", "乙", "丙"]]},
    )
    verify_window.run = run
    sys.argv.append("--verify-window")
    main.main()
    result = json.loads((ARTIFACTS / "report.json").read_text(encoding="utf-8"))
    print(json.dumps({**result, "report": str(ARTIFACTS)}, ensure_ascii=False))
    sys.exit(0 if result["passed"] else 1)
