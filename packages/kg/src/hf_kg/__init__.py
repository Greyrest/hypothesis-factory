"""hf_kg — универсальный движок базы знаний и графа знаний (ТЗ §9).

Ядро доменно-независимо:
- ingest: чтение PDF/DOCX/TXT/MD/CSV/XLSX/JSON в текстовые чанки и строки;
- retrieval: лексический поиск по чанкам;
- graph: типизированный мультиграф (узлы/рёбра — произвольные строковые типы;
  ядро задаёт рекомендуемый универсальный словарь в ontology.py);
- query: полный вид, соседи, трассировка «гипотеза -> источники и данные»;
- serializers: сериализация в формат vis-network;
- store: node-link JSON на диске (интерфейс — задел под Neo4j).

Доменные словари узлов (потоки/классы флотации, материалы/процессы) и
доменные построители графа живут в адаптерах hf_domains.
"""
from hf_kg.graph import add_edge, add_node, new_graph
from hf_kg.ingest import (
    read_csv_rows,
    read_docx_paragraphs,
    read_json_data,
    read_pdf_text,
    read_text_paragraphs,
    read_xlsx_rows,
)
from hf_kg.ontology import CoreEdgeType, CoreNodeType
from hf_kg.query import full_view, neighbors_view, trace_view
from hf_kg.retrieval import retrieve
from hf_kg.serializers import to_vis_nodes, vis_node, wrap
from hf_kg.store import graph_from_dict, graph_to_dict, load_graph, save_graph

__all__ = [
    "new_graph", "add_node", "add_edge",
    "CoreNodeType", "CoreEdgeType",
    "read_docx_paragraphs", "read_text_paragraphs", "read_csv_rows",
    "read_xlsx_rows", "read_json_data", "read_pdf_text",
    "retrieve",
    "full_view", "neighbors_view", "trace_view",
    "vis_node", "to_vis_nodes", "wrap",
    "save_graph", "load_graph", "graph_to_dict", "graph_from_dict",
]
