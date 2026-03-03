import sys
import time
import threading

class WaitSpinner:
    """CLI 환경에서 비동기적으로 동작하는 텍스트 스피너 유틸리티.
    
    API 응답 대기 시간 등 시간이 오래 걸리는 작업 동안 터미널에 
    진행 중임을 알리는 애니메이션을 표시합니다.
    """
    def __init__(self, message="🤖 AI가 답변을 고민 중입니다... "):
        self.message = message
        self.running = False
        self.spinner_thread = None

    def spin(self):
        chars = ['▘', '▚', '▝', '▞', '▙', '▛', '▟', '▜', '▇', '▆', '▅', '▄', '▃', '▂', '▁', '▂', '▃', '▄', '▅', '▆', '▇']
        idx = 0
        while self.running:
            # 윈도우 환경 등에서 커서를 맨 앞으로 돌리고 현재 프레임을 그림
            sys.stdout.write(f"\r{chars[idx]} {self.message}")
            sys.stdout.flush()
            idx = (idx + 1) % len(chars)
            time.sleep(0.3)
            
        # 스피너가 종료되면 해당 라인을 지움
        sys.stdout.write('\r' + ' ' * (len(self.message) + 2) + '\r')
        sys.stdout.flush()

    def start(self):
        """스피너 애니메이션을 백그라운드 스레드에서 시작합니다."""
        if not self.running:
            self.running = True
            self.spinner_thread = threading.Thread(target=self.spin, daemon=True)
            self.spinner_thread.start()

    def stop(self):
        """스피너 애니메이션을 중지하고 청소합니다."""
        if self.running:
            self.running = False
            self.spinner_thread.join()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.stop()
