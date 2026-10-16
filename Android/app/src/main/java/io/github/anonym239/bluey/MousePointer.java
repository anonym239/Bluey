package io.github.anonym239.bluey;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import org.json.JSONObject;

/**
 * Die PC-Maus auf dem Handy: Schiebt man die Maus am PC unten hinaus, kommt sie hier als kleiner Beeren-Zeiger an.
 * Klicks werden zu echten Berührungen (Tippen, Doppeltippen, Halten zum Fragen), damit alles wie mit dem Finger geht.
 */
final class MousePointer extends View {
    interface Listener { void moved(float x, float y, boolean visible); }

    private final ViewGroup root;
    private final Listener listener;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint rim = new Paint(Paint.ANTI_ALIAS_FLAG);
    private boolean visible, down;
    private float x, y;
    private long downTime;
    private double pressedAt;

    MousePointer(Context context, ViewGroup root, Listener listener) {
        super(context);
        this.root = root;
        this.listener = listener;
        rim.setStyle(Paint.Style.STROKE);
        rim.setColor(Color.WHITE);
        setClickable(false);
        setFocusable(false);
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    }

    /** Ein Zeiger-Paket vom PC: {x, y (0…1), state: enter|move|down|up|leave}. */
    void handle(JSONObject event) {
        if (event == null || getWidth() == 0) return;
        String state = event.optString("state", "move");
        x = (float) Math.max(0, Math.min(1, event.optDouble("x", .5))) * getWidth();
        y = (float) Math.max(0, Math.min(1, event.optDouble("y", .5))) * getHeight();
        switch (state) {
            case "leave":
                if (down) touch(MotionEvent.ACTION_CANCEL);
                down = false;
                visible = false;
                break;
            case "down":
                visible = true;
                if (!down) {
                    down = true;
                    downTime = SystemClock.uptimeMillis();
                    pressedAt = FaceView.now();
                    touch(MotionEvent.ACTION_DOWN);
                }
                break;
            case "up":
                visible = true;
                if (down) {
                    down = false;
                    touch(MotionEvent.ACTION_UP);
                }
                break;
            default:
                visible = true;
                if (down) touch(MotionEvent.ACTION_MOVE);
                break;
        }
        listener.moved(x, y, visible);
        invalidate();
    }

    boolean isVisible() { return visible; }

    /** Gibt eine echte Berührung an die Oberfläche weiter, als wäre es ein Finger. */
    private void touch(int action) {
        MotionEvent event = MotionEvent.obtain(downTime, SystemClock.uptimeMillis(), action, x, y, 0);
        event.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);
        root.dispatchTouchEvent(event);
        event.recycle();
    }

    @Override protected void onDraw(Canvas c) {
        if (!visible) return;
        float d = getResources().getDisplayMetrics().density;
        float s = 34 * d;
        double press = down ? Math.min(1, (FaceView.now() - pressedAt) / .08) : 0;
        float squish = (float) (1 - .12 * press);
        c.save();
        c.translate(x, y);
        c.scale(squish, squish);
        // Ein Tropfen mit Spitze oben links, wie der große Cursor am PC.
        Path path = new Path();
        float r = 3 * d, big = s / 2;
        path.moveTo(r, 0);
        path.lineTo(s - big, 0);
        path.arcTo(new RectF(0, 0, s, s), -90, 90);
        path.arcTo(new RectF(0, 0, s, s), 0, 90);
        path.arcTo(new RectF(0, 0, s, s), 90, 90);
        path.lineTo(0, r);
        path.quadTo(0, 0, r, 0);
        path.close();
        paint.setShadowLayer(8 * d, 0, 2 * d, Palette.alpha(Palette.BERRY4, .6));
        paint.setShader(new LinearGradient(.25f * s, .07f * s, .75f * s, .93f * s, Palette.GRADIENT, Palette.STOPS, Shader.TileMode.CLAMP));
        c.drawPath(path, paint);
        paint.clearShadowLayer();
        paint.setShader(null);
        rim.setStrokeWidth(2.5f * d);
        c.drawPath(path, rim);
        // Zwei kleine Augen.
        for (int i = 0; i < 2; i++) {
            float ex = (12 + i * 9) * d, ey = 16 * d;
            paint.setColor(Color.WHITE);
            c.drawCircle(ex, ey, 3.6f * d, paint);
            paint.setColor(Palette.INK);
            c.drawCircle(ex - .8f * d, ey - .8f * d, 1.8f * d, paint);
        }
        c.restore();
        if (down) postInvalidateOnAnimation();
    }
}
