"""Draws an 8-panel chibi anime-style character sheet (2048x1024, white background).

Run:  python make_sheet.py [output.png]
Needs: pip install PySide6
"""
import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QTransform,
)

OUT = QColor("#2b1a14")
SKIN = QColor("#c68b5f")
HAIR = QColor("#1b1a1f")
HAIR_HI = QColor(104, 112, 150, 170)
MOUTH = QColor("#6b1f1a")

W, H = 2048, 1024
CELL = 512


# ------------------------------------------------------------------ path helpers
def pt(a):
    return QPointF(a[0], a[1])


def stroke_path(a, b, w):
    path = QPainterPath()
    path.moveTo(pt(a))
    path.lineTo(pt(b))
    st = QPainterPathStroker()
    st.setWidth(w)
    st.setCapStyle(Qt.RoundCap)
    st.setJoinStyle(Qt.RoundJoin)
    return st.createStroke(path)


def limb_path(a, b, c, w):
    return stroke_path(a, b, w).united(stroke_path(b, c, w * 0.92))


def ellipse_path(cx, cy, rx, ry, ang=0.0):
    path = QPainterPath()
    path.addEllipse(QPointF(0, 0), rx, ry)
    tr = QTransform()
    tr.translate(cx, cy)
    tr.rotate(ang)
    return tr.map(path)


def rrect_path(x, y, w, h, r, ang=0.0):
    path = QPainterPath()
    path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), r, r)
    tr = QTransform()
    tr.translate(x + w / 2, y + h / 2)
    tr.rotate(ang)
    return tr.map(path)


def poly_path(points):
    path = QPainterPath()
    path.moveTo(pt(points[0]))
    for q in points[1:]:
        path.lineTo(pt(q))
    path.closeSubpath()
    return path


def shape(p, path, color, shade=0.16, outline=True, deco=None, width=3.0):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)
    if deco is not None:
        p.save()
        p.setClipPath(path)
        deco(p)
        p.restore()
    if shade:
        sh = path.subtracted(path.translated(-7, -6))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, int(255 * shade)))
        p.drawPath(sh)
    if outline:
        p.setPen(QPen(OUT, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)


def plaid_deco(line1, line2, step=15, ox=0, oy=0):
    def deco(p):
        p.setPen(QPen(QColor(*line1), 5))
        for i in range(-20, 40):
            x = ox + i * step
            p.drawLine(QPointF(x, -200), QPointF(x, 700))
        p.setPen(QPen(QColor(*line2), 5))
        for i in range(-20, 40):
            y = oy + i * step
            p.drawLine(QPointF(-200, y), QPointF(900, y))
    return deco


def quilt_deco(color=(80, 70, 55, 90), step=24):
    def deco(p):
        p.setPen(QPen(QColor(*color), 2.4))
        for i in range(-30, 40):
            p.drawLine(QPointF(i * step, -100), QPointF(i * step + 400, 700))
            p.drawLine(QPointF(i * step + 400, -100), QPointF(i * step, 700))
    return deco


def shadow(p, cx, cy, rx):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 26))
    p.drawEllipse(QPointF(cx, cy), rx, rx * 0.12)


def speed_lines(p, lines):
    p.setPen(QPen(QColor(176, 184, 196), 5, Qt.SolidLine, Qt.RoundCap))
    for x, y, length in lines:
        p.drawLine(QPointF(x, y), QPointF(x + length, y))


def sweat_drop(p, x, y, s=1.0):
    path = QPainterPath()
    path.moveTo(x, y - 13 * s)
    path.quadTo(x + 10 * s, y + 3 * s, x, y + 9 * s)
    path.quadTo(x - 10 * s, y + 3 * s, x, y - 13 * s)
    p.setPen(QPen(OUT, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor(125, 211, 252))
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 200))
    p.drawEllipse(QPointF(x - 2.5 * s, y + 1 * s), 2 * s, 3 * s)


# ------------------------------------------------------------------ body parts
def torso(p, top, bot, w, color, deco=None):
    path = stroke_path(top, bot, w)
    shape(p, path, color, deco=deco)
    return path


