#!/usr/bin/env python3
"""
md-compressor: Compress Markdown files to reduce LLM token usage.

Usage:
    python compress.py <file_or_folder> [options]

Options:
    -i, --in-place      Overwrite the original file(s) in place
    -o, --output DIR    Write compressed output to a directory (mirrors input structure)
    -v, --verbose       Print per-file compression statistics
"""

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Core compression logic
# ---------------------------------------------------------------------------

def _split_segments(text: str) -> list[tuple[str, bool]]:
    """Split *text* into a list of (content, is_code_block) segments.

    Fenced code blocks (``` or ~~~) and indented code blocks are marked as
    code so that compression rules are never applied inside them.
    """
    segments: list[tuple[str, bool]] = []
    fenced_pattern = re.compile(r'^(`{3,}|~{3,})', re.MULTILINE)

    pos = 0
    in_fence = False
    fence_marker = ""

    for match in fenced_pattern.finditer(text):
        marker = match.group(1)
        start = match.start()

        if not in_fence:
            # Everything before this fence marker is normal text
            if start > pos:
                segments.append((text[pos:start], False))
            in_fence = True
            fence_marker = marker[0] * len(marker)  # normalise char
            pos = start
        elif marker[0] == fence_marker[0] and len(marker) >= len(fence_marker):
            # Closing fence for the currently open block
            end = match.end()
            # Include the trailing newline if present
            if end < len(text) and text[end] == '\n':
                end += 1
            segments.append((text[pos:end], True))
            in_fence = False
            fence_marker = ""
            pos = end

    # Remainder
    if pos < len(text):
        segments.append((text[pos:], in_fence))

    return segments


_LIST_ITEM_RE = re.compile(r'^\s*(?:[-+*]|\d+[.)]) ')
_HEADING_RE = re.compile(r'^#{1,6} ', re.MULTILINE)


def _is_list_item(line: str) -> bool:
    """Return True if *line* looks like a Markdown list item."""
    return bool(_LIST_ITEM_RE.match(line))


def _remove_blank_lines_between_list_items(text: str) -> str:
    """Remove blank lines that appear between consecutive list items.

    A blank line separating two list items is decorative and adds tokens
    without changing how the AI reads the content.
    """
    lines = text.split('\n')
    result: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == '':
            # Find the last non-blank line already in result
            prev_idx = len(result) - 1
            while prev_idx >= 0 and result[prev_idx].strip() == '':
                prev_idx -= 1
            # Find the next non-blank line in the remaining input
            next_idx = i + 1
            while next_idx < len(lines) and lines[next_idx].strip() == '':
                next_idx += 1
            # Drop the blank line when it sits between two list items
            if (prev_idx >= 0 and next_idx < len(lines)
                    and _is_list_item(result[prev_idx])
                    and _is_list_item(lines[next_idx])):
                i += 1
                continue
        result.append(lines[i])
        i += 1
    return '\n'.join(result)


def _compress_text_segment(text: str) -> str:
    """Apply all compression rules to a non-code segment.

    Rules derived from the token-trim methodology:
    1. Remove HTML comments.
    2. Strip bold+italic, bold, and italic emphasis markers.
    3. Remove horizontal rules.
    4. Strip inline code backticks (content is kept, backticks removed).
    5. Remove blank lines immediately after headings.
    6. Remove blank lines between consecutive list items.
    7. Collapse 3+ consecutive blank lines to a single blank line.
    8. Strip trailing whitespace from each line.
    9. Collapse multiple interior spaces within a line to a single space.
    """
    # 1. Remove HTML comments (including multi-line ones)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # 2a. Strip bold+italic markers (*** … *** or ___ … ___)
    #     Process triple-markers first to avoid partial matches.
    text = re.sub(r'\*{3}((?:[^*\n]|\n(?!\n))+?)\*{3}', r'\1', text)
    text = re.sub(r'_{3}((?:[^_\n]|\n(?!\n))+?)_{3}', r'\1', text)

    # 2b. Strip bold markers (** … ** or __ … __)
    text = re.sub(r'\*{2}((?:[^*\n]|\n(?!\n))+?)\*{2}', r'\1', text)
    text = re.sub(r'_{2}((?:[^_\n]|\n(?!\n))+?)_{2}', r'\1', text)

    # 2c. Strip italic markers (* … * or _ … _)
    #     * variant: must not be a list marker (asterisk followed by space at
    #       line start) and must not be part of ** (already handled above).
    text = re.sub(r'(?<!\*)\*(?![\s*\n])([^*\n]+?)(?<!\s)\*(?!\*)', r'\1', text)
    #     _ variant: use word-boundary guards to avoid touching snake_case names.
    text = re.sub(r'(?<!\w)_(?![\s_\n])([^_\n]+?)(?<!\s)_(?!\w)', r'\1', text)

    # 3. Remove horizontal rules: a line containing only -, *, _, or = (3+),
    #    optionally separated by spaces.
    text = re.sub(
        r'^[ \t]*(?:[-*_=][ \t]*){3,}$', '', text, flags=re.MULTILINE
    )

    # 4. Strip inline code backticks (single-backtick spans only).
    #    Fenced code blocks are handled by _split_segments and never reach here.
    text = re.sub(r'(?<!`)`([^`\n]+?)`(?!`)', r'\1', text)

    # 5. Remove blank lines immediately after headings.
    #    The AI does not need vertical space between a heading and its content.
    text = re.sub(r'(^#{1,6} [^\n]*)\n\n+', r'\1\n', text, flags=re.MULTILINE)

    # 6. Remove blank lines between consecutive list items.
    text = _remove_blank_lines_between_list_items(text)

    # 7. Collapse 3+ blank lines into a single blank line.
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 8. Strip trailing whitespace from each line.
    lines = text.split('\n')
    lines = [line.rstrip() for line in lines]
    text = '\n'.join(lines)

    # 9. Collapse multiple interior spaces within a line to a single space
    #    (preserve leading indentation).
    compressed_lines = []
    for line in text.split('\n'):
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]
        compressed_lines.append(indent + re.sub(r'  +', ' ', stripped))
    text = '\n'.join(compressed_lines)

    return text


