"""Tests for compress.py"""

import sys
from pathlib import Path

import pytest

# Make sure the module is importable from this directory
sys.path.insert(0, str(Path(__file__).parent))

from compress import (
    compress_markdown,
    compress_file,
    collect_md_files,
    estimate_tokens,
    main,
    _is_list_item,
    _remove_blank_lines_between_list_items,
)


# ---------------------------------------------------------------------------
# _is_list_item
# ---------------------------------------------------------------------------

class TestIsListItem:
    def test_unordered_dash(self):
        assert _is_list_item('- item')

    def test_unordered_asterisk(self):
        assert _is_list_item('* item')

    def test_unordered_plus(self):
        assert _is_list_item('+ item')

    def test_ordered(self):
        assert _is_list_item('1. item')
        assert _is_list_item('10. item')
        assert _is_list_item('2) item')

    def test_indented_list_item(self):
        assert _is_list_item('  - nested')

    def test_not_a_list_item(self):
        assert not _is_list_item('Just a sentence.')
        assert not _is_list_item('## Heading')
        assert not _is_list_item('')


# ---------------------------------------------------------------------------
# compress_markdown – unit tests for individual compression rules
# ---------------------------------------------------------------------------

class TestRemoveHtmlComments:
    def test_single_line_comment(self):
        result = compress_markdown('Hello <!-- a comment --> world\n')
        assert '<!--' not in result
        assert 'Hello' in result
        assert 'world' in result

    def test_multi_line_comment(self):
        text = 'Before\n<!-- this is\na multi-line\ncomment -->\nAfter\n'
        result = compress_markdown(text)
        assert '<!--' not in result
        assert 'Before' in result
        assert 'After' in result

    def test_no_comment(self):
        # No HTML comments — content is unchanged apart from rule 5 removing
        # the blank line that immediately follows the heading.
        text = '# Heading\n\nSome text.\n'
        result = compress_markdown(text)
        assert result == '# Heading\nSome text.\n'


class TestBoldMarkerRemoval:
    def test_bold_double_asterisk(self):
        result = compress_markdown('This is **bold text** here.\n')
        assert '**' not in result
        assert 'bold text' in result

    def test_bold_double_underscore(self):
        result = compress_markdown('This is __bold text__ here.\n')
        assert '__' not in result
        assert 'bold text' in result

    def test_multiple_bold_spans(self):
        result = compress_markdown('**first** and **second**\n')
        assert '**' not in result
        assert 'first' in result
        assert 'second' in result

    def test_bold_italic_triple_asterisk(self):
        result = compress_markdown('This is ***bold italic*** text.\n')
        assert '***' not in result
        assert 'bold italic' in result

    def test_bold_across_single_newline(self):
        result = compress_markdown('**COLD START\nnext line**\n')
        assert '**' not in result
        assert 'COLD START' in result


class TestItalicMarkerRemoval:
    def test_italic_single_asterisk(self):
        result = compress_markdown('This is *italic* text.\n')
        assert '*italic*' not in result
        assert 'italic' in result

    def test_italic_underscore(self):
        result = compress_markdown('This is _italic_ text.\n')
        assert '_italic_' not in result
        assert 'italic' in result

    def test_list_marker_asterisk_preserved(self):
        result = compress_markdown('* list item one\n* list item two\n')
        # The leading `*` list markers must survive
        lines = [l for l in result.splitlines() if l.strip()]
        assert all(line.startswith('*') for line in lines)

    def test_snake_case_underscores_preserved(self):
        result = compress_markdown('Use `my_variable_name` here.\n')
        # Even with backticks stripped the underscores must stay
        assert 'my_variable_name' in result