def hand(p, at, r=11):
    shape(p, ellipse_path(at[0], at[1], r, r), SKIN, shade=0.14)


def arm(p, sh, el, ha, w, sleeve, bare=False, deco=None):
    shape(p, limb_path(sh, el, ha, w), SKIN if bare else sleeve, deco=deco)
    hand(p, ha)


def shoe(p, at, color, rx=24, ry=12, ang=0.0, sole="#f8fafc"):
    shape(p, ellipse_path(at[0], at[1] + 3, rx + 1, ry, ang), sole, shade=0.0)
    shape(p, ellipse_path(at[0], at[1], rx, ry - 1, ang), color, shade=0.2)


def leg(p, hip, knee, foot, w, pant, shoe_color, shorts=False,
        shoe_rx=24, shoe_ry=12, shoe_ang=0.0, shoe_dx=0, shoe_dy=0, deco=None):
    if shorts:
        shape(p, limb_path(hip, knee, foot, w), SKIN)
        mid = (hip[0] + (knee[0] - hip[0]) * 0.78, hip[1] + (knee[1] - hip[1]) * 0.78)
        shape(p, stroke_path(hip, mid, w + 8), pant)
    else:
        shape(p, limb_path(hip, knee, foot, w), pant, deco=deco)
    shoe(p, (foot[0] + shoe_dx, foot[1] + shoe_dy), shoe_color, shoe_rx, shoe_ry, shoe_ang)


