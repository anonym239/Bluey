package io.github.anonym239.bluey;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.view.View;

/** Kleine Symbole, mit Pfaden gezeichnet (in einer 24×24-Box). */
final class Icons {
    enum Kind { EYE, EAR, MIC, SPARKLES, BUBBLE, SUN, SPEAKER, SPEAKER_OFF, GRID, CLOSE, PLAY, STOP, CHECK, DOTS,
        BACK, SHARE, COPY, SEARCH, DOC, SMILE, GEAR, PLUS, MINUS, UP }

    static void draw(Canvas c, Kind kind, float cx, float cy, float size, int color) {
        Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
        fill.setColor(color);
        Paint line = new Paint(Paint.ANTI_ALIAS_FLAG);
        line.setColor(color);
        line.setStyle(Paint.Style.STROKE);
        line.setStrokeCap(Paint.Cap.ROUND);
        line.setStrokeJoin(Paint.Join.ROUND);
        line.setStrokeWidth(2.2f);
        c.save();
        c.translate(cx - size / 2, cy - size / 2);
        c.scale(size / 24f, size / 24f);
        Path p = new Path();
        switch (kind) {
            case EYE:
                p.moveTo(2, 12); p.quadTo(12, 2, 22, 12); p.quadTo(12, 22, 2, 12); p.close();
                c.drawPath(p, fill);
                Paint hole = new Paint(Paint.ANTI_ALIAS_FLAG);
                hole.setColor(0xFF000000);
                c.drawCircle(12, 12, 4, hole);
                c.drawCircle(12, 12, 2.2f, fill);
                break;
            case EAR:
                p.moveTo(7, 10); p.cubicTo(7, 3, 18, 3, 18, 10); p.cubicTo(18, 14, 14, 15, 13, 18);
                p.cubicTo(12, 21, 8, 21, 8, 18);
                c.drawPath(p, line);
                Path inner = new Path();
                inner.moveTo(10, 10); inner.cubicTo(10, 6, 15, 6, 15, 10); inner.cubicTo(15, 12, 13, 12, 12, 14);
                c.drawPath(inner, line);
                break;
            case MIC:
                c.drawRoundRect(new RectF(8.5f, 2, 15.5f, 14), 3.5f, 3.5f, fill);
                p.moveTo(5, 11); p.cubicTo(5, 19, 19, 19, 19, 11);
                c.drawPath(p, line);
                c.drawLine(12, 17, 12, 22, line);
                break;
            case SPARKLES:
                star(c, fill, 9, 13, 7);
                star(c, fill, 18, 6, 4);
                star(c, fill, 18, 18, 3);
                break;
            case BUBBLE:
                c.drawRoundRect(new RectF(2, 3, 22, 17), 6, 6, fill);
                p.moveTo(6, 15); p.lineTo(5, 22); p.lineTo(12, 16); p.close();
                c.drawPath(p, fill);
                break;
            case SUN:
                c.drawCircle(12, 12, 5, fill);
                for (int i = 0; i < 8; i++) {
                    double a = i * Math.PI / 4;
                    c.drawLine((float) (12 + Math.cos(a) * 8), (float) (12 + Math.sin(a) * 8),
                        (float) (12 + Math.cos(a) * 10.5), (float) (12 + Math.sin(a) * 10.5), line);
                }
                break;
            case SPEAKER:
            case SPEAKER_OFF:
                p.moveTo(3, 9); p.lineTo(7, 9); p.lineTo(12, 4); p.lineTo(12, 20); p.lineTo(7, 15); p.lineTo(3, 15); p.close();
                c.drawPath(p, fill);
                if (kind == Kind.SPEAKER) {
                    c.drawArc(new RectF(10, 8, 18, 16), -50, 100, false, line);
                    c.drawArc(new RectF(9, 4, 22, 20), -50, 100, false, line);
                } else {
                    c.drawLine(15, 9, 21, 15, line);
                    c.drawLine(21, 9, 15, 15, line);
                }
                break;
            case GRID:
                for (int x = 0; x < 2; x++) for (int y = 0; y < 2; y++)
                    c.drawRoundRect(new RectF(3 + x * 10, 3 + y * 10, 11 + x * 10, 11 + y * 10), 2.5f, 2.5f, fill);
                break;
            case CLOSE:
                line.setStrokeWidth(2.6f);
                c.drawLine(6, 6, 18, 18, line);
                c.drawLine(18, 6, 6, 18, line);
                break;
            case PLAY:
                p.moveTo(7, 4); p.lineTo(20, 12); p.lineTo(7, 20); p.close();
                c.drawPath(p, fill);
                break;
            case STOP:
                c.drawRoundRect(new RectF(5, 5, 19, 19), 3, 3, fill);
                break;
            case CHECK:
                line.setStrokeWidth(2.8f);
                p.moveTo(5, 12.5f); p.lineTo(10, 17); p.lineTo(19, 7);
                c.drawPath(p, line);
                break;
            case DOTS:
                for (int i = 0; i < 3; i++) c.drawCircle(6 + i * 6, 12, 1.8f, fill);
                break;
            case BACK:
                line.setStrokeWidth(2.6f);
                p.moveTo(15, 5); p.lineTo(8, 12); p.lineTo(15, 19);
                c.drawPath(p, line);
                break;
            case UP:
                line.setStrokeWidth(2.6f);
                p.moveTo(5, 15); p.lineTo(12, 8); p.lineTo(19, 15);
                c.drawPath(p, line);
                break;
            case SHARE:
                c.drawRoundRect(new RectF(5, 9, 19, 21), 2.5f, 2.5f, line);
                c.drawLine(12, 3, 12, 14, line);
                p.moveTo(8, 7); p.lineTo(12, 3); p.lineTo(16, 7);
                c.drawPath(p, line);
                break;
            case COPY:
                c.drawRoundRect(new RectF(8, 8, 20, 20), 2.5f, 2.5f, line);
                c.drawRoundRect(new RectF(4, 4, 16, 16), 2.5f, 2.5f, line);
                break;
            case SEARCH:
                line.setStrokeWidth(2.6f);
                c.drawCircle(10, 10, 6, line);
                c.drawLine(14.5f, 14.5f, 20, 20, line);
                break;
            case DOC:
                c.drawRoundRect(new RectF(5, 3, 19, 21), 2.5f, 2.5f, line);
                c.drawLine(8.5f, 9, 15.5f, 9, line);
                c.drawLine(8.5f, 13, 15.5f, 13, line);
                c.drawLine(8.5f, 17, 13, 17, line);
                break;
            case SMILE:
                c.drawCircle(12, 12, 9.5f, line);
                c.drawCircle(9, 10, 1.3f, fill);
                c.drawCircle(15, 10, 1.3f, fill);
                c.drawArc(new RectF(8, 10, 16, 17), 20, 140, false, line);
                break;
            case GEAR:
                c.drawCircle(12, 12, 3.2f, line);
                for (int i = 0; i < 8; i++) {
                    double a = i * Math.PI / 4;
                    c.drawLine((float) (12 + Math.cos(a) * 6.5), (float) (12 + Math.sin(a) * 6.5),
                        (float) (12 + Math.cos(a) * 9.5), (float) (12 + Math.sin(a) * 9.5), line);
                }
                c.drawCircle(12, 12, 6.5f, line);
                break;
            case PLUS:
                line.setStrokeWidth(3f);
                c.drawLine(12, 6, 12, 18, line);
                c.drawLine(6, 12, 18, 12, line);
                break;
            case MINUS:
                line.setStrokeWidth(3f);
                c.drawLine(6, 12, 18, 12, line);
                break;
        }
        c.restore();
    }

