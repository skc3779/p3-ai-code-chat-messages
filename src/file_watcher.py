"""
FileWatcher - 파일 변경 감지 모듈

watchdog 라이브러리를 사용하여 파일 변경을 실시간으로 감지하고
자동으로 컨텍스트를 갱신합니다.
"""

import fnmatch
import threading
from pathlib import Path
from typing import Callable, List, Set, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object
    FileModifiedEvent = None


class FileChangeHandler(FileSystemEventHandler):
    """파일 변경 이벤트 핸들러!!!"""
    
    def __init__(self, patterns: Set[str], callback: Callable[[str], None], 
                 workspace_dir: Path):
        super().__init__()
        self.patterns = patterns
        self.callback = callback
        self.workspace_dir = workspace_dir
        self._lock = threading.Lock()
    
    def _matches_pattern(self, filepath: str) -> bool:
        """파일이 감시 패턴과 일치하는지 확인"""
        try:
            rel_path = str(Path(filepath).relative_to(self.workspace_dir))
            print(f"### _matches_pattern rel_path: {rel_path}")
        except ValueError:
            rel_path = filepath
            
        for pattern in self.patterns:
            print(f"### _matches_pattern pattern: {pattern}")
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(Path(filepath).name, pattern):
                return True
        return False
    
    def on_modified(self, event):
        """파일 수정 이벤트 처리"""
        if event.is_directory:
            return
            
        with self._lock:
            if self._matches_pattern(event.src_path):
                self.callback(event.src_path)


class FileWatcher:
    """파일 변경 감지 및 자동 컨텍스트 갱신 클래스"""
    
    def __init__(self, workspace_dir: str, callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            workspace_dir: 감시할 작업 디렉토리
            callback: 파일 변경 시 호출될 콜백 함수 (파일 경로를 인자로 받음)
        """
        self.workspace_dir = Path(workspace_dir).resolve()
        self.callback = callback or self._default_callback
        self.patterns: Set[str] = set()
        self._observer: Optional[Observer] = None
        self._handler: Optional[FileChangeHandler] = None
        self._running = False
        self._lock = threading.RLock()
        
        if not WATCHDOG_AVAILABLE:
            print("⚠️  watchdog 라이브러리가 설치되지 않았습니다.")
            print("💡 설치: pip install watchdog")
    
    def _default_callback(self, filepath: str) -> None:
        """기본 콜백: 변경 알림 출력"""
        try:
            rel_path = Path(filepath).relative_to(self.workspace_dir)
        except ValueError:
            rel_path = filepath
        print(f"\n🔄 파일 변경 감지: {rel_path}")
    
    def add_watch(self, pattern: str) -> bool:
        """
        감시 대상 패턴 추가
        
        Args:
            pattern: glob 패턴 (예: *.py, src/*.js)
            
        Returns:
            성공 여부
        """
        if not WATCHDOG_AVAILABLE:
            return False
            
        with self._lock:
            self.patterns.add(pattern)
            
            # Observer가 실행 중이면 핸들러 패턴 업데이트
            if self._handler:
                self._handler.patterns = self.patterns.copy()
                
            # 자동 시작
            if not self._running:
                self.start()
                
        return True
    
    def remove_watch(self, pattern: str) -> bool:
        """
        감시 대상 패턴 제거
        
        Args:
            pattern: 제거할 패턴
            
        Returns:
            성공 여부
        """
        with self._lock:
            if pattern in self.patterns:
                self.patterns.discard(pattern)
                
                if self._handler:
                    self._handler.patterns = self.patterns.copy()
                    
                # 패턴이 없으면 감시 중지
                if not self.patterns and self._running:
                    self.stop()
                    
                return True
        return False
    
    def get_watched_patterns(self) -> List[str]:
        """현재 감시 중인 패턴 목록 반환"""
        with self._lock:
            return sorted(list(self.patterns))
    
    def start(self) -> bool:
        """백그라운드 감시 시작"""
        if not WATCHDOG_AVAILABLE:
            print("❌ watchdog 라이브러리가 필요합니다.")
            return False
            
        with self._lock:
            if self._running:
                return True
                
            if not self.patterns:
                return False
                
            try:
                self._handler = FileChangeHandler(
                    patterns=self.patterns.copy(),
                    callback=self.callback,
                    workspace_dir=self.workspace_dir
                )
                self._observer = Observer()
                self._observer.schedule(
                    self._handler,
                    str(self.workspace_dir),
                    recursive=True
                )
                self._observer.start()
                self._running = True
                return True
            except Exception as e:
                print(f"❌ 파일 감시 시작 실패: {e}")
                return False
    
    def stop(self) -> None:
        """감시 중지"""
        with self._lock:
            if self._observer and self._running:
                self._observer.stop()
                self._observer.join(timeout=2)
                self._observer = None
                self._handler = None
                self._running = False
    
    def is_running(self) -> bool:
        """감시 중인지 여부"""
        return self._running
    
    def set_callback(self, callback: Callable[[str], None]) -> None:
        """콜백 함수 설정"""
        self.callback = callback
        if self._handler:
            self._handler.callback = callback
    
    def __del__(self):
        """소멸자: 리소스 정리"""
        self.stop()