class TestHorizontalRuleRemoval:
    def test_dashes(self):
        result = compress_markdown('Above\n\n---\n\nBelow\n')
        assert '---' not in result
        assert 'Above' in result
        assert 'Below' in result

    def test_asterisks(self):
        result = compress_markdown('Above\n\n***\n\nBelow\n')
        assert '***' not in result

    def test_underscores(self):
        result = compress_markdown('Above\n\n___\n\nBelow\n')
        assert '___' not in result

    def test_spaced_dashes(self):
        result = compress_markdown('Above\n\n- - -\n\nBelow\n')
        assert '- - -' not in result

    def test_equals(self):
        result = compress_markdown('Above\n\n====\n\nBelow\n')
        assert '====' not in result


class TestInlineCodeBacktickStripping:
    def test_backticks_around_path(self):
        result = compress_markdown('Read `state.md` for context.\n')
        assert '`' not in result
        assert 'state.md' in result

    def test_backticks_around_command(self):
        result = compress_markdown('Run `git status` to check.\n')
        assert '`' not in result
        assert 'git status' in result

    def test_fenced_code_block_backticks_preserved(self):
        text = 'Before\n\n```python\nprint("hello")\n```\n\nAfter\n'
        result = compress_markdown(text)
        assert '```python' in result
        assert 'print("hello")' in result

    def test_html_comment_inside_fenced_block_preserved(self):
        text = 'Intro\n\n```html\n<!-- keep this -->\n```\n'
        result = compress_markdown(text)
        assert '<!-- keep this -->' in result


class TestBlankLineAfterHeadingRemoval:
    def test_blank_line_after_h2_removed(self):
        text = '## Section\n\nContent here.\n'
        result = compress_markdown(text)
        assert '## Section\nContent here.' in result

    def test_blank_line_after_h1_removed(self):
        text = '# Title\n\nFirst paragraph.\n'
        result = compress_markdown(text)
        assert '# Title\nFirst paragraph.' in result

    def test_multiple_blank_lines_after_heading_removed(self):
        text = '## Section\n\n\n\nContent.\n'
        result = compress_markdown(text)
        assert '## Section\nContent.' in result

    def test_blank_line_before_heading_kept(self):
        text = 'Paragraph.\n\n## Next Section\nContent.\n'
        result = compress_markdown(text)
        # Blank line before heading acts as section separator — keep it
        assert 'Paragraph.\n\n## Next Section' in result


class TestBlankLinesBetweenListItems:
    def test_blank_line_between_two_items_removed(self):
        text = '- item 1\n\n- item 2\n'
        result = compress_markdown(text)
        assert '- item 1\n- item 2' in result

    def test_blank_lines_across_three_items_removed(self):
        text = '- a\n\n- b\n\n- c\n'
        result = compress_markdown(text)
        assert '\n\n' not in result.strip()

    def test_blank_line_between_ordered_items_removed(self):
        text = '1. first\n\n2. second\n\n3. third\n'
        result = compress_markdown(text)
        assert '1. first\n2. second\n3. third' in result

    def test_blank_line_not_removed_outside_list(self):
        text = 'Paragraph A.\n\nParagraph B.\n'
        result = compress_markdown(text)
        assert 'Paragraph A.\n\nParagraph B.' in result


class TestTrailingWhitespace:
    def test_trailing_spaces_removed(self):
        text = 'Line one   \nLine two  \n'
        result = compress_markdown(text)
        for line in result.splitlines():
            assert line == line.rstrip(), f"Trailing space found in: {repr(line)}"

    def test_trailing_tabs_removed(self):
        text = 'Line one\t\nLine two\t\t\n'
        result = compress_markdown(text)
        for line in result.splitlines():
            assert line == line.rstrip()


class TestCollapseBlankLines:
    def test_three_blank_lines_become_one(self):
        text = 'A\n\n\n\nB\n'
        result = compress_markdown(text)
        assert '\n\n\n' not in result

    def test_two_blank_lines_preserved(self):
        text = 'A\n\nB\n'
        result = compress_markdown(text)
        assert 'A\n\nB' in result

    def test_many_blank_lines(self):
        text = 'First\n' + '\n' * 10 + 'Last\n'
        result = compress_markdown(text)
        assert '\n\n\n' not in result
        assert 'First' in result
        assert 'Last' in result


