"""Versioned prompts for the large-context Map/Reduce pipeline."""

PROMPT_SCHEMA_VERSION = "1.1.011-1"


def build_map_prompt(question: str, inventory: str, payload: str) -> str:
    return f"""You are performing a read-only Map pass over an explicitly bounded source chunk.
Do not call tools, create files, or claim knowledge outside the supplied chunk.
User request:\n{question}\n\nChunk inventory:\n{inventory}\n\nSource chunk:\n{payload}

Return concise Markdown with exactly these sections:
## Scope
## Key facts
## Symbols and responsibilities
## Dependencies and relationships
## Risks / unknowns
## Evidence
Every material fact must cite relative/path.ext:Lx-Ly where possible. Use Unknown when evidence is absent.
"""


def build_reduce_prompt(question: str, summaries: str, inventory: str, *, level: int, final: bool, tree: str = "") -> str:
    mode = "final answer" if final else "intermediate evidence-preserving summary"
    tree_block = f"\nCompressed project tree (use once):\n{tree}\n" if tree else ""
    return f"""Produce a {mode} from read-only summaries. Do not call tools or mutate files.
Preserve file/line evidence, conflicts, unknowns, read failures, and child summary identifiers.
Reduce level: {level}
User request:\n{question}\n\nFile inventory and completeness:\n{inventory}{tree_block}\nInput summaries:\n{summaries}
{('Answer in the language and format requested by the user.' if final else 'Return a materially smaller Markdown summary.')}
"""
