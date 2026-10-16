package io.github.anonym239.bluey;

import android.graphics.LinearGradient;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;

/** Der Blob-Umriss: CSS `border-radius: 52% 48% 46% 54% / 58% 56% 44% 42%`, plus Krönchen. */
final class BlobShape {
    private static final float K = 0.5523f;  // kubische Näherung einer Viertelellipse

    static Path path(RectF r) {
        float w = r.width(), h = r.height();
        float tlw = .52f * w, tlh = .58f * h;
        float trw = .48f * w, trh = .56f * h;
        float brw = .46f * w, brh = .44f * h;
        float blw = .54f * w, blh = .42f * h;
        Path p = new Path();
        p.moveTo(r.left + tlw, r.top);
        p.lineTo(r.right - trw, r.top);
        p.cubicTo(r.right - trw * (1 - K), r.top, r.right, r.top + trh * (1 - K), r.right, r.top + trh);
        p.lineTo(r.right, r.bottom - brh);
        p.cubicTo(r.right, r.bottom - brh * (1 - K), r.right - brw * (1 - K), r.bottom, r.right - brw, r.bottom);
        p.lineTo(r.left + blw, r.bottom);
        p.cubicTo(r.left + blw * (1 - K), r.bottom, r.left, r.bottom - blh * (1 - K), r.left, r.bottom - blh);
        p.lineTo(r.left, r.top + tlh);
        p.cubicTo(r.left, r.top + tlh * (1 - K), r.left + tlw * (1 - K), r.top, r.left + tlw, r.top);
        p.close();
        return p;
    }

    /** Der Blaubeer-Verlauf im 150°-Winkel wie im Design. */
    static Shader fill(RectF r) {
        return new LinearGradient(r.left + .25f * r.width(), r.top + .067f * r.height(),
            r.left + .75f * r.width(), r.top + .933f * r.height(), Palette.GRADIENT, Palette.STOPS, Shader.TileMode.CLAMP);
    }

    /** Das kleine Blaubeer-Krönchen (SVG-Pfad aus dem Design, 60×40-Box). */
    static Path crown(RectF r) {
        float[][] pts = {{30, 4}, {36, 16}, {52, 12}, {40, 24}, {46, 36}, {30, 28}, {14, 36}, {20, 24}, {8, 12}, {24, 16}};
        Path p = new Path();
        for (int i = 0; i < pts.length; i++) {
            float x = r.left + pts[i][0] / 60f * r.width(), y = r.top + pts[i][1] / 40f * r.height();
            if (i == 0) p.moveTo(x, y); else p.lineTo(x, y);
        }
        p.close();
        return p;
    }

    private BlobShape() {}
}
