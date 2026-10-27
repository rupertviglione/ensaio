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
Cria/edita `backend/.env`:
```
MONGO_URL="mongodb://localhost:27017"
DB_NAME="ensaio"
CORS_ORIGINS="*"
EMERGENT_LLM_KEY=a-tua-chave-universal-emergent
ELEVENLABS_API_KEY=a-tua-chave-elevenlabs
```
`ELEVENLABS_API_KEY` (https://elevenlabs.io/app/settings/api-keys) é a chave **secreta** `sk_…` (51 caracteres), não o ID da chave. Permissões: **Text to Speech**, **Speech to Text** e **Single-use tokens** (obrigatórias para vozes pt-PT e escuta em tempo real); **Voices → Read/Write** (opcional: a app procura e adiciona vozes pt-PT da biblioteca; sem isso usa uma lista pt-PT verificada). O backend verifica as permissões ao arrancar (`GET /api/eleven/status?refresh=true`) e mostra "Chave ElevenLabs sem permissão para …" com recurso ao motor anterior (OpenAI TTS / reconhecimento do browser). Opcional: `ELEVEN_TTS_MODEL` (por defeito `eleven_multilingual_v2`; `eleven_v3` também suportado). A chave nunca vai para o frontend: o browser recebe apenas tokens Scribe de uso único (`POST /api/stt/token`).
Arranca:
```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 2. Frontend
```bash
cd frontend
yarn install
```
Cria/edita `frontend/.env`:
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
3. **Sala de ensaio**: o microfone abre uma vez e fica aberto (ElevenLabs Scribe v2 Realtime, transcrição palavra a palavra). A IA diz as falas das outras personagens (vozes ElevenLabs pt-PT pré-geradas); a tua fala só termina quando dizes as últimas palavras ou carregas em **Terminei** — nunca por silêncio. Se ficares calado (por defeito 5 s, configurável 3–15 s em "Preparar ensaio"), o apontador diz e mostra as próximas palavras e continua a ouvir-te. Funciona com auscultadores ou colunas (o eco da voz da IA é ignorado). Latências no console do browser (`[ensaio:latência]`, `window.__ensaioLatency`). Podes dizer coisas como *"aí mudámos, agora digo X em vez de Y"* — fica guardado na **Memória** do texto. Pede ajuda com *"texto!"*.
4. **Terminar** → resumo com tudo o que foi diferente do texto, zonas a rever e dicas de memorização.

## Tecnologia
FastAPI + MongoDB + React. IA: Claude Sonnet 5.5 / Haiku 5.5 (avaliação e resumo, chave universal Emergent); ElevenLabs eleven_multilingual_v2 (vozes pt-PT) e Scribe v2 Realtime (escuta); OpenAI gpt-4o-mini-tts e Web Speech apenas como recurso.
