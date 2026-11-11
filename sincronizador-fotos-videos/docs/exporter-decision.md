# Decisão de exportação — 2026-11-08

Pesquisa realizada antes da implementação do exportador, com inspeção dos
repositórios e do código do pacote instalado. Este documento registra uma
decisão para a prova de conceito; não afirma validação de importação no Final Cut.

## Opções verificadas

| Opção | Evidência observada | Decisão |
|---|---|---|
| OpenTimelineIO + `otio-fcpx-xml-adapter` | Modelo de timeline e adaptador Python separado; suporta múltiplas faixas de vídeo e áudio. Emite FCPXML 1.8. | Escolhido, com versões fixadas e ajustes locais. |
| `salimfadhley/steele_fcpxml` | Biblioteca Python GPL-3; specs públicas com lista linear de clips/gaps e marcadores. Writer usa FCPXML 1.9 e sondagem dos vídeos. | A API examinada não oferece as faixas sobrepostas de fotos/WAV necessárias; exigiria expansão maior. |
| `ChatOctopus/timeline` | Exporta FCPXML, xmeml e OTIO, mas é um pacote ESM/Node.js. | Acrescentaria runtime e integração fora do Python. |
| XML próprio completo | Controle de cada elemento, mas exigiria assumir toda a semântica e manutenção do formato. | Não adotado. |

Fontes primárias:

- [Adaptador OTIO: recursos e limitações](https://github.com/OpenTimelineIO/otio-fcpx-xml-adapter).
- [Código do adaptador](https://github.com/OpenTimelineIO/otio-fcpx-xml-adapter/blob/main/src/otio_fcpx_xml_adapter/fcpx_xml.py).
- [steele_fcpxml](https://github.com/salimfadhley/steele_fcpxml) e
  [specs de timeline](https://github.com/salimfadhley/steele_fcpxml/blob/main/src/steele_fcpxml/specs.py).
- [ChatOctopus/timeline](https://github.com/ChatOctopus/timeline).
- [Apple: DTD e semântica dos tempos](https://developer.apple.com/documentation/professional-video-applications/document-type-definition).
- [FFprobe: documentação no repositório FFmpeg](https://github.com/FFmpeg/FFmpeg/blob/master/doc/ffprobe.texi).
- [ExifTool: tags EXIF](https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Exif.pm).

## Escolha e limites

Instalados e fixados `opentimelineio==0.18.1` e
`otio-fcpx-xml-adapter==1.0.0`. O branch main pesquisado já declara outra versão;
o projeto depende explicitamente da versão efetivamente testada, não de main.
Não confundir `fcpx_xml` com o adaptador `fcp_xml` para Final Cut 7/xmeml.

O adaptador controla o documento, recursos, IDs, sequência, spine e conexão das
faixas. `FujiAdapter` estende sua classe `FcpxOtio` por hooks internos. Isso evita
reimplementar o formato inteiro, mas cria acoplamento à versão fixada. Um upgrade
exige revisar os hooks e repetir os testes de estrutura e importação.

Correções limitadas, motivadas pelo código examinado:

- Formatos com dimensões explícitas; JPEG como imagem estática e duração editável.
- Tempos racionais e busca de clip pai sem truncar FPS fracionário para inteiro.
- `asset-clip` para preservar áudio/vídeo da fonte e para disparos WAV.
- Flags/canais/taxa do áudio obtidos dos metadados.
- Busca de assets por igualdade, evitando interpolar aspas de nomes em XPath.
- Omissão de clips auxiliares do browser: o projeto referencia os recursos
  diretamente, sem entradas extras de duração zero para fotografias.
- Dados de formato já conhecidos evitam o FFprobe adicional interno do adaptador,
  que tem conversão frágil de file URI no Windows.

Os cálculos centrais usam `Fraction`. OTIO utiliza doubles em `RationalTime`;
posições exatas são conservadas também em metadados próprios e no relatório,
e a serialização final usa segundos racionais. A cópia de exportação respeita
uma grade explícita de quadros. Não promete precisão visual inferior a um quadro.

O adaptador não oferece cobertura completa de efeitos, transições ou retiming.
Nenhum desses recursos faz parte desta POC. Assets de taxas mistas/VFR e
HEVC/HDR/rotação de iPhone precisam de validação específica no editor.
O XML referencia originais por file URI; relink no Mac continua necessário
quando os caminhos foram gerados no Windows.

A Apple esclarece que conformidade com a DTD é necessária, mas não suficiente
para importação: valores semanticamente inválidos ainda podem ser recusados.
Por isso os testes Python não substituem a prova de importação no Final Cut.

## Verificação local desta entrega

O XML de demonstração foi validado com `lxml.etree.DTD` usando uma
[cópia da DTD Apple 1.8 mantida pelo projeto ButterCut](https://github.com/barefootford/buttercut/blob/main/dtd/FCPXMLv1_8.dtd)
(cabeçalho Apple 2011–2017). A DTD foi lida em memória; não é distribuída neste
projeto. Esta checagem adicional não faz parte dos testes offline e não implica
que o Final Cut Pro tenha sido executado. A validação final deve usar a DTD
obtida da Apple e a versão do editor no Mac de destino.


## Correção de formatos verticais e taxas mistas — 2026-11-11

O gerador nomeava apenas 1920x1080 a 30 fps. Agora formatos não padronizados
usam FFVideoFormatCustom. Formatos de fonte incluem o FPS racional da mídia
na chave de reutilização; o projeto mantém sua grade explicitamente escolhida.
Assim, um vídeo 1080x1920 a 30000/1001 não é declarado como fonte 30 fps.
Recursos exclusivamente de áudio não recebem formato de vídeo. Nenhum timestamp
de captura, correção de sincronização ou arquivo de mídia foi alterado.

82 testes passaram. O caso real testevacca2 foi reexportado pelo gerador usando
os tempos do JSON original e passou na DTD Apple 1.8. A importação real não foi
confirmada: o acesso ao Final Cut terminou em timeout em duas tentativas.


## Validação real complementar — 11/11/2026

A tentativa anterior com FFVideoFormatCustom não corrigiu a importação.
Uma referência exportada pelo próprio Final Cut mostrou formato vertical sem
name, com dimensões/frameDuration/colorSpace explícitos. O segundo erro era
origem de mídia: o vídeo DJI Mimo tem timecode embutido 08:30:32;19 (drop-frame),
embora start_time do FFprobe seja zero. O leitor agora calcula essa origem
SMPTE separadamente do horário de captura. Âncoras são alinhadas à grade do
projeto após soma da origem. As posições podem variar até um quadro pela
combinação de arredondamentos; os timestamps e o plano exato não são alterados.

A saída do adaptador é normalizada para FCPXML 1.14 com media-rep e
videoSources. O caso real importou sem avisos: vídeo, quatro fotos e quatro
sons visíveis na timeline. Teste não comprova sincronização visual dos disparos.
