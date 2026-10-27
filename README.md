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
`ELEVENLABS_API_KEY` é opcional (obtém em https://elevenlabs.io/app/settings/api-keys). Com ela, as personagens usam vozes ElevenLabs (mais naturais e rápidas); sem ela, usa-se a OpenAI. Para poderes escolher vozes PT-PT da biblioteca na app, dá à chave a permissão **Voices → Read** (e **Write** para as adicionar automaticamente); sem essa permissão podes colar um Voice ID em "Vozes". Nunca coloques chaves no frontend.
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
3. **Sala de ensaio**: a IA diz as falas das outras personagens; quando é a tua vez, fala (a gravação pára sozinha quando te calas) ou escreve. Podes dizer coisas como *"aí mudámos, agora digo X em vez de Y"* — fica guardado na **Memória** do texto. Pede ajuda com *"texto!"*.
4. **Terminar** → resumo com tudo o que foi diferente do texto, zonas a rever e dicas de memorização.

## Tecnologia
FastAPI + MongoDB + React. IA: Claude Sonnet 5.5 (avaliação e resumo), OpenAI gpt-4o-mini-tts (vozes), Whisper (reconhecimento de voz) — via chave universal Emergent.
