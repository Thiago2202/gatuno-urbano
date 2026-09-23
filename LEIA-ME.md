# Piloto urbano — FIRA

Pacote completo. Copie **todos** os arquivos desta pasta para `~/urbano`.
Não renomeie nada.

## Comando da prova

```bash
python3 main_urbano.py            # sem janela (mais FPS)
python3 main_urbano.py --debug    # com janelas, pra bancada
```

## Os arquivos

**Base do robô** (não são "da corrida" — são do robô; o urbano depende deles):

| arquivo | papel |
|---|---|
| `config.py` | pinos, servo, câmera, visão, PID |
| `vision.py` | visão de faixa (já com `last_mask` exposta) |
| `controller.py` | PID de direção |
| `MotorModule.py` | tração + servo (GPIO) |

**Camada urbana:**

| arquivo | papel |
|---|---|
| `config_urbano.py` | placas, zebra, manobras, velocidades |
| `signs.py` | leitura dos marcadores ArUco |
| `crosswalk.py` | detecção da faixa de pedestre |
| `navigator.py` | máquina de estados de decisão |
| `main_urbano.py` | loop principal |
| `test_signs.py` | ferramenta de calibração |

## Duas câmeras

O modo urbano usa **duas câmeras USB**, cada uma com um trabalho só:

| câmera | index (`config_urbano.py`) | resolução | função |
|---|---|---|---|
| faixa  | `CAMERA_INDEX_FAIXA`  | `config.CAMERA_RES` (480x240) | seguir a pista (`vision.py`) e ver a zebra |
| placas | `CAMERA_INDEX_PLACAS` | `CAMERA_RES_CAPTURA` (640x480) | ler só os marcadores ArUco das placas (`signs.py`) |

Antes de rodar, descubra o index de cada uma (a ordem de plugagem USB
decide qual é 0 e qual é 1 -- confira sempre, principalmente se trocar
de porta USB ou reiniciar o Pi):

```bash
ls /dev/video*
v4l2-ctl --list-devices
```

Ajuste `CAMERA_INDEX_FAIXA` / `CAMERA_INDEX_PLACAS` em `config_urbano.py`
de acordo. Se `main_urbano.py` imprimir "AVISO: a camera ... entregou
WxH em vez de ..." no início, é sinal de que os indexes estão trocados
ou a câmera não suporta a resolução pedida.

## Modelo de decisão

    PLACA (ArUco)     -> O QUE fazer no cruzamento
    FAIXA DE PEDESTRE -> QUANDO fazer

A placa arma uma intenção a ~1,2m. A intenção fica guardada até a zebra
aparecer; aí a manobra dispara em malha aberta (PID desligado, porque
dentro do cruzamento não existe faixa pra seguir). Zebra sem placa
armada = atravessa reto.

## As 7 placas suportadas

O mapa `PLACAS` em `config_urbano.py` já cobre a tabela oficial da
prova -- nome da placa, o que o carro deve fazer:

| placa | decisão do carro |
|---|---|
| No Entry (proibido_entrar) | não entra nessa rua -- desvia no cruzamento |
| Dead End (sem_saida) | não entra nessa rua -- desvia no cruzamento |
| Proceed Right (direita) | vira à direita no cruzamento |
| Proceed Left (esquerda) | vira à esquerda no cruzamento |
| Proceed Forward (frente) | segue em frente |
| Stop (parar) | destino final -- encerra a missão |
| Tunnel (tunel) | reduz velocidade e afrouxa a visão (seção 9 do `config_urbano.py`) |

Os **marcadores** dessa tabela são ArUco, não QR Code (ver comentário na
seção 1 de `config_urbano.py`) -- só carregam um ID de 0 a 6, o que é o
que permite ler de longe com câmera barata. Os IDs abaixo são **chute**
e têm que ser confirmados com `test_signs.py --scan` antes de qualquer
coisa (próxima seção).

## Ordem de calibração

**Nunca pule etapas — cada uma depende da anterior estar certa.**

### 1. IDs das placas (pode ser no notebook)

```bash
python3 test_signs.py --scan
```

Por padrão usa a câmera de `CAMERA_INDEX_PLACAS`; para testar com outra,
passe `--cam N` (ex: `python3 test_signs.py --scan --cam 0`).
Mostre uma placa por vez. Anote o dicionário e o ID de cada uma.
Corrija `ARUCO_DICT` e o mapa `PLACAS` no `config_urbano.py`.

> Os IDs 0–6 que estão lá são **chute**. Se estiverem errados, o robô
> obedece a placa errada com total confiança. É o passo mais crítico.

### 2. Distância das placas

Meça o lado do marcador impresso com régua → `MARKER_TAMANHO_M`.
Depois, marcador a exatamente 50 cm da lente da câmera de placas:

```bash
python3 test_signs.py --calib 0.50    # aperte 'c'
```

Cole o `FOCAL_PX` que ele imprimir.

### 3. Verificação ao vivo

```bash
python3 test_signs.py
```

Aproxime a placa e veja se o evento dispara. Ajuste `SIGN_DIST_ACIONA_M`
se disparar cedo/tarde demais.

### 4. Zebra

Robô parado a ~30 cm da faixa de pedestre:

```bash
python3 test_vision.py     # olhe a janela "Mascara"
```

As barras têm que aparecer separadas e limpas. Ajuste
`ZEBRA_BARRA_MIN_PX` / `ZEBRA_BARRA_MAX_PX` conforme a largura real
delas em pixels.

### 5. Bancada — carro na mão, rodas no ar

```bash
python3 main_urbano.py --debug
```

Passe placa e zebra na frente da câmera. Confira a sequência de estados:

    SEGUINDO -> AVANCANDO -> CURVANDO -> REENGATANDO -> SEGUINDO

### 6. Pista — só agora

Ajuste os únicos números que sobram:

- curva fechou cedo/tarde → `MANOBRA_AVANCO_S`
- virou menos/mais que 90° → `MANOBRA_CURVA_S`

Um cruzamento por vez, repetindo até ficar consistente.
**Calibre com a bateria no nível que vai usar na prova** — bateria fraca
muda esses tempos.

## Pendências de regulamento

- **Tunnel**: a linha veio vazia na tabela. Implementado o padrão
  defensivo (reduz velocidade, afrouxa o limiar de branco, tolera mais
  frames sem leitura). Confira a regra real — seção 9 do
  `config_urbano.py`.
- **Stop**: tratado como destino final (`PARADA_DEFINITIVA = True`).
  Se for um PARE comum (para 3 s e segue), troque para `False`.
