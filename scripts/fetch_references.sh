#!/usr/bin/env bash
# fetch_references.sh — Download reference papers and tools
# Usage: ./scripts/fetch_references.sh [--all | --papers | --tools]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PAPERS_DIR="$ROOT/research/papers"
TOOLS_DIR="$ROOT/research/tools"

mkdir -p "$PAPERS_DIR" "$TOOLS_DIR"

fetch_papers() {
    echo "==> Fetching papers..."

    # Steffin/Classen SPTM paper (arXiv 2510.09272)
    PAPER="$PAPERS_DIR/steffin_classen_sptm_2025.pdf"
    if [[ -f "$PAPER" ]]; then
        echo "  [skip] steffin_classen_sptm_2025.pdf already exists"
    else
        echo "  Fetching Steffin/Classen SPTM paper from arXiv..."
        curl -L --progress-bar \
            "https://arxiv.org/pdf/2510.09272" \
            -o "$PAPER"
        echo "  Saved: $PAPER"
    fi

    echo ""
    echo "Papers saved to: $PAPERS_DIR"
    echo "Next step: read steffin_classen_sptm_2025.pdf and annotate docs/SPTM_FINDINGS.md"
}

check_tools() {
    echo "==> Checking required tools..."

    tools=(
        "dtc:brew install dtc:device tree compiler"
        "ipsw:brew install blacktop/tap/ipsw:Apple IPSW extraction tool"
        "python3:brew install python:Python 3"
        "r2:brew install radare2:Radare2 disassembler (for SPTM blob analysis)"
    )

    missing=()
    for entry in "${tools[@]}"; do
        cmd="${entry%%:*}"
        rest="${entry#*:}"
        install="${rest%%:*}"
        desc="${rest##*:}"
        if command -v "$cmd" &>/dev/null; then
            echo "  [ok]   $cmd — $desc"
        else
            echo "  [MISS] $cmd — $desc (install: $install)"
            missing+=("$install")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo ""
        echo "Install missing tools:"
        for cmd in "${missing[@]}"; do
            echo "  $cmd"
        done
    fi
}

case "${1:---all}" in
    --papers) fetch_papers ;;
    --tools)  check_tools ;;
    --all)
        fetch_papers
        echo ""
        check_tools
        ;;
    *)
        echo "Usage: $0 [--all | --papers | --tools]"
        exit 1
        ;;
esac
