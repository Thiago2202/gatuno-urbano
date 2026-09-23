"""
navigator.py - a "cabeca" do motorista urbano.

MODELO DE DECISAO (mudou depois de ver a arena da FIRA)
-------------------------------------------------------
    PLACA (ArUco)        -> O QUE fazer no proximo cruzamento
    FAIXA DE PEDESTRE    -> QUANDO fazer

A placa nao executa mais nada sozinha: ela ARMA uma intencao. A intencao
fica guardada ate a zebra do cruzamento aparecer -- ai a manobra dispara.

Por que isso e melhor que a versao anterior (disparar por distancia da
placa): a placa fica na LATERAL da rua e a camera e baixa, entao o
marcador some do quadro bem antes de o carro chegar ao cruzamento.
Estimar "quanto falta" pela area do marcador funciona, mas com erro de
varios centimetros, e esse erro vira curva iniciada cedo/tarde demais. A
zebra, por outro lado, esta bem na frente do carro e diz com precisao de
frame que o cruzamento e AGORA. Numa arena onde todo cruzamento tem
zebra, essa e a referencia mais confiavel disponivel.

Fallback continua existindo: se a intencao estiver armada e nenhuma zebra
for detectada dentro de INTENCAO_VALIDA_S, ela e descartada (nao vira
manobra as cegas no meio da rua -- isso seria pior que nao manobrar).

Estados
-------
SEGUINDO     : PID no comando. Estado normal.
AVANCANDO    : entrando no cruzamento em linha reta, sem PID.
CURVANDO     : servo no talo por tempo fixo, sem PID.
TRAVESSANDO  : cruzando em frente, em reta, sem PID.
REENGATANDO  : PID de volta, tolerando ausencia de faixa por N frames.
PARANDO      : frenagem suave (na faixa de pedestre, como manda a lei).
PARADO       : parado.
FIM          : missao encerrada.
"""

import time

import config
import config_urbano as cfgu


SEGUINDO = "SEGUINDO"
AVANCANDO = "AVANCANDO"
CURVANDO = "CURVANDO"
TRAVESSANDO = "TRAVESSANDO"
REENGATANDO = "REENGATANDO"
PARANDO = "PARANDO"
PARADO = "PARADO"
FIM = "FIM"

_MANOBRA = (AVANCANDO, CURVANDO, TRAVESSANDO, PARANDO, PARADO, FIM)


class Comando:
    """O que o main deve fazer NESTE frame."""
    __slots__ = ("usa_faixa", "turn", "speed", "resetar_pid",
                 "tolera_perdido", "estado", "fim")

    def __init__(self):
        self.usa_faixa = True
        self.turn = 0.0
        self.speed = 0.0
        self.resetar_pid = False
        self.tolera_perdido = False
        self.estado = SEGUINDO
        self.fim = False


