from typing import TypedDict, Optional, List
from pathlib import Path
import re
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage

from .chains import get_triage_chain, get_rag_chain
from .vectorDB import VectorDB, AmbiguousPersonError
from ..config import Settings

class AgentState(TypedDict, total=False):
    question: str
    history: List[dict]
    triage: dict
    answer: Optional[str]
    citations: List[dict]
    rag_success: bool
    final_action: str

class Citation(TypedDict):
    source: str
    page: Optional[int]
    sheet: Optional[str]
    snippet: str

class GraphResponse(TypedDict):
    response: str
    source_documents: List[Citation]

class ITTGraph:
    def __init__(self, settings: Settings, vector_db: VectorDB):
        self.settings = settings
        self.vector_db = vector_db
        self.triage_chain = get_triage_chain(settings)
        self.rag_chain = get_rag_chain(settings)
        self.graph = self._build_graph()
    
    def _node_triage(self, state: AgentState) -> AgentState:
        question = state.get("question", "")
        messages = [
            (HumanMessage if message['role'] == 'user' else AIMessage)(content=message['content'])
            for message in state.get('history', [])
        ]
        triage_result = self.triage_chain.invoke(messages + [HumanMessage(content=question)])
        return {"triage": triage_result.dict()}

    def _node_auto_resolve(self, state: AgentState) -> AgentState:
        triage = state.get("triage", {})
        question = triage.get('pergunta_contextualizada') or state.get("question", "")
        search_query = triage.get('consulta_busca')
        try:
            related_docs = self.vector_db.query(search_query or question)
        except AmbiguousPersonError as error:
            names = "\n".join(f"- {name}" for name in error.names)
            return {
                "answer": f"Encontrei mais de uma pessoa com esse nome:\n\n{names}\n\nSobre qual delas você quer saber?",
                "citations": [],
                "rag_success": False,
            }

        text = ""
        if related_docs:
            for doc in related_docs:
                file_name = Path(doc.metadata.get('source', 'Desconhecido')).name
                # Arquivos do Drive são salvos como "nome--id.ext". O ID não interessa a quem lê.
                display_name = re.sub(r'--[\w-]+(?=\.\w+$)', '', file_name)
                doc.page_content = doc.page_content.replace(file_name, display_name)
                doc.metadata['source'] = display_name
            text = (self.rag_chain.invoke({"input": question, "context": related_docs}) or "").strip()

        if not text or re.search(r'n[aã]o_encontrado', text, re.IGNORECASE):
            return {"answer": "Não encontrei essa informação nos documentos.", "citations": [], 
                    "rag_success": False}

        seen = set()
        citations = []
        for doc in related_docs:
            raw_source = doc.metadata.get("source", "Desconhecido")
            source_name = Path(raw_source).name
            raw_page = doc.metadata.get("page")
            page = (raw_page + 1) if isinstance(raw_page, int) else None
            sheet = doc.metadata.get('sheet')
            key = (source_name, page, sheet)
            if key in seen:
                continue
            seen.add(key)
            citations.append({
                "source": source_name,
                "page": page,
                "sheet": sheet,
                # Sem o cabeçalho "Arquivo:/Aba:" que a indexação põe em cada trecho para o modelo.
                "snippet": re.sub(r'\A(?:(?:Arquivo|Aba): .*\n)+', '', doc.page_content)[:300].strip(),
            })

        if triage.get("pede_fonte") or triage.get("decisao") == "FONTE_ANTERIOR":
            names = dict.fromkeys(citation["source"] for citation in citations)
            text += f"\n\nFonte: {', '.join(names)}"

        return {"answer": text, "citations": citations, "rag_success": True}

    def _node_previous_sources(self, state: AgentState) -> AgentState:
        answers = [message for message in state.get("history", []) if message["role"] == "assistant"]
        sources = answers[-1].get("sources")
        if not sources:
            return {"answer": "A resposta anterior não usou documentos.", "citations": []}
        return {"answer": f"Fonte: {', '.join(sources)}", "citations": []}

    def _node_request_info(self, state: AgentState) -> AgentState:
        missing_fields = state.get("triage", {}).get("campos_faltantes", [])
        details = ", ".join(missing_fields) if missing_fields else "mais detalhes sobre sua dúvida"
        return {
            "answer": f"Para te ajudar melhor, por favor, forneça {details}.",
            "citations": [],
            "final_action": "REQUEST_INFO"
        }

    def _decide_after_triage(self, state: AgentState) -> str:
        decision = state.get("triage", {}).get("decisao", "").lower()
        has_previous_answer = any(message["role"] == "assistant" for message in state.get("history", []))
        if decision == "fonte_anterior" and has_previous_answer:
            return "previous_sources"
        if decision in ("auto_resolver", "fonte_anterior"):
            return "auto_resolve"
        return "request_info"

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("triage_node", self._node_triage)
        workflow.add_node("auto_resolve", self._node_auto_resolve)
        workflow.add_node("request_info", self._node_request_info)
        workflow.add_node("previous_sources", self._node_previous_sources)

        workflow.add_edge(START, "triage_node")
        workflow.add_conditional_edges("triage_node", self._decide_after_triage, {
            "auto_resolve": "auto_resolve",
            "request_info": "request_info",
            "previous_sources": "previous_sources"
        })
        workflow.add_edge("auto_resolve", END)
        workflow.add_edge("request_info", END)
        workflow.add_edge("previous_sources", END)

        return workflow.compile()
    
    def invoke(self, question: str, history: Optional[List[dict]] = None) -> GraphResponse:
        result = self.graph.invoke({"question": question, "history": history or []})
        return {
            "response": result.get("answer", ""),
            "source_documents": result.get("citations", []),
        }
