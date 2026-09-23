"""
config_urbano.py - parametros do MODO URBANO (placas + leis de transito).

Nao substitui o config.py. O config.py continua sendo a verdade sobre
hardware, visao e PID (tudo que ja foi calibrado na pista de corrida).
Este arquivo so acrescenta o que e especifico da pista urbana e, no fim,
tem uma funcao que aplica os OVERRIDES de velocidade em cima do config.py
em tempo de execucao -- assim o main.py da corrida continua funcionando
exatamente como hoje, sem nenhuma alteracao.
"""

import config

# =====================================================================
# 1. MARCADORES (ArUco)
#
# Os quadradinhos pretos da tabela NAO sao QR Code, sao marcadores ArUco.
# Diferenca pratica importante: QR Code carrega texto e precisa estar
# grande/proximo/nitido pra decodificar. ArUco carrega so um numero (o ID)
# e foi feito pra ser lido de longe, torto e com pouca resolucao. E por
# isso que competicao usa ArUco -- e por isso que o pipeline abaixo
# consegue ver a placa a 1m+ com camera barata.
#
# O DICIONARIO e o TAMANHO do ID voce descobre rodando:
#     python3 test_signs.py --scan
# Ele testa todos os dicionarios e imprime qual deu match e quais IDs.
# =====================================================================
ARUCO_DICT = "DICT_4X4_50"      # troque pelo que o --scan encontrar

# Lado do marcador impresso, em METROS (mede com regua no papel).
MARKER_TAMANHO_M = 0.08

# Distancia focal da camera em PIXELS, na resolucao de CAPTURA (secao 5).
# Calibre com: python3 test_signs.py --calib 0.50
# (coloca o marcador a exatamente 50cm e roda; ele imprime o valor).
FOCAL_PX = 640.0

# =====================================================================
# 2. MAPA ID -> PLACA
#
# PLACEHOLDER. Rode 'python3 test_signs.py --scan' com cada placa da folha
# na frente da camera, anote o ID que aparecer, e corrija aqui. Se o mapa
# estiver errado o robo obedece a placa errada -- e o unico ponto do
# sistema onde um erro de digitacao vira infracao de transito.
# =====================================================================
PLACAS = {
    0: "proibido_entrar",     # No Entry     - nao entra nessa rua
    1: "sem_saida",           # Dead End     - nao entra nessa rua
    2: "direita",             # Proceed Right
    3: "esquerda",            # Proceed Left
    4: "frente",              # Proceed Forward
    5: "parar",               # Stop         - destino final
    6: "tunel",               # Tunnel
}

# =====================================================================
# 3. CONFIRMACAO E ACIONAMENTO
# =====================================================================
# Quantos frames seguidos o mesmo ID precisa aparecer pra ser aceito.
# Marcador ArUco praticamente nao da falso positivo, mas da LEITURA DE ID
# ERRADO quando esta borrado/inclinado no limite. 3 frames mata isso.
SIGN_CONFIRMA_FRAMES = 3

# Fora dessa faixa de distancia a leitura e ignorada (longe demais = ID
# instavel; perto demais = marcador cortado pela borda, area mentirosa).
SIGN_DIST_MIN_M = 0.15
SIGN_DIST_MAX_M = 2.00

# Distancia em que a placa passa a valer como INTENCAO ARMADA.
# ATENCAO -- a semantica mudou depois de ver a arena da FIRA: a placa nao
# executa mais a manobra sozinha. Ela so diz O QUE fazer; QUANDO fazer vem
# da faixa de pedestre (crosswalk.py). Por isso este valor agora e LONGE
# (~1.2m): quanto antes a intencao estiver armada, melhor -- ela fica
# esperando o cruzamento aparecer.
SIGN_DIST_ACIONA_M = 1.20

# Por quanto tempo uma intencao armada continua valendo sem encontrar
# cruzamento nenhum. Passou disso, esquece (a placa provavelmente era de
# outra rua, ou o carro errou o caminho).
INTENCAO_VALIDA_S = 8.0

# O marcador sai do campo de visao antes de o carro chegar nele (a camera
# e baixa e a placa fica na lateral). Entao: depois de confirmada e ja
# proxima, se o marcador SUMIR por estes frames, aciona assim mesmo.
SIGN_SUMIU_ACIONA_FRAMES = 4

# Depois de obedecer uma placa, ignora o MESMO ID por este tempo -- senao
# ele reencontra a mesma placa no meio da curva e manobra duas vezes.
SIGN_COOLDOWN_S = 6.0

