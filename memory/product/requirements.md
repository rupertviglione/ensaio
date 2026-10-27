# Requirements: Ensaio (treino de texto para actores)

## Core Value
Quero criar uma aplicação para treinar e ajudar a decorar texto. Os utilizadores são actores. Para já tem que funcionar para mim.

## Personas & Roles
Actores. Para já, um único utilizador (eu).

## Features
- Interface simples e clara para carregar o texto que se quer trabalhar. Aceita colar texto e ficheiros PDF ou Word.
- Agente de IA que simule uma voz para cada papel envolvido. A IA irá fazer as vozes de todas as personagens que não a do actor. Vozes diferentes por personagem, em português de Portugal.
- Simultaneamente deve verificar se o texto está a ser bem dito pelo actor, de acordo com as instruções dadas pelo actor. Exemplo: quero que interrompas apenas se houver algum erro grave, salto grande, mas que deixes passar pequenas trocas, enganos, ou repetições.
- Interacção por voz em tempo real; também quero poder escrever.
- No final de cada momento, quando o actor entende terminar, existe um resumo detalhado da sua prestação. A IA pode e deve sugerir zonas a rever, ajudar no processo de memorização. No resumo tudo o que foi diferente do texto fornecido deve ser dito.
- A IA deve ter alguma memória sobre cada texto. Exemplo: o actor diz "Ah, aí entretanto mudámos nos ensaios e eu passei mesmo a dizer "X" em vez de "Y"" a IA deve memorizar essa informação para as próximas vezes em que o mesmo texto é trabalhado.

## UI/UX Rules
Interface e textos em português de Portugal.

## Integrations
IA com a chave universal Emergent: voz (TTS e STT) e modelo de texto (Claude Sonnet 5.5), vozes distintas por personagem.

## Edge Cases
Para já convém que funcione num ambiente local com alguma facilidade, para eu conseguir experimentar e ir aprofundando a coisa. Primeiro testo aqui online e depois descarrego. Quero ficar com os ficheiros para download, com tudo funcional (incluindo instruções simples para correr localmente).

## Round 2 (feedback do utilizador, verbatim)
Ora tem algumas falhas já detectadas. Tem que ser muito mais fluido. Em textos por exemplo em que se fala mal "tipo, prá em vez de para" etc ele tende a reconhecer o que quer que digas como a palavra correcta e depois quer corrigir, mas não distingue quando dizes bem. Também me pareceu ouvir mal, talvez seja o modo rigoroso que está tão rigoroso que até coisas que não são erros são tidos como erros, mas não pode estar sempre sempre a parar. as vozes são muito pouco naturais... A openAi não funcionaria? Não sei... Qualquer coisa mais natural dava jeito. Acima de tudo o tempo entre a fala da IA e o do utilizador tem que ser muito menor. O tempo a avaliar a fala tem que ser muito menor. Bater texto tem que ser uma coisa rápida e ágil se cada merdinha demora imenso, não dá.

## Round 3 (verbatim)
faz todas as melhorias, sim.
Melhorias aprovadas: (1) vozes nativas de Portugal da biblioteca ElevenLabs para cada personagem; (2) mostrar as alterações acordadas da memória directamente no guião; (3) ensaiar só as zonas a rever apontadas no resumo; (4) editar falas e personagens à mão depois de carregar o texto.

## Round 4 (verbatim)
Ora o que está a acontecer, várias vozes brasileiras, ainda mais robóticas do que antes. Logo o anotador é uma voz robótica brasileira. Os actores IA demoram imenso a falar. Demora imenso tempo a processar e a verificar aquilo que nós actores reais dizemos. Fica preso em loops a dizer que eu disse um pedaço anterior do texto em loop, que não disse, em vez de reconhecer aquilo que realmente foi dito. Por vezes é muito rápido a assumir que terminámos de falar, basta uma pausa um pouco mais expressiva, ou estar a fraquejar mais a memória e corta logo dizendo que ficámos pela metade, mas em vários casos eu queria continuar e não consegui porque fui cortado. A verificação do que o actor real diz tem que ser muito mas muito mais fluida. Quase nem existir nenhuma paragem para verificar, deveria ser mesmo fluido, como bater texto com uma pessoa, sem ter que se esperar para que o actor de IA siga com o texto quando o ouve correctamente, ou dentro de um nível razoável de dúvida, ou de erro real do utilizador.