class Navigator:
    def __init__(self):
        self.estado = SEGUINDO
        self.t_estado = time.time()
        self.sentido = 0.0
        self.pos_curva = None
        self.frames_reengate = 0
        self.log = []

        # intencao armada pela placa, aguardando o cruzamento
        self.intencao = None        # 'direita' | 'esquerda' | 'frente' | 'parar'
        self.intencao_t = 0.0
        self.intencao_origem = ""

        self._zebra_anterior = False
        self._zebra_bloqueio_ate = 0.0

        self._bloqueio_ate = 0.0
        self._bloqueio_tentativas = 0

        self.em_tunel = False
        self._tunel_ate = 0.0
        self._backup_tunel = None

    # ------------------------------------------------------------------
    def _muda(self, novo):
        self.estado = novo
        self.t_estado = time.time()

    def _dt_estado(self):
        return time.time() - self.t_estado

    def _registrar(self, texto):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {texto}")
        print(f"  >> {texto}")

    # ------------------------------------------------------------------
    # TUNEL: nao e estado, e um MODIFICADOR. O carro continua seguindo a
    # faixa; o que muda e a tolerancia da visao e o teto de velocidade.
    # Feito mexendo no config em runtime e restaurando na saida, pra nao
    # espalhar 'if tunel' dentro do vision.py.
    # ------------------------------------------------------------------
    def _entrar_tunel(self):
        if self.em_tunel:
            self._tunel_ate = time.time() + cfgu.TUNEL_DURACAO_S
            return
        self._backup_tunel = (config.TOPHAT_FATOR, config.V_MIN_ABS,
                              config.MAX_FRAMES_PERDIDO)
        config.TOPHAT_FATOR = cfgu.TUNEL_TOPHAT_FATOR
        config.V_MIN_ABS = cfgu.TUNEL_V_MIN_ABS
        config.MAX_FRAMES_PERDIDO = cfgu.TUNEL_MAX_FRAMES_PERDIDO
        self.em_tunel = True
        self._tunel_ate = time.time() + cfgu.TUNEL_DURACAO_S
        self._registrar("TUNEL: entrando (visao permissiva, velocidade reduzida)")

    def _sair_tunel(self):
        if not self.em_tunel:
            return
        config.TOPHAT_FATOR, config.V_MIN_ABS, config.MAX_FRAMES_PERDIDO = self._backup_tunel
        self.em_tunel = False
        self._registrar("TUNEL: saindo (visao normal)")

    # ------------------------------------------------------------------
    def _armar(self, tipo, origem):
        self.intencao = tipo
        self.intencao_t = time.time()
        self.intencao_origem = origem
        self._registrar(f"intencao ARMADA: {tipo} (placa: {origem}) "
                        f"-- aguardando a faixa de pedestre")

    def on_evento(self, ev):
        """Recebe uma placa confirmada pelo signs.py."""
        if ev is None:
            return
        if self.estado in _MANOBRA:
            # placa vista no meio de uma manobra quase sempre e a placa da
            # rua transversal, nao uma ordem nova
            self._registrar(f"placa '{ev.tipo}' ignorada (manobrando: {self.estado})")
            return

        tipo = ev.tipo

        if tipo == "tunel":
            self._sair_tunel() if self.em_tunel else self._entrar_tunel()
            return

        if tipo in ("direita", "esquerda", "frente", "parar"):
            self._armar(tipo, tipo)
            return

        if tipo in ("proibido_entrar", "sem_saida"):
            # As duas placas ficam no INICIO da rua: ve-las de frente
            # significa "a rua reta esta vedada" -> desvia no cruzamento.
            agora = time.time()
            if agora < self._bloqueio_ate:
                self._bloqueio_tentativas += 1   # a 1a preferencia ja falhou
            else:
                self._bloqueio_tentativas = 0
            self._bloqueio_ate = agora + cfgu.BLOQUEIO_MEMORIA_S

            idx = self._bloqueio_tentativas % len(cfgu.BLOQUEIO_PREFERENCIA)
            escolha = cfgu.BLOQUEIO_PREFERENCIA[idx]
            self._armar(escolha, f"{tipo} -> desvio pela {escolha}")
            return

        self._registrar(f"placa desconhecida ignorada: {tipo}")

    # ------------------------------------------------------------------
    def _disparar(self, tipo):
        """Cruzamento chegou: executa a intencao."""
        self._zebra_bloqueio_ate = time.time() + cfgu.ZEBRA_COOLDOWN_S
        self.intencao = None

        if tipo == "parar":
            self._registrar("cruzamento: PARANDO na faixa de pedestre")
            self._muda(PARANDO)
            return

        if tipo in ("direita", "esquerda"):
            self.sentido = 1.0 if tipo == "direita" else -1.0
            self.pos_curva = CURVANDO
            self._registrar(f"cruzamento: manobra para a {tipo}")
        else:
            self.pos_curva = TRAVESSANDO
            self._registrar("cruzamento: seguindo em frente")
        self._muda(AVANCANDO)

    # ------------------------------------------------------------------
    def update(self, leitura_ok, zebra=False):
        """leitura_ok = visao entregou faixa fresca e confiavel.
        zebra        = faixa de pedestre detectada a frente."""
        cmd = Comando()
        agora = time.time()

        if self.em_tunel and agora > self._tunel_ate:
            self._sair_tunel()

        # intencao vence por tempo (placa de outra rua / carro errou o caminho)
        if self.intencao and (agora - self.intencao_t) > cfgu.INTENCAO_VALIDA_S:
            self._registrar(f"intencao '{self.intencao}' expirou sem cruzamento -- descartada")
            self.intencao = None

        # ---- borda de subida da zebra, so fora de manobra ----
        zebra_nova = (zebra and not self._zebra_anterior
                      and agora >= self._zebra_bloqueio_ate
                      and self.estado in (SEGUINDO, REENGATANDO))
        self._zebra_anterior = zebra

        if zebra_nova:
            # Sem placa armada o correto e atravessar reto: o cruzamento nao
            # tem faixa pra seguir e a zebra ja estragou a leitura da visao.
            # Melhor uma travessia reta controlada do que deixar o PID
            # esterçar em cima das barras da zebra.
            self._disparar(self.intencao or "frente")

        # roda o passo de estado; se a transicao acontecer NESTE frame,
        # roda de novo pra ja emitir o comando do estado novo (senao o
        # primeiro frame de cada manobra sai com turn=0)
        for _ in range(2):
            antes = self.estado
            self._passo(cmd)
            if self.estado == antes:
                break

        if self.estado == REENGATANDO:
            cmd.usa_faixa = True
            cmd.tolera_perdido = True
            self.frames_reengate += 1
            if leitura_ok:
                self._registrar("faixa reengatada")
                self._muda(SEGUINDO)
            elif self.frames_reengate > cfgu.MANOBRA_REENGATE_FRAMES:
                self._registrar("reengate falhou -- devolvendo pro modo perdido")
                self._muda(SEGUINDO)

        cmd.estado = self.estado
        return cmd

    # ------------------------------------------------------------------
    def _passo(self, cmd):
        e = self.estado
        dt = self._dt_estado()

        if e == AVANCANDO:
            cmd.usa_faixa = False
            cmd.speed = cfgu.VELOCIDADE_MANOBRA
            if dt >= cfgu.MANOBRA_AVANCO_S:
                self._muda(self.pos_curva or TRAVESSANDO)

        elif e == CURVANDO:
            cmd.usa_faixa = False
            cmd.turn = self.sentido * cfgu.MANOBRA_TURN_MAG
            cmd.speed = cfgu.VELOCIDADE_MANOBRA
            if dt >= cfgu.MANOBRA_CURVA_S:
                self.frames_reengate = 0
                cmd.resetar_pid = True
                self._muda(REENGATANDO)

        elif e == TRAVESSANDO:
            cmd.usa_faixa = False
            cmd.speed = cfgu.VELOCIDADE_MANOBRA
            if dt >= cfgu.MANOBRA_TRAVESSIA_S:
                self.frames_reengate = 0
                cmd.resetar_pid = True
                self._muda(REENGATANDO)

        elif e == PARANDO:
            cmd.usa_faixa = False
            # rampa: travar seco joga o carro pra frente e desalinha
            frac = max(0.0, 1.0 - dt / cfgu.PARADA_FREIO_S)
            cmd.speed = cfgu.VELOCIDADE_MANOBRA * frac
            if dt >= cfgu.PARADA_FREIO_S:
                if cfgu.PARADA_DEFINITIVA:
                    self._registrar("MISSAO ENCERRADA no destino.")
                    self._muda(FIM)
                    cmd.speed, cmd.fim = 0.0, True
                else:
                    self._muda(PARADO)

        elif e == PARADO:
            cmd.usa_faixa = False
            cmd.speed = 0.0
            if dt >= cfgu.PARADA_TEMPO_S:
                cmd.resetar_pid = True
                self.frames_reengate = 0
                self._registrar("retomando apos a parada")
                self._muda(TRAVESSANDO)   # sai da parada atravessando a zebra

        elif e == FIM:
            cmd.usa_faixa = False
            cmd.speed = 0.0
            cmd.fim = True

        elif e == REENGATANDO:
            pass      # tratado no update() (precisa de leitura_ok)

        else:
            cmd.usa_faixa = True

    # ------------------------------------------------------------------
    def teto_velocidade(self):
        if self.em_tunel:
            return cfgu.VELOCIDADE_TUNEL
        return cfgu.VELOCIDADE_BASE_URBANO

    def hud(self):
        alvo = self.intencao or "-"
        return f"{self.estado} | intencao={alvo}" + (" | TUNEL" if self.em_tunel else "")

    def resumo(self):
        return "\n".join(self.log) if self.log else "(nenhuma placa obedecida)"
