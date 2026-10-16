package io.github.anonym239.bluey;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;
import android.os.Handler;
import android.os.Looper;
import android.text.Layout;
import android.text.StaticLayout;
import android.text.TextPaint;
import android.view.View;

/**
 * Seine Sprechblase auf dem Handy, wenn kein PC sie zeigt (Modus ohne PC oder für Hinweise):
 * eine weiße Wolke mit Blaubeer-Rand und einem Schwänzchen nach unten zu ihm.
 */
final class CaptionBubble extends View {
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final TextPaint text = new TextPaint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint border = new Paint(Paint.ANTI_ALIAS_FLAG);
    private String caption;
    private double born;
    private final Runnable clear = () -> show(null, false);

    CaptionBubble(Context context) {
        super(context);
        text.setColor(Palette.INK);
        border.setStyle(Paint.Style.STROKE);
        border.setColor(Palette.BERRY2);
        border.setStrokeJoin(Paint.Join.ROUND);
        setClickable(false);
        setFocusable(false);
    }

    /** Zeigt Text (null versteckt). Ist er fertig, bleibt er lange genug zum Lesen stehen. */
    void show(String value, boolean finished) {
        ui.removeCallbacks(clear);
        if (value == null || value.trim().isEmpty()) {
            caption = null;
        } else {
            if (caption == null) born = FaceView.now();
            caption = value.trim();
            setContentDescription(caption);
            if (finished) {
                int words = caption.split("\\s+").length;
                long readMs = (long) ((Math.min(Math.max(2.8, 1.2 + words * .32), 12) + 3) * 1000);
                ui.postDelayed(clear, readMs);
            }
        }
        invalidate();
    }

    @Override protected void onDraw(Canvas c) {
        if (caption == null) return;
        float d = getResources().getDisplayMetrics().density;
        int length = caption.length();
        float size = (length <= 50 ? 21 : length <= 110 ? 19 : 17) * d;
        text.setTypeface(Fonts.display);
        text.setTextSize(size);
        int maxWidth = (int) Math.min(getWidth() * .62f, Math.max(240 * d, Math.sqrt(length) * 50 * d));
        StaticLayout layout = StaticLayout.Builder.obtain(caption, 0, caption.length(), text, maxWidth)
            .setAlignment(Layout.Alignment.ALIGN_CENTER).setLineSpacing(1.5f * d, 1f).setMaxLines(8)
            .setEllipsize(android.text.TextUtils.TruncateAt.END).build();
        float textW = 0;
        for (int i = 0; i < layout.getLineCount(); i++) textW = Math.max(textW, layout.getLineWidth(i));
        float padX = 24 * d, padY = 15 * d, tail = 18 * d;
        float w = Math.max(textW + padX * 2, 70 * d), h = layout.getHeight() + padY * 2;
        float bob = (float) Math.sin((FaceView.now() - born) * 2.2) * 2 * d;
        float x = (getWidth() - w) / 2, y = 64 * d + bob;
        RectF box = new RectF(x, y, x + w, y + h);
        float r = Math.min(24 * d, h / 2);
        Path path = new Path();
        path.addRoundRect(box, r, r, Path.Direction.CW);
        Path tailPath = new Path();
        float cx = box.centerX();
        tailPath.moveTo(cx - 13 * d, box.bottom - 1);
        tailPath.quadTo(cx - 2 * d, box.bottom + tail * .5f, cx + 6 * d, box.bottom + tail);
        tailPath.quadTo(cx + 4 * d, box.bottom + tail * .4f, cx + 13 * d, box.bottom - 1);
        tailPath.close();
        path.op(tailPath, Path.Op.UNION);
        fill.setShader(new LinearGradient(0, box.top, 0, box.bottom + tail, Color.WHITE, Palette.CARD, Shader.TileMode.CLAMP));
        c.drawPath(path, fill);
        border.setStrokeWidth(2.5f * d);
        c.drawPath(path, border);
        c.save();
        c.translate(box.left + (w - maxWidth) / 2, box.top + padY);
        layout.draw(c);
        c.restore();
        postInvalidateOnAnimation();
    }
}
