"""
main_urbano.py - piloto autonomo em PISTA URBANA (obedece sinalizacao).

    python3 main_urbano.py            # sem janela (mais FPS)
    python3 main_urbano.py --debug    # com janelas de visao + placas

Diferenca pro main.py (corrida):
  - DUAS cameras: uma so pra faixa (config.CAMERA_RES, igual a corrida) e
    outra so pra placas (resolucao maior, pra conseguir ler o ArUco de
    longe). Indices em config_urbano.CAMERA_INDEX_FAIXA / _PLACAS;
  - existe uma camada de decisao (navigator) que pode TOMAR o controle do
    PID durante cruzamentos e paradas;
  - perfil de velocidade urbano, aplicado sobre o config.py em runtime.

O main.py da corrida NAO foi alterado e continua funcionando como estava
(ele usa uma camera so).
"""

import sys
import time

import cv2

import config
import config_urbano as cfgu
from vision import LaneVision
from controller import SteeringPID, speed_for
from MotorModule import Motor
from signs import SignTracker
from crosswalk import CrosswalkDetector
from navigator import Navigator

DEBUG = "--debug" in sys.argv


def abrir_camera(index, res, nome):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, res[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, res[1])
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc_str = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera {nome} (index {index}): {w}x{h} formato={fourcc_str}")
    if fourcc_str.strip() != "MJPG":
        print(f"AVISO: camera {nome} nao aceitou MJPG -- o FPS vai sofrer nesta resolucao.")
    if (w, h) != tuple(res):
        print(f"AVISO: a camera {nome} entregou {w}x{h} em vez de {res}. "
              f"Se for a camera de placas, recalibre FOCAL_PX nessa resolucao, "
              f"senao a distancia das placas sai errada.")
    return cap


