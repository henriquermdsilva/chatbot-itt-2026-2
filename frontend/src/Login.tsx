import { useEffect, useState } from "react";
import { useTheme } from "./ThemeContext";

interface LoginProps {
  onLogin: (token: string, email: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const { darkMode } = useTheme();
  const [googleError, setGoogleError] = useState(false);
  useEffect(() => {
    const renderGoogleButton = () => {
      /* @ts-ignore */
      window.google.accounts.id.initialize({
        client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID ||
          "961077150905-dsdb9plq43u7akdb4c77g3ai3ch1budm.apps.googleusercontent.com",
        callback: (response: any) => {
          const cred = response.credential;
          const payload = JSON.parse(atob(cred.split(".")[1]));
          onLogin(cred, payload.email);
        },
      });

      /* @ts-ignore */
      window.google.accounts.id.renderButton(document.getElementById("googleBtn"), {
        theme: "filled_black",
        size: "large",
        width: 300,
      });
    };

    // O script do Google carrega de forma assíncrona: na primeira visita ele ainda não 
    // está pronto.
    /* @ts-ignore */
    if (window.google?.accounts) {
      renderGoogleButton();
      return;
    }
    const script = document.getElementById("google-gsi");
    if (!script) {
      console.error('Script do Google com id="google-gsi" não encontrado no index.html.');
      setGoogleError(true);
      return;
    }
    // Sem "load" a tempo, o script falhou (rede, bloqueador) ou falhou antes desta tela 
    // abrir.
    const timeout = setTimeout(() => {
      console.error("O script de login do Google não carregou em 10 s.");
      setGoogleError(true);
    }, 10000);
    const onLoad = () => {
      clearTimeout(timeout);
      setGoogleError(false);
      renderGoogleButton();
    };
    script.addEventListener("load", onLoad);
    return () => {
      clearTimeout(timeout);
      script.removeEventListener("load", onLoad);
    };
  }, []);

  return (
    <div style={{...page, background: darkMode ? "linear-gradient(135deg, #0c0c0f 0%, #1a1626 100%)" : "linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%)"}}>
      <div style={{...card, background: darkMode ? "#1a1a1d" : "#ffffff", borderColor: darkMode ? "#dc2626" : "#dc2626"}}>
        {/* LOGO ITT */}
        <div style={logoContainer}>
          <img src="/icon_itt.png" alt="ITT Logo" style={logo} />
        </div>

        <h1 style={{...title, color: darkMode ? "#dc2626" : "#991b1b"}}>Acessar Assistente ITT</h1>
        <p style={{...subtitle, color: darkMode ? "#cbd5e1" : "#4b5563"}}>Faça login utilizando sua conta Google</p>

        <div style={{...googleBtnContainer, background: darkMode ? "rgba(220, 38, 38, 0.05)" : "rgba(220, 38, 38, 0.08)", borderColor: darkMode ? "rgba(220, 38, 38, 0.1)" : "rgba(220, 38, 38, 0.15)"}}>
          <div id="googleBtn" />
        </div>

        {googleError && (
          <p style={{...subtitle, color: darkMode ? "#fca5a5" : "#b91c1c", opacity: 1}}>
            Não foi possível carregar o login do Google. Recarregue a página; se continuar,
            verifique se uma extensão de privacidade, um bloqueador ou a rede está
            bloqueando accounts.google.com.
          </p>
        )}

        {/* Skip para desenvolvimento local */}
        {window.location.hostname === 'localhost' && (
          <button
            onClick={() => onLogin('dev-token', 'dev@itt.local')}
            style={{...devButton, background: darkMode ? "#4a5568" : "#cbd5e1", color: darkMode ? "#e5e7eb" : "#374151"}}
          >
            Skip Login (Dev)
          </button>
        )}

        <footer style={footer}>
          <small>Instituto Tadao Takahashi</small>
        </footer>
      </div>
    </div>
  );
}

/* ---------------- ESTILOS DARK MODE ---------------- */
const page = {
  background: "linear-gradient(135deg, #0c0c0f 0%, #1a1626 100%)",
  height: "100vh",
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  padding: "20px",
  color: "#e5e7eb",
};

const card = {
  background: "#1a1a1d",
  padding: "50px 40px",
  width: "100%",
  maxWidth: "420px",
  borderRadius: "14px",
  border: "1px solid #dc2626",
  boxShadow: "0 0 40px rgba(220, 38, 38, 0.2)",
  display: "flex",
  flexDirection: "column" as const,
  gap: "20px",
};

const logoContainer = {
  display: "flex",
  justifyContent: "center",
  marginBottom: "10px",
};

const logo = {
  width: "60px",
  height: "60px",
  objectFit: "contain" as const,
};

const title = {
  fontSize: "28px",
  margin: 0,
  marginBottom: "8px",
  fontWeight: 600 as const,
  letterSpacing: "-0.5px",
  textAlign: "center" as const,
  background: "linear-gradient(135deg, #dc2626 0%, #ef4444 100%)",
  WebkitBackgroundClip: "text",
  WebkitTextFillColor: "transparent",
  backgroundClip: "text",
};

const subtitle = {
  opacity: 0.7,
  marginBottom: "8px",
  fontSize: "14px",
  lineHeight: "1.5",
  textAlign: "center" as const,
  color: "#cbd5e1",
};

const footer = {
  marginTop: "20px",
  opacity: 0.4,
  textAlign: "center" as const,
};

const googleBtnContainer = {
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  padding: "20px 0",
  minHeight: "60px",
  background: "rgba(220, 38, 38, 0.05)",
  borderRadius: "10px",
  border: "1px solid rgba(220, 38, 38, 0.1)",
};

const devButton = {
  width: "100%",
  padding: "10px",
  marginTop: "10px",
  background: "#4a5568",
  color: "#e5e7eb",
  border: "1px dashed #6b7280",
  borderRadius: "8px",
  fontSize: "13px",
  cursor: "pointer",
  transition: "all 0.2s",
  fontWeight: 500 as const,
};
