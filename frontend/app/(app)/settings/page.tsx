"use client";
import { useEffect, useState } from "react";
import { api, EmailAccount } from "@/lib/api";

type Provider = "mock" | "gmail" | "outlook";

// ── Tutorial steps ────────────────────────────────────────────────────────────

const GMAIL_STEPS = [
  {
    title: "Criar projeto no Google Cloud Console",
    body: (
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        <li>Acesse <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer" className="text-blue-600 underline">console.cloud.google.com</a></li>
        <li>Clique no seletor de projetos → <b>Novo projeto</b> → dê um nome (ex: <code className="bg-gray-100 px-1 rounded">juridico-email</code>) → <b>Criar</b></li>
        <li>Vá em <b>APIs & Services → Library</b></li>
        <li>Busque <b>Gmail API</b> → clique → <b>Ativar</b></li>
      </ol>
    ),
  },
  {
    title: "Configurar a tela de consentimento OAuth",
    body: (
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        <li>Vá em <b>APIs & Services → OAuth consent screen</b></li>
        <li>Tipo: <b>Externo</b> → <b>Criar</b></li>
        <li>Preencha: App name, e-mail de suporte e developer contact com seu Gmail</li>
        <li>Clique em <b>Salvar e continuar</b> nas próximas telas</li>
        <li>Na aba <b>Test users</b> → <b>+ Add users</b> → adicione o Gmail da caixa de poupança</li>
      </ol>
    ),
  },
  {
    title: "Criar credenciais OAuth",
    body: (
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        <li>Vá em <b>APIs & Services → Credentials</b></li>
        <li><b>+ Create Credentials → OAuth client ID</b></li>
        <li>Application type: <b>Web application</b></li>
        <li>Em <b>Authorized redirect URIs</b> → <b>+ Add URI</b> → cole o endereço abaixo</li>
        <li>Clique em <b>Create</b> e copie o <b>Client ID</b> e o <b>Client Secret</b></li>
      </ol>
    ),
  },
  {
    title: "Preencher as credenciais e conectar",
    body: (
      <p className="text-sm text-gray-700">
        Cole o <b>Client ID</b> e o <b>Client Secret</b> nos campos abaixo e clique em <b>Salvar credenciais</b>.
        Depois clique em <b>Conectar conta Gmail</b> — uma janela abrirá para você autorizar o acesso.
      </p>
    ),
  },
];

const OUTLOOK_STEPS = [
  {
    title: "Registrar o app no Azure",
    body: (
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        <li>Acesse <a href="https://portal.azure.com" target="_blank" rel="noreferrer" className="text-blue-600 underline">portal.azure.com</a> com a conta Microsoft</li>
        <li>Busque <b>App registrations</b> → <b>+ New registration</b></li>
        <li>Name: <code className="bg-gray-100 px-1 rounded">juridico-email</code></li>
        <li>Supported account types:
          <ul className="list-disc list-inside ml-4 mt-1">
            <li>Conta pessoal (Outlook.com/Hotmail): <b>"Accounts in any organizational directory and personal Microsoft accounts"</b></li>
            <li>Conta corporativa (M365): <b>"Accounts in this organizational directory only"</b></li>
          </ul>
        </li>
        <li>Redirect URI: selecione <b>Web</b> → cole o endereço abaixo</li>
        <li>Clique em <b>Register</b></li>
      </ol>
    ),
  },
  {
    title: "Anotar os IDs do app",
    body: (
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        <li>Na tela do app registrado, anote o <b>Application (client) ID</b> → este é o Client ID</li>
        <li>Anote o <b>Directory (tenant) ID</b> → use se for conta corporativa; deixe vazio para conta pessoal</li>
      </ol>
    ),
  },
  {
    title: "Criar o Client Secret",
    body: (
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        <li>Menu lateral → <b>Certificates & secrets</b></li>
        <li>Aba <b>Client secrets</b> → <b>+ New client secret</b></li>
        <li>Description: <code className="bg-gray-100 px-1 rounded">backend</code> | Expires: <b>24 months</b></li>
        <li>Clique em <b>Add</b> → copie imediatamente o valor da coluna <b>Value</b></li>
      </ol>
    ),
  },
  {
    title: "Adicionar permissões da API",
    body: (
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        <li>Menu lateral → <b>API permissions → + Add a permission → Microsoft Graph → Delegated permissions</b></li>
        <li>Adicione: <b>Mail.Read</b>, <b>User.Read</b>, <b>offline_access</b></li>
        <li>Clique em <b>Add permissions</b></li>
        <li>Se tiver permissão de admin: clique em <b>Grant admin consent</b></li>
      </ol>
    ),
  },
  {
    title: "Preencher as credenciais e conectar",
    body: (
      <p className="text-sm text-gray-700">
        Cole o <b>Client ID</b>, <b>Client Secret</b> e (se conta corporativa) o <b>Tenant ID</b> nos campos abaixo.
        Clique em <b>Salvar credenciais</b> e depois em <b>Conectar conta Outlook</b>.
      </p>
    ),
  },
];

