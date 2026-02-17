#!/usr/bin/env python3
"""Prepare training data for fine-tuning Gemma 3 1B on ASMS documentation.

Parses all HTM/HTML files from a documentation folder and generates
instruction-tuning JSONL in the ChatML format expected by MLX fine-tuning.

Usage:
    python scripts/prepare_training_data.py /path/to/htm/folder
    python scripts/prepare_training_data.py /path/to/htm/folder --output training_data --use-ollama

Outputs:
    training_data/train.jsonl   (90% of data)
    training_data/valid.jsonl   (10% of data)
    training_data/stats.json    (dataset statistics)
"""

import argparse
import json
import os
import random
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─── HTML Parser ────────────────────────────────────────────────────────

class DocumentParser(HTMLParser):
    """Extract structured text from HTML documentation files."""

    SKIP_TAGS = {"script", "style", "link", "meta", "noscript", "svg", "path"}
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    BLOCK_TAGS = {"p", "div", "article", "section", "blockquote", "pre", "code", "li", "tr", "td", "th", "dt", "dd"}

    # Navigation / boilerplate text to filter out
    BOILERPLATE = {
        "skip to main content", "account", "settings", "logout", "placeholder",
        "filter:", "all files", "submit search", "is this topic helpful?",
        "yes", "no", "send feedback", "sorry about that",
        "why wasn't this helpful? (check all that apply)",
        "couldn't find what i was looking for", "contents",
        "too long/complicated", "out of date", "other",
    }

    def __init__(self):
        super().__init__()
        self.sections: List[Dict] = []  # [{heading, level, content}]
        self.current_heading = ""
        self.current_level = 0
        self.current_content: List[str] = []
        self.title = ""
        self._skip = False
        self._in_heading = False
        self._heading_text = []
        self._in_title = False
        self._in_li = False
        self._in_code = False
        self._code_text = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip = True
            return
        if tag == "title":
            self._in_title = True
        elif tag in self.HEADING_TAGS:
            self._in_heading = True
            self._heading_text = []
        elif tag == "li":
            self._in_li = True
        elif tag in ("pre", "code"):
            self._in_code = True
            self._code_text = []

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self._skip = False
            return
        if tag == "title":
            self._in_title = False
        elif tag in self.HEADING_TAGS and self._in_heading:
            self._in_heading = False
            heading = " ".join(self._heading_text).strip()
            if heading and heading.lower() not in self.BOILERPLATE:
                # Save previous section
                if self.current_heading or self.current_content:
                    self._flush_section()
                self.current_heading = heading
                self.current_level = int(tag[1])
        elif tag == "li":
            self._in_li = False
        elif tag in ("pre", "code") and self._in_code:
            self._in_code = False
            code = "\n".join(self._code_text).strip()
            if code and len(code) > 3:
                self.current_content.append(f"```\n{code}\n```")

    def handle_data(self, data):
        if self._skip:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title = text
            return
        if self._in_heading:
            self._heading_text.append(text)
            return
        if self._in_code:
            self._code_text.append(text)
            return

        # Filter boilerplate
        if text.lower() in self.BOILERPLATE:
            return
        if len(text) < 3:
            return

        if self._in_li:
            self.current_content.append(f"• {text}")
        else:
            self.current_content.append(text)

    def _flush_section(self):
        content = "\n".join(self.current_content).strip()
        if content and len(content) > 20:
            self.sections.append({
                "heading": self.current_heading,
                "level": self.current_level,
                "content": content,
            })
        self.current_content = []

    def get_document(self) -> Dict:
        """Return the parsed document structure."""
        self._flush_section()
        return {
            "title": self.title,
            "sections": self.sections,
        }


def parse_htm_file(file_path: Path) -> Optional[Dict]:
    """Parse an HTM file and return structured document."""
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    raw = None
    for enc in encodings:
        try:
            raw = file_path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if not raw:
        raw = file_path.read_bytes().decode("utf-8", errors="ignore")

    parser = DocumentParser()
    try:
        parser.feed(raw)
    except Exception:
        return None

    doc = parser.get_document()

    # Fallback title from filename
    if not doc["title"]:
        doc["title"] = file_path.stem.replace("-", " ").replace("_", " ").title()

    # Filter out empty/tiny documents
    total_content = " ".join(s["content"] for s in doc["sections"])
    if len(total_content) < 50:
        return None

    doc["source_file"] = str(file_path.name)
    return doc


