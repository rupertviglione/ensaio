# PRD — Ensaio (treino de texto para actores)

## Problema original
App para treinar e decorar texto (actores, utilizador único). Carregar texto (colar/PDF/Word); IA dá voz PT-PT distinta a cada personagem excepto a do actor; verifica a fala segundo as instruções do actor; voz em tempo real + escrita; resumo detalhado no fim (todas as diferenças, zonas a rever, ajuda a memorizar); memória por texto das alterações acordadas. UI em PT-PT. Correr localmente com instruções simples.

## Arquitectura
- FastAPI + MongoDB (`scripts`, `sessions`) — /app/backend/server.py
- React (Biblioteca, Novo texto, Texto [Guião/Vozes/Memória/Ensaios + Preparar ensaio], Sala de ensaio, Resumo)
- IA (chave universal Emergent): Claude Sonnet 5.5 (parse de fallback, avaliação de falas, notas, resumo), gpt-4o-mini-tts com instruções PT-PT (cache em disco backend/tts_cache), Whisper-1 (language=pt)
- Gravação no browser com detecção de silêncio (MediaRecorder + AnalyserNode)

## Implementado (2026-10-27)
- Parse heurístico (NOME: fala / nome em linha própria / rubricas) com fallback LLM por blocos
- Extracção PDF/DOCX/TXT; texto de demonstração "A Espera"
- Vozes por personagem editáveis + descrição de carácter + pré-visualização
- Ensaio: IA contracena, pré-carrega áudio, ouve/transcreve, avalia (line/note/help/other), interrompe segundo instruções, apontador fala o feedback, repetir/continuar, dica, esconder texto, pausa, saltar, modo só escrita, retomar ensaio em curso
- Memória: notas manuais, detectadas na fala, ou a partir das diferenças do resumo
- Resumo: pontuação, síntese, estatísticas, todas as diferenças, zonas a rever, dicas, pontos fortes
- README com instruções locais

## Round 2 (2026-10-27) — fluidez e vozes
- Verificação local instantânea (difflib + normalização coloquial prá/para, tá/está, números; tolerância fuzzy); IA (claude-haiku-5-5) só em casos duvidosos, negações, notas/pedidos ou linhas com alterações na memória
- Níveis: grave / rigor / nunca (strictness na sessão); rigor ignora pronúncia e coloquialismos
- /voice-turn: STT (Whisper com a fala esperada como pista) + avaliação numa só chamada; silêncio 0,9 s
- ElevenLabs eleven_flash_v2_5 (~0,3 s) com fallback OpenAI; pré-geração de todo o áudio ao criar a sessão; dedupe/cache; timeouts no gpt-4o-mini-tts
- A chave ElevenLabs não tem a permissão voices_read → usa as vozes pré-definidas (multilingue); Voice ID manual possível

## Round 4 (2026-10-27) — fluidez real e vozes PT-PT
- Vozes: OpenAI gpt-4o-mini-tts por defeito (personagens e apontador); vozes ElevenLabs pré-definidas (sotaque BR) removidas; ElevenLabs só com Voice ID manual ou vozes nativas PT-PT (requer permissão voices_read)
- STT: sem a fala esperada no prompt (causava loops/alucinações); corrida gpt-4o-mini-transcribe vs whisper-1 (primeiro a responder)
- Endpointing por conteúdo: reconhecimento ao vivo no browser (Web Speech pt-PT) + sondas Whisper a cada pausa (450 ms) via /sessions/{id}/probe; a fala só termina quando o fim da fala é reconhecido (ou 3,2 s de silêncio / clique); transcrição ao vivo
- Apontador com voz opcional (toggle)
- Correcções da iteração 3 (rename no-op, deixa com texto alterado, blur imediato, reload no resumo, aviso no editor)

## Round 5 / Phase 1 (2026-10-27) — motor de ensaio: vozes pt-PT, tempo real, pausas
- Chave ElevenLabs (backend/.env) verificada: TTS ✓, STT ✓, single-use token realtime_scribe ✓; Voices Read ✗ e Voices Write ✗ (401 missing_permissions) → lista pt-PT verificada (seed) + aviso REQ-26; quando a permissão existir, `GET /api/eleven/status?refresh=true` (ou reinício) procura na biblioteca partilhada (language=pt, accent european/portugal, locale pt-PT), adiciona à conta e migra
- Novo módulo backend/eleven.py: estado/permissões, TTS (eleven_multilingual_v2, language_code pt, sem truncar: divide em frases ≤2400 car. com previous/next_text e concatena MP3), retry 429/409 (limite 3 pedidos simultâneos), token Scribe, curadoria de vozes
- Vozes pt-PT (metadata "Portuguese · European"): Marta bBNhdwrIjl4fcVYiRbT2, Daniela IZipF5JhqPlWzpduTV0E, Benedita NkpT2jezTenCDRKHkWiX, Mariza zKjRewuiqTkXNUVAMwat (F); Diogo RlGHmE2fztwdBDat0jYf, Vasco pjqwOzrEUZ3n3m4rMWWL, Duarte 5tqq6ewvJtcNtaffrqUJ, Dinis RROBrqjHiRb8zmRgGV11, Paulo aLFUti4k8YKvtQGXv0UO (M); apontador Joana nJ5NFqyKb8kn9JBPmo6i (F). Personagens migradas para vozes distintas
- TTS: ElevenLabs com 1 nova tentativa → OpenAI só em falha (registado em log "TTS FALLBACK" + /api/eleven/status stats); cabeçalhos X-TTS-Provider/X-TTS-Voice; cache el_/oa_ em disco; pré-geração de todas as falas IA + dicas iniciais do apontador ao criar a sessão
- Escuta: Scribe v2 Realtime no browser (WebSocket, token de uso único via POST /api/stt/token, commit manual, PCM 16 kHz em blocos de 100 ms via AudioWorklet), microfone aberto toda a sessão, religação mantendo o texto; recurso Web Speech
- Fim da fala: só por conteúdo (últimas palavras, isComplete local) ou "Terminei"; removidos o fim por 3,2 s de silêncio, as sondas Whisper e /sessions/{id}/probe; um só caminho de conclusão
- Veredicto local (porta de local_match/fast_verdict) → próxima fala IA arranca logo; verificação do servidor em paralelo (se o servidor interromper, interrompe como antes; grave/rigor/nunca inalterados)
- Dicas: após X s de silêncio (sessão hint_seconds 3–15, defeito 5, validado no backend) o apontador diz e mostra as próximas 3 palavras e continua a ouvir; repete; "texto!" pede dica imediata
- Eco (colunas): texto que coincide com a fala IA/dica a tocar é ignorado; só palavras dos últimos 2,5 s da fala IA contam como início antecipado do actor
- Instrumentação: console `[ensaio:latência]` e `window.__ensaioLatency` (fim do actor → início do áudio IA; fim do áudio IA → captura activa)
- /api/openapi.json e /api/docs

## Backlog
- P1: aplicar notas da memória visualmente no guião (texto alterado em linha)
- P1: editar manualmente falas/personagens após o parse
- P2: ensaiar só as zonas a rever; histórico de evolução por texto; streaming de áudio para menor latência
- P2: vozes ElevenLabs com sotaque PT-PT nativo (opcional)
