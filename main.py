"""
Agentic Game Studio - CLI Entrypoint
Multi-Agent Game Generation with Automated Testing and Self-Repair.
"""

import argparse
import os
import sys
from typing import Optional

from config.settings import Settings, load_settings
from sandbox.executor import DockerExecutor
from studio.exporter import export_artifacts
from studio.orchestrator import StudioOrchestrator, StudioResult


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="agentic-game-studio",
        description=(
            "Agentic Game Studio: Multi-agent game generation pipeline featuring "
            "deterministic static AST validation, isolated execution testing, "
            "and closed-loop self-repair."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python main.py "Create a retro endless neon runner"
  python main.py "Classic breakout brick-breaker game" --artifacts-dir ./custom_artifacts
        """,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        type=str,
        help="Description or concept of the 2D game to generate.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default="artifacts",
        help="Base directory where run artifacts are stored (default: artifacts).",
    )
    parser.add_argument(
        "--max-repairs",
        type=int,
        default=None,
        help="Override maximum allowed self-repair attempts (default: 2).",
    )
    parser.add_argument(
        "--smoke-frames",
        type=int,
        default=None,
        help="Frames rendered in deterministic headless smoke-test (default: 60).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Google Gemini model identifier (default: gemini-2.5-flash).",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Compile WebAssembly bundle using Pygbag for browser play (requires pygbag).",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Expose game via public Ngrok tunnel (requires NGROK_AUTHTOKEN and ngrok).",
    )
    parser.add_argument(
        "--verify-artifact",
        type=str,
        default=None,
        help="Re-verify an existing run artifact in isolated Docker sandbox and re-export reports.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="Agentic Game Studio v1.0.0",
    )
    return parser


def run_cli(args_list: Optional[list] = None) -> int:
    """Run CLI entrypoint with given arguments. Returns process exit code."""
    parser = create_parser()
    args = parser.parse_args(args_list)

    # 0. Optional Artifact Re-verification Gate
    if args.verify_artifact:
        from pathlib import Path
        target_dir = Path(args.verify_artifact)
        if not target_dir.exists():
            sys.stderr.write(f"Error: Artifact path '{target_dir}' does not exist.\n")
            return 1
        print("=" * 70)
        print(" Agentic Game Studio — Artifact Verification & Re-export")
        print("=" * 70)
        print(f"[*] Target Artifact: {target_dir}")
        try:
            from studio.exporter import verify_and_reexport_artifact
            exported = verify_and_reexport_artifact(target_dir)
            print(f"[+] Successfully verified and regenerated reports in: {exported}")
            return 0
        except Exception as exc:
            sys.stderr.write(f"Error during verification: {exc}\n")
            return 1

    # 1. Validate Game Prompt Input
    if not args.prompt or not args.prompt.strip():
        sys.stderr.write(
            "Error: Game prompt cannot be empty.\n"
            "Please provide a description of the game to generate.\n"
            "Example: python main.py \"Create a neon-themed endless runner\"\n"
        )
        return 2

    game_prompt = args.prompt.strip()

    # 2. Load and Validate Configuration
    try:
        settings = load_settings()
    except Exception as err:
        sys.stderr.write(f"Error loading configuration: {err}\n")
        return 1

    if args.max_repairs is not None:
        if args.max_repairs < 0 or args.max_repairs > 2:
            sys.stderr.write(
                "Error: --max-repairs must be between 0 and 2. Maximum repair budget cannot exceed 2.\n"
            )
            return 2
        settings.max_repair_attempts = args.max_repairs
    if args.smoke_frames is not None:
        settings.smoke_test_frames = args.smoke_frames
    if args.model:
        settings.model_name = args.model
    if args.artifacts_dir:
        settings.artifacts_dir = args.artifacts_dir

    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        sys.stderr.write(
            "Error: GEMINI_API_KEY is not configured.\n"
            "Please configure GEMINI_API_KEY in your .env file or environment variables before running.\n"
        )
        return 1

    # 3. Transparent Environment and Security Reporting
    docker_executor = DockerExecutor()
    docker_available = docker_executor.is_docker_available()

    print("=" * 70)
    print(" Agentic Game Studio — Multi-Agent Generation Pipeline")
    print("=" * 70)
    print(f"[*] Prompt           : \"{game_prompt}\"")
    print(f"[*] Gemini Model     : {settings.model_name}")
    print(f"[*] Max Repairs      : {settings.max_repair_attempts}")
    print(f"[*] Smoke Test Frames: {settings.smoke_test_frames}")
    if docker_available:
        print("[*] Runtime Isolation: Docker container ACTIVE")
    else:
        print("[*] Runtime Isolation: NOT AVAILABLE (Docker daemon not found)")
        print("    -> Host safety policy: Code will NOT execute directly on host.")
        print("    -> Runtime execution status will be reported accurately as NOT_TESTED.")
    print("-" * 70)
    print("[*] Starting multi-agent pipeline...")

    # 4. Orchestrate Pipeline Execution
    orchestrator = StudioOrchestrator(
        settings=settings,
        executor=docker_executor,
    )

    try:
        result: StudioResult = orchestrator.run(game_prompt)
    except Exception as exc:
        sys.stderr.write(f"\nPipeline Execution Error: {exc}\n")
        return 1

    # 5. Export Run Artifacts
    artifact_path = export_artifacts(
        result=result,
        game_prompt=game_prompt,
        base_dir=settings.artifacts_dir,
    )

    # 6. Report Run Outcome to Console
    print("\n" + "=" * 70)
    print(" PIPELINE RESULTS SUMMARY")
    print("=" * 70)
    val = result.validation_result
    exc = result.execution_result

    print(f"Pipeline Status            : {result.pipeline_status}")
    print(f"Static AST Validation      : {result.static_validation_status}")
    print(f"Dual-Runtime Architecture  : {'YES' if val.has_dual_runtime else 'NO'}")
    print(f"Smoke-Test Hook Built-in   : {'YES' if val.has_smoke_test_hook else 'NO'}")
    print(f"Runtime Isolation Status   : {result.runtime_execution_status} (Backend: {exc.isolation_backend})")
    print(f"Game Verified              : {'YES (PASS)' if result.game_verified else 'NO (Unverified - runtime not tested in container)'}")
    print(f"Artifact Export Status     : SUCCESS")
    print(f"Self-Repair Cycles Used    : {result.repair_attempts}/{result.max_repair_attempts}")
    print(f"Status Summary             : {result.status_summary}")
    print("-" * 70)
    print(f"Artifacts exported : {artifact_path.resolve()}")
    print("Files created:")
    print(f"  - {artifact_path / 'game.py'}")
    print(f"  - {artifact_path / 'design.md'}")
    print(f"  - {artifact_path / 'README.md'}")
    print(f"  - {artifact_path / 'qa_report.json'}")
    print(f"  - {artifact_path / 'execution.log'}")
    print("=" * 70)

    # 7. Optional Delivery Features (strictly opt-in)
    if args.web:
        print("\n[*] --web flag requested: Compiling Pygbag WebAssembly package...")
        from studio.delivery import build_web_package
        web_res = build_web_package(artifact_path)
        if web_res.success:
            print(f"[+] Web Build: SUCCESS (Bundle at {web_res.output_path})")
        else:
            print(f"[-] Web Build: {web_res.status} ({web_res.notes})")

    if args.share:
        print("\n[*] --share flag requested: Preparing Ngrok public tunnel...")
        from studio.delivery import start_ngrok_tunnel
        share_res = start_ngrok_tunnel(authtoken=settings.ngrok_authtoken)
        if share_res.success:
            print(f"[+] Tunnel: ACTIVE (URL: {share_res.share_url})")
        else:
            print(f"[-] Tunnel: {share_res.status} ({share_res.notes})")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(run_cli())
