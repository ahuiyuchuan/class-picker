"""全屏与页面导航组合回归，检查真实布局和原生中间尺寸。

@author ahui
使用隔离名单；四个管理页均覆盖普通、最大化、全屏，避免只验证课堂页。
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
ARTIFACTS = Path(tempfile.mkdtemp(prefix="fullscreen-pages-", dir=ROOT.parent))
os.environ["CLASS_PICKER_DATA_DIR"] = str(ARTIFACTS / "data")
import main
import verify_window
from storage import Store


def run(api):
    """点击实际导航，验证占满可用区域、返回可点击；监听退出全屏时的 Resize。"""
    from System import Func, Object

    window = api._window
    report = {
        "passed": False,
        "checks": [],
        "violations": [],
        "exit_resizes": [],
        "webview_resizes": [],
    }

    def wait(code):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if window.evaluate_js(code):
                return
            time.sleep(0.05)
        raise AssertionError(code)

    def click(selector):
        wait(
            f"!!document.querySelector({json.dumps(selector)}) && !document.querySelector({json.dumps(selector)}).disabled"
        )
        window.evaluate_js(f"document.querySelector({json.dumps(selector)}).click()")
        time.sleep(0.08)

    def settled():
        wait("!document.querySelector('.window-actions button').disabled")
        time.sleep(0.1)

    def check_page(label):
        metrics = window.evaluate_js("""(() => {
            const page=document.querySelector('.management-page'), r=page.getBoundingClientRect();
            const button=page.querySelector('.page-heading button'), b=button.getBoundingClientRect();
            const bar=document.querySelector('.topbar').getBoundingClientRect();
            const full=document.querySelector('.app-shell').classList.contains('is-fullscreen');
            return {top:r.top,bottom:r.bottom,height:r.height,expectedTop:full?0:bar.height,
                viewport:innerHeight,clickable:button.contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2)),
                overflow:document.documentElement.scrollHeight>innerHeight};
        })()""")
        report["checks"].append({"label": label, **metrics})
        if (
            abs(metrics["top"] - metrics["expectedTop"]) > 1
            or abs(metrics["bottom"] - metrics["viewport"]) > 1
            or not metrics["clickable"]
            or metrics["overflow"]
        ):
            report["violations"].append(label)

    def screenshot(name):
        """捕获当前应用的 WebView 内容，用于核对四个管理页的全屏可见性。"""
        from System.IO import FileStream, FileMode
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat

        stream = FileStream(str(ARTIFACTS / name), FileMode.Create)
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

    try:
        wait("!!document.querySelector('.class-trigger')")
        for mode in ["small", "normal", "maximized", "fullscreen", "fullscreen-zoom"]:
            if mode in ("small", "normal"):
                window.resize(*((800, 560) if mode == "small" else (1280, 820)))
                time.sleep(0.15)
            elif mode == "maximized":
                click(".window-actions button:nth-child(2)")
                settled()
            elif mode == "fullscreen":
                click(".full-btn")
                settled()
            elif mode == "fullscreen-zoom":

                def zoom():
                    window.native.browser.webview.ZoomFactor = 2.0
                    return None

                window.native.Invoke(Func[Object](zoom))
                time.sleep(0.15)
            for index, page in enumerate(["history", "roster", "settings", "about"]):
                if index == 0:
                    click(".recent")
                else:
                    click(".gear-button")
                    click(f".settings-popover button:nth-child({index})")
                wait(f"!!document.querySelector('.{page}-page')")
                check_page(f"{mode}: {page}")
                if mode.startswith("fullscreen") and not report["violations"]:
                    screenshot(f"{page}-{mode}.png")
                    # 子页面退出再进入全屏，不能丢页面或变成无法退出的状态。
                    window.evaluate_js(
                        "window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))"
                    )
                    wait(
                        "!document.querySelector('.app-shell').classList.contains('is-fullscreen')"
                    )
                    settled()
                    check_page(f"Escape: {page}")
                    window.evaluate_js(
                        "window.dispatchEvent(new KeyboardEvent('keydown',{key:'F11'}))"
                    )
                    wait(
                        "document.querySelector('.app-shell').classList.contains('is-fullscreen')"
                    )
                    settled()
                    check_page(f"F11: {page}")
                click(".page-heading button")
                wait("!!document.querySelector('.full-btn')")

        def reset_zoom():
            window.native.browser.webview.ZoomFactor = 1.0
            return None

        window.native.Invoke(Func[Object](reset_zoom))

        def resized(sender, event):
            form = window.native
            report["exit_resizes"].append(
                [str(form.WindowState), form.Width, form.Height]
            )

        def attach():
            window.native.Resize += resized
            window.native.browser.webview.Resize += webview_resized
            return None

        def webview_resized(sender, event):
            view = window.native.browser.webview
            report["webview_resizes"].append([view.Width, view.Height])

        window.native.Invoke(Func[Object](attach))
        click(".full-btn")
        settled()
        final_size = []

        def final_geometry():
            from System.Windows.Forms import Screen

            form = window.native
            work = Screen.FromControl(form).WorkingArea
            final_size.extend([form.ClientSize.Width, form.ClientSize.Height])
            if form.Bounds != work or str(form.WindowState) != "Maximized":
                report["violations"].append("退出全屏必须回到最大化工作区")
            return None

        window.native.Invoke(Func[Object](final_geometry))
        if not report["webview_resizes"] or any(
            size != final_size for size in report["webview_resizes"]
        ):
            report["violations"].append(
                "WebView 收到了非最终尺寸，可能产生内容缩放闪动"
            )

        # 故障注入仅进入辅助上下文，验证 finally 不留下隐藏窗口/冻结布局。
        def failed_transition():
            from window_transition import batch_window_transition

            form = window.native
            try:
                with batch_window_transition(form):
                    raise RuntimeError("test-only transition failure")
            except RuntimeError:
                pass
            if not form.Visible:
                report["violations"].append("异常退出后窗口重绘/可见状态未恢复")
            return None

        window.native.Invoke(Func[Object](failed_transition))
        click(".window-actions button:nth-child(2)")
        settled()
        window.resize(1000, 700)
        time.sleep(0.1)
        wait("innerWidth===1000 && innerHeight===700")
        report["passed"] = not report["violations"]
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        (ARTIFACTS / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        window.destroy()


if __name__ == "__main__":
    store = Store(ARTIFACTS / "data")
    cid = store.mutate("save_class", {"name": "全屏回归班"})["classes"][0]["id"]
    store.mutate(
        "add_students",
        {"class_id": cid, "rows": [{"name": f"学生{i}"} for i in range(20)]},
    )
    store.draw(cid, "fullscreen-page-fixture")
    verify_window.run = run
    sys.argv.append("--verify-window")
    main.main()
    result = json.loads((ARTIFACTS / "report.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "violations": result["violations"],
                "exit_resizes": result["exit_resizes"],
                "webview_resizes": result["webview_resizes"],
                "error": result.get("error"),
                "report": str(ARTIFACTS),
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0 if result["passed"] else 1)
