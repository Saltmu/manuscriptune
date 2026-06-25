import argparse
import re
import sys
from pathlib import Path


def format_text(text: str) -> str:
    """
    Perform minimal mechanical formatting on the text.
    - Remove NotebookLM reference numbers like [1], (2), 【3】
    - Remove extra spaces after punctuation like 。 、 ！ ？
    Contextual line breaks (like inside 「」) are NOT modified here.
    """
    # Remove reference numbers: [1], [1, 2], (1), 【1】
    # These often appear at the end of sentences in AI outputs
    text = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', text)
    text = re.sub(r'\(\d+(?:,\s*\d+)*\)', '', text)
    text = re.sub(r'【\d+(?:,\s*\d+)*】', '', text)
    
    # Remove extra spaces/tabs after Japanese punctuation marks
    text = re.sub(r'([。、！？])[\t 　]+', r'\1', text)
    
    return text

def main():
    parser = argparse.ArgumentParser(description="Novel Formatter Helper: Performs minimal mechanical substitutions.")
    parser.add_argument("input_file", type=str, help="Path to the input text file")
    parser.add_argument("-o", "--output", type=str, help="Path to the output file. If not provided, prints to stdout.", default=None)
    parser.add_argument("--inplace", action="store_true", help="Modify the input file in-place")
    
    args = parser.parse_args()
    
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: Input file '{args.input_file}' not found.", file=sys.stderr)
        sys.exit(1)
        
    with open(input_path, encoding='utf-8') as f:
        content = f.read()
        
    formatted_content = format_text(content)
    
    if args.inplace:
        with open(input_path, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
        print(f"Formatted text saved to {input_path}")
    elif args.output:
        output_path = Path(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
        print(f"Formatted text saved to {output_path}")
    else:
        print(formatted_content, end="")

if __name__ == "__main__":
    main()
