import logfire
from unstructured.partition.docx import partition_docx
from unstructured.partition.pptx import partition_pptx


def parse_office(file_path: str) -> str:
    """Parse DOCX and PPTX files with Unstructured's format-specific parsers."""
    with logfire.span("Office document parsing", filename=file_path):
        try:
            extension = file_path.lower().rsplit(".", 1)[-1]
            logfire.info(f"Parsing {file_path} with Unstructured")

            if extension == "docx":
                elements = partition_docx(filename=file_path)
            elif extension == "pptx":
                elements = partition_pptx(filename=file_path)
            else:
                raise ValueError(f"Unsupported Office file type: {extension}")

            full_text = "\n".join(str(element) for element in elements)

            if not full_text.strip():
                logfire.warning(f"No text found in {file_path}")
            else:
                logfire.info(
                    f"Extracted {len(elements)} elements and "
                    f"{len(full_text)} characters from {file_path}"
                )

            return full_text
        except Exception as exc:
            logfire.error(f"Office parsing failed for {file_path}: {exc}")
            raise
