# Exportação para DaVinci Resolve — experimental

Na interface, escolha **DaVinci Resolve (experimental)** em **Editor de destino**.
A saída continua `.fcpxml`, no perfil 1.10 com biblioteca/evento/projeto e mídias
originais. CLI: acrescente `--target resolve` ao comando `export` ou `demo`.
Final Cut Pro continua sendo o padrão e usa 1.14.

No Resolve, abra um projeto e use **File > Import > Timeline** para selecionar o
FCPXML. Se necessário, relacione novamente os arquivos de mídia nas pastas do seu
computador. Confira taxa da timeline, enquadramento das fotos, áudio original e
primeiro/último disparo. Não aplique sincronização automática ou retiming adicional
antes de comparar. O XML não contém os vídeos nem as fotografias.

Validação desta entrega: 90 testes Python; comparação dos recursos, tempos,
faixas e origem de fonte entre os dois perfis; caso real validado na DTD Apple
1.10. Resolve não está instalado no Mac usado no teste: importação e resultado
visual ainda não estão validados. A versão mínima exata do Resolve não foi
certificada. Se o editor recusar o arquivo, registre a versão e o aviso completo.

## Precisão da sincronização

A correção de importação da câmera de ação considera timecode SMPTE/drop-frame e
FPS racional de fonte, separadamente do FPS do projeto. Ela não recupera centésimos
ausentes das fotos. Nos arquivos X-H2S examinados, tanto JPEGs quanto RAFs do cartão
não apresentaram SubSecTimeOriginal, nos modos testados. Isso não ocorreu nos JPEGs
X100VI dos testes anteriores. Não usar uma calibração de um par no outro sem conferir.

O protótipo de detectar picos do áudio foi feito fora do aplicativo e ainda NÃO
faz parte desta versão. Não anunciar sincronização automática por clique.