# Roda a deteccao 1 a cada N frames. 1 = todo frame. Em modo urbano a
# velocidade e baixa, entao 2 ainda da folga de sobra e devolve FPS.
SIGN_SKIP_FRAMES = 1

# Fracao SUPERIOR do frame onde as placas sao procuradas (1.0 = frame
# inteiro). Com camera DEDICADA as placas, nao ha garantia de que a
# metade de baixo do quadro seja chao/faixa (a placa pode aparecer em
# qualquer altura, dependendo de como essa camera foi montada) -- por
# isso o padrao agora e 1.0. Se essa camera for montada olhando pra
# frente/baixo e sobrar chao no quadro, pode abaixar pra economizar CPU.
SIGN_ROI_TOP_FRAC = 1.0

# =====================================================================
# 4. VELOCIDADES DO MODO URBANO (override do config.py)
#
# A pista urbana nao premia velocidade, premia obediencia. Baixar a
# velocidade nao e so "andar devagar": e o que da tempo de frame pro
# marcador ser lido antes de o carro passar reto pela placa, e o que faz
# a manobra em malha aberta (curva cronometrada) ficar REPETIVEL.
# =====================================================================
VELOCIDADE_BASE_URBANO    = 0.42
VELOCIDADE_MINIMA_URBANO  = 0.32
VELOCIDADE_PERDIDO_URBANO = 0.20
VELOCIDADE_MANOBRA        = 0.34   # dentro do cruzamento
VELOCIDADE_TUNEL          = 0.26

# Na corrida o alvo e deslocado pra perto da pontilhada (LANE_BIAS_FRAC
# 0.85) porque isso encurta a trajetoria. Na arena da FIRA a pontilhada e
# a divisoria de MAO DUPLA -- se aproximar dela e invadir a contramao, que
# e infracao. E o vision.py ja entrega o centro da PROPRIA faixa (ele mede
# borda esquerda e borda direita da faixa em que o carro esta). Entao o
# vies correto em pista urbana e ZERO: anda no meio da sua faixa.
LANE_BIAS_FRAC_URBANO = 0.0

# =====================================================================
# 4b. FAIXA DE PEDESTRE (zebra) -- ver crosswalk.py
#
# Valores em PIXELS na resolucao da visao (config.CAMERA_RES = 480x240).
# Calibre olhando a mascara com o robo parado antes da zebra:
#     python3 test_vision.py
# =====================================================================
ZEBRA_MIN_BARRAS = 4          # barras claras na mesma linha varrida
ZEBRA_BARRA_MIN_PX = 3        # largura plausivel de UMA barra
ZEBRA_BARRA_MAX_PX = 30
ZEBRA_SPAN_MIN_FRAC = 0.35    # o conjunto tem que cobrir essa fatia da largura
ZEBRA_IRREGULARIDADE_MAX = 0.45   # o quanto o espacamento pode variar
ZEBRA_SCAN_ROWS = 10
ZEBRA_TOP_FRAC = 0.25         # varre do topo do ROI ate o capo
ZEBRA_MIN_LINHAS = 3          # linhas confirmando no MESMO frame
ZEBRA_HIT_FRAMES = 2          # frames pra declarar presente (entra rapido)
ZEBRA_MISS_FRAMES = 6         # frames pra declarar ausente (sai devagar)

# Depois de atravessar um cruzamento, ignora zebra por este tempo -- senao
# a zebra da SAIDA do mesmo cruzamento dispara uma segunda manobra.
ZEBRA_COOLDOWN_S = 3.0

# =====================================================================
# 5. DUAS CAMERAS NO MODO URBANO
#
# Camera 1 (FAIXA) -- olha a pista, alimenta vision.py. Captura DIRETO na
# resolucao calibrada da visao (config.CAMERA_RES = 480x240): a visao usa
# pixels absolutos (LINE_MAX_WIDTH_PX, SCAN_HW_MIN/MAX, etc), entao mudar
# a resolucao dela invalidaria toda a calibracao.
#
# Camera 2 (PLACAS) -- dedicada so a ler os marcadores das placas
# (signs.py). Existe separada da camera de faixa porque o ArUco precisa
# de resolucao pra ler o ID de longe (em 480x240 um marcador a 1m tem
# ~15px de lado e o ID nao fecha), e porque fisicamente a placa fica na
# lateral da pista -- uma segunda camera pode ficar angulada/posicionada
# so pra isso, sem comprometer o enquadramento da faixa.
#
# Descubra o INDEX de cada camera (numero depois de /dev/video) com:
#     ls /dev/video*
#     v4l2-ctl --list-devices
# Normalmente a ordem de plugagem USB define 0, 1, 2... -- se trocar de
# porta USB o index pode mudar, entao confira antes de rodar na prova.
# =====================================================================
CAMERA_INDEX_FAIXA  = 0
CAMERA_INDEX_PLACAS = 1