class TestCollapseInteriorSpaces:
    def test_multiple_spaces_in_paragraph(self):
        text = 'This  has   extra    spaces.\n'
        result = compress_markdown(text)
        assert '  ' not in result

    def test_single_space_unchanged(self):
        text = 'Normal sentence here.\n'
        result = compress_markdown(text)
        assert 'Normal sentence here.' in result


class TestCodeBlockPreservation:
    def test_fenced_code_block_untouched(self):
        code = '```python\nx  =  1 +  2\n```\n'
        text = 'Before\n\n' + code + '\nAfter\n'
        result = compress_markdown(text)
        assert 'x  =  1 +  2' in result

    def test_fenced_tilde_block_untouched(self):
        code = '~~~bash\necho  "hello   world"\n~~~\n'
        text = 'Before\n\n' + code + '\nAfter\n'
        result = compress_markdown(text)
        assert 'echo  "hello   world"' in result

    def test_blank_lines_inside_code_block_preserved(self):
        code = '```\nline1\n\n\n\nline5\n```\n'
        text = 'Start\n\n' + code
        result = compress_markdown(text)
        # The four blank lines inside the fence must survive
        assert '\n\n\n\n' in result


class TestDocumentTrimming:
    def test_leading_blank_lines_removed(self):
        text = '\n\n\n# Title\n'
        result = compress_markdown(text)
        assert result.startswith('# Title')

    def test_trailing_blank_lines_collapsed(self):
        text = '# Title\n\n\n\n'
        result = compress_markdown(text)
        assert result == '# Title\n'

    def test_single_trailing_newline(self):
        text = '# Title\n\nParagraph.\n'
        result = compress_markdown(text)
        assert result.endswith('\n')
        assert not result.endswith('\n\n')


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens('') == 1  # max(1, …)

    def test_approximation(self):
        text = 'a' * 400
        assert estimate_tokens(text) == 100


# ---------------------------------------------------------------------------
# compress_file – integration tests using tmp files
# ---------------------------------------------------------------------------

class TestCompressFile:
    def test_output_file_created(self, tmp_path):
        src = tmp_path / 'sample.md'
        src.write_text('# Hello\n\nWorld   \n', encoding='utf-8')
        dst = tmp_path / 'sample.compressed.md'
        compress_file(src, dst)
        assert dst.exists()

    def test_stats_keys(self, tmp_path):
        src = tmp_path / 'doc.md'
        src.write_text('A  B  C\n', encoding='utf-8')
        dst = tmp_path / 'out.md'
        stats = compress_file(src, dst)
        for key in ('path', 'original_size', 'compressed_size',
                    'original_tokens', 'compressed_tokens', 'savings_pct'):
            assert key in stats

    def test_content_is_compressed(self, tmp_path):
        src = tmp_path / 'verbose.md'
        src.write_text(
            '## Title   \n\n\n\n\n**Bold text** and `inline code`.\n\n---\n',
            encoding='utf-8',
        )
        dst = tmp_path / 'compressed.md'
        compress_file(src, dst)
        result = dst.read_text(encoding='utf-8')
        assert '**' not in result       # bold markers removed
        assert '`' not in result        # inline backticks removed
        assert '---' not in result      # horizontal rule removed
        assert '\n\n\n' not in result   # excess blank lines gone

    def test_in_place_overwrites_original(self, tmp_path):
        src = tmp_path / 'orig.md'
        original = '# Hello   \n\n\n\nWorld\n'
        src.write_text(original, encoding='utf-8')
        compress_file(src, src)  # src == dst → in-place
        result = src.read_text(encoding='utf-8')
        assert result != original


# ---------------------------------------------------------------------------
# collect_md_files
# ---------------------------------------------------------------------------

