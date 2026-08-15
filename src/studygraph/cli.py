import argparse
from pathlib import Path

from studygraph.pdf_text_extractor import PdfTextExtractionError, extract_text_from_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studygraph",
        description="Extract text from a PDF file and print it to the terminal.",
    )
    parser.add_argument("pdf_path", help="Path to the PDF file")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)

    try:
        text = extract_text_from_pdf(pdf_path)
    except PdfTextExtractionError as error:
        parser.exit(status=1, message=f"Error: {error}\n")

    print(text)
    return 0

