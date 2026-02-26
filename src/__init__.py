# Claude AI Code Assistant - Modular Package

from src.file_manager import FileManager
from src.code_executor import CodeExecutor
from src.terminal_executor import TerminalExecutor
from src.tree_builder import TreeBuilder
from src.context_builder import ContextBuilder
from src.claude_assistant import ClaudeCodeAssistant
from src.genai_assistant import GenAICodeAssistant
from src.gemini_assistant import GeminiCodeAssistant
from src.token_manager import TokenManager
from src.api_retry import APIRetry
from src.history_manager import HistoryManager
from src.file_watcher import FileWatcher
from src.template_manager import TemplateManager
from src.file_pattern_matcher import FilePatternMatcher
from src.response_parser import ResponseParser
from src.cli_input import CLIInputHandler
from src.diff_viewer import DiffViewer
from src.command_registry import CommandRegistry
from src.context_processor import ContextProcessor

__all__ = [
    'FileManager',
    'CodeExecutor',
    'TerminalExecutor',
    'TreeBuilder',
    'ContextBuilder',
    'ClaudeCodeAssistant',
    'GenAICodeAssistant',
    'GeminiCodeAssistant',
    'TokenManager',
    'APIRetry',
    'HistoryManager',
    'FileWatcher',
    'TemplateManager',
    'FilePatternMatcher',
    'ResponseParser',
    'CLIInputHandler',
    'DiffViewer',
    'CommandRegistry',
    'ContextProcessor',
]
