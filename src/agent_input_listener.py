"""
AgentInputListener - 에이전트 루프 중 비동기 stop 입력 수신 (FSD v1.0.087)

에이전트 `run()` 루프가 API 호출 / 코드 실행으로 블로킹되어 있을 때,
사용자가 별도 키 입력('s' / 'q' 등) 으로 루프를 안전하게 중단할 수 있도록
백그라운드 데몬 스레드로 stdin 을 폴링한다.

플랫폼별 구현:
    - Windows: `msvcrt.kbhit()` + `msvcrt.getch()` (char 단위)
    - Unix:    `select.select([sys.stdin], ...)` + `readline()` (라인 단위)

TTY 가 아닌 환경(파이프/CI)에서는 자동으로 비활성화된다 — Ctrl+C 가 유일한 수단.

주의:
    - 실제 루프 중단은 "다음 체크포인트에서" 수행된다 (즉시 중단 아님).
      API 호출 / 코드 실행이 진행 중이면 해당 작업이 끝난 후 반응한다.
    - 데몬 스레드이므로 메인 프로세스 종료 시 자동 정리된다.
    - `input()` / `readline` 과 같은 stdin 을 읽는 다른 코드 경로와 동시에
      활성화해서는 안 된다 → `pause()` 로 일시 정지 후 재개할 것.
"""

import sys
import threading
import time
from typing import Optional


def _is_windows() -> bool:
    return sys.platform.startswith("win")


class AgentInputListener:
    """에이전트 루프 실행 중 비동기 입력 리스너.

    사용법:
        listener = AgentInputListener()
        listener.start()
        try:
            while not listener.is_stop_requested():
                ...  # 루프 본문
                # stdin 이 필요한 구간에서는 일시 정지
                with listener.paused():
                    user_input = input(...)
        finally:
            listener.stop()
    """

    POLL_INTERVAL = 0.1           # 100ms
    WINDOWS_STOP_CHARS = {"s", "q"}
    UNIX_STOP_WORDS = {"s", "stop", "q", "quit"}

    def __init__(self, poll_interval: Optional[float] = None):
        self._stop_event = threading.Event()
        self._active = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._enabled = self._detect_tty()
        self._poll_interval = (
            poll_interval if poll_interval is not None else self.POLL_INTERVAL
        )

    # ─── 환경 감지 ───────────────────────────────────────────
    @staticmethod
    def _detect_tty() -> bool:
        try:
            return bool(sys.stdin) and sys.stdin.isatty()
        except Exception:
            return False

    @property
    def enabled(self) -> bool:
        """TTY 환경 여부 (False 이면 리스너 동작하지 않음)."""
        return self._enabled

    @property
    def is_listening(self) -> bool:
        """현재 백그라운드 스레드가 폴링 중인가."""
        return self._thread is not None and self._thread.is_alive()

    # ─── 상태 조회 ───────────────────────────────────────────
    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def clear_stop(self) -> None:
        """stop 요청 플래그 초기화 (테스트/재사용 용)."""
        self._stop_event.clear()

    # ─── 스레드 수명주기 ─────────────────────────────────────
    def start(self) -> None:
        """리스너 스레드 기동. TTY 가 아니거나 이미 동작 중이면 무시."""
        if not self._enabled:
            return
        if self.is_listening:
            return
        self._active.set()
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="agent-input-listener",
        )
        self._thread.start()

    def stop(self) -> None:
        """리스너 스레드에 종료 요청. stop 요청 플래그는 유지된다.

        데몬 스레드이므로 현재 블로킹 중인 stdin 읽기가 있어도
        메인 프로세스 종료 시 자동 정리된다.
        """
        self._active.clear()
        # 폴링 간격 내에 자연 종료 — join 은 하지 않는다
        # (getch/readline 이 블로킹 중이면 join 이 지연되기 때문)
        self._thread = None

    def paused(self) -> "_PauseContext":
        """stdin 을 직접 읽어야 하는 구간에서 사용하는 컨텍스트 매니저.

        ```python
        with listener.paused():
            ans = input("[c/f/s]? ")
        ```
        """
        return _PauseContext(self)

    # ─── 내부 폴링 루프 ─────────────────────────────────────
    def _listen_loop(self) -> None:
        try:
            if _is_windows():
                self._poll_windows()
            else:
                self._poll_unix()
        except Exception:
            # 리스너 오류는 조용히 무시 — Ctrl+C 가 폴백
            pass

    def _poll_windows(self) -> None:
        try:
            import msvcrt  # type: ignore[import-not-found]
        except ImportError:
            return

        while self._active.is_set():
            try:
                if msvcrt.kbhit():
                    raw = msvcrt.getch()
                    try:
                        ch = raw.decode("utf-8", errors="ignore").lower()
                    except Exception:
                        ch = ""
                    if ch and ch in self.WINDOWS_STOP_CHARS:
                        self._stop_event.set()
                        return
            except Exception:
                return
            time.sleep(self._poll_interval)

    def _poll_unix(self) -> None:
        try:
            import select
        except ImportError:
            return

        while self._active.is_set():
            try:
                ready, _, _ = select.select(
                    [sys.stdin], [], [], self._poll_interval
                )
                if not ready:
                    continue
                line = sys.stdin.readline()
                if not line:
                    # stdin 이 닫힘 → 더 이상 폴링 의미 없음
                    return
                normalized = line.strip().lower()
                if normalized in self.UNIX_STOP_WORDS:
                    self._stop_event.set()
                    return
            except Exception:
                return


class _PauseContext:
    """AgentInputListener.paused() 컨텍스트 매니저 구현."""

    def __init__(self, listener: AgentInputListener):
        self._listener = listener
        self._was_listening = False

    def __enter__(self):
        self._was_listening = self._listener.is_listening
        if self._was_listening:
            self._listener.stop()
        return self._listener

    def __exit__(self, exc_type, exc, tb):
        if self._was_listening:
            self._listener.start()
        return False