# ------------------------------------------------------------------ the head
def draw_eye(p, ex, ey, kind, look, sx):
    lx, ly = look
    if kind in ("normal", "wide", "think", "narrow", "sleepy"):
        rx, ry = (16, 19) if kind == "wide" else (14, 16)
        if kind == "narrow":
            ry = 11
        sclera = ellipse_path(ex, ey, rx, ry)
        shape(p, sclera, "#ffffff", shade=0.0, outline=False)
        irx, iry = (9.5, 12) if kind == "wide" else (10.5, 13)
        if kind == "narrow":
            iry = 10
        p.save()
        p.setClipPath(sclera)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#4a2a1b"))
        p.drawEllipse(QPointF(ex + lx, ey + ly + 1), irx, iry)
        p.setBrush(QColor("#140a06"))
        p.drawEllipse(QPointF(ex + lx, ey + ly + 1), irx * 0.55, iry * 0.58)
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawEllipse(QPointF(ex + lx - 4, ey + ly - 5), 3.8, 3.8)
        p.drawEllipse(QPointF(ex + lx + 4, ey + ly + 5), 1.9, 1.9)
        if kind == "sleepy":
            p.setBrush(SKIN)
            p.drawRect(QRectF(ex - 20, ey - 24, 40, 24))
        p.restore()
        top = QPainterPath()
        if kind == "sleepy":
            top.moveTo(ex - 14, ey - 1)
            top.lineTo(ex + 14, ey - 1)
        else:
            rect = QRectF(ex - rx, ey - ry, rx * 2, ry * 2)
            top.arcMoveTo(rect, 165)
            top.arcTo(rect, 165, -150)
        p.setPen(QPen(OUT, 4.6, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(top)
        p.drawLine(QPointF(ex + sx * 13, ey - 6), QPointF(ex + sx * 19, ey - 10))
    elif kind == "happy":
        path = QPainterPath()
        path.moveTo(ex - 13, ey + 4)
        path.quadTo(ex, ey - 15, ex + 13, ey + 4)
        p.setPen(QPen(OUT, 4.8, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    else:  # closed
        path = QPainterPath()
        path.moveTo(ex - 13, ey - 2)
        path.quadTo(ex, ey + 12, ex + 13, ey - 2)
        p.setPen(QPen(OUT, 4.4, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.drawLine(QPointF(ex + sx * 12, ey), QPointF(ex + sx * 18, ey - 3))


def draw_brow(p, ex, by, sx, inner, outer):
    ix, ox = ex - sx * 12, ex + sx * 15
    path = QPainterPath()
    path.moveTo(ix, by + inner)
    path.quadTo((ix + ox) / 2, by - 6 + (inner + outer) / 2, ox, by + outer)
    p.setPen(QPen(HAIR, 8, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


EXPR = {
    # eyes, brow_y, (inner, outer) left, (inner, outer) right, mouth
    "smile": ("normal", -22, (0, 1), (0, 1), "smile"),
    "grin": ("normal", -22, (3, -1), (3, -1), "grin"),
    "focus": ("narrow", -19, (8, -2), (8, -2), "gritted"),
    "wide": ("wide", -30, (-2, 2), (-2, 2), "o"),
    "sleepy_happy": ("sleepy", -19, (-2, 3), (-2, 3), "smile"),
    "think": ("think", -24, (-3, -9), (1, 2), "hmm"),
    "sleep": ("closed", -20, (-1, 2), (-1, 2), "sleepsmile"),
    "determined": ("normal", -22, (6, -1), (6, -1), "grin"),
}


def draw_mouth(p, kind):
    pen = QPen(OUT, 3.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    path = QPainterPath()
    if kind == "smile":
        path.moveTo(-12, 40)
        path.quadTo(0, 53, 12, 40)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    elif kind == "sleepsmile":
        path.moveTo(-8, 44)
        path.quadTo(0, 51, 8, 44)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    elif kind == "hmm":
        path.moveTo(-9, 45)
        path.quadTo(-3, 40, 2, 44)
        path.quadTo(7, 48, 11, 43)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    elif kind in ("grin", "o"):
        if kind == "grin":
            path.moveTo(-18, 38)
            path.quadTo(0, 68, 18, 38)
            path.closeSubpath()
        else:
            path.addEllipse(QPointF(0, 47), 9, 12)
        p.setPen(Qt.NoPen)
        p.setBrush(MOUTH)
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        if kind == "grin":
            p.setBrush(QColor("#ffffff"))
            p.drawRect(QRectF(-24, 34, 48, 12))
        p.setBrush(QColor("#f08a8a"))
        p.drawEllipse(QPointF(0, 58), 10, 6)
        p.restore()
        p.setPen(QPen(OUT, 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    elif kind == "gritted":
        box = QPainterPath()
        box.addRoundedRect(QRectF(-16, 39, 32, 13), 5, 5)
        shape(p, box, "#ffffff", shade=0.0, width=3.2)
        p.setPen(QPen(OUT, 2.2))
        for x in (-8, 0, 8):
            p.drawLine(QPointF(x, 40), QPointF(x, 51))
        p.drawLine(QPointF(-16, 45.5), QPointF(16, 45.5))


def head(p, cx, cy, tilt=0.0, expr="smile", look=(2, 0), headphones=False, scale=1.0):
    eyes, by, br_l, br_r, mouth = EXPR[expr]
    p.save()
    p.translate(cx, cy)
    p.rotate(tilt)
    p.scale(scale, scale)

    # ears
    for sx in (-1, 1):
        shape(p, ellipse_path(sx * 65, 8, 11, 16), SKIN, shade=0.12)
        shape(p, ellipse_path(sx * 66, 9, 5, 9), SKIN.darker(118), shade=0.0, outline=False)

    face = QPainterPath()
    face.addEllipse(QPointF(0, 0), 66, 58)
    shape(p, face, SKIN, shade=0.18)

    # stubble beard
    clip = QPainterPath()
    clip.addRect(QRectF(-80, 18, 160, 80))
    beard = face.intersected(clip)
    dip = QPainterPath()
    dip.addEllipse(QPointF(0, 8), 52, 22)
    beard = beard.subtracted(dip)
    lips = QPainterPath()
    lips.addEllipse(QPointF(0, 44), 20, 11)
    beard = beard.subtracted(lips)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(38, 30, 30, 125))
    p.drawPath(beard)
    # mustache
    must = QPainterPath()
    must.moveTo(-20, 28)
    must.quadTo(-8, 22, 0, 26)
    must.quadTo(8, 22, 20, 28)
    must.quadTo(14, 36, 0, 32)
    must.quadTo(-14, 36, -20, 28)
    p.setBrush(QColor(30, 24, 26, 175))
    p.drawPath(must)

    # blush
    p.setBrush(QColor(235, 120, 105, 55))
    for sx in (-1, 1):
        p.drawEllipse(QPointF(sx * 42, 20), 10, 6)

    # nose
    nose = QPainterPath()
    nose.moveTo(-4, 15)
    nose.quadTo(0, 21, 5, 15)
    p.setPen(QPen(QColor(112, 66, 44), 2.8, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawPath(nose)

    # eyes and brows
    for sx, br in ((-1, br_l), (1, br_r)):
        draw_eye(p, sx * 27, 4, eyes, look, sx)
        draw_brow(p, sx * 27, by, sx, br[0], br[1])

    draw_mouth(p, mouth)

    # hair
    ell = QPainterPath()
    ell.addEllipse(QPointF(0, -8), 72, 66)
    region = poly_path([
        (-90, -100), (90, -100), (90, -6), (65, -6), (60, -26), (42, -34),
        (26, -22), (8, -34), (-8, -22), (-26, -36), (-42, -22), (-60, -30),
        (-65, -6), (-90, -6),
    ])
    hair = ell.intersected(region)
    shape(p, hair, HAIR, shade=0.0, width=3.2)
    for sx in (-1, 1):
        shape(p, ellipse_path(sx * 61, 3, 8, 21), HAIR, shade=0.0, width=2.6)
    p.setBrush(Qt.NoBrush)
    for pts in (((-34, -56), (-14, -66), (8, -60)), ((14, -54), (34, -58), (50, -46)),
                ((-52, -36), (-44, -50), (-34, -50))):
        hi = QPainterPath()
        hi.moveTo(*pts[0])
        hi.quadTo(*pts[1], *pts[2])
        p.setPen(QPen(HAIR_HI, 5, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(hi)

    if headphones:
        band = QPainterPath()
        rect = QRectF(-77, -84, 154, 150)
        band.arcMoveTo(rect, 6)
        band.arcTo(rect, 6, 168)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(OUT, 14, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(band)
        p.setPen(QPen(QColor("#3a3d47"), 9, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(band)
        for sx in (-1, 1):
            shape(p, rrect_path(sx * 70 - 11, -10, 22, 40, 10), "#e11d48", shade=0.2)
    p.restore()


# ------------------------------------------------------------------ props
def desk(p):
    for x in (146, 354):
        shape(p, rrect_path(x, 366, 14, 64, 4), "#ffffff", shade=0.06)
    top = poly_path([(112, 352), (144, 318), (368, 318), (400, 352)])
    shape(p, top, "#f1f3f6", shade=0.06)
    shape(p, rrect_path(112, 352, 288, 14, 5), "#ffffff", shade=0.06)


def hood(p, cx, cy, color, rx=40, ry=19, ang=0.0, deco=None):
    shape(p, ellipse_path(cx, cy, rx, ry, ang), color, deco=deco)


# ------------------------------------------------------------------ panels
def panel_jog(p):
    gray, pants = "#9ca3af", "#4b5563"
    shadow(p, 252, 430, 84)
    speed_lines(p, [(54, 236, 80), (28, 272, 100), (66, 308, 84)])
    leg(p, (236, 318), (206, 350), (170, 378), 26, pants, "#f3f4f6", shoe_ang=-30)
    arm(p, (240, 252), (202, 274), (184, 246), 21, gray)
    torso(p, (262, 242), (246, 318), 66, gray)
    hood(p, 268, 236, "#8b929e", ang=-10)
    p.setPen(QPen(QColor("#f8fafc"), 3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(266, 252), QPointF(264, 286))
    p.drawLine(QPointF(278, 252), QPointF(280, 284))
    leg(p, (256, 318), (298, 340), (302, 394), 26, pants, "#f3f4f6", shoe_ang=8, shoe_dx=10, shoe_dy=4)
    head(p, 282, 176, tilt=6, expr="smile", look=(4, 0))
    arm(p, (280, 252), (314, 278), (338, 248), 21, gray)
    sweat_drop(p, 206, 130)
    sweat_drop(p, 188, 160, 0.7)


def panel_walk(p):
    shirt, jeans = "#3b6fd4", "#3f5f9a"
    plaid = plaid_deco((20, 40, 120, 130), (255, 255, 255, 80), ox=232, oy=236)
    shadow(p, 258, 428, 84)
    leg(p, (244, 318), (232, 362), (222, 410), 26, jeans, "#f3f4f6", shoe_ang=0, shoe_dx=-2)
    arm(p, (228, 250), (214, 286), (206, 320), 21, shirt)
    torso(p, (257, 242), (257, 318), 66, shirt, deco=plaid)
    leg(p, (270, 318), (286, 360), (308, 406), 26, jeans, "#f3f4f6", shoe_ang=-8, shoe_dx=8, shoe_dy=2)
    head(p, 256, 176, tilt=-2, expr="smile", look=(3, 1), headphones=True)
    arm(p, (286, 250), (306, 286), (318, 314), 21, shirt)
    p.setPen(QPen(QColor(150, 158, 170), 4, Qt.SolidLine, Qt.RoundCap))
    for (x, y, d) in ((356, 150, 0), (376, 128, 8)):
        n = QPainterPath()
        n.moveTo(x, y + 18)
        n.lineTo(x, y)
        n.lineTo(x + 14, y - 4)
        n.lineTo(x + 14, y + 14)
        p.setBrush(Qt.NoBrush)
        p.drawPath(n)
        p.setBrush(QColor(150, 158, 170))
        p.drawEllipse(QPointF(x - 5, y + 19), 5, 4)
        p.drawEllipse(QPointF(x + 9, y + 15), 5, 4)


def panel_sprint(p):
    red, shorts, blue = "#e53935", "#16181d", "#2563eb"
    shadow(p, 240, 430, 100)
    speed_lines(p, [(30, 214, 120), (10, 252, 150), (40, 290, 120), (24, 328, 130), (60, 366, 100)])
    leg(p, (232, 318), (188, 350), (132, 330), 27, shorts, blue, shorts=True,
        shoe_ang=-50, shoe_rx=26, shoe_dx=-6, shoe_dy=-2)
    arm(p, (258, 254), (218, 276), (194, 244), 21, red, bare=True)
    torso(p, (272, 240), (236, 316), 64, red)
    leg(p, (248, 318), (320, 318), (342, 374), 27, shorts, blue, shorts=True,
        shoe_ang=15, shoe_rx=26, shoe_dx=10, shoe_dy=6)
    head(p, 296, 172, tilt=14, expr="focus", look=(6, 0))
    arm(p, (290, 252), (326, 286), (354, 248), 21, red, bare=True)
    sweat_drop(p, 216, 120)
    sweat_drop(p, 196, 150, 0.7)
    sweat_drop(p, 384, 130, 0.8)


def panel_pushups(p):
    gray, pants = "#8d939b", "#1f2937"
    shape(p, rrect_path(56, 404, 408, 24, 11), "#3b82f6", shade=0.18)
    arm(p, (330, 338), (338, 372), (338, 404), 21, gray)
    leg(p, (268, 352), (196, 372), (126, 394), 27, pants, "#e5e7eb",
        shoe_rx=14, shoe_ry=24, shoe_ang=-15, shoe_dx=-4, shoe_dy=2)
    torso(p, (344, 332), (268, 354), 58, gray)
    arm(p, (352, 336), (362, 372), (360, 404), 21, gray)
    head(p, 396, 296, tilt=-12, expr="determined", look=(6, 2))
    sweat_drop(p, 330, 232)
    p.setPen(QPen(QColor(176, 184, 196), 5, Qt.SolidLine, Qt.RoundCap))
    for i in range(3):
        p.drawLine(QPointF(222 + i * 28, 296), QPointF(222 + i * 28, 318))


def panel_coding(p):
    shirt, jeans = "#c2413a", "#3f5f9a"
    plaid = plaid_deco((60, 10, 10, 140), (255, 230, 210, 70), ox=244, oy=240)
    shadow(p, 256, 432, 120)
    for x in (236, 278):
        leg(p, (x, 350), (x, 384), (x, 412), 26, jeans, "#f3f4f6")
    torso(p, (257, 242), (257, 336), 66, shirt, deco=plaid)
    head(p, 256, 178, expr="sleepy_happy", look=(0, 2))
    arm(p, (226, 252), (204, 300), (228, 332), 21, shirt)
    arm(p, (288, 252), (310, 300), (286, 332), 21, shirt)
    desk(p)
    # mug
    shape(p, rrect_path(338, 294, 32, 34, 7), "#f59e0b", shade=0.2)
    handle = QPainterPath()
    handle.addEllipse(QPointF(372, 311), 9, 10)
    p.setPen(QPen(OUT, 8, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawPath(handle)
    p.setPen(QPen(QColor("#f59e0b"), 4, Qt.SolidLine, Qt.RoundCap))
    p.drawPath(handle)
    shape(p, rrect_path(338, 294, 32, 34, 7), "#f59e0b", shade=0.2)
    p.setPen(QPen(QColor(176, 184, 196), 4, Qt.SolidLine, Qt.RoundCap))
    for x in (346, 360):
        s = QPainterPath()
        s.moveTo(x, 288)
        s.quadTo(x - 7, 276, x, 266)
        s.quadTo(x + 7, 256, x, 246)
        p.drawPath(s)
    # laptop (back of the lid faces us)
    shape(p, rrect_path(184, 262, 144, 68, 9), "#9ca3af", shade=0.2)
    shape(p, rrect_path(172, 326, 168, 11, 5), "#6b7280", shade=0.2)
    hand(p, (230, 332))
    hand(p, (284, 332))


def panel_movie(p):
    tee, jeans = "#6b8e7f", "#3f5f9a"
    shadow(p, 256, 432, 150)
    shape(p, rrect_path(112, 226, 288, 130, 36), "#f7f8fa", shade=0.1)
    shape(p, rrect_path(96, 276, 54, 146, 24), "#eef1f5", shade=0.1)
    shape(p, rrect_path(362, 276, 54, 146, 24), "#eef1f5", shade=0.1)
    torso(p, (257, 252), (257, 352), 66, tee)
    head(p, 256, 192, expr="wide", look=(6, -3))
    shape(p, rrect_path(100, 376, 312, 46, 14), "#eef1f5", shade=0.1)
    shape(p, rrect_path(124, 330, 264, 58, 24), "#ffffff", shade=0.08)
    for x in (238, 276):
        leg(p, (x, 356), (x - 4, 390), (x - 6, 420), 26, jeans, "#f3f4f6")
    # bucket
    bucket = poly_path([(212, 338), (300, 338), (290, 408), (222, 408)])

    def stripes(pp):
        pp.setPen(Qt.NoPen)
        pp.setBrush(QColor("#e11d48"))
        for i in range(0, 8, 2):
            pp.drawRect(QRectF(206 + i * 12.5, 330, 12.5, 90))

    shape(p, bucket, "#ffffff", shade=0.12, deco=stripes)
    for (x, y, r) in ((228, 326, 13), (250, 318, 14), (274, 322, 13), (240, 334, 11),
                      (262, 332, 12), (288, 332, 11)):
        shape(p, ellipse_path(x, y, r, r), "#fff1c1", shade=0.18, width=2.4)
    shape(p, ellipse_path(256, 340, 44, 9), "#ffffff", shade=0.0, width=3, outline=True)
    for (x, y, r) in ((322, 290, 8), (190, 282, 7), (300, 262, 6)):
        shape(p, ellipse_path(x, y, r, r), "#fff1c1", shade=0.18, width=2.2)
    arm(p, (228, 254), (198, 314), (214, 366), 21, tee)
    arm(p, (286, 254), (316, 314), (300, 366), 21, tee)
    p.setPen(QPen(QColor(100, 116, 139), 4, Qt.SolidLine, Qt.RoundCap))
    for (a, b) in (((172, 150), (186, 160)), ((160, 190), (178, 192)), ((178, 112), (190, 130)),
                   ((342, 150), (328, 160)), ((354, 190), (336, 192)), ((334, 112), (322, 130))):
        p.drawLine(QPointF(*a), QPointF(*b))


def panel_writing(p):
    sweater, jeans = "#4f9d69", "#3f5f9a"
    shadow(p, 256, 432, 120)
    for x in (236, 278):
        leg(p, (x, 350), (x, 384), (x, 412), 26, jeans, "#f3f4f6")
    torso(p, (257, 244), (257, 336), 66, sweater)
    head(p, 250, 186, tilt=-8, expr="think", look=(-4, 6))
    arm(p, (226, 254), (204, 302), (222, 336), 21, sweater)
    arm(p, (288, 254), (308, 302), (292, 336), 21, sweater)
    desk(p)
    book = poly_path([(186, 348), (312, 348), (330, 322), (204, 322)])
    shape(p, book, "#ffffff", shade=0.08)
    p.setPen(QPen(QColor(160, 170, 185), 2.4))
    for i in range(4):
        y = 328 + i * 5
        p.drawLine(QPointF(212 - i * 3.5 + 6, y), QPointF(318 - i * 3.5 + 6, y))
    p.setPen(QPen(OUT, 10, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(294, 334), QPointF(326, 302))
    p.setPen(QPen(QColor("#1d4ed8"), 6, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(294, 334), QPointF(326, 302))
    hand(p, (222, 338))
    hand(p, (294, 336))
    for (x, y, r) in ((330, 148, 6), (350, 124, 9), (378, 90, 14)):
        shape(p, ellipse_path(x, y, r, r), "#ffffff", shade=0.0, width=2.4)


def panel_sleep(p):
    taupe = "#c8bba4"
    quilt = quilt_deco()
    shadow(p, 250, 432, 170)
    shape(p, rrect_path(70, 352, 176, 76, 28), "#fff7e6", shade=0.14)
    leg(p, (352, 374), (414, 388), (386, 416), 28, "#6b7280", "#f3f4f6",
        shoe_rx=20, shoe_ry=11, shoe_ang=0)
    torso(p, (232, 360), (354, 372), 72, taupe, deco=quilt)
    hood(p, 236, 352, "#b9ab92", rx=24, ry=42, ang=8, deco=quilt)
    shape(p, rrect_path(268, 330, 122, 92, 30, ang=-8), "#dbeafe", shade=0.14)
    arm(p, (246, 362), (300, 338), (338, 384), 24, taupe, deco=quilt)
    head(p, 158, 322, tilt=-90, expr="sleep")
    f = QFont("DejaVu Sans")
    f.setBold(True)
    f.setItalic(True)
    p.setPen(QColor("#475569"))
    for (x, y, s) in ((112, 262, 30), (84, 222, 38), (58, 172, 48)):
        f.setPixelSize(s)
        p.setFont(f)
        p.drawText(QPointF(x, y), "z")


PANELS = [
    ("MORNING JOG", panel_jog),
    ("CITY WALK", panel_walk),
    ("SPRINT", panel_sprint),
    ("PUSH-UPS", panel_pushups),
    ("CODING", panel_coding),
    ("MOVIE NIGHT", panel_movie),
    ("WRITING", panel_writing),
    ("SLEEPING", panel_sleep),
]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "character_sheet.png"
    app = QGuiApplication.instance() or QGuiApplication([])
    img = QImage(W, H, QImage.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    font = QFont("DejaVu Sans")
    font.setBold(True)
    font.setPixelSize(30)
    for i, (title, fn) in enumerate(PANELS):
        col, row = i % 4, i // 4
        p.save()
        p.translate(col * CELL, row * CELL)
        p.setClipRect(QRectF(0, 0, CELL, CELL))
        fn(p)
        p.setClipping(False)
        p.setFont(font)
        p.setPen(QColor("#000000"))
        p.drawText(QRectF(0, 452, CELL, 44), Qt.AlignCenter, title)
        p.restore()
    p.end()
    img.save(out)
    print("saved", out, img.width(), img.height())


if __name__ == "__main__":
    main()
