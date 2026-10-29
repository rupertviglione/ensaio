# Ensaio — treino de texto para actores

Aplicação para ensaiar e decorar texto: a IA dá voz (PT-PT) a todas as personagens excepto a tua, ouve-te, corrige-te segundo as tuas instruções, guarda alterações acordadas (memória do texto) e faz um resumo detalhado no fim.

## Correr localmente

Requisitos: **Python 3.11+**, **Node 18+ com Yarn**, **MongoDB** (local, ex. `docker run -d -p 27017:27017 mongo`).

### 1. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
```
Copia `backend/.env.example` para `backend/.env` e preenche:
```
MONGO_URL="mongodb://localhost:27017"
DB_NAME="ensaio"
CORS_ORIGINS="*"
EMERGENT_LLM_KEY=a-tua-chave-universal-emergent
DEEPGRAM_API_KEY=a-tua-chave-deepgram
GEMINI_API_KEY=a-tua-chave-gemini-ai-studio
ELEVENLABS_API_KEY=
```
- `DEEPGRAM_API_KEY` (https://console.deepgram.com → API Keys, crédito grátis): escuta principal (nova-3, pt-PT, streaming). O browser recebe só um token temporário (`POST /api/stt/deepgram-token`, 120 s).
- `GEMINI_API_KEY` (https://aistudio.google.com/apikey, formato `AQ.…` ou `AIza…`): escuta de reserva (Gemini Live `gemini-3.5-transcribe-live`). O browser recebe só um token efémero de uso único (`POST /api/stt/gemini-token`).
- Sem chave Deepgram/Gemini a app mostra "Falta a chave <motor> no ficheiro backend/.env" e passa ao motor seguinte (Deepgram → Gemini → reconhecimento do browser).
- Vozes: Microsoft Edge pt-PT (`edge-tts`, grátis, sem chave). Reserva: OpenAI gpt-4o-mini-tts via `EMERGENT_LLM_KEY` (registado no log como `TTS FALLBACK`).
- `ELEVENLABS_API_KEY` é opcional (gasta créditos): só é usada se escolheres manualmente "ElevenLabs" para uma personagem no separador Vozes. A escuta ElevenLabs Scribe também é opcional: no browser, `localStorage.setItem("ensaio-stt","scribe")`.
- Opcional: `DEEPGRAM_MODEL` (defeito `nova-3`), `GEMINI_LIVE_MODEL` (defeito `gemini-3.5-transcribe-live`).
- Nenhuma chave vai para o browser.
Arranca:
```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 2. Frontend
```bash
cd frontend
yarn install
```
Copia `frontend/.env.example` para `frontend/.env`:
```
REACT_APP_BACKEND_URL=http://localhost:8001
```
Arranca:
```bash
yarn start
```
Abre http://localhost:3000 (o microfone funciona em `localhost` sem HTTPS). Usa o Chrome ou Edge.

## Como usar
1. **Carregar texto**: cola o texto ou carrega PDF / Word (.docx) / .txt. Formato ideal: `NOME: fala` ou nome numa linha e a fala por baixo; rubricas entre parêntesis.
2. No texto: escolhe **o teu papel**, escreve **como queres ser corrigido**, ajusta **vozes** por personagem, e podes clicar "Começar aqui" numa fala.
3. **Sala de ensaio**: o microfone abre uma vez e fica aberto (motor indicado no ecrã: "Escuta: Deepgram" / "Escuta: Gemini" / "Escuta do browser"; troca automática sem perder palavras). As tuas falas seguidas (mesmo com rubricas pelo meio) são um só bloco: a app ouve-te através das pausas e só avalia no fim do bloco; a transcrição recomeça vazia em cada bloco. O que soa como o texto conta como o texto (comparação fonética pt-PT); as diferenças duvidosas são confirmadas em segundo plano e o resumo final só mostra diferenças reais. A IA diz as falas das outras personagens (vozes Edge pt-PT pré-geradas); o bloco só termina quando dizes as últimas palavras ou carregas em **Terminei** — nunca por silêncio. Se ficares calado (por defeito 5 s, configurável 3–15 s em "Preparar ensaio"), o apontador diz e mostra as próximas palavras e continua a ouvir-te. Funciona com auscultadores ou colunas (o eco da voz da IA é ignorado). Latências no console do browser (`[ensaio:latência]`, `window.__ensaioLatency`). Podes dizer coisas como *"aí mudámos, agora digo X em vez de Y"* — fica guardado na **Memória** do texto. Pede ajuda com *"texto!"*.
4. **Durante o ensaio**: clica numa fala do texto à direita para **Saltar para aqui** ou **Editar** (texto, personagem com um clique, "Cortada" — fica guardado no texto). **Modo Saltar** (no "Preparar ensaio" ou tecla S): só se ouve a deixa antes de cada fala tua. Atalhos: → seguinte, ← anterior, Espaço pausa, Enter Terminei, H dica, E editar, S Modo Saltar, T mostrar/esconder texto, ? lista. No editor do Guião há os tipos Fala / Rubrica / Texto não pertencente (números de página, cabeçalhos — ignorados no ensaio) / Cortada, e selecção múltipla.
5. **Terminar** → resumo com tudo o que foi diferente do texto, zonas a rever e dicas de memorização.

## Tecnologia
FastAPI + MongoDB + React. IA: Claude Sonnet 5.5 / Haiku 5.5 (avaliação, confirmação de diferenças e resumo, chave universal Emergent); escuta Deepgram nova-3 (principal), Gemini Live (reserva), Web Speech (último recurso); vozes Microsoft Edge pt-PT (edge-tts), OpenAI gpt-4o-mini-tts como reserva, ElevenLabs opcional.
Teste automático de leitura correcta (áudio sintetizado → STT real → relatório): `cd backend && python tests/readthrough_phase2.py deepgram MARTA` (ou `gemini JOÃO`).
Teste no browser real (Chromium, UI completa, microfone simulado): `cd tests/e2e && python browser_readthrough.py fakemic` e `python browser_readthrough.py read deepgram|gemini clean|distorted "A Espera" MARTA`.

**Definições** (cabeçalho → Definições): chaves ElevenLabs, Deepgram e Gemini podem ser coladas na app; são validadas, guardadas no servidor (MongoDB) e têm prioridade sobre o `backend/.env`. O browser só vê os últimos 4 caracteres. Com uma chave ElevenLabs válida (Text to Speech), o ElevenLabs passa a ser a voz principal (uma voz pt-PT diferente por personagem) e o Edge fica como reserva.
**Escuta Deepgram**: o browser liga-se a `wss://<backend>/api/stt/deepgram` (proxy no backend, a chave nunca sai do servidor); se o proxy falhar, liga directamente com token temporário.
**Pronúncia** (separador por texto): palavras/nomes escritos na forma estrangeira são detectados pelo Claude (língua, grafia para a voz, variantes que a escuta pode ouvir); editáveis. Aplicadas às vozes, às keyterms do Deepgram e à comparação. Palavras já escritas em português ("Nova Iorque") dizem-se em português.
