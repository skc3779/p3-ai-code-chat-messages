"""
AgentInputListener - 에이전트 루프 중 비동기 stop 입력 수신 (FSD v1.0.087 / v1.1.062 P4)

에이전트 `run()` 루프가 API 호출 / 코드 실행으로 블로킹되어 있을 때,
사용자가 별도 키 입력으로 루프를 통제할 수 있도록 백그라운드 데몬 스레드로
stdin 을 폴링한다.

지원 키 (FSD v1.1.062 §3.6, FR-062-06):
    - 's' / 'q'      : 중단 (기존)
    - 'p'            : 일시정지/재개 토글
    - 'i'            : 인터럽트 후 피드백 주입(스티어) 요청

우선순위 s > p > i: 같은 폴링 주기에 여러 키가 버퍼링되면 stop 을 최우선으로,
그다음 pause, 그다음 steer 를 처리한다. 이미 버퍼된 약한 우선순위 키는 더 강한
키가 들어오면 무시(flush)된다.

플랫폼별 구현:
    - Windows: `msvcrt.kbhit()` + `msvcrt.getch()` (char 단위)
    - Unix:    `select.select([sys.stdin], ...)` + `readline()` (라인 단위)

TTY 가 아닌 환경(파이프/CI)에서는 자동으로 비활성화된다 — Ctrl+C 가 유일한 수단.

주의:
    - 실제 루프 중단/스티어는 "다음 체크포인트(action 경계)에서" 수행된다
      (즉시 중단 아님). API 호출 / 코드 실행이 진행 중이면 해당 작업이 끝난 후
      반응한다 (between-action steering).
    - 데몬 스레드이므로 메인 프로세스 종료 시 자동 정리된다.
    - `input()` / `readline` 과 같은 stdin 을 읽는 다른 코드 경로와 동시에
      활성화해서는 안 된다 → `pause()` 로 일시 정지 후 재개할 것.
      스티어('i') 피드백 수집·pause('p') 처리도 반드시 `paused()` 경계 안에서
      수행해야 한다 (리스너 스레드와 동기 input 동시 소비 금지).
"""

