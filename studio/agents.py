"""
CrewAI Agent definitions for Agentic Game Studio.
"""

from typing import Any, Optional
from config.settings import Settings, load_settings


def create_llm(settings: Optional[Settings] = None, api_key: Optional[str] = None) -> Any:
    """Instantiate CrewAI LLM configured for Google Gemini."""
    if settings is None:
        settings = load_settings()
    
    key = api_key or settings.gemini_api_key
    if not key:
        raise ValueError(
            "GEMINI_API_KEY is not configured. Please provide a valid API key in .env "
            "or set GEMINI_API_KEY environment variable."
        )
    model_name = settings.model_name
    # Ensure correct format for CrewAI Gemini integration
    if not model_name.startswith("gemini/"):
        model_name = f"gemini/{model_name}"

    try:
        from crewai import LLM
        return LLM(model=model_name, api_key=key)
    except ImportError:
        class DummyLLM:
            def __init__(self, model: str, api_key: str):
                self.model = model
                self.api_key = api_key
        return DummyLLM(model=model_name, api_key=key)


class _FallbackAgent:
    def __init__(self, role: str, goal: str, backstory: str, verbose: bool, llm: Any):
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.verbose = verbose
        self.llm = llm


def create_game_designer(llm: Any = None, settings: Optional[Settings] = None) -> Any:
    """Create the Creative Game Designer Agent."""
    if llm is None:
        llm = create_llm(settings)

    try:
        from crewai import Agent
        return Agent(
            role="Creative Game Designer",
            goal="Transform user ideas into fun, feasible 2D game designs with clear mechanics and controls.",
            backstory=(
                "You are an experienced 2D game designer. You excel at turning vague ideas into "
                "precise, structured game design documents including core gameplay loops, rules, "
                "win/lose conditions, player/enemy entities, and control schemes. You ensure "
                "the scope remains feasible for a single-file Pygame implementation."
            ),
            verbose=True,
            llm=llm,
        )
    except ImportError:
        return _FallbackAgent(
            role="Creative Game Designer",
            goal="Transform user ideas into fun, feasible 2D game designs with clear mechanics and controls.",
            backstory=(
                "You are an experienced 2D game designer. You excel at turning vague ideas into "
                "precise, structured game design documents including core gameplay loops, rules, "
                "win/lose conditions, player/enemy entities, and control schemes. You ensure "
                "the scope remains feasible for a single-file Pygame implementation."
            ),
            verbose=True,
            llm=llm,
        )


def create_game_developer(llm: Any = None, settings: Optional[Settings] = None) -> Any:
    """Create the Senior Python Game Developer Agent."""
    if llm is None:
        llm = create_llm(settings)

    try:
        from crewai import Agent
        return Agent(
            role="Senior Python Game Developer",
            goal="Write clean, robust, standalone Pygame code adhering to dual-runtime and smoke-test standards.",
            backstory=(
                "You are a senior software engineer specialized in Pygame development. "
                "You write clean, modular, self-contained Python scripts. You strictly follow "
                "the dual-runtime async pattern (async def main with await asyncio.sleep(0)) so code "
                "runs both on local Python and WebAssembly (Pygbag). You always incorporate a "
                "deterministic smoke-test hook that allows automated test runners to verify frames cleanly."
            ),
            verbose=True,
            llm=llm,
        )
    except ImportError:
        return _FallbackAgent(
            role="Senior Python Game Developer",
            goal="Write clean, robust, standalone Pygame code adhering to dual-runtime and smoke-test standards.",
            backstory=(
                "You are a senior software engineer specialized in Pygame development. "
                "You write clean, modular, self-contained Python scripts. You strictly follow "
                "the dual-runtime async pattern (async def main with await asyncio.sleep(0)) so code "
                "runs both on local Python and WebAssembly (Pygbag). You always incorporate a "
                "deterministic smoke-test hook that allows automated test runners to verify frames cleanly."
            ),
            verbose=True,
            llm=llm,
        )


def create_qa_engineer(llm: Any = None, settings: Optional[Settings] = None) -> Any:
    """Create the QA Engineer & Code Auditor Agent."""
    if llm is None:
        llm = create_llm(settings)

    try:
        from crewai import Agent
        return Agent(
            role="QA Engineer & Code Auditor",
            goal="Audit game code, design compliance, and empirical test metrics to produce objective quality reports.",
            backstory=(
                "You are a meticulous QA engineer and software auditor. You do not guess or hallucinate "
                "whether code works; you ground your analysis in empirical evidence: deterministic AST "
                "syntax checks, static structural analysis, and concrete execution logs. You report "
                "pass/fail status accurately and flag missing features or edge cases."
            ),
            verbose=True,
            llm=llm,
        )
    except ImportError:
        return _FallbackAgent(
            role="QA Engineer & Code Auditor",
            goal="Audit game code, design compliance, and empirical test metrics to produce objective quality reports.",
            backstory=(
                "You are a meticulous QA engineer and software auditor. You do not guess or hallucinate "
                "whether code works; you ground your analysis in empirical evidence: deterministic AST "
                "syntax checks, static structural analysis, and concrete execution logs. You report "
                "pass/fail status accurately and flag missing features or edge cases."
            ),
            verbose=True,
            llm=llm,
        )
