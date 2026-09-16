"""本机 Agent：API 客户端、LLM、页面解析与流水线。"""

from resume_agent.pipeline import ProcessResult, process_candidate
from resume_agent.parse_page import RawCandidate, detect_risk_page, parse_list_html

__all__ = [
    "ProcessResult",
    "RawCandidate",
    "detect_risk_page",
    "parse_list_html",
    "process_candidate",
]