def main():
    cfgu.aplicar_overrides()
    print("PILOTO URBANO -- seguindo faixa e obedecendo sinalizacao.\n")

    cam_faixa = abrir_camera(cfgu.CAMERA_INDEX_FAIXA, config.CAMERA_RES, "faixa")
    cam_placas = abrir_camera(cfgu.CAMERA_INDEX_PLACAS, cfgu.CAMERA_RES_CAPTURA, "placas")
    if not cam_faixa.isOpened():
        print("Erro critico: camera de faixa nao abriu "
              f"(index {cfgu.CAMERA_INDEX_FAIXA}).")
        return
    if not cam_placas.isOpened():
        print("Erro critico: camera de placas nao abriu "
              f"(index {cfgu.CAMERA_INDEX_PLACAS}).")
        return

    vision = LaneVision()
    pid = SteeringPID()
    placas = SignTracker()
    zebra_det = CrosswalkDetector()
    nav = Navigator()
    motor = Motor(config.ENA_A, config.IN1_A, config.IN2_A,
                  config.ENA_B, config.IN3_B, config.IN4_B,
                  config.SERVO_PIN)

    frames, t_fps = 0, time.time()
    turn = 0.0
    fps_medido = 30.0
    frame_anterior_confiavel = True
    t_cam = t_vis = t_sign = 0.0

    try:
        while True:
            t0 = time.time()
            ok_f, frame = cam_faixa.read()
            ok_p, frame_placas = cam_placas.read()
            t1 = time.time()
            if not ok_f or not ok_p:
                motor.stop()
                continue

            # ---------- 1. PLACAS (camera dedicada, resolucao cheia) --
            evento = placas.update(frame_placas)
            nav.on_evento(evento)
            t2 = time.time()

            # ---------- 2. FAIXA (camera dedicada, resolucao calibrada)
            res = vision.process(frame, debug=DEBUG)
            t3 = time.time()

            # ---------- 3. FAIXA DE PEDESTRE --------------------------
            # reaproveita a mascara que a visao ja calculou. Se o vision.py
            # nao expuser 'last_mask', recalcula (custa ~5ms a mais).
            mask = getattr(vision, "last_mask", None)
            if mask is None:
                y0 = int(vision.H * config.SCAN_TOP_PCT)
                mask = vision.threshold(frame[y0:, :])
            zebra = zebra_det.detect(mask)
            t4 = time.time()

            leitura_ok = bool(res.valid and res.motivo == "ok"
                              and (res.found_left or res.found_right))
            # Em cima da zebra a leitura de faixa NAO vale, mesmo que o
            # vision.py diga que esta ok: as barras brancas atravessadas
            # sao lidas como borda de faixa e o alvo pula.
            if zebra.presente:
                leitura_ok = False

            # ---------- 4. DECISAO ------------------------------------
            cmd = nav.update(leitura_ok, zebra.presente)

            if cmd.resetar_pid:
                # depois de uma manobra em malha aberta, o estado interno do
                # PID (integral, erro anterior) descreve uma pista que nao
                # existe mais. Reaproveitar isso e garantir um esterco errado
                # no primeiro frame da rua nova.
                pid.reset()
                vision.ref_e = vision.ref_d = None   # forca reengate do rastreio
                zebra_det.reset()
                frame_anterior_confiavel = False

            if cmd.fim:
                motor.stop()
                print("\nDestino alcancado. Encerrando.")
                break

            # ---------- 5. COMANDO ------------------------------------
            if not cmd.usa_faixa:
                # manobra cronometrada: o navigator manda, a visao nao opina
                turn = cmd.turn
                speed = cmd.speed
                frame_anterior_confiavel = False
            elif leitura_ok:
                if not frame_anterior_confiavel:
                    pid.marcar_retomada()
                frame_anterior_confiavel = True
                turn = pid.update(res.error, res.heading)
                speed = speed_for(turn, res.curvature)
                if fps_medido < config.FPS_MINIMO_SEGURO:
                    speed *= max(0.35, fps_medido / config.FPS_MINIMO_SEGURO)
            elif cmd.tolera_perdido or vision.lost_frames <= config.MAX_FRAMES_PERDIDO:
                frame_anterior_confiavel = False
                turn *= 0.85
                speed = config.VELOCIDADE_PERDIDO
            else:
                turn, speed = 0.0, 0.0
                pid.reset()

            # teto global (tunel, perfil urbano) -- vale pra TODO caminho
            speed = min(speed, nav.teto_velocidade())

            motor.move(speed, turn)

            t_cam += (t1 - t0); t_sign += (t2 - t1); t_vis += (t4 - t2)

            # ---------- 6. TELEMETRIA ---------------------------------
            frames += 1
            if time.time() - t_fps >= 2.0:
                fps_medido = frames / (time.time() - t_fps)
                st = "OK" if leitura_ok else (
                    f"DEGRADADO({res.motivo})" if res.valid else f"PERDIDO({res.motivo})")
                z = f" ZEBRA({zebra.linhas})" if zebra.presente else ""
                print(f"FPS {fps_medido:.1f} | {nav.hud()}{z} | erro {res.error:+.2f} "
                      f"| turn {turn:+.2f} | v {speed:.2f} | {st}")
                print(f"  {placas.hud()}")
                print(f"  custo -> cam {1000*t_cam/frames:.0f}ms  "
                      f"placas {1000*t_sign/frames:.0f}ms  faixa {1000*t_vis/frames:.0f}ms")
                frames, t_fps = 0, time.time()
                t_cam = t_vis = t_sign = 0.0

            if DEBUG:
                vis_placas = placas.detector.desenhar(frame_placas.copy())
                cv2.putText(vis_placas, nav.hud() + (" ZEBRA" if zebra.presente else ""), (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.imshow("Placas", vis_placas)
                if res.debug_view is not None:
                    cv2.imshow("Faixa", res.debug_view)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        print("\nParada de emergencia.")
    finally:
        motor.cleanup()
        cam_faixa.release()
        cam_placas.release()
        cv2.destroyAllWindows()
        print("\n--- placas obedecidas nesta execucao ---")
        print(nav.resumo())
        print("\nDesligado com seguranca.")


if __name__ == '__main__':
    main()