class TestCollectMdFiles:
    def test_single_file(self, tmp_path):
        f = tmp_path / 'a.md'
        f.write_text('# A\n')
        assert collect_md_files(f) == [f]

    def test_non_md_file_returns_empty(self, tmp_path):
        f = tmp_path / 'a.txt'
        f.write_text('hello\n')
        result = collect_md_files(f)
        assert result == []

    def test_directory_recurses(self, tmp_path):
        (tmp_path / 'a.md').write_text('# A\n')
        sub = tmp_path / 'sub'
        sub.mkdir()
        (sub / 'b.md').write_text('# B\n')
        (sub / 'c.txt').write_text('ignore\n')
        files = collect_md_files(tmp_path)
        names = {f.name for f in files}
        assert names == {'a.md', 'b.md'}

    def test_nonexistent_path_returns_empty(self, tmp_path):
        result = collect_md_files(tmp_path / 'nope.md')
        assert result == []


# ---------------------------------------------------------------------------
# CLI (main)
# ---------------------------------------------------------------------------

class TestCLI:
    def test_single_file_default_output(self, tmp_path):
        src = tmp_path / 'doc.md'
        src.write_text('Hello   world\n\n\n\nEnd\n')
        rc = main([str(src)])
        assert rc == 0
        compressed = tmp_path / 'doc.compressed.md'
        assert compressed.exists()

    def test_single_file_in_place(self, tmp_path):
        src = tmp_path / 'doc.md'
        src.write_text('Hello   world\n\n\n\nEnd\n')
        rc = main([str(src), '--in-place'])
        assert rc == 0
        result = src.read_text()
        assert '\n\n\n' not in result

    def test_single_file_output_dir(self, tmp_path):
        src = tmp_path / 'doc.md'
        src.write_text('# Title\n')
        out = tmp_path / 'out'
        rc = main([str(src), '--output', str(out)])
        assert rc == 0
        assert (out / 'doc.md').exists()

    def test_directory_processes_all_md(self, tmp_path):
        (tmp_path / 'a.md').write_text('A   text\n')
        (tmp_path / 'b.md').write_text('B   text\n')
        out = tmp_path / 'out'
        rc = main([str(tmp_path), '--output', str(out)])
        assert rc == 0
        assert (out / 'a.md').exists()
        assert (out / 'b.md').exists()

    def test_no_md_files_returns_1(self, tmp_path):
        rc = main([str(tmp_path)])
        assert rc == 1

    def test_verbose_flag(self, tmp_path, capsys):
        src = tmp_path / 'doc.md'
        src.write_text('# Hello\n')
        main([str(src), '--in-place', '--verbose'])
        captured = capsys.readouterr()
        assert 'token' in captured.out.lower()


# ---------------------------------------------------------------------------
# End-to-end: real-world-style instruction file
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_session_init_compression(self, tmp_path):
        """Mirrors the 'Session Initialization' example from the token-trim article."""
        original = (
            '## Session Initialization\n'
            '\n'
            '**COLD START -- minimum reads only. Load nothing\n'
            'else until the task requires it.**\n'
            '\n'
            '1. Read `state.md` (if it exists). Extract carry-forwards only.\n'
            '\n'
            '2. Read `time-sensitive.md` (8-line table, ~100 tokens).\n'
            '\n'
            '3. Call `memory_session_start` with session context.\n'
            '\n'
            '4. Generate greeting. STOP.\n'
            '\n'
            '---\n'
        )
        src = tmp_path / 'CLAUDE.md'
        src.write_text(original, encoding='utf-8')
        dst = tmp_path / 'CLAUDE.compressed.md'
        stats = compress_file(src, dst)

        result = dst.read_text(encoding='utf-8')

        # Bold markers stripped
        assert '**' not in result
        # Inline backticks stripped, filenames preserved
        assert 'state.md' in result
        assert 'time-sensitive.md' in result
        assert 'memory_session_start' in result
        # Horizontal rule removed
        assert '---' not in result
        # Blank lines between ordered list items removed
        assert '1. ' in result
        assert '2. ' in result
        # Blank line after heading removed
        assert '## Session Initialization\n' in result
        assert '## Session Initialization\n\n' not in result
        # Token savings achieved
        assert stats['compressed_tokens'] < stats['original_tokens']

