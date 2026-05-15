"""Interactive query console (Stage 4)."""

from __future__ import annotations

from pathlib import Path
from typing import List

from .models import RepoMeta
from .query import QueryInterface

try:
    from colorama import Fore, Style
    C = Fore
    S = Style
except ImportError:
    class _Fake:
        def __getattr__(self, _: str) -> str: return ""
    C = _Fake()
    S = _Fake()


def interactive_loop(metadata_dir: Path, warehouse_root: Path) -> None:
    """Run the Stage 4 interactive query console."""
    qif = QueryInterface(metadata_dir)

    print(f"\n{C.CYAN}{'=' * 60}{S.RESET_ALL}")
    print(f"{C.GREEN}  DeepSeek_DataV4 — Interactive Query Console{S.RESET_ALL}")
    print(f"{C.CYAN}{'=' * 60}{S.RESET_ALL}")
    print(f"  Warehouse : {warehouse_root}")
    stats = qif.stats()
    print(f"  Repos     : {stats['total_repos']}")
    print(f"  Data files: {stats['total_data_files']}")
    print(f"  Types     : {', '.join(stats['data_types']) or 'none'}")
    if stats.get('licensed_count'):
        print(f"  Licensed  : {stats['licensed_count']}")
    print(f"{C.CYAN}{'-' * 60}{S.RESET_ALL}")
    print(f"  Commands:")
    print(f"    /search <query>   — natural-language search")
    print(f"    /stats            — warehouse statistics")
    print(f"    /recent [n]       — show n most recently ingested repos")
    print(f"    /best [n]         — top-n by quality score")
    print(f"    /rebuild          — rebuild search index")
    print(f"    /help             — this message")
    print(f"    /quit             — exit")
    print(f"{C.CYAN}{'=' * 60}{S.RESET_ALL}\n")

    while True:
        try:
            raw = input(f"{C.YELLOW}DS4>{S.RESET_ALL} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/quit":
            print("Goodbye.")
            break
        elif cmd == "/help":
            print("Commands: /search, /stats, /recent, /best, /rebuild, /quit")
        elif cmd == "/rebuild":
            qif._rebuild_index()
            print(f"Index rebuilt. {qif.stats()['total_repos']} repos indexed.")
        elif cmd == "/stats":
            s = qif.stats()
            print(f"  Total repos      : {s['total_repos']}")
            print(f"  Total data files : {s['total_data_files']}")
            print(f"  Data types       : {', '.join(s['data_types']) or 'none'}")
            print(f"  With API docs    : {s['api_docs_count']}")
            print(f"  Avg quality score: {s['avg_quality_score']}")
            if s.get('licensed_count'):
                print(f"  Licensed repos   : {s['licensed_count']}")
        elif cmd == "/recent":
            n = int(arg) if arg.isdigit() else 10
            recent = sorted(
                qif._index, key=lambda m: m.ingested_at or "", reverse=True)[:n]
            _print_results(recent)
        elif cmd == "/best":
            n = int(arg) if arg.isdigit() else 10
            best = sorted(qif._index, key=lambda m: m.quality_score, reverse=True)[:n]
            _print_results(best)
        elif cmd == "/search":
            if not arg:
                print("Usage: /search <natural language query>")
                continue
            results = qif.search(arg)
            if not results:
                print(f"  No results for '{arg}'. Try different keywords.")
            else:
                _print_results(results)
        else:
            results = qif.search(raw)
            if results:
                _print_results(results)
            else:
                print(f"  Unknown command '{cmd}'. Type /help for options.")


def _print_results(results: List[RepoMeta]) -> None:
    """Pretty-print a list of RepoMeta results."""
    for i, meta in enumerate(results, 1):
        score_color = C.GREEN if meta.quality_score >= 30 else (
            C.YELLOW if meta.quality_score >= 15 else C.RED)
        print(f"\n  {C.CYAN}[{i}]{S.RESET_ALL} {C.WHITE}{meta.repo_name}{S.RESET_ALL}")
        print(f"      Score: {score_color}{meta.quality_score:.1f}{S.RESET_ALL}  "
              f"Stars: {meta.stars}  Lang: {meta.language or '?'}")
        if meta.license:
            print(f"      License: {meta.license}")
        if meta.description:
            print(f"      Desc: {meta.description[:120]}")
        if meta.data_types:
            print(f"      Types: {', '.join(meta.data_types)}")
        if meta.api_docs_found:
            print(f"      {C.GREEN}API docs available{S.RESET_ALL}")
        print(f"      Path: {meta.local_path or 'not stored'}")