    private static void star(Canvas c, Paint paint, float cx, float cy, float r) {
        Path p = new Path();
        p.moveTo(cx, cy - r);
        p.quadTo(cx, cy, cx + r, cy);
        p.quadTo(cx, cy, cx, cy + r);
        p.quadTo(cx, cy, cx - r, cy);
        p.quadTo(cx, cy, cx, cy - r);
        p.close();
        c.drawPath(p, paint);
    }

    /** Ein runder, dezenter Knopf mit Symbol (wie die Knöpfe oben rechts auf dem iPhone). */
    static final class Button extends View {
        Kind kind;
        int color = 0x59FFFFFF;
        int circle = 0x0FFFFFFF;
        float iconSize = 15;
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

        Button(Context context, Kind kind) {
            super(context);
            this.kind = kind;
            setClickable(true);
            setFocusable(true);
        }

        void set(Kind kind, int color, int circle) {
            this.kind = kind;
            this.color = color;
            this.circle = circle;
            invalidate();
        }

        @Override protected void onDraw(Canvas c) {
            float d = getResources().getDisplayMetrics().density;
            float cx = getWidth() / 2f, cy = getHeight() / 2f;
            paint.setColor(circle);
            c.drawCircle(cx, cy, 17 * d, paint);
            Icons.draw(c, kind, cx, cy, iconSize * d, color);
        }
    }

    private Icons() {}
}
