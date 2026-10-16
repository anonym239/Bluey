package io.github.anonym239.bluey;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.os.SystemClock;
import android.view.View;

/** Das Querformat-Gesicht auf Schwarz: Er füllt den Bildschirm und lugt von unten herauf. */
final class FaceView extends View {
    /** Das Design ist für ein 844 × 390 Querformat-Handy gezeichnet. */
    static final float DESIGN_W = 844, DESIGN_H = 390;

    final FaceAnimator animator = new FaceAnimator();
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF body = new RectF();
    private final RectF tmp = new RectF();

    FaceView(Context context) {
        super(context);
        setContentDescription("Bluey. Doppelt tippen zum Aufwecken oder Schlafenlegen. Gedrückt halten, um etwas zu fragen.");
        stroke.setStyle(Paint.Style.STROKE);
        stroke.setStrokeCap(Paint.Cap.ROUND);
        stroke.setStrokeJoin(Paint.Join.ROUND);
    }

    static double now() { return SystemClock.elapsedRealtimeNanos() / 1e9; }

    /** Rechnet einen Bildschirmpunkt in Blickrichtung (−1…1) um, für den Finger auf dem Gesicht. */
    double[] gazeFor(float x, float y) {
        double gx = Math.max(-1, Math.min(1, (x - getWidth() / 2.0) / (getWidth() / 2.0)));
        double gy = Math.max(-1, Math.min(1, (y - getHeight() * .4) / (getHeight() / 2.0)));
        return new double[]{gx, gy};
    }

    @Override public boolean performClick() { super.performClick(); return true; }

    @Override protected void onDraw(Canvas canvas) {
        FaceAnimator.Frame f = animator.step(now());
        draw(f, canvas, getWidth(), getHeight());
        postInvalidateOnAnimation();
    }

    /** Füllt eine Form mit seiner Haut (Verlauf plus derselbe weiche Glanz), für Augenlider. */
    private void fillSkin(Canvas c, Path path) {
        paint.setShader(BlobShape.fill(body));
        c.drawPath(path, paint);
        paint.setShader(shine());
        c.drawPath(path, paint);
        paint.setShader(null);
    }

    private Shader shine() {
        return new RadialGradient(body.left + 246, body.top + 126, 243,
            new int[]{Color.argb(128, 255, 255, 255), Color.argb(0, 255, 255, 255)}, null, Shader.TileMode.CLAMP);
    }

    private void oval(float cx, float cy, float rx, float ry) { tmp.set(cx - rx, cy - ry, cx + rx, cy + ry); }

