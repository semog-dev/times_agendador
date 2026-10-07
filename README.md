# Times Agendador

Script Python que monitora a caixa de entrada do Outlook via IMAP, detecta
emails de confirmação de aulas da **Times Idiomas** e cria automaticamente
eventos no **Microsoft Outlook Calendar** via Microsoft Graph API.

---

## Pré-requisitos

- Python **3.11** ou superior
- pip (incluído com o Python)
- Conta Microsoft pessoal (hotmail.com, outlook.com ou similar)
- Acesso ao [portal.azure.com](https://portal.azure.com) com a mesma conta

---

## 1. Instalação

```bash
# Clone ou copie a pasta times_agendador para o local desejado.
# Navegue até ela:
cd C:\Users\semog\projects\times_agendador

# (Opcional, mas recomendado) Crie um ambiente virtual:
python -m venv .venv
.venv\Scripts\activate

# Instale as dependências:
pip install -r requirements.txt
```

---

## 2. Configurar senha de aplicativo do Outlook (IMAP)

O Outlook bloqueia o acesso IMAP com a senha normal quando a autenticação
em dois fatores está ativa. Você precisa gerar uma **senha de aplicativo**:

1. Acesse [account.microsoft.com/security](https://account.microsoft.com/security)
2. Faça login com a sua conta `@hotmail.com`
3. Clique em **"Opções de segurança avançadas"**
4. Na seção **"Senhas de aplicativo"**, clique em **"Criar uma nova senha de aplicativo"**
5. Copie a senha gerada (formato `xxxx xxxx xxxx xxxx`) — ela só aparece uma vez
6. Cole-a no `.env` como `OUTLOOK_APP_PASSWORD` (sem espaços)

> **Nota:** Se a opção de senha de aplicativo não aparecer, certifique-se de
> que a verificação em dois fatores está ativada na sua conta.

---

## 3. Registrar o aplicativo no Azure (Client ID e Client Secret)

Este passo é necessário para que o script possa criar eventos no calendário
via Microsoft Graph API.

### 3.1 Criar o registro do aplicativo

1. Acesse [portal.azure.com](https://portal.azure.com) e faça login com sua
   conta Microsoft pessoal
2. Na barra de pesquisa, busque por **"App registrations"** e clique em
   **"Registros de aplicativo"**
3. Clique em **"+ Novo registro"**
4. Preencha:
   - **Nome:** `Times Agendador` (ou qualquer nome)
   - **Tipos de conta com suporte:** selecione
     _"Contas pessoais da Microsoft somente"_
   - **URI de redirecionamento:** selecione a plataforma
     **"Cliente público/nativo (mobile e desktop)"** e insira a URI:
     ```
     https://login.microsoftonline.com/common/oauth2/nativeclient
     ```
5. Clique em **"Registrar"**
6. Na tela do aplicativo criado, copie o valor de **"ID do aplicativo (cliente)"**
   — esse é o `AZURE_CLIENT_ID`

### 3.2 Habilitar fluxo de cliente público

1. No menu lateral, clique em **"Autenticação"**
2. Na seção **"Configurações avançadas"**, mude
   _"Permitir fluxos de cliente público"_ para **Sim**
3. Clique em **"Salvar"**

### 3.3 Criar o Client Secret

1. No menu lateral, clique em **"Certificados e segredos"**
2. Clique em **"+ Novo segredo do cliente"**
3. Adicione uma descrição (ex: `times-agendador`) e escolha a validade
4. Clique em **"Adicionar"**
5. Copie imediatamente o **Valor** gerado (coluna "Valor", não "ID do segredo")
   — ele não será exibido novamente. Esse é o `AZURE_CLIENT_SECRET`

### 3.4 Adicionar permissões de API

1. No menu lateral, clique em **"Permissões de API"**
2. Clique em **"+ Adicionar uma permissão"**
3. Selecione **"Microsoft Graph"** → **"Permissões delegadas"**
4. Busque e adicione:
   - `Calendars.ReadWrite`
5. Clique em **"Adicionar permissões"**

> **Nota:** A permissão `Mail.Read` via Graph API não é necessária porque a
> leitura dos emails é feita diretamente via IMAP.

---

## 4. Preencher o arquivo `.env`

```bash
# Copie o template:
copy .env.example .env
```

Abra o `.env` em um editor e preencha todos os campos:

```env
OUTLOOK_EMAIL=seu_email@hotmail.com
OUTLOOK_APP_PASSWORD=suasenhadaaplicacaosemespaco

IMAP_HOST=outlook.office365.com
IMAP_PORT=993

SUBJECT_FILTER=Informativo - Aula agendada
SENDER_DOMAIN=timesidiomas

AZURE_CLIENT_ID=cole-aqui-o-id-do-aplicativo
AZURE_CLIENT_SECRET=cole-aqui-o-valor-do-segredo

DURACAO_AULA_MINUTOS=50
SEARCH_WINDOW_DAYS=7

# Opcional: pasta onde ficam o365_token.txt e processed_ids.json (padrão: pasta do script)
# DATA_DIR=/data
```

> **Importante:** Nunca commite o arquivo `.env` em repositórios públicos.

---

## 5. Primeira execução — Device Code Flow

Na primeira vez que rodar o script, ele iniciará o **Device Code Flow** para
autenticar com a Microsoft e obter permissão de criar eventos no seu calendário.

```bash
python main.py
```

O terminal exibirá algo como:

```
2026-06-14 10:00:00 [INFO] times_agendador: Iniciando autenticação via Device Code Flow.
To sign in, use a web browser to open the page https://microsoft.com/devicelogin
and enter the code XXXXXXXXX to authenticate.
```

**Passos:**
1. Abra o navegador em [microsoft.com/devicelogin](https://microsoft.com/devicelogin)
2. Digite o código de 9 letras exibido no terminal
3. Faça login com a mesma conta `@hotmail.com`
4. Autorize as permissões solicitadas (`Calendars.ReadWrite`)
5. Volte ao terminal — o script continuará automaticamente

O token é salvo em `o365_token.txt` na pasta do script (ou em `DATA_DIR`, se
definida). Nas próximas
execuções, o script reutiliza esse token e **não solicita autenticação
novamente** (enquanto o token não expirar, o que pode ser meses).

---

## 6. Estrutura de arquivos

```
times_agendador/
├── main.py               ← ponto de entrada
├── imap_reader.py        ← lê emails via IMAP
├── email_parser.py       ← extrai dados do HTML do email
├── calendar_service.py   ← cria eventos via Microsoft Graph (O365)
├── state_store.py        ← controle de emails já processados
├── models.py             ← dataclass DadosAula
├── .env                  ← suas credenciais (NÃO commitar)
├── .env.example          ← template sem valores reais
├── requirements.txt
├── processed_ids.json    ← criado automaticamente na 1ª execução
└── o365_token.txt        ← criado automaticamente na 1ª autenticação
```

---

## 7. Agendar no Task Scheduler do Windows (a cada 5 minutos)

### 7.1 Abrir o Agendador de Tarefas

Pressione `Win + R`, digite `taskschd.msc` e pressione Enter.

### 7.2 Criar nova tarefa

1. No painel direito, clique em **"Criar Tarefa..."** (não "Criar Tarefa Básica")

### 7.3 Aba "Geral"

- **Nome:** `Times Agendador`
- **Descrição:** `Monitora emails de aula e cria eventos no Outlook Calendar`
- Marque **"Executar estando o usuário conectado ou não"**
- Marque **"Executar com privilégios mais altos"** (necessário para alguns
  ambientes)
- **Configurar para:** `Windows 10`

### 7.4 Aba "Gatilhos"

1. Clique em **"Novo..."**
2. **Iniciar a tarefa:** `Ao iniciar`
3. Marque **"Repetir a tarefa a cada:"** → `5 minutos`
4. **Por uma duração de:** `Indefinidamente`
5. Marque **"Habilitado"**
6. Clique em **OK**

### 7.5 Aba "Ações"

1. Clique em **"Novo..."**
2. **Ação:** `Iniciar um programa`
3. **Programa/script:**
   ```
   C:\Users\semog\projects\times_agendador\.venv\Scripts\python.exe
   ```
   *(Se não usar venv, use o caminho do Python global, ex:*
   *`C:\Users\semog\AppData\Local\Programs\Python\Python311\python.exe`)*
4. **Adicionar argumentos:**
   ```
   main.py
   ```
5. **Iniciar em:**
   ```
   C:\Users\semog\projects\times_agendador
   ```
6. Clique em **OK**

### 7.6 Aba "Condições"

- Desmarque **"Iniciar a tarefa somente se o computador estiver ocioso por"**
- Opcionalmente desmarque **"Interromper se o computador passar para energia
  da bateria"** se usar notebook

### 7.7 Aba "Configurações"

- Marque **"Permitir que a tarefa seja executada sob demanda"**
- Marque **"Se a tarefa em execução não terminar quando solicitado, forçar
  parada"**
- **Se a tarefa já estiver em execução:** `Não iniciar uma nova instância`

### 7.8 Salvar e testar

1. Clique em **OK** e forneça sua senha do Windows se solicitado
2. Para testar imediatamente, clique com o botão direito na tarefa e selecione
   **"Executar"**
3. Verifique o log em **"Histórico"** ou no terminal se executar manualmente

---

## Deploy no Railway

O filesystem do container é efêmero: sem um volume, o token e o
`processed_ids.json` se perdem a cada redeploy e o bot pede autenticação de novo.

1. No serviço, em **Settings → Volumes**, crie um volume com mount path `/data`.
2. Em **Variables**, adicione `DATA_DIR=/data` (além das variáveis do `.env`).
3. Após o deploy, abra o log do serviço. Ele exibirá:
   ```
   To sign in, use a web browser to open the page https://microsoft.com/devicelogin
   and enter the code XXXXXXXXX to authenticate.
   ```
   Autentique com a conta `@hotmail.com` (o código expira em ~15 minutos; se
   expirar, o serviço reinicia e gera outro).
4. No primeiro ciclo aparecerá um **segundo código**, precedido de
   `Consentimento para acesso ao IMAP necessário` — repita o passo 3. Calendário
   (Graph) e IMAP exigem consentimentos separados.

Nos deploys seguintes o log deve mostrar
`Token existente válido. Nenhuma nova autenticação necessária.`

---

## Comportamento e idempotência

- A busca considera emails dos últimos `SEARCH_WINDOW_DAYS` dias (padrão: 7)
  com o assunto configurado, **lidos ou não**. O script não altera a flag de
  lido no Outlook.
- O script **não cria eventos duplicados**: cada email processado tem seu
  `Message-ID` salvo em `processed_ids.json`. Além disso, antes de criar o
  evento, o calendário é consultado; se já existir um evento com o mesmo título
  no mesmo horário, nada é criado.
- Emails cujo agendamento falhou (falha de rede, erro do Graph) **não são
  marcados como processados** e serão tentados novamente no próximo ciclo.
  Emails com formato inválido são registrados no log e não são repetidos.

---

## Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| `IMAP LOGIN failed` | Senha de aplicativo incorreta ou 2FA desativado | Gere nova senha de aplicativo em account.microsoft.com/security |
| `Campo obrigatório não encontrado` | Formato do email mudou | Inspecione o HTML do email e ajuste `email_parser.py` |
| `Falha na autenticação` com Graph | Client ID/Secret incorretos ou permissão faltando | Verifique o registro no Azure e as permissões da API |
| Token expirado | `o365_token.txt` desatualizado | Delete `o365_token.txt` e execute `python main.py` para re-autenticar |
| Tarefa no Scheduler não roda | Caminho do Python incorreto | Execute `where python` no terminal para confirmar o caminho |
