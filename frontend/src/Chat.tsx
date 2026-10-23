import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { useTheme } from "./ThemeContext";

// MUDANÇA IMPORTANTE:
// Se estiver rodando localmente (backend na sua máquina), use localhost.
// Se for subir para produção, você pode trocar aqui ou usar variável de ambiente.
// Sugestão: Deixar localhost enquanto desenvolvemos.
// const API_URL = "http://localhost:8000"; 
const API_URL = "https://chatbot-itt-5lbt.onrender.com"; // URL antiga

interface ChatProps {
  idToken: string;
  email: string;
  onLogout: () => void;
}

interface SourceDocument {
  source: string;
  page: number | null;
  snippet: string;
}

interface Mensagem {
  autor: "user" | "assistant";
  texto: string;
  fontes?: SourceDocument[];
  timestamp: string;
}

const horaAtual = () =>
  new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

export default function Chat({ idToken, email, onLogout }: ChatProps) {
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [pergunta, setPergunta] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const { darkMode } = useTheme();

  // Estado para o botão de sincronização
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<'idle' | 'success' | 'error'>('idle');

  // Carregar histórico do localStorage ao montar
  useEffect(() => {
    const saved = localStorage.getItem('chat_history');
    if (saved) {
      try {
        setMensagens(JSON.parse(saved));
      } catch (e) {
        console.error('Erro ao carregar histórico:', e);
      }
    }
  }, []);

  // Salvar histórico em localStorage sempre que mensagens mudam
  useEffect(() => {
    localStorage.setItem('chat_history', JSON.stringify(mensagens));
  }, [mensagens]);


  const enviarPergunta = async () => {
    if (!pergunta.trim() || isLoading) return;

    const msgUser: Mensagem = { autor: "user", texto: pergunta, timestamp: horaAtual() };
    setMensagens((m) => [...m, msgUser]);

    const perguntaTexto = pergunta;
    setPergunta("");

    const loadingMsg: Mensagem = {
      autor: "assistant",
      texto: "Analisando a pergunta, aguarde um momento...",
      timestamp: horaAtual()
    };
    setMensagens((m) => [...m, loadingMsg]);
    setIsLoading(true);

    const { texto, fontes } = await consultarBackend(perguntaTexto);

    setMensagens((m) =>
      m.map((msg) =>
        msg === loadingMsg
          ? { autor: "assistant" as const, texto, fontes, timestamp: horaAtual() }
          : msg
      )
    );

    setIsLoading(false);
  };

  const consultarBackend = async (texto: string): Promise<{ texto: string; fontes: SourceDocument[] }> => {
    try {
      const res = await fetch(`${API_URL}/chat/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: texto, user_id: email }),
      });

      if (!res.ok) {
        const err = await res.json();
        return { texto: `Erro do servidor: ${err.detail ?? "Desconhecido"}`, fontes: [] };
      }

      const data = await res.json();
      return {
        texto: data.response ?? "Erro ao gerar resposta.",
        fontes: data.source_documents ?? [],
      };
    } catch (e) {
      return { texto: "Erro de conexão com o servidor. " + e, fontes: [] };
    }
  };

  // --- NOVA FUNÇÃO: Sincronizar Google Drive ---
  const sincronizarConhecimento = async () => {
    if (isSyncing) return;
    
    setIsSyncing(true);
    setSyncStatus('idle');

    try {
      const res = await fetch(`${API_URL}/admin/sync-knowledge`, {
        method: 'POST'
      });

      if (!res.ok) throw new Error('Falha na sincronização');

      setSyncStatus('success');
      // Volta ao normal depois de 3 segundos
      setTimeout(() => setSyncStatus('idle'), 3000);
      
    } catch (error) {
      console.error(error);
      setSyncStatus('error');
      setTimeout(() => setSyncStatus('idle'), 3000);
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div style={{...page, background: darkMode ? '#0c0c0f' : '#f9fafb'}}>
      <div style={{...container, background: darkMode ? '#1a1a1d' : '#ffffff', borderColor: darkMode ? '#2b2b2e' : '#d1d5db', color: darkMode ? '#e5e7eb' : '#1a1a1d'}}>
        <header style={{...header, background: darkMode ? '#1a1a1d' : '#ffffff', borderColor: darkMode ? '#2b2b2e' : '#d1d5db'}}>
          <div>
            <h2 style={{...title, color: darkMode ? '#e5e7eb' : '#1a1a1d'}}>Assistente ITT</h2>
            <span style={{...emailStyle, color: darkMode ? '#6b7280' : '#9ca3af'}}>{email}</span>
          </div>

          {/* GRUPO DE BOTÕES NO CABEÇALHO */}
          <div style={{ display: 'flex', gap: '10px' }}>

            {/* --- BOTÃO DE SINCRONIZAÇÃO --- */}
            <button
              onClick={sincronizarConhecimento}
              style={{
                ...syncBtn,
                background: syncStatus === 'error' ? '#ef4444' :
                           syncStatus === 'success' ? '#22c55e' : '#dc2626',
                opacity: isSyncing ? 0.7 : 1,
                cursor: isSyncing ? 'wait' : 'pointer'
              }}
              title="Atualizar base de conhecimento com arquivos do Google Drive"
            >
              {isSyncing ? 'Atualizando...' :
               syncStatus === 'success' ? 'Docs Atualizados!' :
               syncStatus === 'error' ? 'Erro' :
               'Atualizar Docs'}
            </button>

            <button onClick={onLogout} style={{...logoutBtn, background: darkMode ? '#2b2b2e' : '#e5e7eb', color: darkMode ? '#e5e7eb' : '#1a1a1d'}}>Sair</button>
          </div>
        </header>

        <div style={{...chatBox, background: darkMode ? '#0f1117' : '#ffffff'}}>
          {mensagens.length === 0 && (
            <div style={welcomeMessage}>
              <div style={welcomeIcon}>👋</div>
              <h3 style={{...welcomeTitle, color: darkMode ? '#e5e7eb' : '#1a1a1d'}}>Bem-vindo ao Assistente ITT</h3>
              <p style={{...welcomeText, color: darkMode ? '#cbd5e1' : '#4b5563'}}>
                Faça perguntas sobre estatuto, processos, currículos, horários de funcionamento e muito mais.
              </p>
              <div style={{...exampleSection, background: darkMode ? '#2a2a2d' : '#f3f4f6', borderColor: darkMode ? '#3a3a3d' : '#e5e7eb'}}>
                <p style={{...exampleLabel, color: darkMode ? '#94a3b8' : '#6b7280'}}>Exemplos de perguntas:</p>
                <ul style={exampleList}>
                  <li style={{...exampleListItem, color: darkMode ? '#cbd5e1' : '#4b5563'}}>"Qual é o horário de funcionamento do ITT?"</li>
                  <li style={{...exampleListItem, color: darkMode ? '#cbd5e1' : '#4b5563'}}>"Como funciona o processo de admissão?"</li>
                  <li style={{...exampleListItem, color: darkMode ? '#cbd5e1' : '#4b5563'}}>"Quais são os cursos disponíveis?"</li>
                </ul>
              </div>
            </div>
          )}
          {mensagens.map((m, i) => (
            <div key={i} style={{ alignSelf: m.autor === "user" ? "flex-end" : "flex-start", width: '100%', display: 'flex', justifyContent: m.autor === "user" ? "flex-end" : "flex-start", flexDirection: 'column', alignItems: m.autor === "user" ? "flex-end" : "flex-start" }}>
              <div style={m.autor === "user" ? {...msgUser, background: darkMode ? '#dc2626' : '#b91c1c', color: '#ffffff'} : {...msgAssistant, background: darkMode ? '#2a2a2d' : '#f3f4f6', color: darkMode ? '#e5e7eb' : '#1a1a1d'}}>
                <ReactMarkdown
                  components={{
                    p: ({ children }) => (
                      <p style={{ marginBottom: "8px", lineHeight: "1.6" }}>{children}</p>
                    ),
                    strong: ({ children }) => (
                      <strong style={{ color: "#fff" }}>{children}</strong>
                    ),
                    em: ({ children }) => {
                      const texto = typeof children === "string" ? children
                        : Array.isArray(children) && typeof children[0] === "string" ? children[0]
                        : "";
                      if (texto.toLowerCase().startsWith("fonte:")) {
                        return <em style={fonteAtribuicao}>{children}</em>;
                      }
                      return <em style={{ opacity: 0.85 }}>{children}</em>;
                    },
                    ul: ({ children }) => (
                      <ul style={{ marginLeft: "20px", marginBottom: "8px" }}>{children}</ul>
                    ),
                    li: ({ children }) => (
                      <li style={{ marginBottom: "4px" }}>{children}</li>
                    )
                  }}
                >
                  {m.texto}
                </ReactMarkdown>
              </div>
              <span style={{fontSize: '11px', color: darkMode ? '#64748b' : '#9ca3af', marginTop: '4px', marginRight: m.autor === "user" ? '0px' : 'auto', marginLeft: m.autor === "user" ? 'auto' : '0px'}}>{m.timestamp}</span>

              {m.autor === "assistant" && m.fontes && m.fontes.length > 0 && (
                <div style={{...sourcesCard, background: darkMode ? '#2a2a2d' : '#f3f4f6', borderColor: darkMode ? '#3a3a3d' : '#e5e7eb'}}>
                  <div style={{...sourcesHeader, color: darkMode ? '#cbd5e1' : '#4b5563'}}>
                    📄 Fontes Utilizadas:
                  </div>
                  <div style={sourcesList}>
                    {m.fontes.map((fonte, idx) => (
                      <div key={idx} style={{...sourceItem, color: darkMode ? '#cbd5e1' : '#4b5563'}}>
                        <span style={{...sourceIcon, color: darkMode ? '#64748b' : '#9ca3af'}}>•</span>
                        <span style={{...sourceName, color: darkMode ? '#cbd5e1' : '#4b5563'}}>
                          {fonte.source}
                          {fonte.page && <span style={sourcePage}> (página {fonte.page})</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={{...inputArea, background: darkMode ? '#1a1a1d' : '#f3f4f6', borderColor: darkMode ? '#2b2b2e' : '#d1d5db'}}>
          <input
            style={{...input, background: darkMode ? '#0f0f12' : '#ffffff', color: darkMode ? '#e5e7eb' : '#1a1a1d', borderColor: darkMode ? '#2b2b2e' : '#d1d5db'}}
            value={pergunta}
            placeholder={isLoading ? "Aguarde a resposta..." : "Digite sua pergunta..."}
            onChange={(e) => setPergunta(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && enviarPergunta()}
            disabled={isLoading}
          />
          <button
            onClick={() => setShowHistory(!showHistory)}
            style={historyIconBtn}
            title="Ver histórico de conversas"
          >
            <img
              src="/clock.svg"
              alt="History"
              style={{width: "20px", height: "20px", filter: darkMode ? 'brightness(0) invert(1)' : 'brightness(0.6)'}}
            />
          </button>
          <button
            style={{ ...sendBtn, background: darkMode ? '#dc2626' : '#b91c1c', opacity: isLoading ? 0.5 : 1 }}
            onClick={enviarPergunta}
            disabled={isLoading}
          >
            {isLoading ? "Processando..." : "Enviar"}
          </button>
        </div>
      </div>

      {/* PAINEL DE HISTÓRICO */}
      {showHistory && (
        <div style={{...historyOverlay, background: 'rgba(0,0,0,0.7)'}}>
          <div style={{...historyPanel, background: darkMode ? '#1a1a1d' : '#ffffff', borderColor: darkMode ? '#2b2b2e' : '#d1d5db'}}>
            <div style={{...historyHeader, borderColor: darkMode ? '#2b2b2e' : '#d1d5db'}}>
              <h3 style={{...historyTitle, color: darkMode ? '#e5e7eb' : '#1a1a1d'}}>Histórico de Conversas</h3>
              <button
                onClick={() => setShowHistory(false)}
                style={{...closeHistoryBtn, color: darkMode ? '#e5e7eb' : '#1a1a1d'}}
              >
                ✕
              </button>
            </div>

            <div style={{...historySummary, background: darkMode ? '#2a2a2d' : '#f3f4f6', borderColor: darkMode ? '#2b2b2e' : '#d1d5db'}}>
              <p style={{...historySummaryText, color: darkMode ? '#cbd5e1' : '#4b5563'}}>
                Total de mensagens: <strong>{mensagens.length}</strong>
              </p>
              <p style={{...historySummaryText, color: darkMode ? '#cbd5e1' : '#4b5563'}}>
                Perguntas: <strong>{mensagens.filter(m => m.autor === 'user').length}</strong>
              </p>
              <p style={{...historySummaryText, color: darkMode ? '#cbd5e1' : '#4b5563'}}>
                Respostas: <strong>{mensagens.filter(m => m.autor === 'assistant').length}</strong>
              </p>
            </div>

            <div style={historyList}>
              {mensagens.length === 0 ? (
                <p style={{...emptyHistoryText, color: darkMode ? '#64748b' : '#9ca3af'}}>Nenhuma conversa ainda</p>
              ) : (
                mensagens.map((msg, idx) => (
                  <div key={idx} style={msg.autor === 'user' ? historyItemUser : {...historyItemAssistant, background: darkMode ? '#2a2a2d' : '#f3f4f6', borderColor: darkMode ? '#3a3a3d' : '#e5e7eb'}}>

                    <span style={{...historyLabel, color: darkMode ? 'rgba(229, 231, 235, 0.7)' : 'rgba(26, 26, 29, 0.7)'}}>
                      {msg.autor === 'user' ? 'Você' : 'Assistente'}
                    </span>
                    <p style={{...historyMessage, color: darkMode ? '#e5e7eb' : '#1a1a1d'}}>
                      {msg.texto.substring(0, 100)}
                      {msg.texto.length > 100 ? '...' : ''}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------ DARK UI MODERN ------------------ */

const page = {
  height: "100vh",
  background: "#0c0c0f",
  color: "#e5e7eb",
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  padding: "20px",
};

const container = {
  width: "100%",
  maxWidth: "900px",
  height: "100%",
  display: "flex",
  flexDirection: "column" as const,
  background: "#1a1a1d",
  borderRadius: "14px",
  border: "1px solid #2b2b2e",
  boxShadow: "0 0 25px rgba(0,0,0,0.4)",
  overflow: "hidden",
};

const header = {
  padding: "20px",
  borderBottom: "1px solid #2b2b2e",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  background: "#1a1a1d",
};

const title = {
  margin: 0,
  fontSize: "20px",
  fontWeight: 500,
};

const emailStyle = {
  fontSize: "13px",
  opacity: 0.5,
};

const logoutBtn = {
  background: "#2b2b2e",
  color: "#e5e7eb",
  borderRadius: "8px",
  padding: "8px 12px",
  border: "none",
  cursor: "pointer",
  fontWeight: 500,
};

// Estilo novo para o botão de sync
const syncBtn = {
  color: "white",
  borderRadius: "8px",
  padding: "8px 12px",
  border: "none",
  fontWeight: 500,
  fontSize: "13px",
  transition: "all 0.2s",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  minWidth: "140px"
};

const historyBtn = {
  background: "#4b5563",
  color: "#e5e7eb",
  borderRadius: "8px",
  padding: "8px 12px",
  border: "none",
  cursor: "pointer",
  fontWeight: 500,
  fontSize: "13px",
  transition: "all 0.2s",
};

const historyOverlay = {
  position: "fixed" as const,
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: "rgba(0,0,0,0.7)",
  display: "flex",
  justifyContent: "flex-end",
  zIndex: 10000,
};

const historyPanel = {
  background: "#1a1a1d",
  width: "100%",
  maxWidth: "350px",
  height: "100%",
  display: "flex",
  flexDirection: "column" as const,
  borderLeft: "1px solid #2b2b2e",
  boxShadow: "-2px 0 15px rgba(0,0,0,0.5)",
};

const historyHeader = {
  padding: "20px",
  borderBottom: "1px solid #2b2b2e",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const historyTitle = {
  margin: 0,
  fontSize: "18px",
  fontWeight: 600,
};

const closeHistoryBtn = {
  background: "transparent",
  border: "none",
  color: "#e5e7eb",
  fontSize: "28px",
  cursor: "pointer",
  padding: "8px 12px",
  transition: "all 0.2s",
  borderRadius: "6px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const historySummary = {
  padding: "15px",
  background: "#2a2a2d",
  borderBottom: "1px solid #2b2b2e",
};

const historySummaryText = {
  margin: "6px 0",
  fontSize: "13px",
  color: "#cbd5e1",
};

const historyList = {
  flexGrow: 1,
  overflowY: "auto" as const,
  padding: "10px",
  display: "flex",
  flexDirection: "column" as const,
  gap: "8px",
};

const historyItemUser = {
  background: "#dc2626",
  padding: "10px",
  borderRadius: "8px",
  marginLeft: "auto",
  maxWidth: "90%",
};

const historyItemAssistant = {
  background: "#2a2a2d",
  padding: "10px",
  borderRadius: "8px",
  marginRight: "auto",
  maxWidth: "90%",
  border: "1px solid #3a3a3d",
};

const historyLabel = {
  fontSize: "11px",
  fontWeight: 600,
  opacity: 0.7,
  textTransform: "uppercase" as const,
};

const historyMessage = {
  margin: "6px 0 0 0",
  fontSize: "12px",
  color: "#e5e7eb",
  lineHeight: "1.4",
};

const emptyHistoryText = {
  textAlign: "center" as const,
  color: "#64748b",
  fontSize: "13px",
  padding: "20px",
};

const chatBox = {
  flexGrow: 1,
  padding: "25px",
  overflowY: "auto" as const,
  display: "flex",
  flexDirection: "column" as const,
  gap: "14px",
};

const msgUser = {
  alignSelf: "flex-end",
  background: "#dc2626",
  color: "white",
  padding: "12px 15px",
  borderRadius: "10px",
  maxWidth: "70%",
  fontSize: "15px",
  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
};

const msgAssistant = {
  alignSelf: "flex-start",
  background: "#2a2a2d",
  padding: "12px 15px",
  borderRadius: "10px",
  maxWidth: "75%",
  fontSize: "15px",
  boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
};

const inputArea = {
  display: "flex",
  padding: "18px",
  gap: "12px",
  borderTop: "1px solid #2b2b2e",
  background: "#1a1a1d",
  alignItems: "center",
} as const;

const input = {
  flexGrow: 1,
  background: "#0f0f12",
  border: "1px solid #2b2b2e",
  borderRadius: "10px",
  padding: "12px",
  color: "#e5e7eb",
  fontSize: "15px",
};

const sendBtn = {
  padding: "12px 18px",
  background: "#dc2626",
  border: "none",
  borderRadius: "10px",
  color: "white",
  cursor: "pointer",
  fontSize: "15px",
  fontWeight: 500,
  boxShadow: "0 0 10px rgba(220,38,38,0.5)",
};

const historyIconBtn = {
  background: "transparent",
  border: "none",
  fontSize: "20px",
  cursor: "pointer",
  padding: "8px 12px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};


const fonteAtribuicao = {
  display: "block",
  fontSize: "11px",
  color: "#6b7280",
  fontStyle: "italic" as const,
  opacity: 1,
  marginTop: "2px",
  marginBottom: "4px",
};

const sourcesCard = {
  background: "#2a2a2d",
  border: "1px solid #3a3a3d",
  borderRadius: "8px",
  padding: "12px 14px",
  marginTop: "8px",
  maxWidth: "75%",
  fontSize: "13px",
};

const sourcesHeader = {
  color: "#cbd5e1",
  fontWeight: 600 as const,
  marginBottom: "8px",
  fontSize: "12px",
  textTransform: "uppercase" as const,
  letterSpacing: "0.5px",
};

const sourcesList = {
  display: "flex",
  flexDirection: "column" as const,
  gap: "5px",
};

const sourceItem = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  color: "#cbd5e1",
};

const sourceIcon = {
  color: "#64748b",
  fontSize: "14px",
  minWidth: "10px",
};

const sourceName = {
  fontSize: "13px",
};

const sourcePage = {
  color: "#94a3b8",
  fontSize: "12px",
};

const welcomeMessage = {
  alignSelf: "center" as const,
  textAlign: "center" as const,
  padding: "40px 30px",
  maxWidth: "500px",
};

const welcomeIcon = {
  fontSize: "48px",
  marginBottom: "16px",
};

const welcomeTitle = {
  fontSize: "22px",
  fontWeight: 600 as const,
  marginBottom: "12px",
  color: "#e5e7eb",
};

const welcomeText = {
  fontSize: "14px",
  color: "#cbd5e1",
  marginBottom: "24px",
  lineHeight: "1.6",
};

const exampleSection = {
  background: "#2a2a2d",
  borderRadius: "8px",
  padding: "16px",
  border: "1px solid #3a3a3d",
};

const exampleLabel = {
  fontSize: "12px",
  fontWeight: 600 as const,
  color: "#94a3b8",
  textTransform: "uppercase" as const,
  marginBottom: "10px",
};

const exampleList = {
  listStyle: "none",
  padding: 0,
  margin: 0,
  display: "flex",
  flexDirection: "column" as const,
  gap: "8px",
};

const exampleListItem = {
  fontSize: "13px",
  color: "#cbd5e1",
  textAlign: "left" as const,
};