    void draw(FaceAnimator.Frame f, Canvas c, int width, int height) {
        c.drawColor(Color.BLACK);
        if (width <= 0 || height <= 0) return;
        float scale = Math.max(width / DESIGN_W, height / DESIGN_H);
        c.save();
        c.translate((width - DESIGN_W * scale) / 2, height - DESIGN_H * scale);
        c.scale(scale, scale);

        // Ganzkörperbewegung: Atmen, Sprech-Wippen, Hüpfer und Neigen Richtung Blick.
        float bounce = (float) (-f.talk * 16 + f.breathe * 3 - f.hop);
        body.set(12, 44 + bounce, 12 + 820, 44 + bounce + 700);
        float pivotX = body.centerX(), pivotY = body.bottom;
        c.translate(pivotX, pivotY);
        c.rotate((float) Math.toDegrees(f.lean));
        float stretch = (float) (1 + Math.min(.03, Math.max(-.03, f.hop / 900)));
        c.scale(2 - stretch, stretch);
        c.translate(-pivotX, -pivotY);

        Path blob = BlobShape.path(body);

        // Sanftes Leuchten um ihn herum.
        paint.setColor(Palette.BERRY3);
        paint.setShadowLayer(45, 0, -10, Palette.alpha(Palette.BERRY2, .5));
        c.drawPath(blob, paint);
        paint.clearShadowLayer();

        paint.setShader(BlobShape.fill(body));
        c.drawPath(blob, paint);
        c.save();
        c.clipPath(blob);
        paint.setShader(shine());
        c.drawPath(blob, paint);
        paint.setShader(null);
        // Ein kleiner Glanzpunkt auf dem Kopf.
        paint.setColor(Color.argb(89, 255, 255, 255));
        tmp.set(body.left + 190, body.top + 40, body.left + 236, body.top + 62);
        c.drawOval(tmp, paint);
        c.restore();

        int navy = Palette.NOSE, ink = Palette.INK;
        paint.setColor(navy);
        float crownY = (float) (body.top - 20 - f.browLift * .3);
        c.drawPath(BlobShape.crown(new RectF(body.left + 368, crownY, body.left + 452, crownY + 56)), paint);

        float eyeY = body.top + 157;
        float[][] eyes = {{body.left + 280, eyeY}, {body.left + 540, eyeY}};
        double squash = 1 - f.talk * .12;

        // Rosige Bäckchen, röter, wenn er sich freut.
        for (int i = 0; i < 2; i++) {
            float side = i == 0 ? -1 : 1;
            float cx = eyes[i][0] + side * 62, cy = eyes[i][1] + 96 + 21;
            int pink = Palette.alpha(0xFFF3A6D8, .25 + .45 * f.blush);
            paint.setShader(new RadialGradient(cx, cy, 55, new int[]{pink, pink, Color.argb(0, 243, 166, 216)},
                new float[]{0, .45f, 1}, Shader.TileMode.CLAMP));
            c.save();
            c.scale(1, .56f, cx, cy);
            oval(cx, cy, 58, 58);
            c.drawOval(tmp, paint);
            c.restore();
            paint.setShader(null);
        }

        for (int i = 0; i < 2; i++) {
            float side = i == 0 ? -1 : 1;
            float cx = eyes[i][0], cy = eyes[i][1];

            // Kleine geschwungene Augenbrauen machen viel vom Schauspiel.
            c.save();
            float browY = (float) (cy - 112 - Math.min(18, Math.max(-10, f.browLift)) * .7);
            c.translate(cx + side * 6, browY);
            double tilt = f.browTilt * side * -1 + (f.mood == Mood.THINKING && i == 1 ? -.25 : 0);
            c.rotate((float) Math.toDegrees(tilt));
            Path arch = new Path();
            arch.moveTo(-38, 6);
            arch.quadTo(0, -12, 38, 6);
            stroke.setColor(navy);
            stroke.setStrokeWidth(14);
            c.drawPath(arch, stroke);
            c.restore();

            if (f.mood == Mood.RESTING) {
                // Friedlich geschlossen: eine weiche Kurve nach unten.
                Path shut = new Path();
                shut.moveTo(cx - 62, cy + 6);
                shut.quadTo(cx, cy + 52, cx + 62, cy + 6);
                stroke.setColor(ink);
                stroke.setStrokeWidth(18);
                c.drawPath(shut, stroke);
                continue;
            }
            if (f.mood == Mood.HAPPY && f.squint > .6) {
                Path arc = new Path();
                arc.moveTo(cx - 60, cy + 34);
                arc.quadTo(cx, cy - 54, cx + 60, cy + 34);
                stroke.setColor(ink);
                stroke.setStrokeWidth(24);
                c.drawPath(arc, stroke);
                continue;
            }

            float open = (float) (Math.max(.06, 1 - f.closed) * squash);
            RectF white = new RectF(cx - 95, cy - 95 * open, cx + 95, cy + 95 * open);
            Path whitePath = new Path();
            whitePath.addOval(white, Path.Direction.CW);
            paint.setColor(Color.WHITE);
            c.drawPath(whitePath, paint);
            if (open <= .2) continue;

            double gx = f.gazeX, gy = f.gazeY;
            double len = Math.hypot(gx, gy);
            if (len > 1) { gx /= len; gy /= len; }
            float reach = 50;
            float r = (float) (46 * f.pupil);
            float px = (float) (cx + gx * reach - side * 3);
            float py = (float) (cy + gy * reach * open);
            if (f.mood == Mood.SLEEPY) py = Math.max(py, cy) + 28;  // Augen sinken unter schwere Lider

            c.save();
            c.clipPath(whitePath);
            paint.setColor(ink);
            oval(px, py, r, r);
            c.drawOval(tmp, paint);
            // Zwei Lichtpunkte bringen sie zum Glänzen.
            paint.setColor(Color.WHITE);
            tmp.set(px - r * .58f, py - r * .72f, px - r * .02f, py - r * .16f);
            c.drawOval(tmp, paint);
            paint.setColor(Color.argb(217, 255, 255, 255));
            tmp.set(px + r * .28f, py + r * .22f, px + r * .52f, py + r * .46f);
            c.drawOval(tmp, paint);
            // Fröhliche Bäckchen schieben sich beim Lächeln von unten hoch.
            if (f.squint > .02) {
                Path lid = new Path();
                float top = (float) (cy + 95 * open - 70 * f.squint);
                lid.addOval(new RectF(cx - 110, top, cx + 110, top + 160), Path.Direction.CW);
                fillSkin(c, lid);
            }
            // Schwere, hängende Lider, wenn er müde wird.
            if (f.mood == Mood.SLEEPY) {
                float droop = (float) (.5 + .06 * Math.sin(f.time * 1.3));
                Path lid = new Path();
                lid.addRect(cx - 100, white.top - 10, cx + 100, white.top + white.height() * droop, Path.Direction.CW);
                fillSkin(c, lid);
                stroke.setColor(Palette.alpha(navy, .7));
                stroke.setStrokeWidth(8);
                float ly = white.top + white.height() * droop;
                c.drawLine(cx - 92, ly, cx + 92, ly, stroke);
            }
            // Ein weiches Oberlid, wenn er sich aufs Zeigen konzentriert.
            if (f.mood == Mood.POINTING) {
                Path lid = new Path();
                lid.addRect(cx - 100, white.top - 20, cx + 100, white.top + 20, Path.Direction.CW);
                fillSkin(c, lid);
            }
            c.restore();
        }

        if (f.mood == Mood.RESTING) {
            // Kleine z's, die beim Nickerchen aufsteigen.
            paint.setTypeface(Fonts.display);
            paint.setTextAlign(Paint.Align.CENTER);
            for (int i = 0; i < 3; i++) {
                double phase = (f.time * .35 + i / 3.0) % 1;
                float size = 26 + i * 8;
                float x = (float) (body.left + 660 + phase * 70 + Math.sin(phase * 6) * 8);
                float y = (float) (body.top + 90 - phase * 110);
                paint.setTextSize(size);
                paint.setColor(Color.argb((int) (255 * .9 * Math.sin(Math.PI * phase)), 255, 255, 255));
                c.drawText("z", x, y + size * .35f, paint);
            }
        }

        if (f.mood == Mood.THINKING) {
            for (int i = 0; i < 3; i++) {
                double wobble = Math.sin(f.time * 3 + i) * 4;
                float x = body.left + 690 + i * 26 + 8, y = (float) (body.top + 40 - i * 12 + wobble + 8);
                paint.setColor(Color.argb((int) (255 * (1 - i * .3)), 255, 255, 255));
                c.drawCircle(x, y, 8, paint);
            }
        }

        // Sein kleiner Mund-Nase: öffnet sich beim Sprechen, wird zum Lächeln, wenn er sich freut.
        float noseW = (float) (60 - f.talk * 8);
        float noseH = (float) (38 + f.talk * 34);
        RectF nose = new RectF(body.left + 410 - noseW / 2, (float) (body.top + 272 - f.talk * 6), 0, 0);
        nose.right = nose.left + noseW;
        nose.bottom = nose.top + noseH;
        paint.setColor(navy);
        if (f.mood == Mood.HAPPY && f.talk < .1) {
            Path smile = new Path();
            smile.moveTo(nose.left - 8, nose.top + 8);
            smile.quadTo(nose.centerX(), nose.top + 58, nose.right + 8, nose.top + 8);
            smile.close();
            c.drawPath(smile, paint);
        } else {
            c.drawOval(nose, paint);
            if (f.talk > .25) {
                paint.setColor(Palette.alpha(0xFFE58BC4, .9));
                tmp.set(nose.centerX() - noseW * .28f, nose.bottom - noseH * .38f,
                    nose.centerX() + noseW * .28f, nose.bottom - noseH * .08f);
                c.drawOval(tmp, paint);
            }
        }
        c.restore();
    }
}