# ─── Training Data Generation ──────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are PSK Bot, a professional assistant for AlgoSec ASMS documentation. "
    "Answer questions accurately based on the provided documentation context. "
    "Use bullet points and clear formatting. Be precise and direct. "
    "If the information is not available, clearly state that."
)


MAX_CONTEXT_CHARS = 500   # ~125 tokens
MAX_ANSWER_CHARS = 600    # ~150 tokens
MAX_TOTAL_CHARS = 1800    # ~450 tokens (fits in 512 token window)


def generate_qa_from_section(doc_title: str, section: Dict, all_sections: List[Dict]) -> List[Dict]:
    """Generate Q&A training pairs from a document section.

    Each example is kept small enough to fit within 512 tokens:
    - system prompt: ~70 tokens
    - question: ~20-40 tokens
    - context: ~125 tokens
    - answer: ~150 tokens
    - formatting overhead: ~30 tokens
    Total: ~400-450 tokens
    """
    heading = section["heading"]
    content = section["content"]
    examples = []

    if not heading and not content:
        return examples

    # Use ONLY this section's content as context (not all sections)
    context = _truncate_context(content)
    topic = heading or doc_title

    # Clean the content for answer generation
    clean_content = _clean_text(content)
    if len(clean_content) < 30:
        return examples

    # ── Template 1: "What is X?" ── (for descriptive content)
    if len(clean_content) > 30:
        answer = _make_concise_answer(clean_content, style="describe")
        if answer:
            examples.append(_make_example(
                f"What is {topic}?",
                answer,
                context,
            ))

    # ── Template 2: "How do I X?" (for procedural content) ──
    procedural_kw = ["do the following", "step", "click", "navigate", "select", "configure", "to add", "to create", "to edit", "to delete"]
    if any(kw in content.lower() for kw in procedural_kw):
        answer = _make_concise_answer(clean_content, style="steps")
        if answer:
            examples.append(_make_example(
                f"How do I {topic.lower().rstrip('.')}?",
                answer,
                context,
            ))

    # ── Template 3: Parameter/config questions ──
    if any(kw in content.lower() for kw in ["parameter", "configuration", "setting", "value", "default"]):
        answer = _make_concise_answer(clean_content, style="config")
        if answer:
            examples.append(_make_example(
                f"What are the configuration options for {topic}?",
                answer,
                context,
            ))

    return examples


def _truncate_context(content: str) -> str:
    """Truncate context to fit within token budget."""
    cleaned = _clean_text(content)
    if len(cleaned) <= MAX_CONTEXT_CHARS:
        return cleaned
    # Cut at sentence boundary
    cutoff = cleaned[:MAX_CONTEXT_CHARS].rfind(".")
    if cutoff > MAX_CONTEXT_CHARS // 2:
        return cleaned[:cutoff + 1]
    return cleaned[:MAX_CONTEXT_CHARS]


