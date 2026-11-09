# Checkpoint de desenvolvimento — 2026-11-08

## Origem e conteúdo

- Raiz Git local: pasta `New project`; código em `sincronizador-fotos-videos/`.
- Branch de trabalho: `codex/fujitimeline`.
- Antes deste checkpoint, não havia commits nem remotos, nem outros projetos
  nessa raiz. Mantida a estrutura original; nenhum histórico foi reescrito.
- Checkpoint inicial preservado: `b10287d24d0cb3d52c64687897ccc602a110c453`.
- Publicação autorizada em repositório privado `vsardou/FujiTimeline`.
- Versionados somente Python, testes, documentação, `pyproject.toml` e regras
  de exclusão. Ambientes, caches, logs, saídas, segredos e mídias ficam locais.

## Implementado no checkpoint inicial

Leitura somente por metadados via FFprobe/ExifTool, tempos racionais e fusos
explícitos, seleção de JPEGs, concatenação cronológica dos vídeos, tolerância
configurável 0–60 s, fotos independentes em `until_next`/`fixed`, WAV de disparo
opcional e exportação FCPXML 1.8 com o adaptador OpenTimelineIO fixado.

O JSON conserva os instantes exatos. A edição exportada usa a grade de quadros
escolhida, limita a cauda de vídeos a quadros completos e registra diferenças.
Esse commit inicial não aplicava correção de −2,272 s. A restrição foi
substituída por autorização explícita do proprietário na continuação abaixo.
O commit original permanece disponível, sem reescrita de histórico.

## Continuação autorizada: calibração opcional

- Perfis por identificador do par, sem inventar modelos de aparelhos.
- Zero é padrão; o preset `experimental-minus-2.272` exige seleção explícita.
- Convenção: horário corrigido = original + offset; offset negativo antecipa.
- Correção exata antes da seleção; mídia e CaptureTime originais preservados.
- Perfis salvos e reutilizados localmente. Validação/recalibração escreve nova
  revisão e digest do perfil anterior; nenhuma revisão anterior é sobrescrita.
- Validação exige ao menos quatro fotos distintas, duas no primeiro quinto e
  duas no último quinto da sessão, resíduos dentro da tolerância e avaliação de
  deriva por grupos e regressão. Dados declarados simulados não validam perfis reais.
- Relatório contém perfil/status/offset/revisão e horários originais/corrigidos,
  inclusive para fotos excluídas após a correção. Perfis/evidências ficam fora do Git.
- **52 testes aprovados** no Windows. Nenhum perfil de aparelhos reais foi
  validado nesta entrega; `validated` em testes refere-se somente às fixtures.
- Guia completo: [calibration.md](calibration.md). Sem GUI ou integração Drive.

## Evidência de verificação

- Windows, Python 3.12.4: `python -m pytest -q` — **32 passed** no checkpoint inicial.
- Caso exigido: vídeo 24,398 s; fotos 12,660 / 16,880 / 19,830 / 23,420 s.
- Dependências instaladas sem conflitos (`pip check`) na entrega inicial.
- Na entrega inicial, XMLs simulados dos dois modos, em 30 e 30000/1001 FPS,
  com múltiplos vídeos e WAV, passaram pela cópia Apple DTD 1.8 consultada no
  repositório ButterCut. Isso não comprova importação no Final Cut Pro.
- Os testes automatizados usam metadados simulados e mocks dos executáveis.
  Os testes de preservação usam arquivos fictícios e conferem bytes e mtime.

## Pendências e próximo passo

1. Disponibilizar FFprobe e ExifTool (não encontrados no PATH da sessão de
   preparação); executar `plan` com as mídias originais. Não impor os tempos
   simulados às mídias reais. Confirmar tag selecionada, fuso e subsequundos.
   Se usar calibração, reunir correspondências reais no início/fim da sessão;
   o preset −2,272 s permanece experimental até essa verificação.
2. Gerar XML real e validar contra a DTD oficial da Apple da versão 1.8.
3. No Mac, executar instalação/testes e importar XML no Final Cut Pro.
   Conferir relink, duração, faixas, áudio original, disparos, rotação e HDR.
4. Validar vídeos VFR/taxas mistas; os formatos de assets da POC usam o FPS do
   projeto. Há acoplamento a hooks internos do adaptador, detalhado na decisão.
5. Melhorias posteriores devem permanecer em commits pequenos, na branch de
   trabalho; nenhum merge automático ou publicação de mídias.

## Revisão em outra conversa

Fornecer a URL privada, a branch e o SHA entregues no chat. Pedir leitura do
README da raiz, deste documento e da decisão do exportador antes de alterar
código. O acesso pela conexão GitHub deve ser verificado separadamente; se
recusado, o proprietário seleciona FujiTimeline nas permissões da conexão.
Nunca compartilhar tokens ou arquivos de autenticação no repositório/chat.

## Atualização — interface autorizada em 09/11/2026

A solicitação de interface substitui a antiga restrição de escopo somente CLI.
GUI nativa Tkinter, serviço desktop separado, lançador Windows, correção editável
em segundos ou HH:MM:SS (vírgula/ponto), prévia, perfis e exportação sem sobrescrita.
CLI e ausência de integração Drive preservadas. Metadados originais intactos.
68 testes passaram; smoke test da GUI com mídias reais passou (4 fotos,
primeira em 10,458 s com offset manual experimental −2,202 s).
O usuário confirmou importação/relink no Final Cut do XML anterior com zero.
FFprobe e ExifTool estão instalados nesta máquina; as pendências antigas de
instalação/primeira exportação Windows estão concluídas. Não confundir esse
resultado com validação visual dos offsets ou certificação do exportador.
Próximos testes: ergonomia dos campos/seletores pelo usuário, macOS, pastas grandes,
HDR/rotação/VFR, som de disparo e sincronização visual em vários pontos da sessão.
