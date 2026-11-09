# Calibração opcional por par Fujifilm/iPhone

Atualização autorizada pelo proprietário em 2026-11-08. Substitui a proibição
anterior do ajuste experimental; mantém o escopo CLI/metadados/FCPXML.

## Convenção e seleção

**Horário corrigido da foto = horário original da foto + offset_seconds.**
Um offset **−2,272 s antecipa** a foto em relação à referência do vídeo; um
offset positivo atrasa. A soma usa `Fraction` no instante UTC antes de selecionar
as fotos cobertas pelas gravações. Os metadados originais e seu fuso permanecem
intactos e aparecem no relatório. A grade de quadros só é aplicada na exportação.

- Omitir `--profile` usa zero e status `uncalibrated`. Nenhuma descoberta
  automática de perfis ocorre e a existência de um arquivo salvo não ativa nada.
- `--profile experimental-minus-2.272 --pair-id meu-par` seleciona o preset
  explicitamente. Seu status é sempre `experimental`, nunca validado de fábrica.
- `--profile profiles/meu-par-v1.profile.json --pair-id meu-par` reutiliza um
  perfil salvo. O identificador precisa coincidir; divergência é erro.
- `pair_id` é um rótulo local escolhido por você para aquele par específico.
  Não representa um modelo inferido, número de série ou autodetecção de hardware.
  Na POC, cada execução usa um par; processe pares diferentes separadamente.

Exemplo: a foto que originalmente ocorre em 12,660 s passa a 10,388 s com o
preset. Se uma foto sair/entrar na cobertura após a correção, a seleção muda.
A tolerância de cobertura é aplicada depois da soma, separadamente da calibração.

## Salvar e reutilizar

Comandos a partir da pasta Python (no Mac, troque o executável por `.venv/bin/python`):

```powershell
.\.venv\Scripts\python.exe -m fujitimeline profile create --pair-id meu-par --preset experimental-minus-2.272 --output profiles\meu-par-v1.profile.json
.\.venv\Scripts\python.exe -m fujitimeline profile inspect --profile profiles\meu-par-v1.profile.json
.\.venv\Scripts\python.exe -m fujitimeline plan --video "C:\Midias\video.mov" --photos "C:\Midias\JPEG" --profile profiles\meu-par-v1.profile.json --pair-id meu-par --report output\sessao.json
```

Para um valor manual diferente, use `profile create --pair-id meu-par --offset=1.5
--output profiles/meu-par-v1.profile.json`. Valores negativos usam, por exemplo,
`--offset=-2.272`. Aceita ponto decimal ou fração racional; qualquer valor criado
manualmente começa `experimental`, mesmo zero. O zero implícito sem perfil é
`uncalibrated`. Arquivos salvos exigem extensão `.profile.json` e criação exclusiva.

## Correspondências para validar

O programa não reconhece visualmente fotos dentro dos vídeos. O usuário precisa
identificar várias correspondências reais, conferir suas datas/fusos e informar
o início e o fim **reais** da sessão (não apenas a região onde as medições coincidem).
O instante de referência é `video_start + video_position_seconds`. Essa posição
é o tempo desde o início da gravação, não timecode absoluto nem tempo da timeline compacta.

Para cada foto, o offset observado é `referência do vídeo − horário da foto`.
Por isso o valor observado terá sinal negativo quando a câmera estiver adiantada.
Escolha pontos perto do início e do fim e, quando possível, também no meio.
Considere a incerteza de localizar uma correspondência em vídeo por quadros.

Formato JSON abaixo é **inteiramente simulado**. Salve suas medições reais em
`calibration-evidence/sessao.evidence.json`, substitua os valores e use
`"synthetic": false` somente se as correspondências forem efetivamente reais e
conferidas. Datas das evidências precisam incluir fuso explícito.

```json
{
  "pair_id": "meu-par",
  "synthetic": true,
  "session_start": "2026-01-01T12:00:00-03:00",
  "session_end": "2026-01-01T12:01:40-03:00",
  "matches": [
    {"photo_id": "foto-1.jpg", "photo_time": "2026-01-01T12:00:12.272-03:00", "video_id": "video.mov", "video_start": "2026-01-01T12:00:00-03:00", "video_position_seconds": "10"},
    {"photo_id": "foto-2.jpg", "photo_time": "2026-01-01T12:00:22.272-03:00", "video_id": "video.mov", "video_start": "2026-01-01T12:00:00-03:00", "video_position_seconds": "20"},
    {"photo_id": "foto-3.jpg", "photo_time": "2026-01-01T12:01:22.272-03:00", "video_id": "video.mov", "video_start": "2026-01-01T12:00:00-03:00", "video_position_seconds": "80"},
    {"photo_id": "foto-4.jpg", "photo_time": "2026-01-01T12:01:32.272-03:00", "video_id": "video.mov", "video_start": "2026-01-01T12:00:00-03:00", "video_position_seconds": "90"}
  ]
}
```