import os
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
    # P4 (FR-062-06): 스티어('i') / 일시정지('p') 키
    WINDOWS_STEER_CHARS = {"i"}
    UNIX_STEER_WORDS = {"i", "interrupt"}
    WINDOWS_PAUSE_CHARS = {"p"}
    UNIX_PAUSE_WORDS = {"p", "pause"}

    def __init__(self, poll_interval: Optional[float] = None):
        self._stop_event = threading.Event()
        self._active = threading.Event()
        # P4: 스티어/일시정지 요청 플래그 (스레드 → 메인 루프 신호)
        self._steer_event = threading.Event()
        self._pause_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()
        self._enabled = self._detect_tty()
        self._poll_interval = (
            poll_interval if poll_interval is not None else self.POLL_INTERVAL
        )
        self._terminal_fd: Optional[int] = None
        self._terminal_attrs = None
        self._terminal_flags: Optional[int] = None
        self._terminal_lock = threading.Lock()

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

    # ─── P4: 스티어('i') / 일시정지('p') 상태 (FR-062-06) ──────
    def is_steer_requested(self) -> bool:
        """스티어('i') 인터럽트가 버퍼되어 있는가 (소비하지 않음)."""
        return self._steer_event.is_set()

    def pop_steer_request(self) -> Optional[str]:
        """스티어 요청을 소비한다. 요청이 있었으면 True 를 반환하고 플래그를
        초기화, 없으면 None.

        (현재 리스너는 키만 감지하므로 페이로드는 bool 플래그로 표현된다 —
        실제 피드백 텍스트는 메인 루프가 paused() 경계 안에서 수집한다.)
        """
        if self._steer_event.is_set():
            self._steer_event.clear()
            return True  # type: ignore[return-value]
        return None

    def clear_steer(self) -> None:
        """스티어 요청 플래그 초기화 (소비 없이 버림 — 우선순위 처리/재사용 용)."""
        self._steer_event.clear()

    def is_pause_requested(self) -> bool:
        """일시정지('p') 토글 요청이 버퍼되어 있는가 (소비하지 않음)."""
        return self._pause_event.is_set()

    def pop_pause_request(self) -> bool:
        """일시정지 토글 요청을 소비한다. 있었으면 True, 없으면 False."""
        if self._pause_event.is_set():
            self._pause_event.clear()
            return True
        return False

    def clear_pause(self) -> None:
        """일시정지 요청 플래그 초기화."""
        self._pause_event.clear()

    def clear_all(self) -> None:
        """모든 인터럽트 플래그 초기화 (stop/steer/pause)."""
        self._stop_event.clear()
        self._steer_event.clear()
        self._pause_event.clear()

    # ─── 스레드 수명주기 ─────────────────────────────────────
    def start(self) -> None:
        """리스너 스레드 기동. TTY 가 아니거나 이미 동작 중이면 무시."""
        if not self._enabled:
            return
        if self.is_listening:
            return
        with self._thread_lock:
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
        thread = self._thread
        if thread is not None and thread.is_alive() \
                and thread is not threading.current_thread():
            thread.join(timeout=max(0.2, self._poll_interval * 3))
        self._restore_terminal()
        with self._thread_lock:
            if self._thread is thread:
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
        finally:
            self._restore_terminal()

    def _classify_key(self, token: str, *, char_mode: bool) -> Optional[str]:
        """입력 토큰을 'stop' | 'pause' | 'steer' | None 으로 분류.

        char_mode=True 면 Windows char 집합, False 면 Unix 단어 집합을 사용.
        """
        if char_mode:
            if token in self.WINDOWS_STOP_CHARS:
                return "stop"
            if token in self.WINDOWS_PAUSE_CHARS:
                return "pause"
            if token in self.WINDOWS_STEER_CHARS:
                return "steer"
        else:
            if token in self.UNIX_STOP_WORDS:
                return "stop"
            if token in self.UNIX_PAUSE_WORDS:
                return "pause"
            if token in self.UNIX_STEER_WORDS:
                return "steer"
        return None

    def _apply_key(self, kind: Optional[str]) -> bool:
        """분류된 키를 우선순위(s > p > i)로 플래그에 반영.

        Returns:
            True  — stop 이 설정되어 폴링 루프를 종료해야 함.
            False — 계속 폴링.

        우선순위 처리: stop 이 들어오면 약한 플래그(pause/steer)를 flush 하고
        stop 만 남긴다. pause 가 들어오면 steer 를 flush 한다. 이렇게 같은
        주기에 여러 키가 버퍼되어도 더 강한 우선순위만 살아남는다.
        """
        if kind == "stop":
            # stop 최우선: 약한 플래그 제거 후 stop 설정.
            self._pause_event.clear()
            self._steer_event.clear()
            self._stop_event.set()
            return True
        if kind == "pause":
            # pause 는 steer 보다 우선: 버퍼된 steer 제거.
            self._steer_event.clear()
            self._pause_event.set()
            return False
        if kind == "steer":
            # 이미 stop/pause 가 버퍼된 경우 더 약한 steer 는 무시.
            if self._stop_event.is_set() or self._pause_event.is_set():
                return False
            self._steer_event.set()
            return False
        return False

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
                    if ch:
                        kind = self._classify_key(ch, char_mode=True)
                        if self._apply_key(kind):
                            return
            except Exception:
                return
            time.sleep(self._poll_interval)

    def _configure_unix_terminal(self) -> None:
        """Unix/WSL 에서 Enter 없이 단일 키를 읽도록 터미널을 cbreak 로 전환.

        cbreak 는 Ctrl+C 같은 signal 처리를 보존하면서 canonical line buffering 만
        끈다. 리스너 종료/일시정지 시 반드시 원래 속성으로 복구한다.
        """
        try:
            import fcntl
            import termios
            import tty
        except ImportError:
            return

        try:
            fd = sys.stdin.fileno()
            attrs = termios.tcgetattr(fd)
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            tty.setcbreak(fd)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        except Exception:
            return

        with self._terminal_lock:
            self._terminal_fd = fd
            self._terminal_attrs = attrs
            self._terminal_flags = flags

    def _restore_terminal(self) -> None:
        """리스너가 변경한 Unix 터미널 모드를 원복한다."""
        with self._terminal_lock:
            fd = self._terminal_fd
            attrs = self._terminal_attrs
            flags = self._terminal_flags
            self._terminal_fd = None
            self._terminal_attrs = None
            self._terminal_flags = None

        if fd is None:
            return
        try:
            import fcntl
            import termios
            if attrs is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
            if flags is not None:
                fcntl.fcntl(fd, fcntl.F_SETFL, flags)
        except Exception:
            pass

    def _poll_unix(self) -> None:
        try:
            import select
        except ImportError:
            return

        self._configure_unix_terminal()
        while self._active.is_set():
            try:
                ready, _, _ = select.select(
                    [sys.stdin], [], [], self._poll_interval
                )
                if not ready:
                    continue
                try:
                    raw = os.read(sys.stdin.fileno(), 32)
                except BlockingIOError:
                    continue
                if not raw:
                    # stdin 이 닫힘 → 더 이상 폴링 의미 없음
                    return
                text = raw.decode("utf-8", errors="ignore").lower()
                for ch in text:
                    if ch in ("\r", "\n"):
                        continue
                    kind = self._classify_key(ch, char_mode=True)
                    if self._apply_key(kind):
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