def _clean_text(text: str) -> str:
    """Clean up text content — remove empty lines, boilerplate, normalize whitespace."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.lower() in DocumentParser.BOILERPLATE:
            continue
        # Remove pure formatting artifacts
        if line in ("•", "##", "#", "---", "***"):
            continue
        cleaned.append(line)
    result = "\n".join(cleaned)
    # Collapse excessive whitespace
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


def _make_concise_answer(content: str, style: str = "describe") -> Optional[str]:
    """Create a concise, well-formatted answer from content.

    Returns None if the content is too short to be useful.
    """
    lines = content.split("\n")

    if style == "steps":
        # Extract bullet / numbered steps
        steps = [l for l in lines if l.startswith("•") or re.match(r'^\d+\.?\s', l)]
        if steps:
            answer = "\n".join(steps[:8])  # max 8 steps
        else:
            answer = "\n".join(lines[:6])
    elif style == "config":
        # Look for parameter-like lines
        params = [l for l in lines if any(kw in l.lower() for kw in [":", "=", "default", "parameter", "•"])]
        if params:
            answer = "\n".join(params[:6])
        else:
            answer = "\n".join(lines[:5])
    else:
        # Descriptive — take first few meaningful sentences
        answer = "\n".join(lines[:5])

    # Enforce length limit
    if len(answer) > MAX_ANSWER_CHARS:
        cutoff = answer[:MAX_ANSWER_CHARS].rfind(".")
        if cutoff > MAX_ANSWER_CHARS // 2:
            answer = answer[:cutoff + 1]
        else:
            cutoff = answer[:MAX_ANSWER_CHARS].rfind("\n")
            if cutoff > MAX_ANSWER_CHARS // 2:
                answer = answer[:cutoff]
            else:
                answer = answer[:MAX_ANSWER_CHARS]

    if len(answer) < 20:
        return None
    return answer


def _make_example(question: str, answer: str, context: str) -> Dict:
    """Create a training example in ChatML format.

    Format: question FIRST so the model always sees the question,
    then short context to ground the answer.
    """
    # Put question first, then context — ensures question is always in the window
    user_content = f"{question}\n\nContext:\n{context}"

    # Enforce total size limit
    total_chars = len(SYSTEM_PROMPT) + len(user_content) + len(answer)
    if total_chars > MAX_TOTAL_CHARS:
        # Trim context first, then answer
        overshoot = total_chars - MAX_TOTAL_CHARS
        if len(context) > overshoot + 100:
            context = context[:len(context) - overshoot]
            user_content = f"{question}\n\nContext:\n{context}"
        else:
            answer = answer[:max(len(answer) - overshoot, 50)]

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": answer},
        ]
    }


def generate_negative_examples(docs: List[Dict]) -> List[Dict]:
    """Generate examples where the answer is NOT in the context."""
    negatives = []
    unrelated_questions = [
        "What is the weather today?",
        "How do I cook pasta?",
        "What is the capital of France?",
        "Tell me a joke",
        "What are the latest stock prices?",
        "How do I fix my car engine?",
        "What is quantum computing?",
    ]

    refusal = (
        "I'm sorry, but this information is not available in the ASMS documentation. "
        "I can only answer questions related to AlgoSec Security Management Suite. "
        "Please ask a question about ASMS features, configuration, or administration."
    )

    for q in unrelated_questions:
        # Pick a random document context
        if docs:
            doc = random.choice(docs)
            ctx = " ".join(s["content"] for s in doc["sections"])[:500]
        else:
            ctx = "No documentation context available."
        negatives.append(_make_example(q, refusal, ctx))

    return negatives


# ─── Ollama-powered Q&A Generation ─────────────────────────────────────

def generate_qa_with_ollama(doc_title: str, content: str, base_url: str = "http://localhost:11434", model: str = "gemma3:1b") -> List[Dict]:
    """Use Ollama to generate diverse Q&A pairs from document content."""
    import urllib.request

    prompt = f"""You are a training data generator. Given this documentation excerpt, generate exactly 3 question-answer pairs.

Documentation Title: {doc_title}
Content:
{content[:2000]}

Rules:
- Questions should be natural and varied (What, How, Why, Can I, etc.)
- Answers should be accurate, based ONLY on the content above
- Answers should be concise (2-4 sentences or bullet points)
- Output ONLY valid JSON array, nothing else