// ── Accordion ─────────────────────────────────────────────────────────────────

function Accordion({ steps }: { steps: { title: string; body: React.ReactNode }[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="border rounded divide-y text-sm">
      {steps.map((s, i) => (
        <div key={i}>
          <button
            className="w-full flex items-center justify-between px-3 py-2 text-left font-medium hover:bg-gray-50"
            onClick={() => setOpen(open === i ? null : i)}
          >
            <span><span className="text-gray-400 mr-2">{i + 1}.</span>{s.title}</span>
            <span className="text-gray-400">{open === i ? "▲" : "▼"}</span>
          </button>
          {open === i && <div className="px-4 py-3 bg-gray-50">{s.body}</div>}
        </div>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type GmailFlow = null | "home" | "update-pick" | "wizard";

export default function SettingsPage() {
  const [provider, setProvider] = useState<Provider>("mock");
  const [emailAddr, setEmailAddr] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [msgColor, setMsgColor] = useState<"green" | "red">("green");
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [busy, setBusy] = useState(false);

  // Modal Gmail wizard
  const [gmailFlow, setGmailFlow] = useState<GmailFlow>(null);
  const [gmailWizardStep, setGmailWizardStep] = useState(0);
  const [gmailWizardFor, setGmailWizardFor] = useState<"add" | "redo">("add");

  // Modal para adicionar nova conta com credenciais opcionais (Outlook)
  const [addModal, setAddModal] = useState<{ provider: "outlook" } | null>(null);
  const [addUseCustom, setAddUseCustom] = useState(false);
  const [addClientId, setAddClientId] = useState("");
  const [addClientSecret, setAddClientSecret] = useState("");

  // Gmail creds
  const [gmailClientId, setGmailClientId] = useState("");
  const [gmailClientSecret, setGmailClientSecret] = useState("");
  const [gmailSecretSet, setGmailSecretSet] = useState(false);
  const [gmailCredSaved, setGmailCredSaved] = useState(false);
  const [gmailSavedClientId, setGmailSavedClientId] = useState(""); // client_id atual no banco

  // Outlook creds
  const [outlookClientId, setOutlookClientId] = useState("");
  const [outlookClientSecret, setOutlookClientSecret] = useState("");
  const [outlookTenantId, setOutlookTenantId] = useState("");
  const [outlookSecretSet, setOutlookSecretSet] = useState(false);
  const [outlookCredSaved, setOutlookCredSaved] = useState(false);
  const [outlookSavedClientId, setOutlookSavedClientId] = useState(""); // client_id atual no banco

  // redirect URI exibido ao usuário
  const redirectUri = typeof window !== "undefined"
    ? `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}/api/v1/email/oauth/callback`
    : "http://localhost:8001/api/v1/email/oauth/callback";

  async function refreshAll() {
    try { const p = await api.getEmailProvider(); setProvider(p.provider as Provider); setEmailAddr(p.email_address); } catch {}
    try { setAccounts(await api.listAccounts()); } catch {}
    try {
      const g = await api.getGmailCreds();
      setGmailClientId(g.client_id);
      setGmailSavedClientId(g.client_id);
      setGmailSecretSet(g.client_secret_set);
      setGmailCredSaved(!!g.client_id && g.client_secret_set);
    } catch {}
    try {
      const o = await api.getOutlookCreds();
      setOutlookClientId(o.client_id);
      setOutlookSavedClientId(o.client_id);
      setOutlookTenantId(o.tenant_id);
      setOutlookSecretSet(o.client_secret_set);
      setOutlookCredSaved(!!o.client_id && o.client_secret_set);
    } catch {}
  }

  async function refreshStatuses() {
    try { setAccounts(await api.listAccounts()); } catch {}
  }

  useEffect(() => { refreshAll(); }, []);
  useEffect(() => {
    window.addEventListener("focus", refreshStatuses);
    return () => window.removeEventListener("focus", refreshStatuses);
  }, []);

  function flash(text: string, color: "green" | "red" = "green") {
    setMsg(text); setMsgColor(color);
    setTimeout(() => setMsg(null), 4000);
  }

  async function saveProvider() {
    try { await api.setEmailProvider({ provider, email_address: emailAddr }); flash("Configuração salva."); }
    catch (e: any) { flash(e.message, "red"); }
  }

  async function saveGmailCreds() {
    if (!gmailClientId.trim()) { flash("Preencha o Client ID.", "red"); return; }
    if (!gmailClientSecret.trim() && !gmailSecretSet) { flash("Preencha o Client Secret.", "red"); return; }
    const clientIdChanged = gmailSavedClientId && gmailClientId.trim() !== gmailSavedClientId;
    if (clientIdChanged) {
      if (!confirm("Você trocou o Client ID (nova conta). Isso vai limpar toda a caixa de entrada e desconectar a conta atual. Confirmar?")) return;
      try { await api.oauthDisconnect("gmail"); } catch {}
    }
    try {
      await api.saveGmailCreds({ client_id: gmailClientId, client_secret: gmailClientSecret });
      setGmailSavedClientId(gmailClientId.trim());
      setGmailSecretSet(true); setGmailCredSaved(true); setGmailClientSecret("");
      await refreshStatuses();
      setGmailSavedClientId(gmailClientId.trim());
      flash("Credenciais Gmail salvas!");
    } catch (e: any) { flash(e.message, "red"); }
  }

  async function saveOutlookCreds() {
    if (!outlookClientId.trim()) { flash("Preencha o Client ID.", "red"); return; }
    if (!outlookClientSecret.trim() && !outlookSecretSet) { flash("Preencha o Client Secret.", "red"); return; }
    try {
      await api.saveOutlookCreds({ client_id: outlookClientId, client_secret: outlookClientSecret, tenant_id: outlookTenantId });
      setOutlookSavedClientId(outlookClientId.trim());
      setOutlookSecretSet(true); setOutlookCredSaved(true); setOutlookClientSecret("");
      flash("Credenciais Outlook salvas!");
    } catch (e: any) { flash(e.message, "red"); }
  }

  async function connectWithCredentials(prov: "gmail" | "outlook", clientId?: string, clientSecret?: string) {
    setBusy(true);
    try {
      const { authorize_url } = await api.oauthStart(prov, clientId, clientSecret);
      const popup = window.open(authorize_url, "oauth", "width=520,height=700");
      const timer = setInterval(async () => {
        if (popup?.closed) {
          clearInterval(timer);
          await refreshAll();
          flash(`Conta ${prov} conectada! Sincronização iniciada em segundo plano.`);
          setBusy(false);
        }
      }, 800);
    } catch (e: any) {
      flash(e.message, "red");
      setBusy(false);
    }
  }

  function openGmailWizard(intent: "add" | "redo") {
    setGmailWizardFor(intent);
    setGmailWizardStep(0);
    setGmailFlow("wizard");
  }

  async function finishGmailWizard() {
    if (!gmailClientId.trim()) { flash("Preencha o Client ID.", "red"); return; }
    if (!gmailClientSecret.trim() && !gmailSecretSet) { flash("Preencha o Client Secret.", "red"); return; }
    // Salva credenciais e conecta
    try {
      await api.saveGmailCreds({ client_id: gmailClientId, client_secret: gmailClientSecret });
      setGmailSavedClientId(gmailClientId.trim());
      setGmailSecretSet(true); setGmailCredSaved(true);
    } catch (e: any) { flash(e.message, "red"); return; }
    setGmailFlow(null);
    await connectWithCredentials("gmail", gmailClientId.trim(), gmailClientSecret || undefined);
  }

  async function reconnectGmail() {
    setGmailFlow(null);
    await connectWithCredentials("gmail", gmailClientId || undefined, undefined);
  }

  async function openAddModal(prov: "outlook") {
    setAddModal({ provider: prov });
    setAddUseCustom(false);
    setAddClientId("");
    setAddClientSecret("");
  }

  async function confirmAddAccount() {
    if (!addModal) return;
    setAddModal(null);
    await connectWithCredentials("outlook", undefined, undefined);
  }

  async function removeAccount(acc: EmailAccount) {
    if (!confirm(`Remover ${acc.email_address}? Isso vai APAGAR as demandas desta conta.`)) return;
    setBusy(true);
    try {
      const r = await api.deleteAccount(acc.id);
      flash(`Conta removida. ${r.demands_removed} demandas apagadas.`);
      await refreshAll();
    } catch (e: any) { flash(e.message, "red"); }
    finally { setBusy(false); }
  }

  async function updateColor(acc: EmailAccount, color: string) {
    try {
      const updated = await api.updateAccountColor(acc.id, color);
      setAccounts(prev => prev.map(a => a.id === acc.id ? updated : a));
    } catch (e: any) { flash(e.message, "red"); }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold">Configurações</h1>

      {/* Mensagem global */}
      {msg && (
        <div className={`text-sm px-4 py-2 rounded ${msgColor === "green" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}>
          {msg}
        </div>
      )}

      {/* Provider ativo */}
      <div className="card p-4">
        <h2 className="font-semibold mb-3">Provedor de e-mail ativo</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="md:col-span-1">
            <label className="text-sm font-medium">Provider</label>
            <select className="input mt-1" value={provider} onChange={(e) => setProvider(e.target.value as Provider)}>
              <option value="mock">Mock (PoC)</option>
              <option value="gmail">Gmail</option>
              <option value="outlook">Outlook</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="text-sm font-medium">E-mail central (caixa a ser lida)</label>
            <input className="input mt-1" value={emailAddr} onChange={(e) => setEmailAddr(e.target.value)} placeholder="poupanca@empresa.com.br" />
          </div>
        </div>
        <button className="btn-primary mt-3" onClick={saveProvider}>Salvar</button>
        <p className="text-xs text-gray-500 mt-2">
          Após conectar Gmail ou Outlook abaixo, mude o provider aqui e clique em Salvar. Depois vá ao Dashboard e clique em Sincronizar.
        </p>
      </div>

      {/* URI de redirecionamento */}
      <div className="card p-4 bg-blue-50 border-blue-200">
        <p className="text-sm font-semibold text-blue-800 mb-1">URI de redirecionamento OAuth</p>
        <p className="text-xs text-blue-700 mb-2">
          Use este endereço ao cadastrar o app no Google Cloud Console ou no Azure Portal:
        </p>
        <div className="flex items-center gap-2">
          <code className="bg-white border border-blue-200 rounded px-3 py-1.5 text-sm font-mono flex-1 break-all">{redirectUri}</code>
          <button className="btn-secondary text-xs whitespace-nowrap" onClick={() => { navigator.clipboard.writeText(redirectUri); flash("Copiado!"); }}>
            Copiar
          </button>
        </div>
      </div>

      {/* Contas conectadas ──────────────────────────────────────────────── */}
      {accounts.length > 0 && (
        <div className="card p-4 space-y-3">
          <h2 className="font-semibold text-lg">Contas conectadas</h2>
          <div className="divide-y">
            {accounts.map((acc) => (
              <div key={acc.id} className="flex items-center gap-3 py-2">
                <div
                  className="w-4 h-4 rounded-full shrink-0 border border-gray-200 cursor-pointer"
                  style={{ backgroundColor: acc.color }}
                  title="Clique para alterar a cor"
                  onClick={() => document.getElementById(`color-${acc.id}`)?.click()}
                />
                <input
                  id={`color-${acc.id}`}
                  type="color"
                  className="sr-only"
                  value={acc.color}
                  onChange={(e) => updateColor(acc, e.target.value)}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{acc.email_address}</div>
                  <div className="text-xs text-gray-500">{acc.provider}</div>
                </div>
                <button
                  className="btn-danger text-xs py-1 px-2"
                  onClick={() => removeAccount(acc)}
                  disabled={busy}
                >
                  Remover
                </button>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-500">Clique no círculo colorido para escolher a cor da conta.</p>
        </div>
      )}

      {/* Gmail ──────────────────────────────────────────────────────────── */}
      <div className="card p-4 space-y-4">
        <h2 className="font-semibold text-lg">Gmail</h2>
        <p className="text-sm text-gray-600">Conecte uma ou mais contas Gmail para receber e responder e-mails diretamente pelo sistema.</p>
        <button className="btn-primary" onClick={() => setGmailFlow("home")} disabled={busy}>
          + Adicionar / Atualizar conta Gmail
        </button>
      </div>

      {/* ── Modal Gmail wizard ─────────────────────────────────────────────── */}
      {gmailFlow && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg">

            {/* Tela 1: Escolha da ação */}
            {gmailFlow === "home" && (
              <div className="p-6 space-y-4">
                <h3 className="font-semibold text-lg">Conta Gmail</h3>
                <p className="text-sm text-gray-600">O que deseja fazer?</p>
                <div className="space-y-2">
                  <button
                    className="w-full text-left px-4 py-3 border rounded-lg hover:bg-blue-50 hover:border-blue-400 transition-colors"
                    onClick={() => openGmailWizard("add")}
                  >
                    <div className="font-medium text-sm">+ Adicionar nova conta</div>
                    <div className="text-xs text-gray-500 mt-0.5">Conectar um novo Gmail ao sistema com passo a passo</div>
                  </button>
                  <button
                    className="w-full text-left px-4 py-3 border rounded-lg hover:bg-amber-50 hover:border-amber-400 transition-colors"
                    onClick={() => setGmailFlow("update-pick")}
                  >
                    <div className="font-medium text-sm">↺ Atualizar conta existente</div>
                    <div className="text-xs text-gray-500 mt-0.5">Reconectar ou reconfigurar uma conta já vinculada</div>
                  </button>
                </div>
                <div className="flex justify-end pt-2">
                  <button className="btn-secondary" onClick={() => setGmailFlow(null)}>Fechar</button>
                </div>
              </div>
            )}

            {/* Tela 2: Atualizar — escolhe reconectar ou refazer */}
            {gmailFlow === "update-pick" && (
              <div className="p-6 space-y-4">
                <h3 className="font-semibold text-lg">Atualizar conta Gmail</h3>
                <p className="text-sm text-gray-600">Como deseja atualizar?</p>
                <div className="space-y-2">
                  <button
                    className="w-full text-left px-4 py-3 border rounded-lg hover:bg-green-50 hover:border-green-400 transition-colors"
                    onClick={reconnectGmail}
                    disabled={busy}
                  >
                    <div className="font-medium text-sm">Reconectar conta</div>
                    <div className="text-xs text-gray-500 mt-0.5">Refaz a autorização usando as credenciais já salvas. Mantém todo o histórico.</div>
                  </button>
                  <button
                    className="w-full text-left px-4 py-3 border rounded-lg hover:bg-amber-50 hover:border-amber-400 transition-colors"
                    onClick={() => openGmailWizard("redo")}
                  >
                    <div className="font-medium text-sm">Refazer configuração completa</div>
                    <div className="text-xs text-gray-500 mt-0.5">Preenche novamente Client ID e Secret. Use se as credenciais expiraram ou mudaram.</div>
                  </button>
                </div>
                <div className="flex justify-between pt-2">
                  <button className="btn-secondary" onClick={() => setGmailFlow("home")}>← Voltar</button>
                  <button className="btn-secondary" onClick={() => setGmailFlow(null)}>Fechar</button>
                </div>
              </div>
            )}

            {/* Tela 3: Wizard passo a passo */}
            {gmailFlow === "wizard" && (
              <div className="p-6 space-y-4">
                {/* Header do wizard */}
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full">
                    Passo {gmailWizardStep + 1} de {GMAIL_STEPS.length}
                  </span>
                  <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                    <div
                      className="bg-blue-500 h-1.5 rounded-full transition-all"
                      style={{ width: `${((gmailWizardStep + 1) / GMAIL_STEPS.length) * 100}%` }}
                    />
                  </div>
                </div>

                <h3 className="font-semibold text-base">{GMAIL_STEPS[gmailWizardStep].title}</h3>

                {/* Conteúdo do passo */}
                <div className="min-h-32">
                  {GMAIL_STEPS[gmailWizardStep].body}

                  {/* No passo 2 (índice 2) mostra o redirect URI */}
                  {gmailWizardStep === 2 && (
                    <div className="mt-3 bg-blue-50 border border-blue-200 rounded-lg p-3">
                      <p className="text-xs font-semibold text-blue-800 mb-1">URI de redirecionamento para colar no Google:</p>
                      <div className="flex items-center gap-2">
                        <code className="text-xs font-mono bg-white border border-blue-200 rounded px-2 py-1.5 flex-1 break-all">{redirectUri}</code>
                        <button
                          className="btn-secondary text-xs shrink-0"
                          onClick={() => { navigator.clipboard.writeText(redirectUri); flash("Copiado!"); }}
                        >Copiar</button>
                      </div>
                    </div>
                  )}

                  {/* Último passo: campos de credenciais */}
                  {gmailWizardStep === GMAIL_STEPS.length - 1 && (
                    <div className="mt-4 space-y-3">
                      <div>
                        <label className="text-xs text-gray-500 font-medium">Client ID</label>
                        <input
                          className="input mt-1 w-full font-mono text-sm"
                          placeholder="xxxxxxxxxx-xxxx.apps.googleusercontent.com"
                          value={gmailClientId}
                          onChange={e => setGmailClientId(e.target.value)}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 font-medium">
                          Client Secret {gmailSecretSet && <span className="text-green-600 ml-1">✓ já configurado</span>}
                        </label>
                        <input
                          className="input mt-1 w-full font-mono text-sm"
                          type="password"
                          placeholder={gmailSecretSet ? "••••••• (deixe vazio para manter)" : "GOCSPX-..."}
                          value={gmailClientSecret}
                          onChange={e => setGmailClientSecret(e.target.value)}
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Navegação */}
                <div className="flex justify-between pt-2 border-t">
                  <button
                    className="btn-secondary"
                    onClick={() => gmailWizardStep === 0 ? setGmailFlow("home") : setGmailWizardStep(s => s - 1)}
                  >
                    ← {gmailWizardStep === 0 ? "Voltar" : "Anterior"}
                  </button>
                  {gmailWizardStep < GMAIL_STEPS.length - 1 ? (
                    <button className="btn-primary" onClick={() => setGmailWizardStep(s => s + 1)}>
                      Próximo →
                    </button>
                  ) : (
                    <button className="btn-primary disabled:opacity-50" onClick={finishGmailWizard} disabled={busy}>
                      {busy ? "Aguardando..." : "Salvar e Conectar"}
                    </button>
                  )}
                </div>
              </div>
            )}

          </div>
        </div>
      )}

      {/* Outlook ─────────────────────────────────────────────────────────── */}
      <div className="card p-4 space-y-4">
        <h2 className="font-semibold text-lg">Outlook / Microsoft 365</h2>

        <details className="group">
          <summary className="cursor-pointer text-sm text-blue-600 hover:underline list-none flex items-center gap-1">
            <span className="group-open:hidden">▶ Ver passo a passo de configuração</span>
            <span className="hidden group-open:inline">▼ Ocultar passo a passo</span>
          </summary>
          <div className="mt-3"><Accordion steps={OUTLOOK_STEPS} /></div>
        </details>

        <div className="space-y-3">
          <p className="text-sm font-medium text-gray-700">Credenciais padrão Outlook (Azure Portal)</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500">Client ID (Application ID)</label>
              <input className="input mt-1" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value={outlookClientId} onChange={(e) => setOutlookClientId(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-gray-500">Client Secret {outlookSecretSet && <span className="text-green-600 ml-1">✓ configurado</span>}</label>
              <input className="input mt-1" type="password" placeholder={outlookSecretSet ? "••••••••• (deixe vazio para manter)" : "Valor do secret"} value={outlookClientSecret} onChange={(e) => setOutlookClientSecret(e.target.value)} />
            </div>
            <div className="md:col-span-2">
              <label className="text-xs text-gray-500">Tenant ID <span className="text-gray-400">(vazio para Outlook.com/Hotmail)</span></label>
              <input className="input mt-1" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value={outlookTenantId} onChange={(e) => setOutlookTenantId(e.target.value)} />
            </div>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button className="btn-secondary" onClick={saveOutlookCreds}>Salvar credenciais</button>
            <button className="btn-primary" onClick={() => openAddModal("outlook")} disabled={busy || !outlookCredSaved} title={!outlookCredSaved ? "Salve as credenciais primeiro" : ""}>
              + Adicionar conta Outlook
            </button>
          </div>
          {!outlookCredSaved && <p className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1">Preencha e salve as credenciais antes de conectar.</p>}
        </div>
      </div>

      {/* Modal: adicionar conta Outlook ─────────────────────────────────── */}
      {addModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md space-y-4">
            <h3 className="font-semibold text-lg">Adicionar conta Outlook</h3>
            <p className="text-sm text-gray-600">
              Uma janela da Microsoft vai abrir para você autorizar a conta Outlook.
              Após autorizar, a sincronização começa automaticamente em segundo plano.
            </p>
            <div className="flex gap-2 justify-end pt-2">
              <button className="btn-secondary" onClick={() => setAddModal(null)}>Cancelar</button>
              <button className="btn-primary" onClick={confirmAddAccount} disabled={busy}>
                {busy ? "Aguardando..." : "Conectar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
