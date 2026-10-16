package io.github.anonym239.bluey;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Kleine Bausteine für die Oberfläche (alles in Code, ohne AndroidX). */
final class Ui {
    static int dp(Context c, float value) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, c.getResources().getDisplayMetrics()));
    }

    static TextView text(Context c, String value, Typeface face, float size, int color) {
        TextView t = new TextView(c);
        t.setText(value);
        t.setTypeface(face);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
        t.setTextColor(color);
        t.setIncludeFontPadding(true);
        return t;
    }

    /** Kleines Etikett in Großbuchstaben (wie die Mono-Labels im Original). */
    static TextView label(Context c, String value) {
        TextView t = text(c, value.toUpperCase(java.util.Locale.GERMANY), Fonts.mono, 11, Palette.INK_SOFT);
        t.setLetterSpacing(.04f);
        return t;
    }

    static GradientDrawable round(int color, float radiusDp, Context c) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(dp(c, radiusDp));
        return d;
    }

    static GradientDrawable berry(float radiusDp, Context c) {
        GradientDrawable d = new GradientDrawable(GradientDrawable.Orientation.TL_BR, Palette.GRADIENT);
        d.setCornerRadius(dp(c, radiusDp));
        return d;
    }

    /** Ein großer Knopf mit Symbol und Text. */
    static LinearLayout button(Context c, Icons.Kind icon, String title, Typeface face, float size, android.graphics.drawable.Drawable background) {
        LinearLayout row = new LinearLayout(c);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER);
        row.setMinimumHeight(dp(c, 46));
        row.setPadding(dp(c, 14), dp(c, 6), dp(c, 14), dp(c, 6));
        row.setBackground(background);
        row.setClickable(true);
        row.setFocusable(true);
        if (icon != null) {
            IconView v = new IconView(c, icon, Color.WHITE, 18);
            row.addView(v, new LinearLayout.LayoutParams(dp(c, 22), dp(c, 22)));
            View gap = new View(c);
            row.addView(gap, new LinearLayout.LayoutParams(dp(c, 9), 1));
        }
        TextView t = text(c, title, face, size, Color.WHITE);
        t.setSingleLine(true);
        t.setEllipsize(TextUtils.TruncateAt.END);
        row.addView(t);
        return row;
    }

    /** Nur ein Symbol. */
    static final class IconView extends View {
        Icons.Kind kind;
        int color;
        final float size;

        IconView(Context c, Icons.Kind kind, int color, float sizeDp) {
            super(c);
            this.kind = kind;
            this.color = color;
            this.size = sizeDp;
        }

        void set(Icons.Kind kind, int color) {
            this.kind = kind;
            this.color = color;
            invalidate();
        }

        @Override protected void onDraw(Canvas canvas) {
            Icons.draw(canvas, kind, getWidth() / 2f, getHeight() / 2f, dp(getContext(), size), color);
        }
    }

    /** Ein winziger Bluey: der Blob mit zwei Kulleraugen. */
    static final class MiniBluey extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        MiniBluey(Context c) { super(c); }

        @Override protected void onDraw(Canvas canvas) {
            float w = getWidth(), h = getHeight();
            RectF r = new RectF(0, 0, w, h);
            paint.setShader(BlobShape.fill(r));
            canvas.drawPath(BlobShape.path(r), paint);
            paint.setShader(null);
            float eye = w * .13f;
            for (int i = 0; i < 2; i++) {
                float cx = w / 2 + (i == 0 ? -1 : 1) * (eye + w * .05f), cy = h / 2 - w * .04f;
                paint.setColor(Color.WHITE);
                canvas.drawCircle(cx, cy, eye, paint);
                paint.setColor(Palette.INK);
                canvas.drawCircle(cx + w * .02f, cy + w * .03f, w * .06f, paint);
            }
        }
    }

    /** Ein Ladekreis in Blaubeerfarbe. */
    static final class Spinner extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        Spinner(Context c) {
            super(c);
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeCap(Paint.Cap.ROUND);
            paint.setColor(Palette.BERRY1);
        }

        @Override protected void onDraw(Canvas canvas) {
            float s = Math.min(getWidth(), getHeight());
            paint.setStrokeWidth(s * .12f);
            float inset = s * .12f;
            float angle = (float) ((FaceView.now() * 360) % 360);
            canvas.drawArc(new RectF(inset, inset, s - inset, s - inset), angle, 270, false, paint);
            postInvalidateOnAnimation();
        }
    }

    /** Die schlafende Blaubeere für den Verbindungsbildschirm. */
    static final class SleepyBlob extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        SleepyBlob(Context c) { super(c); }

        @Override protected void onDraw(Canvas canvas) {
            float w = getWidth(), h = getHeight();
            double t = FaceView.now();
            float bodyW = w * .78f, bodyH = h * .88f;
            float scale = (float) (1 + .02 * Math.sin(t * 1.1));
            canvas.save();
            canvas.scale(scale, scale, bodyW / 2, h);
            RectF r = new RectF(0, h - bodyH, bodyW, h);
            Path blob = BlobShape.path(r);
            paint.setShader(BlobShape.fill(r));
            paint.setAlpha(230);
            canvas.drawPath(blob, paint);
            paint.setShader(new android.graphics.RadialGradient(r.left + r.width() * .3f, r.top + r.height() * .22f, bodyW * .4f,
                new int[]{Color.argb(128, 255, 255, 255), Color.argb(0, 255, 255, 255)}, null, android.graphics.Shader.TileMode.CLAMP));
            canvas.drawPath(blob, paint);
            paint.setShader(null);
            paint.setAlpha(255);
            paint.setColor(Palette.INK);
            float cy = r.centerY() - bodyH * .1f;
            float cap = bodyW * .21f, thick = bodyW * .035f;
            for (int i = 0; i < 2; i++) {
                float cx = r.centerX() + (i == 0 ? -1 : 1) * (cap / 2 + bodyW * .06f);
                canvas.drawRoundRect(new RectF(cx - cap / 2, cy - thick / 2, cx + cap / 2, cy + thick / 2), thick, thick, paint);
            }
            paint.setColor(Palette.NOSE);
            canvas.drawOval(new RectF(r.centerX() - bodyW * .04f + 4, cy + bodyH * .2f, r.centerX() + bodyW * .04f + 4, cy + bodyH * .26f), paint);
            canvas.restore();
            paint.setTypeface(Fonts.display);
            paint.setColor(Palette.BERRY3);
            paint.setTextSize(h * .14f);
            canvas.drawText("z", bodyW * .92f, (float) (h * .18f - 4 * Math.sin(t * 1.5)), paint);
            paint.setColor(Palette.BERRY4);
            paint.setTextSize(h * .1f);
            canvas.drawText("z", bodyW * 1.02f, (float) (h * .05f + 10 - 4 * Math.sin(t * 1.5 + 1)), paint);
            postInvalidateOnAnimation();
        }
    }

    private Ui() {}
}
