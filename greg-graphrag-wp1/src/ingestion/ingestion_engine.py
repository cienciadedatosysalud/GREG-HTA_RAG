import re
import html
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat

class IngestionEngine:
    def __init__(self, min_chunk_size=2500, max_chunk_size=3500):
        pipeline_opt = PdfPipelineOptions()
        pipeline_opt.do_ocr = False
        pipeline_opt.do_table_structure = True
        
        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opt)}
        )
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.noise_patterns = [
            r"table of contents", r"^contents$", r"list of figures", 
            r"list of tables", r"bibliography", r"references", r"^index$",
            r'\.{4,}', r'\|\s*\d+(\.\d+)+\s*\|'
        ]

    def _is_noise(self, text):
        if not text: return True
        t_lower = text.lower().strip()
        return any(re.search(p, t_lower) for p in self.noise_patterns)

    def _clean_text(self, text):
        if not text: return ""
        text = html.unescape(text)
        replacements = {"â€™": "'", "â€˜": "'", "â€œ": '"', "â€": '"', "…": "...", "\xa0": " "}
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        text = re.sub(r'!\[.*?\]\(.*?\)|\[([^\]]+)\]\(http.*?\)|\[\d+(?:-\d+)?\]|http[s]?://\S+', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _linearize_table(self, table_node):
        cells = table_node.get("data", {}).get("cells", [])
        if not cells: return ""
        
        data_rows = {}
        headers = {}
        
        for cell in cells:
            r_idx = cell.get("row_index", 0)
            c_idx = cell.get("col_index", 0)
            text = self._clean_text(cell.get("text", ""))
            
            if cell.get("column_header"):
                headers[c_idx] = text
            else:
                data_rows.setdefault(r_idx, []).append(f"{headers.get(c_idx, f'Col_{c_idx}')}: {text}")
        
        label = self._clean_text(table_node.get("label", "TABLA"))
        output = [f"### {label} ###"]
        for r_idx in sorted(data_rows.keys()):
            output.append(f"Fila_{r_idx}: " + " | ".join(data_rows[r_idx]))
        return "\n".join(output)

    def get_parent_chunks(self, pdf_path):
        result = self.converter.convert(pdf_path)
        doc = result.document
        final_chunks = []
        current_content = ""

        for node, level in doc.iterate_items():
            processed = ""
            item_type = type(node).__name__            
            if "TableItem" in item_type:
                processed = self._linearize_table(node.model_dump() if hasattr(node, 'model_dump') else node.__dict__)
            elif "TextItem" in item_type or "SectionHeaderItem" in item_type:
                text = getattr(node, "text", "")
                if self._is_noise(text) or len(text) < 15:
                    continue
                processed = self._clean_text(text)

            if not processed: continue

            if len(current_content) + len(processed) <= self.max_chunk_size:
                current_content += "\n\n" + processed
            else:
                if current_content: final_chunks.append(current_content.strip())
                current_content = processed

            if len(current_content) >= self.min_chunk_size:
                final_chunks.append(current_content.strip())
                current_content = ""

        if current_content:
            if final_chunks and (len(current_content) + len(final_chunks[-1]) < self.max_chunk_size):
                final_chunks[-1] += "\n\n" + current_content
            else:
                final_chunks.append(current_content.strip())
                
        return final_chunks