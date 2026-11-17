"""PIL ressamı: BlendCAD şerit / pencere çizim kodunu Blender'sız PNG'ye döker.

ribbon_preview.py ve bpy_model_check.py kullanır. Blender'daki GPUPainter ile aynı arayüz:
rect / outline / lines / tri / circle / text / measure (koordinat: sol alt 0,0, y yukarı).
"""
import math

from PIL import Image, ImageDraw, ImageFont

SS = 2                                   # süper örnekleme
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class PILPainter:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * SS, h * SS), (57, 57, 57))
        self.d = ImageDraw.Draw(self.img, "RGBA")
        self._fonts = {}

    def _c(self, c):
        return tuple(int(max(0, min(1, v)) * 255) for v in c)

    def _x(self, x):
        return x * SS

    def _y(self, y):
        return (self.h - y) * SS

    def font(self, size, bold=False):
        k = (size, bold)
        if k not in self._fonts:
            self._fonts[k] = ImageFont.truetype(FONT_B if bold else FONT, int(size * SS * 0.92))
        return self._fonts[k]

    def rect(self, x0, y0, x1, y1, col, r=0):
        box = [self._x(x0), self._y(y1), self._x(x1), self._y(y0)]
        if box[2] <= box[0] or box[3] <= box[1]:
            return
        if r:
            self.d.rounded_rectangle(box, radius=r * SS, fill=self._c(col))
        else:
            self.d.rectangle(box, fill=self._c(col))

    def outline(self, x0, y0, x1, y1, col, r=0, width=1.0):
        box = [self._x(x0), self._y(y1), self._x(x1), self._y(y0)]
        self.d.rounded_rectangle(box, radius=r * SS, outline=self._c(col), width=int(width * SS))

    def lines(self, seg, col, width):
        c = self._c(col)
        for i in range(0, len(seg) - 1, 2):
            a, b = seg[i], seg[i + 1]
            self.d.line([(self._x(a[0]), self._y(a[1])), (self._x(b[0]), self._y(b[1]))], fill=c,
                        width=max(1, int(width * SS)))

    def tri(self, pts, col):
        self.d.polygon([(self._x(x), self._y(y)) for x, y in pts], fill=self._c(col))

    def circle(self, cx, cy, r, col):
        self.d.ellipse([self._x(cx - r), self._y(cy + r), self._x(cx + r), self._y(cy - r)],
                       fill=self._c(col))

    def text(self, x, y, txt, col, size, bold=False):
        self.d.text((self._x(x), self._y(y)), txt, font=self.font(size, bold), fill=self._c(col),
                    anchor="ls")

    def measure(self, txt, size, bold=False):
        f = self.font(size, bold)
        l, t, r, b = f.getbbox(txt)
        return ((r - l) / SS, (b - t) / SS)

    def viewport(self):
        """Blender görünümüne benzer zemin: ızgara, eksenler, başlık şeridi."""
        d = self.d
        w, h = self.w, self.h
        for gx in range(0, w, 40):
            d.line([(gx * SS, 0), (gx * SS, h * SS)], fill=(66, 66, 66), width=1)
        for gy in range(0, h, 40):
            d.line([(0, gy * SS), (w * SS, gy * SS)], fill=(66, 66, 66), width=1)
        d.line([(0, h * 0.62 * SS), (w * SS, h * 0.62 * SS)], fill=(150, 60, 60), width=2)
        d.line([(w * 0.45 * SS, 0), (w * 0.45 * SS, h * SS)], fill=(90, 140, 40), width=2)
        # gezinme gizmosu
        cx, cy, r = (w - 52), 52, 38
        d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS],
                  fill=(255, 255, 255, 18))
        for ang, col in ((0, (230, 70, 80)), (240, (110, 170, 30)), (90, (60, 130, 230))):
            ex = cx + 28 * math.cos(math.radians(ang))
            ey = cy - 28 * math.sin(math.radians(ang))
            d.line([(cx * SS, cy * SS), (ex * SS, ey * SS)], fill=col, width=3)
            d.ellipse([(ex - 8) * SS, (ey - 8) * SS, (ex + 8) * SS, (ey + 8) * SS], fill=col)

    def headers(self, top):
        """Saydam başlık + araç başlığı (Blender 4.x / 5.x bölge örtüşmesi) ve araç çubuğu."""
        d, w, h = self.d, self.w, self.h
        d.rectangle([0, 0, w * SS, top * SS], fill=(48, 48, 48, 235))
        d.line([(0, 26 * SS), (w * SS, 26 * SS)], fill=(40, 40, 40), width=SS)
        f = self.font(11)
        x = 12
        for t in ("Object Mode", "View", "Select", "Add", "Object"):
            d.text((x * SS, 18 * SS), t, font=f, fill=(210, 210, 210), anchor="ls")
            x += self.measure(t, 11)[0] + 18
        x = 12
        for t in ("Global", "Snap", "Options"):
            d.text((x * SS, 44 * SS), t, font=f, fill=(190, 190, 190), anchor="ls")
            x += self.measure(t, 11)[0] + 26
        d.rectangle([4 * SS, (top + 6) * SS, 40 * SS, (top + 150) * SS], fill=(45, 45, 45, 230))
        for k in range(4):
            y = top + 12 + k * 34
            d.rectangle([9 * SS, y * SS, 35 * SS, (y + 26) * SS], fill=(70, 70, 70))

    def save(self, path):
        self.img.resize((self.w * SS // 2 * 2 // SS * 1, self.h), Image.LANCZOS) if False else None
        self.img.save(path)
