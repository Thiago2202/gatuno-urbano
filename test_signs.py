"""
test_signs.py - descobre os IDs das placas e calibra a distancia.
NAO liga motor, nao toca em GPIO. Pode rodar no notebook tambem.

Tres modos:

1) DESCOBRIR o dicionario e os IDs (faca isso PRIMEIRO):
       python3 test_signs.py --scan
   Mostre uma placa por vez pra camera. Ele testa todos os dicionarios
   ArUco e imprime qual deu match e com que ID. Anote e preencha o
   dicionario PLACAS no config_urbano.py.

2) CALIBRAR a distancia:
       python3 test_signs.py --calib 0.50
   Posicione o marcador a EXATAMENTE 50cm da lente, de frente. Aperte 'c'.
   Ele imprime o FOCAL_PX pra colar no config_urbano.py.

3) VERIFICAR ao vivo (depois de configurado):
       python3 test_signs.py
   Mostra placa reconhecida + distancia estimada + votos.

Camera: por padrao usa cfgu.CAMERA_INDEX_PLACAS (a camera dedicada as
placas). Se sua montagem ainda so tem uma camera, ou quiser testar em
outro index, passe --cam N (ex: --cam 0).

Teclas: 'q' sai | 'c' captura (modo --calib)
"""

import sys
import time

import cv2
import numpy as np

import config_urbano as cfgu
from signs import SignTracker, SignDetector


DICIONARIOS = [d for d in dir(cv2.aruco) if d.startswith("DICT_")]


def _camera_index():
    if "--cam" in sys.argv:
        i = sys.argv.index("--cam")
        if len(sys.argv) > i + 1:
            return int(sys.argv[i + 1])
    return cfgu.CAMERA_INDEX_PLACAS


def abrir(src=None):
    if src is None:
        src = _camera_index()
    print(f"Abrindo camera index {src} "
          f"({'--cam' if '--cam' in sys.argv else 'CAMERA_INDEX_PLACAS'})")
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfgu.CAMERA_RES_CAPTURA[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfgu.CAMERA_RES_CAPTURA[1])
    return cap


# ---------------------------------------------------------------- scan
def modo_scan():
    print("SCAN: mostre UMA placa por vez. Ctrl+C ou 'q' pra sair.\n")
    detectores = {}
    for nome in DICIONARIOS:
        try:
            detectores[nome] = SignDetector(nome)
        except Exception:
            pass

    cap = abrir()
    visto = {}
    t = time.time()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            achou_algo = False
            for nome, det in detectores.items():
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                corners, ids = det._detect_raw(gray)
                if ids is None or len(ids) == 0:
                    continue
                achou_algo = True
                for i in ids.flatten():
                    chave = (nome, int(i))
                    visto[chave] = visto.get(chave, 0) + 1

            if time.time() - t >= 1.0:
                t = time.time()
                if visto:
                    print("--- acumulado (dicionario, id): frames ---")
                    for (nome, i), n in sorted(visto.items(), key=lambda x: -x[1])[:8]:
                        print(f"  {nome:16s} id={i:<4d} {n} frames")
                elif not achou_algo:
                    print("nada detectado -- aproxime, melhore a luz, evite reflexo")
                print()

            cv2.imshow("scan (q sai)", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if visto:
            melhor = max(visto.items(), key=lambda x: x[1])[0][0]
            print(f"\nDicionario mais provavel: ARUCO_DICT = \"{melhor}\"")
            print("Cole no config_urbano.py junto com o mapa PLACAS.")


# --------------------------------------------------------------- calib
def modo_calib(dist_real):
    det = SignDetector()
    cap = abrir()
    print(f"CALIB: marcador a {dist_real:.2f}m, de frente. 'c' captura, 'q' sai.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            leituras = det.detect(frame)
            vis = det.desenhar(frame.copy())
            if leituras:
                l = leituras[0]
                cv2.putText(vis, f"lado {l.lado_px:.1f}px  id {l.id}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("calib", vis)
            k = cv2.waitKey(1) & 0xFF
            if k == ord('q'):
                break
            if k == ord('c') and leituras:
                lado = leituras[0].lado_px
                focal = (lado * dist_real) / cfgu.MARKER_TAMANHO_M
                print(f"\nlado={lado:.1f}px  dist={dist_real:.2f}m  "
                      f"tamanho={cfgu.MARKER_TAMANHO_M:.3f}m")
                print(f"Cole no config_urbano.py:\n  FOCAL_PX = {focal:.1f}\n")
    finally:
        cap.release()
        cv2.destroyAllWindows()


# ----------------------------------------------------------------- ao vivo
def modo_vivo():
    tracker = SignTracker()
    cap = abrir()
    print("AO VIVO: mostra o que o robo REALMENTE entenderia. 'q' sai.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            ev = tracker.update(frame)
            if ev:
                print(f"  >> EVENTO ACIONADO: {ev.tipo} (id {ev.id}) a {ev.dist:.2f}m")
            vis = tracker.detector.desenhar(frame.copy())
            cv2.putText(vis, tracker.hud(), (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            cv2.imshow("placas", vis)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    if "--scan" in sys.argv:
        modo_scan()
    elif "--calib" in sys.argv:
        i = sys.argv.index("--calib")
        d = float(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 0.5
        modo_calib(d)
    else:
        modo_vivo()