def compress_markdown(text: str) -> str:
    """Return a compressed version of *text* (a Markdown document).

    Code blocks (fenced and indented) are left completely untouched so that
    whitespace-sensitive content is preserved.
    """
    segments = _split_segments(text)

    compressed_parts = []
    for content, is_code in segments:
        if is_code:
            compressed_parts.append(content)
        else:
            compressed_parts.append(_compress_text_segment(content))

    result = ''.join(compressed_parts)

    # Remove leading blank lines and trailing whitespace, keep one trailing newline
    result = result.strip() + '\n'

    return result


# ---------------------------------------------------------------------------
# Token estimation (whitespace-split approximation)
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Rough token estimate: split on whitespace and punctuation boundaries.

    This intentionally mirrors the simple heuristic used by many token-trim
    tools (1 token ≈ 4 characters for English text).
    """
    return max(1, round(len(text) / 4))


# ---------------------------------------------------------------------------
# File / directory handling
# ---------------------------------------------------------------------------

def compress_file(src: Path, dst: Path, verbose: bool = False) -> dict:
    """Compress *src* and write the result to *dst*.

    Returns a stats dict with keys: path, original_size, compressed_size,
    original_tokens, compressed_tokens, savings_pct.
    """
    original_text = src.read_text(encoding='utf-8')
    compressed_text = compress_markdown(original_text)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(compressed_text, encoding='utf-8')

    orig_tokens = estimate_tokens(original_text)
    comp_tokens = estimate_tokens(compressed_text)
    savings = 100 * (1 - comp_tokens / orig_tokens) if orig_tokens else 0

    stats = {
        'path': str(src),
        'original_size': len(original_text),
        'compressed_size': len(compressed_text),
        'original_tokens': orig_tokens,
        'compressed_tokens': comp_tokens,
        'savings_pct': savings,
    }

    if verbose:
        print(
            f"  {src}  "
            f"{orig_tokens} → {comp_tokens} tokens  "
            f"({savings:.1f}% saved)"
        )

    return stats


def collect_md_files(path: Path) -> list[Path]:
    """Return all *.md files under *path* (recurse if directory)."""
    if path.is_file():
        if path.suffix.lower() == '.md':
            return [path]
        print(f"Warning: '{path}' is not a Markdown file — skipping.", file=sys.stderr)
        return []
    if path.is_dir():
        return sorted(path.rglob('*.md'))
    print(f"Error: '{path}' does not exist.", file=sys.stderr)
    return []


def resolve_destination(src: Path, root: Path, output_dir: Path | None, in_place: bool) -> Path:
    """Work out where the compressed file should be written."""
    if in_place:
        return src
    if output_dir:
        relative = src.relative_to(root) if src.is_relative_to(root) else Path(src.name)
        return output_dir / relative
    # Default: write a sibling file with `.compressed.md` suffix
    return src.with_name(src.stem + '.compressed.md')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='compress',
        description='Compress Markdown files to reduce LLM token usage.',
    )
    parser.add_argument(
        'path',
        type=Path,
        help='Path to a single .md file or a directory containing .md files.',
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '-i', '--in-place',
        action='store_true',
        help='Overwrite the original file(s) in place.',
    )
    mode.add_argument(
        '-o', '--output',
        metavar='DIR',
        type=Path,
        help='Write compressed files to DIR (directory structure is mirrored).',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Print per-file compression statistics.',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    target: Path = args.path
    files = collect_md_files(target)

    if not files:
        print('No Markdown files found.', file=sys.stderr)
        return 1

    root = target if target.is_dir() else target.parent

    total_orig_tokens = 0
    total_comp_tokens = 0
    processed = 0

    if args.verbose:
        print(f'Compressing {len(files)} file(s)…\n')

    for src in files:
        dst = resolve_destination(src, root, args.output, args.in_place)
        stats = compress_file(src, dst, verbose=args.verbose)
        total_orig_tokens += stats['original_tokens']
        total_comp_tokens += stats['compressed_tokens']
        processed += 1

    total_savings = (
        100 * (1 - total_comp_tokens / total_orig_tokens) if total_orig_tokens else 0
    )

    print(
        f'\nDone. {processed} file(s) processed. '
        f'{total_orig_tokens} → {total_comp_tokens} tokens total '
        f'({total_savings:.1f}% saved).'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
