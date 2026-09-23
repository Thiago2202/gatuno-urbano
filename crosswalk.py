"""
crosswalk.py - detecta a FAIXA DE PEDESTRE (zebra) a frente.

Por que este arquivo existe
---------------------------
Olhando a arena da FIRA, TODO cruzamento e cercado de faixa de pedestre.
Isso tem duas consequencias, uma ruim e uma otima, e as duas obrigam a
mexer no projeto:

RUIM: a zebra QUEBRA a visao de faixa. O vision.py procura estrutura
clara e fina (top-hat) e mede "borda branca da esquerda / da direita" em
cada scanline. A zebra e exatamente isso -- varias barras brancas finas,
atravessadas, ocupando a largura inteira da pista. O scanline vai achar
run branco em todo canto, a meia-largura aprendida vai desandar, e o alvo
vai pular. Se o PID rodar em cima disso, o carro esterca dentro do
cruzamento. Nao adianta "ajustar o limiar": a zebra e branca e fina de
verdade, ela e indistinguivel da faixa por brilho. So da pra separar por
GEOMETRIA (varias barras paralelas repetidas na horizontal).

OTIMA: a zebra e o melhor gatilho de cruzamento que existe nessa pista.
Ela e um marcador geometrico confiavel de "voce chegou no cruzamento
AGORA" -- muito mais confiavel que estimar distancia pela area do ArUco
ou que cronometrar depois que a placa sumiu do quadro.

Dai a divisao de papeis que passa a valer:
    PLACA  = O QUE fazer no cruzamento (vira, segue, para, nao entra)
    ZEBRA  = QUANDO fazer

Trabalha em cima da MESMA mascara binaria que o vision.py ja calculou, em
vez de refazer o top-hat -- custo proximo de zero.
"""

import numpy as np

import config_urbano as cfgu


class CrosswalkResult:
    __slots__ = ("presente", "linhas", "y_mais_proximo", "frac_proximidade")

    def __init__(self):
        self.presente = False
        self.linhas = 0              # quantas scanlines viram padrao de zebra
        self.y_mais_proximo = None   # y (no ROI) da barra mais perto do carro
        self.frac_proximidade = 0.0  # 0 = longe (topo do ROI), 1 = colado no capo


class CrosswalkDetector:
    """Procura o padrao 'varias barras claras paralelas' na mascara.

    Criterio por linha varrida:
      - N runs brancos com largura dentro de uma faixa plausivel;
      - espacamento entre eles razoavelmente REGULAR (e o que separa zebra
        de sujeira/reflexo, que aparece em posicao aleatoria);
      - o conjunto cobrindo uma fatia larga da imagem.

    Criterio final: varias linhas seguidas confirmando. Uma linha sozinha
    e ruido; a zebra tem altura, entao ela aparece em varias.
    """

    def __init__(self):
        self._presente = False
        self._hits = 0
        self._miss = 0

    @staticmethod
    def _runs(row):
        idx = np.flatnonzero(row)
        if idx.size == 0:
            return []
        cortes = np.flatnonzero(np.diff(idx) > 1)
        grupos = np.split(idx, cortes + 1)
        return [(int(g[0]), int(g[-1])) for g in grupos]

    def _linha_e_zebra(self, row, largura):
        runs = [r for r in self._runs(row)
                if cfgu.ZEBRA_BARRA_MIN_PX <= (r[1] - r[0] + 1) <= cfgu.ZEBRA_BARRA_MAX_PX]
        if len(runs) < cfgu.ZEBRA_MIN_BARRAS:
            return False

        centros = np.array([(a + b) / 2.0 for a, b in runs])
        span = centros[-1] - centros[0]
        if span < largura * cfgu.ZEBRA_SPAN_MIN_FRAC:
            return False

        gaps = np.diff(centros)
        if gaps.size == 0:
            return False
        med = float(np.median(gaps))
        if med <= 0:
            return False
        # regularidade: desvio relativo dos espacamentos.
        # Zebra pintada tem passo constante; ruido nao tem.
        irregularidade = float(np.mean(np.abs(gaps - med)) / med)
        return irregularidade <= cfgu.ZEBRA_IRREGULARIDADE_MAX

    def detect(self, mask):
        """mask = mascara binaria do ROI (a mesma do vision.py)."""
        res = CrosswalkResult()
        if mask is None:
            self._miss += 1
            if self._miss >= cfgu.ZEBRA_MISS_FRAMES:
                self._presente = False
            res.presente = self._presente
            return res

        h, w = mask.shape[:2]
        ys = np.linspace(h - 3, int(h * cfgu.ZEBRA_TOP_FRAC),
                         cfgu.ZEBRA_SCAN_ROWS).astype(int)

        linhas = 0
        y_prox = None
        for y in ys:
            if self._linha_e_zebra(mask[y], w):
                linhas += 1
                if y_prox is None or y > y_prox:
                    y_prox = int(y)

        res.linhas = linhas
        res.y_mais_proximo = y_prox
        if y_prox is not None:
            res.frac_proximidade = float(y_prox) / float(h)

        # histerese: entra rapido (nao pode perder o cruzamento), sai devagar
        # (nao pode piscar no meio da travessia)
        if linhas >= cfgu.ZEBRA_MIN_LINHAS:
            self._hits += 1
            self._miss = 0
            if self._hits >= cfgu.ZEBRA_HIT_FRAMES:
                self._presente = True
        else:
            self._miss += 1
            self._hits = 0
            if self._miss >= cfgu.ZEBRA_MISS_FRAMES:
                self._presente = False

        res.presente = self._presente
        return res

    def reset(self):
        self._presente = False
        self._hits = self._miss = 0