Output format:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]"""

    try:
        data = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 512},
        }).encode()

        req = urllib.request.Request(
            f"{base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            response_text = result.get("response", "")

        # Try to extract JSON from response
        # Look for JSON array in the response
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            pairs = json.loads(match.group())
            examples = []
            for pair in pairs:
                if "question" in pair and "answer" in pair:
                    examples.append(_make_example(
                        pair["question"],
                        pair["answer"],
                        content[:2000],
                    ))
            return examples
    except Exception as e:
        print(f"  Warning: Ollama Q&A generation failed: {e}", file=sys.stderr)

    return []


# ─── Main Pipeline ─────────────────────────────────────────────────────

def collect_htm_files(folder: Path) -> List[Path]:
    """Recursively find all HTM/HTML files, excluding navigation/template files."""
    skip_patterns = {"index", "toc", "search", "glossary", "_csh", "template"}
    files = []
    for ext in ("*.htm", "*.html"):
        for f in folder.rglob(ext):
            # Skip navigation/framework files
            if any(pat in f.stem.lower() for pat in skip_patterns):
                continue
            # Skip skin/resource directories
            rel = str(f.relative_to(folder)).lower()
            if any(skip in rel for skip in ["skins/", "resources/scripts", "resources/stylesheets"]):
                continue
            # Skip very small files (likely navigation stubs)
            if f.stat().st_size < 500:
                continue
            files.append(f)
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(
        description="Prepare fine-tuning training data from HTM documentation"
    )
    parser.add_argument("input_folder", type=Path, help="Folder containing HTM/HTML files")
    parser.add_argument("--output", type=Path, default=Path("training_data"), help="Output directory (default: training_data)")
    parser.add_argument("--split", type=float, default=0.9, help="Train/validation split ratio (default: 0.9)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--use-ollama", action="store_true", help="Use Ollama to generate additional Q&A pairs (slower but higher quality)")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL")
    parser.add_argument("--ollama-model", default="gemma3:1b", help="Ollama model for Q&A generation")
    parser.add_argument("--max-files", type=int, default=0, help="Max files to process (0 = all)")
    args = parser.parse_args()

    random.seed(args.seed)

    if not args.input_folder.exists():
        print(f"Error: Input folder not found: {args.input_folder}", file=sys.stderr)
        sys.exit(1)

    # Collect files
    print(f"Scanning {args.input_folder} for HTM/HTML files...")
    htm_files = collect_htm_files(args.input_folder)
    if args.max_files > 0:
        htm_files = htm_files[:args.max_files]
    print(f"Found {len(htm_files)} content files")

    # Parse all documents
    print("Parsing documents...")
    documents = []
    failed = 0
    for i, f in enumerate(htm_files):
        if (i + 1) % 50 == 0:
            print(f"  Parsed {i + 1}/{len(htm_files)}...")
        doc = parse_htm_file(f)
        if doc:
            documents.append(doc)
        else:
            failed += 1

    print(f"Successfully parsed {len(documents)}/{len(htm_files)} documents ({failed} skipped)")

    # Generate training examples
    print("Generating training examples...")
    all_examples = []

    for i, doc in enumerate(documents):
        if (i + 1) % 50 == 0:
            print(f"  Generating from doc {i + 1}/{len(documents)}...")

        # Template-based Q&A
        for section in doc["sections"]:
            examples = generate_qa_from_section(
                doc["title"], section, doc["sections"]
            )
            all_examples.extend(examples)

        # Optional: Ollama-generated Q&A
        if args.use_ollama:
            full_text = "\n".join(s["content"] for s in doc["sections"])
            if len(full_text) > 100:
                ollama_examples = generate_qa_with_ollama(
                    doc["title"], full_text,
                    base_url=args.ollama_url,
                    model=args.ollama_model,
                )
                all_examples.extend(ollama_examples)

    # Add negative examples (out-of-domain refusals)
    negatives = generate_negative_examples(documents)
    all_examples.extend(negatives)

    print(f"Generated {len(all_examples)} total training examples")

    # Deduplicate by question
    seen_questions = set()
    unique_examples = []
    for ex in all_examples:
        user_msg = ex["messages"][1]["content"]
        q_key = re.sub(r'[^a-z0-9\s]', '', user_msg.split("Question:")[-1].lower().strip())
        if q_key not in seen_questions:
            seen_questions.add(q_key)
            unique_examples.append(ex)

    print(f"After dedup: {len(unique_examples)} unique examples")

    # Shuffle and split
    random.shuffle(unique_examples)
    split_idx = int(len(unique_examples) * args.split)
    train_data = unique_examples[:split_idx]
    valid_data = unique_examples[split_idx:]

    # Write output
    args.output.mkdir(parents=True, exist_ok=True)

    train_path = args.output / "train.jsonl"
    valid_path = args.output / "valid.jsonl"

    with open(train_path, "w") as f:
        for ex in train_data:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with open(valid_path, "w") as f:
        for ex in valid_data:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Stats
    stats = {
        "source_folder": str(args.input_folder),
        "total_htm_files": len(htm_files),
        "parsed_documents": len(documents),
        "total_examples": len(all_examples),
        "unique_examples": len(unique_examples),
        "train_examples": len(train_data),
        "valid_examples": len(valid_data),
        "used_ollama": args.use_ollama,
        "avg_user_msg_len": int(sum(
            len(ex["messages"][1]["content"]) for ex in unique_examples
        ) / max(len(unique_examples), 1)),
        "avg_assistant_msg_len": int(sum(
            len(ex["messages"][2]["content"]) for ex in unique_examples
        ) / max(len(unique_examples), 1)),
    }

    with open(args.output / "stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Training data ready!")
    print(f"  Train:  {train_path} ({len(train_data)} examples)")
    print(f"  Valid:  {valid_path} ({len(valid_data)} examples)")
    print(f"  Stats:  {args.output / 'stats.json'}")
    print(f"  Avg user msg:      {stats['avg_user_msg_len']} chars")
    print(f"  Avg assistant msg:  {stats['avg_assistant_msg_len']} chars")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
