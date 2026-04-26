# md-compressor

Compress Markdown files to reduce LLM token usage. Strips decorative formatting (bold, italic, horizontal rules, inline backticks, redundant blank lines) while leaving code blocks completely untouched.

## Requirements

- Python 3.10+

## Installation

No external runtime dependencies are required. Clone the repository and you're ready to go:

```bash
git clone https://github.com/ogu83/md-compressor.git
cd md-compressor
```

To run the tests you will also need **pytest**:

```bash
pip install pytest
```

## Usage

```
python compress.py <file_or_folder> [options]
```

| Option | Description |
|---|---|
| `-i`, `--in-place` | Overwrite the original file(s) in place |
| `-o DIR`, `--output DIR` | Write compressed files to `DIR` (directory structure is mirrored) |
| `-v`, `--verbose` | Print per-file compression statistics |

### Examples

Compress a single file (creates `doc.compressed.md` next to the original):

```bash
python compress.py doc.md
```

Compress in place:

```bash
python compress.py doc.md --in-place
```

Compress an entire folder (including all subdirectories) and write results to `out/`, mirroring the original directory structure:

```bash
python compress.py docs/ --output out/
```

Show token savings for every file:

```bash
python compress.py docs/ --output out/ --verbose
```

Compress all Markdown files in place, recursively through every subdirectory:

```bash
python compress.py docs/ --in-place
```

## Testing

Run the full test suite:

```bash
python -m pytest test_compress.py -v
```