# Resolucao de CAPTURA da camera de placas (a de faixa captura direto em
# config.CAMERA_RES, nao precisa de constante propria aqui).
CAMERA_RES_CAPTURA = (640, 480)

# =====================================================================
# 6. MANOBRAS EM MALHA ABERTA (cronometradas)
#
# Por que malha aberta: dentro do cruzamento NAO EXISTE faixa pra seguir.
# Se o PID continuar rodando ali, ele persegue restos de linha da rua
# transversal e o carro entra torto. A unica coisa honesta a fazer e:
# desligar o PID, executar um movimento cronometrado, e so entao devolver
# o controle pra visao quando ja houver faixa de novo.
#
# CALIBRE ESTES TEMPOS NA PISTA. Sao os unicos numeros do sistema que
# dependem do seu carro, do seu piso e da sua bateria.
# =====================================================================
MANOBRA_AVANCO_S   = 0.55   # entra no cruzamento antes de girar
MANOBRA_CURVA_S    = 1.30   # tempo com o servo no talo
MANOBRA_TRAVESSIA_S = 1.10  # atravessar em frente (sem faixa)
MANOBRA_TURN_MAG   = 0.95   # 0..1, quanto de esterco na curva

# Depois da manobra, quantos frames sem faixa sao tolerados antes de
# declarar perdido (o reengate na faixa nova leva alguns frames).
MANOBRA_REENGATE_FRAMES = 25

# =====================================================================
# 7. PARADA / DESTINO
# =====================================================================
PARADA_FREIO_S   = 0.6    # desacelera antes de travar (nao trava seco)
PARADA_DEFINITIVA = True  # STOP da tabela = destino -> encerra a missao.
                          # False = para 3s e segue (placa de PARE comum).
PARADA_TEMPO_S    = 3.0   # so usado se PARADA_DEFINITIVA = False

# =====================================================================
# 8. RUA BLOQUEADA (No Entry / Dead End)
#
# As duas placas significam a mesma coisa pro carro: nao entra nessa rua.
# Como elas ficam no INICIO da rua, ver uma delas de frente = a rua a
# frente esta vedada -> tem que desviar no cruzamento.
# Ordem de preferencia do desvio (primeira opcao viavel vence).
# =====================================================================
BLOQUEIO_PREFERENCIA = ("direita", "esquerda")

# Depois de ver bloqueio, por quantos segundos a rua fica marcada como
# vedada (evita o carro "esquecer" e tentar entrar de novo no reengate).
BLOQUEIO_MEMORIA_S = 5.0

# =====================================================================
# 9. TUNEL
#
# A linha do tunel veio VAZIA na tabela da prova -- a regra oficial nao
# foi definida ali. O comportamento abaixo e o padrao defensivo de
# competicao: dentro do tunel a iluminacao cai e a segmentacao da faixa
# degrada, entao o carro reduz, afrouxa o limiar de branco e tolera mais
# frames sem leitura antes de declarar perdido. CONFIRA O REGULAMENTO e
# ajuste aqui se a regra real for outra (ex: acender farol, buzinar).
# =====================================================================
TUNEL_DURACAO_S       = 6.0    # sai sozinho depois disso (ou ao ver o ID de novo)
TUNEL_TOPHAT_FATOR    = 0.30   # limiar mais permissivo no escuro
TUNEL_V_MIN_ABS       = 40     # aceita branco mais apagado
TUNEL_MAX_FRAMES_PERDIDO = 30  # tolera mais buraco de leitura


# =====================================================================
# APLICACAO DOS OVERRIDES
# =====================================================================
def aplicar_overrides():
    """Aplica o perfil urbano em cima do config.py, em runtime.

    Nao edita arquivo nenhum. O config.py continua com os valores de
    CORRIDA gravados -- rodar main.py depois disso nao herda nada.
    """
    config.VELOCIDADE_BASE    = VELOCIDADE_BASE_URBANO
    config.VELOCIDADE_MINIMA  = VELOCIDADE_MINIMA_URBANO
    config.VELOCIDADE_PERDIDO = VELOCIDADE_PERDIDO_URBANO
    config.LANE_BIAS_FRAC     = LANE_BIAS_FRAC_URBANO
    print("[urbano] perfil aplicado: "
          f"base={config.VELOCIDADE_BASE:.2f} min={config.VELOCIDADE_MINIMA:.2f} "
          f"bias={config.LANE_BIAS_FRAC:.2f}")
