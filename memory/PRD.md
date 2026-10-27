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

## Backlog
- P1: aplicar notas da memória visualmente no guião (texto alterado em linha)
- P1: editar manualmente falas/personagens após o parse
- P2: ensaiar só as zonas a rever; histórico de evolução por texto; streaming de áudio para menor latência
- P2: vozes ElevenLabs com sotaque PT-PT nativo (opcional)
