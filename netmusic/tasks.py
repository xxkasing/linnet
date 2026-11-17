"""后台任务工具：网络请求放到线程池，回调统一回到主线程"""
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class _Relay(QObject):
    """驻留在主线程，把工作线程信号转成主线程回调"""
    OK = 0
    ERR = 1

    def __init__(self, callback, kind):
        super().__init__()
        self._cb = callback
        self._kind = kind

    def call(self, value):
        try:
            if self._kind == _Relay.OK:
                self._cb(value)
            else:
                self._cb(str(value))
        except Exception as exc:  # 回调里出错不要吞掉整个事件循环
            print("[callback error]", exc)


class _Job(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _Signals()
        self.relays = []
        # 交给 Python 侧 _KEEP 管理生命周期，避免 C++ 对象先被回收导致回调时崩
        self.setAutoDelete(False)

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001
            try:
                self.signals.error.emit(str(exc))
            except RuntimeError:  # 程序退出瞬间信号对象已释放，忽略
                pass
        else:
            try:
                self.signals.done.emit(result)
            except RuntimeError:
                pass


class _Signals(QObject):
    done = pyqtSignal(object)
    error = pyqtSignal(str)


_KEEP = []


def run_async(fn, on_done=None, on_error=None):
    job = _Job(fn)
    if on_done is not None:
        relay = _Relay(on_done, _Relay.OK)
        job.signals.done.connect(relay.call)
        job.relays.append(relay)
    if on_error is not None:
        relay = _Relay(on_error, _Relay.ERR)
        job.signals.error.connect(relay.call)
        job.relays.append(relay)
    # 持有引用，防止 QRunnable 被回收导致回调丢失
    _KEEP.append(job)
    if len(_KEEP) > 120:
        del _KEEP[:60]
    QThreadPool.globalInstance().start(job)
    return job
