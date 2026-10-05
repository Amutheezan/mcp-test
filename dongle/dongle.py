"""Dongle: a little animated character that hangs from the top-right corner of your screen.

Controls
  Left click ........ random reaction (wave, spin, laugh, swing)
  Double click ...... dance
  Drag left/right ... push the swing
  Hover ............. surprised look
  Right click ....... menu (animations, customize, photo face, start with Windows, quit)
  Left alone for 90s  he falls asleep. Click him to wake him up.
"""
import json
import math
import os
import random
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QMenu,
    QSystemTrayIcon,
    QWidget,
)

APP_NAME = "Dongle"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "skin": "#f1c27d",
    "hair": "#2b1b12",
    "shirt": "#3b82f6",
    "pants": "#1f2937",
    "hair_style": "short",  # short, spiky, long, bun, bald
    "glasses": True,
    "beard": False,
    "photo": "",  # optional path to a face photo
    "sprites": False,  # use the images in sprites/ instead of the drawn character
}

_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))  # _MEIPASS: PyInstaller bundle
SPRITE_DIR = _BASE / "sprites"
N_FRAMES = 9  # sprites/f_0.png .. f_8.png, cut from assets/sheet.png
FRAME_ANIMS = {  # state -> (frame indices, frames per second)
    "idle": ([0], 1),
    "swing": ([0], 1),
    "wave": ([1, 2], 4),
    "dance": ([2, 3, 6, 7], 5),
    "laugh": ([6, 7], 6),
    "spin": ([0, 4, 5, 4], 5),
    "surprised": ([3], 1),
    "sleep": ([8], 1),
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- startup (Windows)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    runner = pyw if pyw.exists() else exe
    return f'"{runner}" "{Path(__file__).resolve()}"'


def startup_enabled():
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except Exception:
        return False


def set_startup(enable):
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------- the character
class Dongle(QWidget):
    WIDTH, HEIGHT = 320, 300
    ANCHOR_X = 200
    ROPE = 40
    SCALE = 1.25

    DURATIONS = {
        "wave": 2.6,
        "dance": 4.2,
        "surprised": 1.3,
        "spin": 1.8,
        "laugh": 2.4,
        "swing": 3.2,
    }
    AUTO_CHOICES = ["wave", "dance", "laugh", "swing", "spin"]

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.photo = None
        self.load_photo()
        self.frames = []
        self.load_sprites()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.resize(self.WIDTH, self.HEIGHT)
        self.place()

        self.theta = 0.2
        self.omega = 0.0
        self.state = "idle"
        self.state_t = 0.0
        self.clock = 0.0
        self.last_active = 0.0
        self.next_blink = 2.0
        self.blink_until = 0.0
        self.next_auto = random.uniform(15, 30)
        self.next_breeze = 4.0
        self.next_hover = 0.0
        self.drag_last = None
        self.moved = False
        self.last_time = time.perf_counter()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    # ------------------------------------------------------------ setup helpers
    def place(self):
        geo = QApplication.primaryScreen().geometry()
        self.move(geo.x() + geo.width() - self.WIDTH, geo.y())

    def load_photo(self):
        self.photo = None
        path = self.cfg.get("photo")
        if path and Path(path).exists():
            pm = QPixmap(path)
            if not pm.isNull():
                self.photo = pm.scaled(
                    104, 100, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )

    def load_sprites(self):
        """Load frames; keep the x of the string at the top so we can swing about it."""
        self.frames = []
        for k in range(N_FRAMES):
            pm = QPixmap(str(SPRITE_DIR / f"f_{k}.png"))
            if pm.isNull():
                self.frames = []
                return
            img = pm.toImage()
            xs = [x for x in range(img.width()) for y in range(3)
                  if QColor(img.pixel(x, y)).alpha() > 128]
            self.frames.append((pm, sum(xs) / len(xs) if xs else img.width() / 2))

    def sprite_mode(self):
        return bool(self.cfg.get("sprites")) and bool(self.frames)

    def draw_sprite(self, p):
        seq, fps = FRAME_ANIMS.get(self.state, FRAME_ANIMS["idle"])
        pm, ax = self.frames[seq[int(self.state_t * fps) % len(seq)]]
        p.translate(self.ANCHOR_X, 0)
        p.rotate(math.degrees(self.theta))
        p.drawPixmap(QPointF(-ax, 0), pm)

    # ------------------------------------------------------------ state machine
    def set_state(self, name, user=False):
        self.state = name
        self.state_t = 0.0
        if user:
            self.last_active = self.clock
        sign = random.choice([-1, 1])
        if name == "swing":
            self.omega += 2.2 * sign
        elif name == "surprised":
            self.omega += 1.4 * sign
        elif name == "dance":
            self.omega += 0.8 * sign

    def user_trigger(self, name):
        self.last_active = self.clock
        if self.state == "sleep":
            self.set_state("surprised", user=True)
        else:
            self.set_state(name, user=True)

    def tick(self):
        now = time.perf_counter()
        dt = min(now - self.last_time, 0.05)
        self.last_time = now
        self.clock += dt
        self.state_t += dt

        dur = self.DURATIONS.get(self.state)
        if dur and self.state_t >= dur:
            self.set_state("idle")

        if self.state == "idle":
            if self.clock - self.last_active > 90:
                self.set_state("sleep")
            elif self.clock >= self.next_auto:
                self.set_state(random.choice(self.AUTO_CHOICES))
                self.next_auto = self.clock + random.uniform(20, 45)

        if self.state != "sleep" and self.clock >= self.next_breeze:
            self.omega += random.choice([-1, 1]) * random.uniform(0.3, 0.7)
            self.next_breeze = self.clock + random.uniform(6, 12)

        if self.clock >= self.next_blink:
            self.blink_until = self.clock + 0.13
            self.next_blink = self.clock + random.uniform(2, 5)

        self.physics(dt)
        self.update()

    def physics(self, dt):
        k, c = 14.0, 0.45
        if self.state == "sleep":
            c = 1.0
        if self.state == "swing" and self.state_t > 0.3:
            self.omega += (1.4 if self.omega >= 0 else -1.4) * dt
        if self.state == "dance":
            self.omega += math.sin(self.state_t * 8) * 0.5 * dt
        acc = -k * math.sin(self.theta) - c * self.omega
        self.omega = clamp(self.omega + acc * dt, -4.0, 4.0)
        self.theta += self.omega * dt
        if abs(self.theta) > 0.42:
            self.theta = math.copysign(0.42, self.theta)
            self.omega *= -0.3

    # ------------------------------------------------------------ pose per animation
    def pose(self):
        t, s = self.state_t, self.state
        dur = self.DURATIONS.get(s)
        env = clamp(min(t / 0.25, (dur - t) / 0.25), 0, 1) if dur else 1.0
        sway = math.sin(self.clock * 1.6)
        p = dict(
            la=8 + 3 * sway, lf=4, ra=8 - 3 * sway, rf=4,
            ll=3 * sway, rl=-3 * sway,
            bob=0.0, tilt=0.0, eyes="open", mouth="smile", spin=1.0, zzz=False,
        )

        if s == "wave":
            p["ra"] = lerp(p["ra"], 140, env)
            p["rf"] = lerp(p["rf"], 10 + 25 * math.sin(t * 13), env)
            p["tilt"] = 4 * env
        elif s == "dance":
            ph = t * 8
            p["la"] = lerp(p["la"], 100 + 55 * math.sin(ph), env)
            p["ra"] = lerp(p["ra"], 100 + 55 * math.sin(ph + math.pi), env)
            p["lf"] = 20 * math.sin(ph * 2) * env
            p["rf"] = -20 * math.sin(ph * 2) * env
            p["ll"] = lerp(p["ll"], -28 * max(0, math.sin(ph)), env)
            p["rl"] = lerp(p["rl"], 28 * max(0, -math.sin(ph)), env)
            p["bob"] = -4 * abs(math.sin(ph)) * env
            p["tilt"] = 6 * math.sin(ph) * env
            p["mouth"] = "open"
        elif s == "surprised":
            p["la"] = lerp(p["la"], 115, env)
            p["ra"] = lerp(p["ra"], 115, env)
            p["lf"] = p["rf"] = 10
            p["ll"] = lerp(p["ll"], -10, env)
            p["rl"] = lerp(p["rl"], 10, env)
            p["bob"] = -3 * env
            p["eyes"] = "wide"
            p["mouth"] = "o"
        elif s == "spin":
            p["la"] = lerp(p["la"], 75, env)
            p["ra"] = lerp(p["ra"], 75, env)
            p["spin"] = math.cos(t / dur * 4 * math.pi)
        elif s == "laugh":
            p["eyes"] = "happy"
            p["mouth"] = "open"
            p["bob"] = -3 * abs(math.sin(t * 10)) * env
            p["tilt"] = -5 * env
            arm = 25 + 8 * math.sin(t * 10)
            p["la"] = lerp(p["la"], arm, env)
            p["ra"] = lerp(p["ra"], arm, env)
        elif s == "swing":
            ph = t * 6
            p["la"] = lerp(p["la"], 70 + 20 * math.sin(ph), env)
            p["ra"] = lerp(p["ra"], 70 + 20 * math.sin(ph + 1), env)
            p["ll"] = lerp(p["ll"], 22 * math.sin(ph), env)
            p["rl"] = lerp(p["rl"], 22 * math.sin(ph + 0.6), env)
            p["eyes"] = "happy"
            p["mouth"] = "open"
        elif s == "sleep":
            p.update(la=3, ra=3, lf=0, rf=0, ll=0, rl=0, tilt=14,
                     eyes="closed", mouth="flat", zzz=True)
            p["bob"] = 1.5 * math.sin(self.clock * 1.5)

        if p["eyes"] == "open" and self.clock < self.blink_until:
            p["eyes"] = "closed"
        return p

    # ------------------------------------------------------------ drawing
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.sprite_mode():
            self.draw_sprite(p)
            p.end()
            return
        pose = self.pose()

        p.translate(self.ANCHOR_X, 0)
        p.rotate(math.degrees(self.theta))

        # string and ring
        p.setPen(QPen(QColor("#4b5563"), 2.2))
        p.drawLine(QPointF(0, 0), QPointF(0, self.ROPE))
        p.setPen(QPen(QColor("#d4a017"), 2.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(0, self.ROPE + 5), 5, 5)

        p.translate(0, self.ROPE + 10 + pose["bob"])
        p.scale(self.SCALE, self.SCALE)
        sx = pose["spin"]
        back = sx < 0
        if abs(sx) < 0.05:
            sx = 0.05
        p.scale(abs(sx), 1)
        self.draw_character(p, pose, back)
        p.end()

    def limb(self, p, x, y, ang, length, width, color):
        a = math.radians(ang)
        x2, y2 = x + math.sin(a) * length, y + math.cos(a) * length
        p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(x, y), QPointF(x2, y2))
        return x2, y2

    def draw_character(self, p, pose, back):
        cfg = self.cfg
        skin, shirt, pants = cfg["skin"], cfg["shirt"], cfg["pants"]

        # legs
        for side, ang in ((-1, pose["ll"]), (1, pose["rl"])):
            hx, hy = side * 9, 100
            kx, ky = self.limb(p, hx, hy, ang, 17, 10, pants)
            fx, fy = self.limb(p, kx, ky, ang * 0.6, 16, 9, pants)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#111827"))
            p.drawEllipse(QPointF(fx + side * 2, fy + 2), 7, 4)

        # waist and torso
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pants))
        p.drawRoundedRect(QRectF(-19, 92, 38, 14), 5, 5)
        p.setBrush(QColor(shirt))
        p.drawRoundedRect(QRectF(-21, 54, 42, 44), 12, 12)

        # arms
        for side, up, fore in ((-1, pose["la"], pose["lf"]), (1, pose["ra"], pose["rf"])):
            sxp, syp = side * 19, 63
            ex, ey = self.limb(p, sxp, syp, side * up, 14, 10, shirt)
            hx, hy = self.limb(p, ex, ey, side * (up + fore), 15, 8, skin)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(skin))
            p.drawEllipse(QPointF(hx, hy), 4.6, 4.6)

        self.draw_head(p, pose, back)

        if pose["zzz"]:
            font = QFont("Segoe UI")
            font.setBold(True)
            for i in range(3):
                ph = (self.clock * 0.6 + i / 3) % 1
                font.setPixelSize(int(9 + ph * 9))
                p.setFont(font)
                p.setPen(QColor(100, 116, 139, int((1 - ph) * 255)))
                p.drawText(QPointF(30 + ph * 14, 10 - ph * 40), "z")

    def draw_head(self, p, pose, back):
        cfg = self.cfg
        skin = QColor(cfg["skin"])
        hair = QColor(cfg["hair"])
        style = cfg["hair_style"]
        cx, cy = 0.0, 26.0

        p.save()
        p.translate(0, 52)
        p.rotate(pose["tilt"])
        p.translate(0, -52)

        p.setPen(Qt.NoPen)
        # neck
        p.setBrush(skin.darker(108))
        p.drawRoundedRect(QRectF(-6, 46, 12, 12), 3, 3)

        # long hair sits behind the head
        if style == "long":
            p.setBrush(hair)
            p.drawRoundedRect(QRectF(-29, 4, 58, 62), 22, 22)

        # ears
        p.setBrush(skin)
        p.drawEllipse(QPointF(-26, 28), 4, 5)
        p.drawEllipse(QPointF(26, 28), 4, 5)

        head_rect = QRectF(cx - 26, cy - 25, 52, 50)
        head_path = QPainterPath()
        head_path.addEllipse(head_rect)

        if back:
            p.setBrush(skin if style == "bald" else hair)
            p.drawEllipse(head_rect.adjusted(-1, -1, 1, 1))
            p.restore()
            return

        if self.photo is not None:
            p.setClipPath(head_path)
            sw, sh = self.photo.width(), self.photo.height()
            src = QRectF((sw - 104) / 2, (sh - 100) / 2, 104, 100)
            p.drawPixmap(head_rect, self.photo, src)
            p.setClipping(False)
            p.setPen(QPen(QColor(0, 0, 0, 60), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(head_rect)
            p.restore()
            return

        p.setBrush(skin)
        p.drawEllipse(head_rect)

        self.draw_hair(p, hair, style, cx, cy)
        self.draw_face(p, pose, hair)
        p.restore()

    def draw_hair(self, p, hair, style, cx, cy):
        if style == "bald":
            return
        p.setPen(Qt.NoPen)
        p.setBrush(hair)
        p.save()
        p.setClipRect(QRectF(-40, -30, 80, 48))
        p.drawEllipse(QPointF(cx, cy), 27.5, 26.5)
        p.restore()
        # side tufts
        p.drawEllipse(QPointF(-24, 20), 4, 8)
        p.drawEllipse(QPointF(24, 20), 4, 8)
        if style == "spiky":
            for i in range(-2, 3):
                x = i * 10
                p.drawPolygon(QPolygonF([
                    QPointF(x - 6, 6), QPointF(x, -10 + abs(i) * 3), QPointF(x + 6, 6)
                ]))
        elif style == "bun":
            p.drawEllipse(QPointF(0, -5), 9, 9)

    def draw_face(self, p, pose, hair):
        # where the eyes look (follow the mouse)
        cur = self.mapFromGlobal(QCursor.pos())
        lx = clamp((cur.x() - self.ANCHOR_X) / 60.0, -1, 1) * 2.5
        ly = clamp((cur.y() - (self.ROPE + 40)) / 60.0, -1, 1) * 2.0
        dark = QColor("#111827")
        ey = 28.0
        eyes = pose["eyes"]

        # beard (behind the mouth and eyes)
        if self.cfg["beard"]:
            full = QPainterPath()
            full.addEllipse(QPointF(0, 26), 26.5, 25.5)
            hole = QPainterPath()
            hole.addEllipse(QPointF(0, 38.5), 11, 6)
            p.save()
            p.setClipRect(QRectF(-40, 34, 80, 40))
            p.setPen(Qt.NoPen)
            p.setBrush(hair)
            p.drawPath(full.subtracted(hole))
            p.restore()

        # cheeks
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 110, 110, 60))
        p.drawEllipse(QPointF(-16, 37), 4.5, 3.2)
        p.drawEllipse(QPointF(16, 37), 4.5, 3.2)

        # eyebrows
        p.setPen(QPen(hair.darker(120) if hair.lightness() > 40 else hair, 2.2,
                      Qt.SolidLine, Qt.RoundCap))
        by = ey - 9 - (3 if eyes == "wide" else 0)
        for ex in (-9, 9):
            p.drawLine(QPointF(ex - 4.5, by), QPointF(ex + 4.5, by))

        # eyes
        for ex in (-9, 9):
            if eyes in ("open", "wide"):
                if eyes == "wide":
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor("white"))
                    p.drawEllipse(QPointF(ex, ey), 6.2, 6.2)
                    r = 3.2
                else:
                    r = 3.0
                p.setPen(Qt.NoPen)
                p.setBrush(dark)
                p.drawEllipse(QPointF(ex + lx, ey + ly), r, r + 0.6)
                p.setBrush(QColor("white"))
                p.drawEllipse(QPointF(ex + lx + 1, ey + ly - 1), 1.0, 1.0)
            else:
                path = QPainterPath()
                path.moveTo(ex - 4.5, ey + 1)
                bend = -4.5 if eyes == "happy" else 3.5
                path.quadTo(ex, ey + 1 + bend, ex + 4.5, ey + 1)
                p.setPen(QPen(dark, 2.0, Qt.SolidLine, Qt.RoundCap))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)

        # glasses
        if self.cfg["glasses"]:
            p.setPen(QPen(dark, 2.2))
            p.setBrush(QColor(255, 255, 255, 38))
            p.drawEllipse(QPointF(-9, ey), 8.2, 7.6)
            p.drawEllipse(QPointF(9, ey), 8.2, 7.6)
            p.drawLine(QPointF(-1, ey - 1), QPointF(1, ey - 1))
            p.drawLine(QPointF(-17, ey - 1), QPointF(-24, ey - 2))
            p.drawLine(QPointF(17, ey - 1), QPointF(24, ey - 2))

        # mouth
        mouth = pose["mouth"]
        mdark = QColor("#7f1d1d")
        if mouth == "smile":
            path = QPainterPath()
            path.moveTo(-7, 39)
            path.quadTo(0, 47, 7, 39)
            p.setPen(QPen(mdark, 2.0, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        elif mouth == "open":
            path = QPainterPath()
            path.moveTo(-7.5, 38)
            path.quadTo(0, 53, 7.5, 38)
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(mdark)
            p.drawPath(path)
            p.setBrush(QColor("#f87171"))
            p.drawEllipse(QPointF(0, 45.5), 3.6, 2.0)
        elif mouth == "o":
            p.setPen(Qt.NoPen)
            p.setBrush(mdark)
            p.drawEllipse(QPointF(0, 43), 4, 5)
        else:
            p.setPen(QPen(mdark, 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(-4, 42), QPointF(4, 42))

    # ------------------------------------------------------------ mouse
    def enterEvent(self, _event):
        if self.clock >= self.next_hover and self.state in ("idle", "sleep"):
            self.next_hover = self.clock + 8
            self.user_trigger("surprised")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_last = e.position()
            self.moved = False

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton and self.drag_last is not None:
            dx = e.position().x() - self.drag_last.x()
            if abs(dx) > 0:
                self.moved = True
            self.omega = clamp(self.omega + dx * 0.03, -4, 4)
            self.drag_last = e.position()
            self.last_active = self.clock

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and not self.moved:
            self.user_trigger(random.choice(["wave", "spin", "laugh", "swing"]))
        self.drag_last = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.user_trigger("dance")

    # ------------------------------------------------------------ menu
    def contextMenuEvent(self, e):
        self.build_menu().exec(e.globalPos())

    def build_menu(self):
        menu = QMenu(self)
        if self.frames:
            body = menu.addAction("Use image sprites")
            body.setCheckable(True)
            body.setChecked(bool(self.cfg.get("sprites")))
            body.triggered.connect(lambda v: self.set_option("sprites", bool(v)))
            menu.addSeparator()
        for label, name in (("Wave", "wave"), ("Dance", "dance"), ("Laugh", "laugh"),
                            ("Spin", "spin"), ("Swing", "swing"),
                            ("Surprise", "surprised"), ("Sleep", "sleep")):
            act = menu.addAction(label)
            act.triggered.connect(lambda _=False, n=name: self.menu_anim(n))
        menu.addSeparator()

        look = menu.addMenu("Customize")
        for label, key in (("Skin color...", "skin"), ("Hair color...", "hair"),
                           ("Shirt color...", "shirt"), ("Pants color...", "pants")):
            act = look.addAction(label)
            act.triggered.connect(lambda _=False, k=key, t=label: self.pick_color(k, t))

        styles = look.addMenu("Hair style")
        group = QActionGroup(styles)
        for style in ("short", "spiky", "long", "bun", "bald"):
            act = styles.addAction(style.capitalize())
            act.setCheckable(True)
            act.setChecked(self.cfg["hair_style"] == style)
            group.addAction(act)
            act.triggered.connect(lambda _=False, s=style: self.set_option("hair_style", s))

        glasses = look.addAction("Glasses")
        glasses.setCheckable(True)
        glasses.setChecked(self.cfg["glasses"])
        glasses.triggered.connect(lambda v: self.set_option("glasses", bool(v)))

        beard = look.addAction("Beard")
        beard.setCheckable(True)
        beard.setChecked(self.cfg["beard"])
        beard.triggered.connect(lambda v: self.set_option("beard", bool(v)))

        look.addSeparator()
        photo = look.addAction("Use my photo for the face...")
        photo.triggered.connect(self.choose_photo)
        if self.photo is not None:
            nophoto = look.addAction("Remove photo (use drawn face)")
            nophoto.triggered.connect(self.remove_photo)

        menu.addSeparator()
        start = menu.addAction("Start with Windows")
        start.setCheckable(True)
        start.setChecked(startup_enabled())
        start.setEnabled(sys.platform == "win32")
        start.triggered.connect(lambda v: set_startup(bool(v)))

        menu.addAction("Quit").triggered.connect(QApplication.quit)
        return menu

    def menu_anim(self, name):
        self.last_active = self.clock
        self.set_state(name, user=True)

    def pick_color(self, key, title):
        color = QColorDialog.getColor(QColor(self.cfg[key]), None, title)
        if color.isValid():
            self.set_option(key, color.name())

    def set_option(self, key, value):
        self.cfg[key] = value
        if key != "sprites":  # customizing only shows on the drawn character
            self.cfg["sprites"] = False
        save_config(self.cfg)
        self.update()

    def choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            None, "Choose a face photo", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.cfg["photo"] = path
            self.cfg["sprites"] = False
            save_config(self.cfg)
            self.load_photo()
            self.update()

    def remove_photo(self):
        self.cfg["photo"] = ""
        save_config(self.cfg)
        self.load_photo()
        self.update()


def tray_icon(cfg):
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(cfg["skin"]))
    p.drawEllipse(4, 4, 24, 24)
    p.setBrush(QColor(cfg["hair"]))
    p.drawChord(4, 4, 24, 24, 0, 180 * 16)
    p.end()
    return QIcon(pm)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()
    dongle = Dongle(cfg)
    dongle.show()

    tray = QSystemTrayIcon(tray_icon(cfg), app)
    tray.setToolTip(APP_NAME)
    tray_menu = QMenu()
    toggle = QAction("Show / hide", tray_menu)
    toggle.triggered.connect(lambda: dongle.setVisible(not dongle.isVisible()))
    tray_menu.addAction(toggle)
    tray_menu.addAction("Quit").triggered.connect(app.quit)
    tray.setContextMenu(tray_menu)
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