O programa exige `photo_id` distintos e instantes originais distintos; repetir
a mesma foto não conta como novas evidências. IDs podem ser nomes locais sem
caminhos pessoais. Os valores de tempo são mantidos exatos, inclusive quando
informados como strings de frações.

## Validar, recalibrar e considerar deriva

```powershell
.\.venv\Scripts\python.exe -m fujitimeline profile validate --profile profiles\meu-par-v1.profile.json --evidence calibration-evidence\sessao.evidence.json --output profiles\meu-par-v2.profile.json
.\.venv\Scripts\python.exe -m fujitimeline profile recalibrate --profile profiles\meu-par-v2.profile.json --evidence calibration-evidence\nova-sessao.evidence.json --output profiles\meu-par-v3.profile.json
```

`validate` verifica o offset existente. `recalibrate` estima um novo offset pela
mediana dos offsets observados e aplica as mesmas verificações. Cada operação
salva outra revisão com `previous_digest` (SHA-256 do conteúdo normalizado do
perfil anterior), mantendo o arquivo anterior. Isso é rastreabilidade, não
assinatura criptográfica nem garantia de origem das correspondências.

Critérios conservadores desta POC, documentados e não equivalentes a uma
certificação de precisão dos equipamentos:

1. Ao menos quatro fotos distintas: duas nos primeiros 20% da sessão e duas nos
   últimos 20%, com referências dentro de seus limites.
2. Todos os resíduos absolutos após aplicar o offset devem ser menores ou iguais
   a `--residual-tolerance` (padrão **0,1 s**).
3. A diferença entre medianas do fim/início e a deriva estimada por regressão
   linear dos offsets ao longo da sessão devem ser menores ou iguais a
   `--drift-tolerance` (padrão **0,05 s**). A regressão informa a mudança estimada
   de offset durante toda a sessão, não uma correção automaticamente aplicada.
4. Dados declarados `synthetic: true` nunca promovem o perfil a `validated`.

As duas tolerâncias aceitam valores positivos até 1 s. Aumentá-las reduz a
precisão exigida e fica registrado na revisão. Se qualquer critério falhar,
o arquivo novo é salvo como **experimental**, com motivos, e a CLI retorna
código **2**. Falhas estruturais no JSON não criam revisão. Somente uma
verificação consistente retorna status **validated** e código **0**.

Ao carregar um perfil `validated`, o programa recalcula a validação a partir das
evidências armazenadas. Alterar apenas o status ou offset não basta para obter
esse status. As correspondências e identidade do par são declaradas pelo
usuário: o software não atesta sozinho a veracidade das imagens ou da sessão.
Nenhum perfil de aparelhos reais foi validado nesta entrega.

Um perfil validado se refere às condições/sessão medidas. Mudança de relógio,
fuso, aparelho ou sessão longa pede nova avaliação. Deriva detectada não é
compensada nesta versão; não se introduz um fator linear escondido na timeline.

## Relatório e privacidade

`calibration` contém nome, `pair_id`, offset racional, status, revisão,
evidências e avaliação quando presentes. `photo_timings` contém, para **todas**
as fotos lidas: horário original completo, `corrected_utc` racional,
`corrected_time` legível no offset de fuso original, perfil/offset/status e
`selected`. `photos[].source_offset` passa a representar o tempo corrigido
dentro do vídeo; o horário original continua em `media.captured`.

Frações não terminantes têm sufixo racional em `corrected_time`; `corrected_utc`
sempre é a representação exata. O relatório FCPXML registra à parte os ajustes
de quadros, que não alteram os valores originais/corrigidos.

`profiles/`, `calibration-evidence/`, `*.profile.json`, `*.evidence.json` e
`output/` são ignorados pelo Git. Não envie perfis pessoais/evidências/mídias no
checkpoint. Somente código, documentação e fixtures simuladas dos testes são versionados.
