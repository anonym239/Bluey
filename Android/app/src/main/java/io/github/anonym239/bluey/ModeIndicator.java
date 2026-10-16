package io.github.anonym239.bluey;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.os.Build;
import android.view.RoundedCorner;
import android.view.View;
import android.view.WindowInsets;

/**
 * Zeigt, in welchem Modus er ist: ein Rahmen, der die runden Bildschirmecken umarmt (blau, während er
 * zuhört), plus ein kleines Etikett in der Ecke. Im Folgemodus nur ein kleines Augen-Symbol.
 */
final class ModeIndicator extends View {
    private LiveVoice.State state = LiveVoice.State.ASLEEP;
    private final Paint border = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private float cornerRadius = -1;
    /** Optionaler Zusatz im Etikett, z. B. „ohne PC“. */
    String suffix;

    private static final int BLUE = 0xFF4F8BFF;

    ModeIndicator(Context context) {
        super(context);
        border.setStyle(Paint.Style.STROKE);
        text.setColor(Color.WHITE);
        setClickable(false);
        setFocusable(false);
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    }

    void setState(LiveVoice.State state) {
        this.state = state;
        invalidate();
    }

    private static final class Look {
        final int color; final String label; final Icons.Kind icon; final float border; final double pulse;
        Look(int color, String label, Icons.Kind icon, float border, double pulse) {
            this.color = color; this.label = label; this.icon = icon; this.border = border; this.pulse = pulse;
        }
    }

    private Look look() {
        switch (state) {
            case WAKING: return new Look(0xFFFFD66B, "Wacht auf", Icons.Kind.SUN, 6, 1.6);
            case LISTENING: return null;  // ruhig zuhören: nichts anzeigen
            case ASKING: return new Look(BLUE, "Ganz Ohr", Icons.Kind.MIC, 16, 1.2);
            case THINKING: return new Look(0xFFC79BFF, "Denkt nach", Icons.Kind.SPARKLES, 8, 1.1);
            case SPEAKING: return new Look(0xFFFF9AD0, "Antwortet", Icons.Kind.BUBBLE, 8, 0);
            default: return null;  // schläft / Folgemodus: nichts anzeigen
        }
    }

    private float screenCornerRadius() {
        if (cornerRadius >= 0) return cornerRadius;
        float d = getResources().getDisplayMetrics().density;
        cornerRadius = 40 * d;
        if (Build.VERSION.SDK_INT >= 31) {
            WindowInsets insets = getRootWindowInsets();
            if (insets != null) {
                RoundedCorner corner = insets.getRoundedCorner(RoundedCorner.POSITION_TOP_LEFT);
                if (corner != null && corner.getRadius() > 0) cornerRadius = corner.getRadius();
                else cornerRadius = 12 * d;
            }
        }
        return cornerRadius;
    }

    @Override protected void onDraw(Canvas c) {
        float d = getResources().getDisplayMetrics().density;
        Look look = look();
        if (look == null) return;
        double t = FaceView.now();
        double wave = look.pulse > 0 ? .5 + .5 * Math.sin(t * look.pulse * 2 * Math.PI) : 1;
        float width = look.border * d * .5f;
        if (look.border > 0) {
            border.setColor(look.color);
            border.setAlpha((int) (255 * (look.pulse > 0 ? .65 + .35 * wave : 1)));
            border.setStrokeWidth(width);
            float r = screenCornerRadius();
            c.drawRoundRect(new RectF(width / 2, width / 2, getWidth() - width / 2, getHeight() - width / 2),
                Math.max(0, r - width / 2), Math.max(0, r - width / 2), border);
        }
        // Etikett oben links.
        float top = 14 * d + width, left = 24 * d + width;
        float h = 34 * d;
        if (look.label == null) {
            fill.setColor(0x0FFFFFFF);
            c.drawCircle(left + h / 2, top + h / 2, h / 2, fill);
            Icons.draw(c, look.icon, left + h / 2, top + h / 2, 15 * d, Palette.alpha(look.color, .7));
        } else {
            String label = suffix == null ? look.label : look.label + " · " + suffix;
            text.setTypeface(Fonts.display);
            text.setTextSize(15 * d);
            float textW = text.measureText(label);
            float w = 14 * d + 15 * d + 7 * d + textW + 14 * d;
            fill.setColor(look.color);
            c.drawRoundRect(new RectF(left, top, left + w, top + h), h / 2, h / 2, fill);
            Icons.draw(c, look.icon, left + 14 * d + 7.5f * d, top + h / 2, 15 * d, Color.WHITE);
            Paint.FontMetrics m = text.getFontMetrics();
            c.drawText(label, left + 14 * d + 15 * d + 7 * d, top + h / 2 - (m.ascent + m.descent) / 2, text);
        }
        if (look.pulse > 0) postInvalidateOnAnimation();
    }
}
